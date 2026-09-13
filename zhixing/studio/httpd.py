"""Bounded local HTTP API for ZhiXing Studio authoring services."""

from __future__ import annotations

import json
import logging
import re
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, BinaryIO, Mapping, cast
from urllib.parse import parse_qs, unquote, urlparse

from zhixing.studio.agent_registry import build_agent_registry_payload
from zhixing.studio.benchmark_composition import (
    StudioBenchmarkComposition,
    build_default_studio_benchmark_composition,
)
from zhixing.studio.benchmark_authoring_errors import (
    StudioBenchmarkAuthoringCapacityError,
    StudioBenchmarkAuthoringFreezeEligibilityError,
    StudioBenchmarkAuthoringRevisionConflictError,
    StudioBenchmarkAuthoringStorageError,
)
from zhixing.studio.benchmark_authoring_content import (
    StudioBenchmarkAuthoringContentApplicationService,
    parse_authoring_content_remove_query,
    parse_authoring_content_replace_query,
    parse_authoring_content_upload_query,
)
from zhixing.studio.benchmark_authoring_analysis import (
    StudioBenchmarkAuthoringAnalysisService,
)
from zhixing.studio.benchmark_authoring_contracts import (
    StudioBenchmarkContractTestApplicationService,
)
from zhixing.studio.benchmark_authoring_freeze_service import (
    StudioBenchmarkValidatedFreezeApplicationService,
)
from zhixing.studio.benchmark_authoring_release_service import (
    StudioBenchmarkPackageReleaseApplicationService,
)
from zhixing.studio.benchmark_authoring_migration import (
    StudioBenchmarkLegacyMigrationApplicationService,
)
from zhixing.studio.benchmark_authoring_models import (
    STUDIO_BENCHMARK_AUTHORING_MAX_RESOURCE_BYTES,
)
from zhixing.studio.benchmark_authoring_service import (
    StudioBenchmarkAuthoringApplicationService,
)
from zhixing.studio.benchmark_errors import (
    StudioBenchmarkCapacityError,
    StudioBenchmarkConflictError,
    StudioBenchmarkError,
    StudioBenchmarkNotFoundError,
    StudioBenchmarkSnapshotTooLargeError,
    StudioBenchmarkValidationError,
)
from zhixing.studio.benchmark_events import DurableBenchmarkEventService
from zhixing.studio.benchmark_artifacts import (
    LocalStudioBenchmarkManagedArtifactStore,
)
from zhixing.studio.benchmark_experiment_service import (
    StudioBenchmarkExperimentApplicationService,
)
from zhixing.studio.benchmark_experiment_models import (
    StudioBenchmarkExperimentHistoryFilterV1,
)
from zhixing.studio.benchmark_publication_models import (
    StudioBenchmarkArtifactDescriptorV1,
)
from zhixing.studio.benchmark_service import StudioBenchmarkApplicationService
from zhixing.studio.catalog import build_studio_component_catalog
from zhixing.studio.flow_template_loader import (
    get_flow_template_document,
    list_flow_templates,
)
from zhixing.studio.event_waiters import BoundedConnectionLimiter
from zhixing.studio.repository import (
    AgentNotFoundError,
    AgentRevisionConflictError,
    AgentRevisionNotFoundError,
    SQLiteAgentDocumentRepository,
    default_studio_database_path,
)
from zhixing.studio.replay_contracts import (
    ReplayArtifactNotFoundError,
    ReplayConflictError,
    ReplayImportError,
    ReplayNotFoundError,
)
from zhixing.studio.replay_service import build_default_replay_service
from zhixing.studio.run_artifacts import LocalStudioRunArtifactStore
from zhixing.studio.run_composition import (
    StudioRunComposition,
    build_default_studio_run_composition,
)
from zhixing.studio.run_execution import (
    AndroidDeviceProfileResolver,
    DeviceLeaseRegistry,
    ProductionComponentResolverFactory,
)
from zhixing.studio.run_errors import (
    StudioRunArtifactNotFoundError,
    StudioRunConflictError,
    StudioRunError,
    StudioRunNotFoundError,
    StudioRunValidationError,
)
from zhixing.studio.run_service import StudioRunApplicationService
from zhixing.studio.service import (
    StudioApplicationError,
    StudioApplicationService,
    agent_record_payload,
    revision_record_payload,
)


logger = logging.getLogger(__name__)

_MAX_REQUEST_BYTES = 2 * 1024 * 1024
_DEFAULT_ALLOWED_ORIGINS = frozenset(
    {
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:4173",
        "http://localhost:4173",
    }
)


class _ExactContentLengthStream:
    """Expose exactly one declared request body as a bounded binary stream."""

    def __init__(self, source: BinaryIO, length: int) -> None:
        """Bind one HTTP input stream and its already validated length.

        Args:
            source: Handler-owned binary request stream.
            length: Exact non-negative declared body length.

        Raises:
            ValueError: Length is negative.

        Returns:
            None.
        """
        if length < 0:
            raise ValueError("content length cannot be negative")
        self._source = source
        self._remaining = length

    def read(self, size: int = -1) -> bytes:
        """Read without crossing the declared request body boundary.

        Args:
            size: Maximum requested byte count, or a negative value for all.

        Raises:
            StudioBenchmarkAuthoringValidationError: The connection ends before
                the declared body has been received.

        Returns:
            Next bytes, or an empty value only at the exact declared boundary.
        """
        if self._remaining == 0:
            return b""
        requested = (
            self._remaining
            if size is None or size < 0
            else min(size, self._remaining)
        )
        block = self._source.read(requested)
        if not block:
            raise StudioBenchmarkValidationError(
                "benchmark.authoring.content_length_mismatch",
                "Benchmark authoring content ended before Content-Length",
            )
        if not isinstance(block, bytes) or len(block) > requested:
            raise StudioBenchmarkValidationError(
                "benchmark.authoring.content_length_mismatch",
                "Benchmark authoring content does not match Content-Length",
            )
        self._remaining -= len(block)
        return block


def _json_bytes(
    obj: object,
    status: int = 200,
    *,
    origin: str | None = None,
    private: bool = False,
) -> tuple[int, bytes, list[tuple[str, str]]]:
    """Encode one finite JSON response and explicit safe headers.

    Args:
        obj (object): JSON-compatible response.
        status (int): HTTP status code.
        origin (str | None): Validated request Origin to echo.
        private (bool): Whether response facts are user-private and non-cacheable.

    Raises:
        TypeError: Response is not JSON serializable.
        ValueError: Response contains a non-finite float.

    Returns:
        tuple[int, bytes, list[tuple[str, str]]]: Status, body, and headers.
    """
    body = json.dumps(
        obj,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")
    headers = [
        ("Content-Type", "application/json; charset=utf-8"),
        ("Content-Length", str(len(body))),
        ("Cache-Control", "private, no-store" if private else "no-store"),
        ("X-Content-Type-Options", "nosniff"),
    ]
    if origin is not None:
        headers.extend(
            [
                ("Access-Control-Allow-Origin", origin),
                ("Vary", "Origin"),
            ]
        )
    return status, body, headers


def _error_payload(code: str, message: str) -> dict[str, Any]:
    """Build the stable versioned HTTP error envelope.

    Args:
        code (str): Stable machine-readable error code.
        message (str): Safe bounded explanation.

    Raises:
        None.

    Returns:
        dict[str, Any]: Error envelope.
    """
    return {
        "schemaVersion": 1,
        "error": {
            "code": code,
            "message": str(message).replace("\n", " ")[:500],
        },
    }


class StudioHTTPServer(ThreadingHTTPServer):
    """Threaded HTTP server carrying explicit Studio application boundaries."""

    daemon_threads = True

    def __init__(
        self,
        server_address: tuple[str, int],
        handler_class: type[BaseHTTPRequestHandler],
        *,
        application_service: StudioApplicationService,
        allowed_origins: frozenset[str],
        allowed_hosts: frozenset[str],
        run_composition: StudioRunComposition | None = None,
        benchmark_composition: StudioBenchmarkComposition | None = None,
        sse_heartbeat_seconds: float = 15.0,
        sse_write_timeout_seconds: float = 20.0,
        benchmark_sse_max_connections: int = 32,
    ) -> None:
        """Create one local Studio HTTP server.

        Args:
            server_address (tuple[str, int]): Bind host and port.
            handler_class (type[BaseHTTPRequestHandler]): Request handler.
            application_service (StudioApplicationService): Explicit
                application boundary.
            allowed_origins (frozenset[str]): Browser origins allowed for CORS.
            allowed_hosts (frozenset[str]): HTTP Host names accepted.
            run_composition (StudioRunComposition | None): Optional shared live
                Run dependencies.
            benchmark_composition (StudioBenchmarkComposition | None):
                Optional shared Benchmark definition and worker dependencies.
            sse_heartbeat_seconds (float): Empty-stream heartbeat interval.
            sse_write_timeout_seconds (float): Per-connection socket timeout.
            benchmark_sse_max_connections (int): Maximum concurrent Benchmark
                Experiment SSE connections.

        Raises:
            ValueError: An SSE timeout is outside its bounded range.
            OSError: Socket binding fails.

        Returns:
            None.
        """
        if not 0 < sse_heartbeat_seconds <= 60:
            raise ValueError("SSE heartbeat must be within 60 seconds")
        if not 0 < sse_write_timeout_seconds <= 120:
            raise ValueError("SSE write timeout must be within 120 seconds")
        self.application_service = application_service
        self.run_composition = run_composition
        self.benchmark_composition = benchmark_composition
        self.allowed_origins = allowed_origins
        self.allowed_hosts = allowed_hosts
        self.sse_heartbeat_seconds = float(sse_heartbeat_seconds)
        self.sse_write_timeout_seconds = float(sse_write_timeout_seconds)
        self.benchmark_sse_connections = BoundedConnectionLimiter(
            max_connections=benchmark_sse_max_connections
        )
        self._run_composition_closed = False
        self._benchmark_composition_closed = False
        super().__init__(server_address, handler_class)

    def server_close(self) -> None:
        """Close the listener and release both bounded execution schedulers.

        Args:
            None.

        Raises:
            OSError: Listener shutdown fails.

        Returns:
            None.
        """
        if self.run_composition is not None and not self._run_composition_closed:
            self._run_composition_closed = True
            self.run_composition.shutdown(wait=False)
        if (
            self.benchmark_composition is not None
            and not self._benchmark_composition_closed
        ):
            self._benchmark_composition_closed = True
            self.benchmark_composition.shutdown(wait=False)
        super().server_close()


class StudioHTTPRequestHandler(BaseHTTPRequestHandler):
    """Map versioned JSON HTTP contracts to Studio application services."""

    server_version = "ZhiXingStudio/1.0"
    protocol_version = "HTTP/1.1"

    @property
    def studio_server(self) -> StudioHTTPServer:
        """Return the concrete server carrying Studio dependencies.

        Args:
            None.

        Raises:
            None.

        Returns:
            StudioHTTPServer: Typed server.
        """
        return cast(StudioHTTPServer, self.server)

    def log_message(self, fmt: str, *args: object) -> None:
        """Write request logs through project logging.

        Args:
            fmt (str): Base handler format string.
            *args (object): Format values.

        Raises:
            None.

        Returns:
            None.
        """
        logger.info("%s - %s", self.address_string(), fmt % args)

    def _request_origin(self) -> str | None:
        """Return a validated request Origin.

        Args:
            None.

        Raises:
            PermissionError: Origin is not allowed.

        Returns:
            str | None: Allowed Origin, if supplied.
        """
        origin = self.headers.get("Origin")
        if origin is None:
            return None
        if origin not in self.studio_server.allowed_origins:
            raise PermissionError("Browser origin is not allowed")
        return origin

    def _require_host(self) -> None:
        """Reject DNS-rebinding Host values outside the local allowlist.

        Args:
            None.

        Raises:
            PermissionError: HTTP Host is absent or untrusted.

        Returns:
            None.
        """
        raw = self.headers.get("Host", "")
        host = raw.rsplit(":", 1)[0].strip("[]").lower()
        if host not in self.studio_server.allowed_hosts:
            raise PermissionError("HTTP Host is not allowed")

    def _send_json(
        self,
        payload: object,
        status: int = 200,
        *,
        private: bool = False,
    ) -> None:
        """Send one finite JSON response.

        Args:
            payload (object): JSON-compatible response.
            status (int): HTTP status.
            private (bool): Whether to emit a private non-cacheable response.

        Raises:
            None: Encoding errors are converted by the dispatch boundary.

        Returns:
            None.
        """
        origin = self._request_origin()
        response_status, body, headers = _json_bytes(
            payload,
            status,
            origin=origin,
            private=private,
        )
        self.send_response(response_status)
        for key, value in headers:
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _send_binary(
        self,
        stream: BinaryIO,
        *,
        content_type: str,
        content_length: int,
        disposition: str,
        head_only: bool = False,
        digest: str | None = None,
    ) -> None:
        """Send one verified artifact or bundle with safe download headers.

        Args:
            stream (BinaryIO): Open verified binary stream.
            content_type (str): Validated response media type.
            content_length (int): Exact byte count.
            disposition (str): Safe Content-Disposition value.
            head_only (bool): Whether to omit the verified response body.
            digest: Optional verified prefixed SHA-256 response digest.

        Raises:
            OSError: Socket or stream read fails.

        Returns:
            None.
        """
        origin = self._request_origin()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(content_length))
        self.send_header("Content-Disposition", disposition)
        self.send_header("Cache-Control", "private, no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        if digest is not None:
            self.send_header("X-Content-SHA256", digest)
            self.send_header("ETag", f'"{digest.removeprefix("sha256:")}"')
        if origin is not None:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header(
                "Access-Control-Expose-Headers",
                (
                    "Content-Disposition, Content-Length, Content-Type, "
                    "X-Content-Type-Options, X-Content-SHA256, ETag"
                ),
            )
            self.send_header("Vary", "Origin")
        self.end_headers()
        try:
            if not head_only:
                while chunk := stream.read(1024 * 1024):
                    self.wfile.write(chunk)
        finally:
            stream.close()

    def _require_run_service(self) -> StudioRunApplicationService:
        """Return the configured live Run service.

        Args:
            None.

        Raises:
            StudioRunNotFoundError: Stage 3 service is not configured.

        Returns:
            StudioRunApplicationService: Shared process service.
        """
        composition = self.studio_server.run_composition
        if composition is None:
            raise StudioRunNotFoundError(
                "studio.run.unavailable",
                "Studio Run service is not configured",
            )
        return composition.service

    def _require_run_artifacts(self) -> LocalStudioRunArtifactStore:
        """Return the configured live Run artifact boundary.

        Args:
            None.

        Raises:
            StudioRunArtifactNotFoundError: Stage 3 storage is unavailable.

        Returns:
            LocalStudioRunArtifactStore: Shared managed content store.
        """
        composition = self.studio_server.run_composition
        if composition is None:
            raise StudioRunArtifactNotFoundError(
                "studio.run.artifact_not_found",
                "Studio Run artifact was not found",
            )
        return composition.artifacts

    def _require_benchmark_service(self) -> StudioBenchmarkApplicationService:
        """Return the configured definition-only Benchmark service.

        Args:
            None.

        Raises:
            StudioBenchmarkNotFoundError: Stage 5.1 service is not configured.

        Returns:
            StudioBenchmarkApplicationService: Shared process service.
        """
        composition = self.studio_server.benchmark_composition
        if composition is None:
            raise StudioBenchmarkNotFoundError(
                "benchmark.catalog.unavailable",
                "Studio Benchmark service is not configured",
            )
        return composition.service

    def _require_benchmark_authoring_service(
        self,
    ) -> StudioBenchmarkAuthoringApplicationService:
        """Return the configured durable Benchmark authoring service.

        Args:
            None.

        Raises:
            StudioBenchmarkNotFoundError: Authoring is not configured.

        Returns:
            Shared durable Benchmark authoring application service.
        """
        composition = self.studio_server.benchmark_composition
        if composition is None or composition.authoring is None:
            raise StudioBenchmarkNotFoundError(
                "benchmark.authoring.unavailable",
                "Benchmark authoring service is not configured",
            )
        return composition.authoring

    def _require_benchmark_authoring_content_service(
        self,
    ) -> StudioBenchmarkAuthoringContentApplicationService:
        """Return the configured draft-owned managed-content service.

        Args:
            None.

        Raises:
            StudioBenchmarkNotFoundError: Managed authoring content is not
                configured.

        Returns:
            Shared managed-content application service.
        """
        composition = self.studio_server.benchmark_composition
        if (
            composition is None
            or composition.authoring_content_service is None
        ):
            raise StudioBenchmarkNotFoundError(
                "benchmark.authoring.content_unavailable",
                "Benchmark authoring content service is not configured",
            )
        return composition.authoring_content_service

    def _require_benchmark_authoring_analysis_service(
        self,
    ) -> StudioBenchmarkAuthoringAnalysisService:
        """Return the configured revision-bound authoring analysis service.

        Args:
            None.

        Raises:
            StudioBenchmarkNotFoundError: Authoring analysis is not configured.

        Returns:
            Shared side-effect-free validation and dry-run service.
        """
        composition = self.studio_server.benchmark_composition
        if composition is None or composition.authoring_analysis is None:
            raise StudioBenchmarkNotFoundError(
                "benchmark.authoring.analysis_unavailable",
                "Benchmark authoring analysis service is not configured",
            )
        return composition.authoring_analysis

    def _require_benchmark_authoring_contract_test_service(
        self,
    ) -> StudioBenchmarkContractTestApplicationService:
        """Return the configured exact-revision Contract Test service.

        Raises:
            StudioBenchmarkAuthoringStorageError: Contract Tests are not
                configured for this Studio process.

        Returns:
            Shared transient Contract Test application service.
        """
        composition = self.studio_server.benchmark_composition
        if (
            composition is None
            or composition.authoring_contract_tests is None
        ):
            raise StudioBenchmarkAuthoringStorageError(
                "benchmark.authoring.contract_tests_unavailable",
                "Benchmark Contract Test service is not configured",
            )
        return composition.authoring_contract_tests

    def _require_benchmark_authoring_freeze_service(
        self,
    ) -> StudioBenchmarkValidatedFreezeApplicationService:
        """Return the configured exact-current validated-freeze service.

        Raises:
            StudioBenchmarkAuthoringStorageError: Freeze is not configured.

        Returns:
            Shared durable validated-freeze application service.
        """
        composition = self.studio_server.benchmark_composition
        if composition is None or composition.authoring_freeze is None:
            raise StudioBenchmarkAuthoringStorageError(
                "benchmark.authoring.freeze_unavailable",
                "Benchmark validated-freeze service is not configured",
            )
        return composition.authoring_freeze

    def _require_benchmark_authoring_release_service(
        self,
    ) -> StudioBenchmarkPackageReleaseApplicationService:
        """Return the configured immutable Package release service.

        Raises:
            StudioBenchmarkAuthoringStorageError: Release is not configured.

        Returns:
            Shared durable publication/export application service.
        """
        composition = self.studio_server.benchmark_composition
        if composition is None or composition.authoring_release is None:
            raise StudioBenchmarkAuthoringStorageError(
                "benchmark.authoring.release_unavailable",
                "Benchmark Package release service is not configured",
            )
        return composition.authoring_release

    def _require_benchmark_authoring_migration_service(
        self,
    ) -> StudioBenchmarkLegacyMigrationApplicationService:
        """Return the configured definition-only legacy migration service.

        Args:
            None.

        Raises:
            StudioBenchmarkAuthoringStorageError: Migration is not configured.

        Returns:
            Shared pure-Preview and confirmed-create application service.
        """
        composition = self.studio_server.benchmark_composition
        if composition is None or composition.authoring_migration is None:
            raise StudioBenchmarkAuthoringStorageError(
                "benchmark.migration.unavailable",
                "Benchmark legacy migration service is not configured",
            )
        return composition.authoring_migration

    def _require_benchmark_experiment_service(
        self,
    ) -> StudioBenchmarkExperimentApplicationService:
        """Return the configured durable Benchmark Experiment service.

        Raises:
            StudioBenchmarkNotFoundError: Stage 5.2A is not configured.

        Returns:
            Shared durable Experiment application service.
        """
        composition = self.studio_server.benchmark_composition
        if composition is None or composition.experiments is None:
            raise StudioBenchmarkNotFoundError(
                "benchmark.experiment.unavailable",
                "Benchmark Experiment service is not configured",
            )
        return composition.experiments

    def _require_benchmark_event_service(
        self,
    ) -> DurableBenchmarkEventService:
        """Return the configured durable Benchmark event service.

        Raises:
            StudioBenchmarkNotFoundError: Event transport is not configured.

        Returns:
            Shared durable Benchmark event service.
        """
        composition = self.studio_server.benchmark_composition
        if composition is None or composition.events is None:
            raise StudioBenchmarkNotFoundError(
                "benchmark.event.unavailable",
                "Benchmark event service is not configured",
            )
        return composition.events

    def _require_benchmark_artifact_store(
        self,
    ) -> LocalStudioBenchmarkManagedArtifactStore:
        """Return the configured managed Benchmark artifact resolver.

        Raises:
            StudioBenchmarkNotFoundError: Publication is not configured.

        Returns:
            Shared managed Benchmark artifact store.
        """
        composition = self.studio_server.benchmark_composition
        if composition is None or composition.artifacts is None:
            raise StudioBenchmarkNotFoundError(
                "benchmark.publication.unavailable",
                "Benchmark publication service is not configured",
            )
        return composition.artifacts

    def _benchmark_publication_artifact_id(
        self,
        experiment_id: str,
        kind: str,
    ) -> str:
        """Resolve one available report or bundle artifact identity.

        Args:
            experiment_id: Owning Experiment identity.
            kind: ``report`` or ``bundle``.

        Raises:
            StudioBenchmarkNotFoundError: Publication/component is absent.

        Returns:
            Opaque managed artifact identity.
        """
        composition = self.studio_server.benchmark_composition
        if composition is None or composition.publications is None:
            raise StudioBenchmarkNotFoundError(
                "benchmark.publication.unavailable",
                "Benchmark publication service is not configured",
            )
        publication = composition.publications.get_publication(experiment_id)
        artifact_id = (
            publication.report_artifact_id
            if publication is not None and kind == "report"
            else publication.bundle_artifact_id
            if publication is not None and kind == "bundle"
            else None
        )
        if artifact_id is None:
            raise StudioBenchmarkNotFoundError(
                "benchmark.publication.component_not_found",
                "Benchmark publication component was not found",
            )
        return artifact_id

    @staticmethod
    def _validate_run_id(run_id: str) -> str:
        """Validate one opaque Run path identity before repository access.

        Args:
            run_id (str): URL-decoded candidate identity.

        Raises:
            StudioRunValidationError: Identity is malformed.

        Returns:
            str: Validated identity.
        """
        if re.fullmatch(r"run-[a-f0-9]{32}", run_id) is None:
            raise StudioRunValidationError(
                "studio.run.identifier_invalid",
                "Studio Run identity is invalid",
            )
        return run_id

    @staticmethod
    def _validate_artifact_id(artifact_id: str) -> str:
        """Validate one opaque artifact path identity.

        Args:
            artifact_id (str): URL-decoded candidate identity.

        Raises:
            StudioRunValidationError: Identity is malformed.

        Returns:
            str: Validated identity.
        """
        if re.fullmatch(r"artifact-[a-f0-9]{32}", artifact_id) is None:
            raise StudioRunValidationError(
                "studio.run.artifact_identifier_invalid",
                "Studio Run artifact identity is invalid",
            )
        return artifact_id

    @staticmethod
    def _validate_benchmark_artifact_id(artifact_id: str) -> str:
        """Validate one opaque Benchmark artifact path identity.

        Args:
            artifact_id: URL-decoded candidate identity.

        Raises:
            StudioBenchmarkValidationError: Identity is malformed.

        Returns:
            Validated opaque Benchmark artifact identity.
        """
        if re.fullmatch(r"artifact-[a-f0-9]{32}", artifact_id) is None:
            raise StudioBenchmarkValidationError(
                "benchmark.artifact.identifier_invalid",
                "Benchmark artifact identity is invalid",
            )
        return artifact_id

    @staticmethod
    def _benchmark_page_query(
        query: Mapping[str, list[str]],
        *,
        resource: str,
    ) -> tuple[int, str | None]:
        """Parse one strict bounded Benchmark metadata page query.

        Args:
            query: Parsed URL query parameters.
            resource: Stable error-code segment for the requested resource.

        Raises:
            StudioBenchmarkValidationError: Query shape or limit is invalid.

        Returns:
            Page limit and optional opaque cursor.
        """
        if set(query) - {"limit", "cursor"}:
            raise StudioBenchmarkValidationError(
                f"benchmark.{resource}.query_invalid",
                "Benchmark page query is invalid",
            )
        limit_values = query.get("limit") or ["50"]
        cursor_values = query.get("cursor") or [None]
        if len(limit_values) != 1 or len(cursor_values) != 1:
            raise StudioBenchmarkValidationError(
                f"benchmark.{resource}.query_invalid",
                "Benchmark page query is invalid",
            )
        try:
            limit = int(limit_values[0])
        except (TypeError, ValueError) as error:
            raise StudioBenchmarkValidationError(
                f"benchmark.{resource}.limit_invalid",
                "Benchmark page limit is invalid",
            ) from error
        return limit, cursor_values[0]

    @staticmethod
    def _benchmark_experiment_history_query(
        query: Mapping[str, list[str]],
    ) -> tuple[int, str | None, StudioBenchmarkExperimentHistoryFilterV1]:
        """Parse one strict filtered Experiment History metadata query.

        Args:
            query: Parsed URL query preserving duplicate and blank values.

        Raises:
            StudioBenchmarkValidationError: Query shape, filter, or limit is
                invalid.

        Returns:
            Page limit, optional opaque cursor, and immutable exact filters.
        """
        allowed = {
            "limit",
            "cursor",
            "lifecycle",
            "catalogEntryId",
            "agentId",
            "acceptedFrom",
            "acceptedBefore",
        }
        if set(query) - allowed or any(
            len(values) != 1 or values[0] == ""
            for values in query.values()
        ):
            raise StudioBenchmarkValidationError(
                "benchmark.experiment.history.query_invalid",
                "Benchmark Experiment history query is invalid",
            )
        limit_value = (query.get("limit") or ["50"])[0]
        try:
            limit = int(limit_value)
        except (TypeError, ValueError) as error:
            raise StudioBenchmarkValidationError(
                "benchmark.experiment.history_limit_invalid",
                "Benchmark Experiment history limit is invalid",
            ) from error
        cursor = (query.get("cursor") or [None])[0]

        def parse_epoch(name: str) -> int | None:
            """Parse one canonical non-negative epoch-millisecond filter.

            Args:
                name: Public query parameter name.

            Raises:
                ValueError: Present value is not canonical decimal syntax.

            Returns:
                Parsed integer or ``None`` when the parameter is absent.
            """
            value = (query.get(name) or [None])[0]
            if value is None:
                return None
            if re.fullmatch(r"0|[1-9][0-9]*", value) is None:
                raise ValueError("invalid epoch")
            return int(value)

        try:
            filters = StudioBenchmarkExperimentHistoryFilterV1(
                lifecycle=(query.get("lifecycle") or [None])[0],
                catalog_entry_id=(
                    query.get("catalogEntryId") or [None]
                )[0],
                agent_id=(query.get("agentId") or [None])[0],
                accepted_from=parse_epoch("acceptedFrom"),
                accepted_before=parse_epoch("acceptedBefore"),
            )
        except (TypeError, ValueError) as error:
            raise StudioBenchmarkValidationError(
                "benchmark.experiment.history_filter_invalid",
                "Benchmark Experiment history filter is invalid",
            ) from error
        return limit, cursor, filters

    def _sse_cursor(self, query: Mapping[str, list[str]]) -> int:
        """Resolve reconnect cursor from query or Last-Event-ID.

        Args:
            query (Mapping[str, list[str]]): Parsed URL query.

        Raises:
            StudioRunValidationError: Cursor values conflict or are invalid.

        Returns:
            int: Exclusive journal cursor.
        """
        explicit = (query.get("after") or [None])[0]
        header = self.headers.get("Last-Event-ID")
        if explicit is not None and header is not None and explicit != header:
            raise StudioRunValidationError(
                "studio.run.event_cursor_invalid",
                "SSE cursor sources disagree",
            )
        raw = explicit if explicit is not None else header
        try:
            cursor = int(raw) if raw is not None else 0
        except ValueError as error:
            raise StudioRunValidationError(
                "studio.run.event_cursor_invalid",
                "SSE cursor is invalid",
            ) from error
        if cursor < 0:
            raise StudioRunValidationError(
                "studio.run.event_cursor_invalid",
                "SSE cursor is invalid",
            )
        return cursor

    def _send_run_events_sse(
        self,
        run_id: str,
        query: Mapping[str, list[str]],
    ) -> None:
        """Backfill, follow, heartbeat, and close one durable Run stream.

        Args:
            run_id (str): Validated Run identity.
            query (Mapping[str, list[str]]): Parsed cursor parameters.

        Raises:
            StudioRunError: Initial journal query is invalid.
            OSError: Socket streaming fails before disconnect cleanup.

        Returns:
            None.
        """
        service = self._require_run_service()
        cursor = self._sse_cursor(query)
        page = service.query_events(run_id, after=cursor, limit=100)
        origin = self._request_origin()
        self.connection.settimeout(
            self.studio_server.sse_write_timeout_seconds
        )
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.send_header("X-Accel-Buffering", "no")
        self.send_header("X-Content-Type-Options", "nosniff")
        if origin is not None:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.end_headers()
        self.close_connection = True
        try:
            while True:
                for item in page.items:
                    body = json.dumps(
                        item.model_dump(
                            mode="json",
                            by_alias=True,
                            exclude_none=True,
                        ),
                        ensure_ascii=False,
                        allow_nan=False,
                        separators=(",", ":"),
                    )
                    frame = (
                        f"id: {item.sequence}\n"
                        "event: journal\n"
                        f"data: {body}\n\n"
                    ).encode("utf-8")
                    self.wfile.write(frame)
                    cursor = item.sequence
                self.wfile.flush()
                if page.terminal:
                    return
                page = service.events.wait_for_events(
                    run_id,
                    after=cursor,
                    limit=100,
                    timeout=self.studio_server.sse_heartbeat_seconds,
                )
                if not page.items and not page.terminal:
                    self.wfile.write(b": heartbeat\n\n")
                    self.wfile.write(
                        b"event: heartbeat\n"
                        b"data: {\"schemaVersion\":1}\n\n"
                    )
                    self.wfile.flush()
        except (
            BrokenPipeError,
            ConnectionResetError,
            ConnectionAbortedError,
            socket.timeout,
            StudioRunError,
        ):
            return

    def _benchmark_sse_cursor(
        self,
        query: Mapping[str, list[str]],
    ) -> int:
        """Resolve one Benchmark SSE reconnect cursor.

        Args:
            query: Parsed URL query.

        Raises:
            StudioBenchmarkValidationError: Cursor sources are invalid.

        Returns:
            Exclusive Experiment-local journal cursor.
        """
        explicit_values = query.get("after") or []
        if len(explicit_values) > 1:
            raise StudioBenchmarkValidationError(
                "benchmark.event.cursor_invalid",
                "Benchmark SSE cursor is invalid",
            )
        explicit = explicit_values[0] if explicit_values else None
        header = self.headers.get("Last-Event-ID")
        try:
            explicit_cursor = int(explicit) if explicit is not None else None
            header_cursor = int(header) if header is not None else None
        except ValueError as error:
            raise StudioBenchmarkValidationError(
                "benchmark.event.cursor_invalid",
                "Benchmark SSE cursor is invalid",
            ) from error
        if (
            explicit_cursor is not None
            and header_cursor is not None
            and explicit_cursor != header_cursor
        ):
            raise StudioBenchmarkValidationError(
                "benchmark.event.cursor_invalid",
                "Benchmark SSE cursor sources disagree",
            )
        cursor = (
            explicit_cursor
            if explicit_cursor is not None
            else header_cursor
            if header_cursor is not None
            else 0
        )
        if cursor < 0:
            raise StudioBenchmarkValidationError(
                "benchmark.event.cursor_invalid",
                "Benchmark SSE cursor is invalid",
            )
        return cursor

    def _send_benchmark_events_sse(
        self,
        experiment_id: str,
        query: Mapping[str, list[str]],
    ) -> None:
        """Backfill, follow, heartbeat, and close one Benchmark event stream.

        Args:
            experiment_id: Validated Experiment identity.
            query: Parsed cursor parameters.

        Raises:
            StudioBenchmarkError: Initial cursor or journal query is invalid.

        Returns:
            None.
        """
        cursor = self._benchmark_sse_cursor(query)
        events = self._require_benchmark_event_service()
        limiter = self.studio_server.benchmark_sse_connections
        if not limiter.acquire():
            raise StudioBenchmarkCapacityError(
                "benchmark.event.connection_capacity",
                "Benchmark event stream capacity is exhausted",
            )
        try:
            page = events.query(experiment_id, after=cursor, limit=100)
        except Exception:
            limiter.release()
            raise
        try:
            origin = self._request_origin()
            self.connection.settimeout(
                self.studio_server.sse_write_timeout_seconds
            )
            self.send_response(200)
            self.send_header(
                "Content-Type",
                "text/event-stream; charset=utf-8",
            )
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.send_header("X-Accel-Buffering", "no")
            self.send_header("X-Content-Type-Options", "nosniff")
            if origin is not None:
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Vary", "Origin")
            self.end_headers()
            self.close_connection = True
        except Exception:
            limiter.release()
            raise
        try:
            while True:
                for item in page.items:
                    body = json.dumps(
                        item.model_dump(
                            mode="json",
                            by_alias=True,
                            exclude_none=True,
                        ),
                        ensure_ascii=False,
                        allow_nan=False,
                        separators=(",", ":"),
                    )
                    frame = (
                        f"id: {item.sequence}\n"
                        "event: journal\n"
                        f"data: {body}\n\n"
                    ).encode("utf-8")
                    self.wfile.write(frame)
                    cursor = item.sequence
                self.wfile.flush()
                if page.terminal:
                    return
                page = events.wait_for_events(
                    experiment_id,
                    after=cursor,
                    limit=100,
                    timeout=self.studio_server.sse_heartbeat_seconds,
                )
                if not page.items and not page.terminal:
                    self.wfile.write(
                        b"event: heartbeat\n"
                        b"data: {\"schemaVersion\":1}\n\n"
                    )
                    self.wfile.flush()
        except (
            BrokenPipeError,
            ConnectionResetError,
            ConnectionAbortedError,
            socket.timeout,
            StudioBenchmarkError,
        ):
            return
        finally:
            limiter.release()

    def _read_json(self) -> Mapping[str, Any]:
        """Read one bounded JSON object request body.

        Args:
            None.

        Raises:
            StudioApplicationError: Length, media type, JSON, or root type is
                invalid.

        Returns:
            Mapping[str, Any]: Parsed JSON object.
        """
        content_type = self.headers.get("Content-Type", "")
        if "application/json" not in content_type.lower():
            raise StudioApplicationError(
                "studio.http.content_type_invalid",
                "Content-Type must be application/json",
            )
        raw_length = self.headers.get("Content-Length")
        try:
            length = int(raw_length or "")
        except ValueError as error:
            raise StudioApplicationError(
                "studio.http.content_length_invalid",
                "Content-Length is required",
            ) from error
        if length < 0 or length > _MAX_REQUEST_BYTES:
            raise StudioApplicationError(
                "studio.http.body_too_large",
                f"Request body must not exceed {_MAX_REQUEST_BYTES} bytes",
            )
        try:
            parsed = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise StudioApplicationError(
                "studio.http.json_invalid",
                "Request body is not valid UTF-8 JSON",
            ) from error
        if not isinstance(parsed, Mapping):
            raise StudioApplicationError(
                "studio.http.envelope_invalid",
                "Request JSON root must be an object",
            )
        return parsed

    @staticmethod
    def _require_schema_version(payload: Mapping[str, Any]) -> None:
        """Require the versioned HTTP request envelope.

        Args:
            payload (Mapping[str, Any]): Parsed request object.

        Raises:
            StudioApplicationError: Version is absent or unsupported.

        Returns:
            None.
        """
        if payload.get("schemaVersion") != 1:
            raise StudioApplicationError(
                "studio.http.schema_version_unsupported",
                "Request requires schemaVersion 1",
            )

    @staticmethod
    def _path_segments(path: str) -> tuple[str, ...]:
        """Split and URL-decode an HTTP path.

        Args:
            path (str): URL path.

        Raises:
            None.

        Returns:
            tuple[str, ...]: Decoded non-empty segments.
        """
        return tuple(unquote(item) for item in path.split("/") if item)

    @staticmethod
    def _normalize_api_path(path: str) -> str:
        """Map the public API prefix onto the existing Studio route namespace.

        Args:
            path (str): Parsed request path.

        Raises:
            None.

        Returns:
            str: Internal route path retaining backward-compatible endpoints.
        """
        if path == "/api/studio":
            return "/studio"
        if path.startswith("/api/studio/"):
            return "/studio/" + path.removeprefix("/api/studio/")
        return path

    @classmethod
    def _authoring_content_route_kind(cls, path: str) -> str | None:
        """Classify one exact managed authoring content route.

        Args:
            path: Normalized Studio request path.

        Raises:
            None.

        Returns:
            ``action`` for mutation routes, ``content`` for exact reads, or
            None for every other route.
        """
        segments = cls._path_segments(path)
        if (
            len(segments) == 7
            and segments[:3]
            == ("studio", "benchmark-authoring", "drafts")
            and segments[4] == "resources"
            and segments[6] in {"upload", "replace", "remove"}
        ):
            return "action"
        if (
            len(segments) == 9
            and segments[:3]
            == ("studio", "benchmark-authoring", "drafts")
            and segments[4] == "revisions"
            and segments[6] == "resources"
            and segments[8] == "content"
        ):
            return "content"
        if (
            len(segments) == 5
            and segments[:3]
            == ("studio", "benchmark-authoring", "drafts")
            and segments[4] in {"validate", "dry-run"}
        ):
            return "analysis"
        if path == "/studio/benchmark-authoring/contract-test-profiles":
            return "contract-profiles"
        if path in {
            "/studio/benchmark-authoring/legacy-migrations/preview",
            "/studio/benchmark-authoring/legacy-migrations/confirm",
        }:
            return "migration"
        if (
            len(segments) == 5
            and segments[:3]
            == ("studio", "benchmark-authoring", "drafts")
            and segments[4] == "contract-tests"
        ):
            return "contract-tests"
        if (
            len(segments) == 5
            and segments[:3]
            == ("studio", "benchmark-authoring", "drafts")
            and segments[4] == "package-revisions"
        ):
            return "package-revision-collection"
        if (
            len(segments) == 6
            and segments[:3]
            == ("studio", "benchmark-authoring", "drafts")
            and segments[4] == "package-revisions"
        ):
            return "freeze-detail"
        if (
            len(segments) == 7
            and segments[:3]
            == ("studio", "benchmark-authoring", "drafts")
            and segments[4] == "package-revisions"
            and segments[6] in {"publications", "exports"}
        ):
            return "release-command"
        if (
            len(segments) == 8
            and segments[:3]
            == ("studio", "benchmark-authoring", "drafts")
            and segments[4] == "package-revisions"
            and segments[6] in {"publications", "exports"}
        ):
            return "release-detail"
        if (
            len(segments) == 9
            and segments[:3]
            == ("studio", "benchmark-authoring", "drafts")
            and segments[4] == "package-revisions"
            and segments[6] == "exports"
            and segments[8] == "content"
        ):
            return "release-content"
        return None

    def _authoring_content_length(self, *, maximum: int) -> int:
        """Validate one non-chunked exact binary request length.

        Args:
            maximum: Inclusive request-specific byte maximum.

        Raises:
            StudioBenchmarkValidationError: Transfer framing is ambiguous,
                absent, malformed, or above the bound.
            StudioBenchmarkAuthoringCapacityError: Body exceeds the content
                command capacity.

        Returns:
            Exact declared request byte count.
        """
        if self.headers.get_all("Transfer-Encoding"):
            raise StudioBenchmarkValidationError(
                "benchmark.authoring.transfer_encoding_invalid",
                "Chunked Benchmark authoring content is not supported",
            )
        values = self.headers.get_all("Content-Length") or []
        if len(values) != 1 or not values[0].isdigit():
            raise StudioBenchmarkValidationError(
                "benchmark.authoring.content_length_invalid",
                "One exact Content-Length is required",
            )
        length = int(values[0])
        if length > maximum:
            raise StudioBenchmarkAuthoringCapacityError(
                "benchmark.authoring.content_too_large",
                "Benchmark authoring content exceeds its safe limit",
            )
        return length

    def _authoring_content_type(self) -> str:
        """Return one exact declared binary media type header.

        Args:
            None.

        Raises:
            StudioBenchmarkValidationError: Header is absent or duplicated.

        Returns:
            Untrusted media type for strict DTO parsing.
        """
        values = self.headers.get_all("Content-Type") or []
        if len(values) != 1 or not values[0]:
            raise StudioBenchmarkValidationError(
                "benchmark.authoring.content_type_invalid",
                "One exact Content-Type is required",
            )
        return values[0]

    def do_OPTIONS(self) -> None:
        """Respond to an allowed browser CORS preflight.

        Args:
            None.

        Raises:
            None.

        Returns:
            None.
        """
        try:
            self._require_host()
            origin = self._request_origin()
        except PermissionError:
            self._send_forbidden_without_cors()
            return
        self.send_response(204)
        if origin is not None:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.send_header(
            "Access-Control-Allow-Methods",
            "GET, HEAD, POST, PATCH, OPTIONS",
        )
        self.send_header(
            "Access-Control-Allow-Headers",
            "Accept, Content-Type, Last-Event-ID",
        )
        self.send_header("Access-Control-Max-Age", "600")
        self.end_headers()

    def _send_forbidden_without_cors(self) -> None:
        """Send a safe forbidden response without echoing an untrusted Origin.

        Args:
            None.

        Raises:
            None.

        Returns:
            None.
        """
        status, body, headers = _json_bytes(
            _error_payload(
                "studio.http.forbidden",
                "Request host or origin is not allowed",
            ),
            403,
        )
        self.send_response(status)
        for key, value in headers:
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _dispatch(self, method: str) -> None:
        """Dispatch one request and map domain failures to stable HTTP errors.

        Args:
            method (str): HTTP method.

        Raises:
            None: All exceptions are mapped to safe responses.

        Returns:
            None.
        """
        private_error = False
        try:
            self._require_host()
            self._request_origin()
            parsed = urlparse(self.path)
            path = self._normalize_api_path(parsed.path or "/")
            query = parse_qs(
                parsed.query or "",
                keep_blank_values=True,
            )
            content_route = self._authoring_content_route_kind(path)
            private_error = content_route in {
                "analysis",
                "contract-profiles",
                "contract-tests",
                "package-revision-collection",
                "freeze-detail",
                "release-command",
                "release-detail",
                "release-content",
                "migration",
            }
            if (
                content_route == "action"
                and method != "POST"
            ) or (
                content_route == "content"
                and method not in {"GET", "HEAD"}
            ) or (
                content_route == "analysis"
                and method != "POST"
            ) or (
                content_route == "contract-profiles"
                and method != "GET"
            ) or (
                content_route == "contract-tests"
                and method != "POST"
            ) or (
                content_route == "package-revision-collection"
                and method not in {"GET", "POST"}
            ) or (
                content_route == "freeze-detail"
                and method != "GET"
            ) or (
                content_route == "release-command"
                and method != "POST"
            ) or (
                content_route == "release-detail"
                and method != "GET"
            ) or (
                content_route == "release-content"
                and method not in {"GET", "HEAD"}
            ) or (
                content_route == "migration"
                and method != "POST"
            ):
                self._send_json(
                    _error_payload(
                        "studio.http.method_not_allowed",
                        "HTTP method is not supported for this resource",
                    ),
                    405,
                    private=private_error,
                )
                return
            if method == "GET":
                self._handle_get(path, query)
            elif method == "HEAD":
                self._handle_head(path, query)
            elif method == "POST":
                self._handle_post(path, query)
            elif method == "PATCH":
                self._handle_patch(path)
            else:
                self._send_json(
                    _error_payload(
                        "studio.http.method_not_allowed",
                        "HTTP method is not supported",
                    ),
                    405,
                )
        except PermissionError:
            self._send_forbidden_without_cors()
        except StudioApplicationError as error:
            status = 413 if error.code == "studio.http.body_too_large" else 400
            self._send_json(
                _error_payload(error.code, str(error)),
                status,
                private=private_error,
            )
        except StudioBenchmarkAuthoringCapacityError as error:
            self._send_json(
                _error_payload(error.code, str(error)),
                413,
                private=private_error,
            )
        except StudioBenchmarkAuthoringFreezeEligibilityError as error:
            payload = _error_payload(error.code, str(error))
            payload["error"]["diagnostics"] = [
                item.model_dump(
                    mode="json",
                    by_alias=True,
                    exclude_none=True,
                )
                for item in error.diagnostics
            ]
            self._send_json(payload, 400, private=True)
        except StudioBenchmarkAuthoringRevisionConflictError as error:
            payload = _error_payload(error.code, str(error))
            payload["error"]["currentRevisionId"] = (
                error.current_revision_id
            )
            self._send_json(payload, 409, private=private_error)
        except StudioBenchmarkAuthoringStorageError as error:
            self._send_json(
                _error_payload(error.code, str(error)),
                503,
                private=private_error,
            )
        except StudioBenchmarkCapacityError as error:
            self._send_json(_error_payload(error.code, str(error)), 503)
        except StudioBenchmarkNotFoundError as error:
            self._send_json(
                _error_payload(error.code, str(error)),
                404,
                private=private_error,
            )
        except StudioBenchmarkConflictError as error:
            self._send_json(
                _error_payload(error.code, str(error)),
                409,
                private=private_error,
            )
        except StudioBenchmarkSnapshotTooLargeError as error:
            self._send_json(_error_payload(error.code, str(error)), 413)
        except StudioBenchmarkValidationError as error:
            self._send_json(
                _error_payload(error.code, str(error)),
                400,
                private=private_error,
            )
        except StudioBenchmarkError as error:
            self._send_json(_error_payload(error.code, str(error)), 422)
        except (
            StudioRunNotFoundError,
            StudioRunArtifactNotFoundError,
        ) as error:
            self._send_json(_error_payload(error.code, str(error)), 404)
        except StudioRunConflictError as error:
            self._send_json(_error_payload(error.code, str(error)), 409)
        except StudioRunValidationError as error:
            self._send_json(_error_payload(error.code, str(error)), 400)
        except StudioRunError as error:
            self._send_json(_error_payload(error.code, str(error)), 422)
        except (AgentNotFoundError, AgentRevisionNotFoundError):
            self._send_json(
                _error_payload(
                    "studio.resource.not_found",
                    "Requested Studio resource was not found",
                ),
                404,
            )
        except AgentRevisionConflictError as error:
            payload = _error_payload(
                "studio.revision.conflict",
                "Agent current revision changed",
            )
            payload["error"]["currentRevisionId"] = error.current_revision_id
            self._send_json(payload, 409)
        except (ReplayNotFoundError, ReplayArtifactNotFoundError):
            self._send_json(
                _error_payload(
                    "studio.replay.not_found",
                    "Requested Replay resource was not found",
                ),
                404,
            )
        except ReplayConflictError:
            self._send_json(
                _error_payload(
                    "studio.replay.conflict",
                    "Replay run identity already exists",
                ),
                409,
            )
        except ReplayImportError as error:
            self._send_json(_error_payload(error.code, str(error)), 422)
        except KeyError:
            self._send_json(
                _error_payload(
                    "studio.template.not_found",
                    "Requested Studio template was not found",
                ),
                404,
            )
        except FileNotFoundError:
            self._send_json(
                _error_payload(
                    "studio.template.document_missing",
                    "Studio template document is unavailable",
                ),
                404,
            )
        except (TypeError, ValueError) as error:
            self._send_json(
                _error_payload(
                    "studio.request.invalid",
                    str(error),
                ),
                400,
                private=private_error,
            )
        except Exception:
            logger.exception("studio_http_error method=%s path=%s", method, self.path)
            self._send_json(
                _error_payload(
                    "studio.server.error",
                    "Studio service encountered an internal error",
                ),
                500,
                private=private_error,
            )

    def do_GET(self) -> None:
        """Handle one GET request.

        Args:
            None.

        Raises:
            None.

        Returns:
            None.
        """
        self._dispatch("GET")

    def do_HEAD(self) -> None:
        """Handle one HEAD request for exact managed Benchmark content.

        Args:
            None.

        Raises:
            None.

        Returns:
            None.
        """
        self._dispatch("HEAD")

    def do_POST(self) -> None:
        """Handle one POST request.

        Args:
            None.

        Raises:
            None.

        Returns:
            None.
        """
        self._dispatch("POST")

    def do_PATCH(self) -> None:
        """Handle one PATCH request.

        Args:
            None.

        Raises:
            None.

        Returns:
            None.
        """
        self._dispatch("PATCH")

    @staticmethod
    def _benchmark_download_disposition(
        descriptor: StudioBenchmarkArtifactDescriptorV1,
        *,
        publication_kind: str | None = None,
    ) -> str:
        """Build an attachment disposition from validated opaque identities.

        Args:
            descriptor: Verified managed artifact descriptor.
            publication_kind: Optional ``report`` or ``bundle`` route kind.

        Raises:
            ValueError: Publication kind is unsupported.

        Returns:
            Safe attachment Content-Disposition value.
        """
        if publication_kind is None:
            filename = descriptor.artifact_id
        elif publication_kind == "report":
            filename = f"{descriptor.experiment_id}.report.json"
        elif publication_kind == "bundle":
            filename = f"{descriptor.experiment_id}.zip"
        else:
            raise ValueError("benchmark publication kind is invalid")
        return f'attachment; filename="{filename}"'

    def _handle_benchmark_content(
        self,
        path: str,
        *,
        head_only: bool,
    ) -> bool:
        """Serve one exact Benchmark managed-content capability.

        Args:
            path: Normalized Studio request path.
            head_only: Whether to emit headers without the verified body.

        Raises:
            StudioBenchmarkError: Identity, scope, availability, or integrity
                validation fails.
            ValueError: A route identity is malformed.

        Returns:
            ``True`` when ``path`` is a managed-content route, otherwise
            ``False``.
        """
        segments = self._path_segments(path)
        if (
            len(segments) == 7
            and segments[:2] == ("studio", "benchmark-experiments")
            and segments[3] == "task-runs"
            and segments[5] == "artifacts"
        ):
            experiment_id = (
                self._require_benchmark_experiment_service()
                .validate_experiment_id(segments[2])
            )
            task_run_id = (
                self._require_benchmark_experiment_service()
                .validate_task_run_id(segments[4])
            )
            artifact_id = self._validate_benchmark_artifact_id(segments[6])
            composition = self.studio_server.benchmark_composition
            if composition is None or composition.publications is None:
                raise StudioBenchmarkNotFoundError(
                    "benchmark.publication.unavailable",
                    "Benchmark publication service is not configured",
                )
            record = composition.publications.get_artifact(
                experiment_id,
                artifact_id,
            )
            if record.descriptor.task_run_id != task_run_id:
                raise StudioBenchmarkNotFoundError(
                    "benchmark.artifact.not_found",
                    "Benchmark artifact was not found",
                )
            descriptor, stream = (
                self._require_benchmark_artifact_store().open_artifact(
                    experiment_id,
                    artifact_id,
                )
            )
            self._send_binary(
                stream,
                content_type=descriptor.content_type,
                content_length=descriptor.size,
                disposition=self._benchmark_download_disposition(descriptor),
                head_only=head_only,
            )
            return True
        if (
            len(segments) == 5
            and segments[:2] == ("studio", "benchmark-experiments")
            and segments[3] == "artifacts"
        ):
            experiment_id = (
                self._require_benchmark_experiment_service()
                .validate_experiment_id(segments[2])
            )
            artifact_id = self._validate_benchmark_artifact_id(segments[4])
            descriptor, stream = (
                self._require_benchmark_artifact_store().open_artifact(
                    experiment_id,
                    artifact_id,
                )
            )
            self._send_binary(
                stream,
                content_type=descriptor.content_type,
                content_length=descriptor.size,
                disposition=self._benchmark_download_disposition(descriptor),
                head_only=head_only,
            )
            return True
        if (
            len(segments) == 4
            and segments[:2] == ("studio", "benchmark-experiments")
            and segments[3] in {"report", "bundle"}
        ):
            experiment_id = (
                self._require_benchmark_experiment_service()
                .validate_experiment_id(segments[2])
            )
            kind = segments[3]
            artifact_id = self._benchmark_publication_artifact_id(
                experiment_id,
                kind,
            )
            descriptor, stream = (
                self._require_benchmark_artifact_store().open_artifact(
                    experiment_id,
                    artifact_id,
                )
            )
            self._send_binary(
                stream,
                content_type=descriptor.content_type,
                content_length=descriptor.size,
                disposition=self._benchmark_download_disposition(
                    descriptor,
                    publication_kind=kind,
                ),
                head_only=head_only,
            )
            return True
        return False

    def _handle_authoring_content_read(
        self,
        path: str,
        query: Mapping[str, list[str]],
        *,
        head_only: bool,
    ) -> bool:
        """Serve one exact owned authoring resource after integrity closure.

        Args:
            path: Normalized Studio request path.
            query: Parsed query parameters, which must be empty.
            head_only: Whether to emit headers without body bytes.

        Raises:
            StudioBenchmarkError: Ownership, identity, or integrity fails.

        Returns:
            True when the path was the exact authoring content route.
        """
        segments = self._path_segments(path)
        if not (
            len(segments) == 9
            and segments[:3]
            == ("studio", "benchmark-authoring", "drafts")
            and segments[4] == "revisions"
            and segments[6] == "resources"
            and segments[8] == "content"
        ):
            return False
        if query:
            raise StudioBenchmarkValidationError(
                "benchmark.authoring.query_invalid",
                "Benchmark authoring content query is invalid",
            )
        opened = (
            self._require_benchmark_authoring_content_service().open_content(
                segments[3],
                segments[5],
                segments[7],
            )
        )
        self._send_binary(
            opened.stream,
            content_type=opened.resource.media_type,
            content_length=opened.resource.size,
            disposition=(
                f'attachment; filename="{opened.resource.id}"'
            ),
            head_only=head_only,
        )
        return True

    def _handle_authoring_content_command(
        self,
        path: str,
        query: Mapping[str, list[str]],
    ) -> bool:
        """Execute one bounded raw-body authoring content command.

        Args:
            path: Normalized Studio request path.
            query: Strict versioned command metadata envelope.

        Raises:
            StudioBenchmarkError: Metadata, storage, idempotency, or CAS fails.

        Returns:
            True when the path was an exact supported content action.
        """
        segments = self._path_segments(path)
        if not (
            len(segments) == 7
            and segments[:3]
            == ("studio", "benchmark-authoring", "drafts")
            and segments[4] == "resources"
            and segments[6] in {"upload", "replace", "remove"}
        ):
            return False
        draft_id = segments[3]
        resource_id = segments[5]
        operation = segments[6]
        service = self._require_benchmark_authoring_content_service()
        if operation == "remove":
            self._authoring_content_length(maximum=0)
            request = parse_authoring_content_remove_query(
                resource_id=resource_id,
                query=query,
            )
            result = service.remove(draft_id, request)
        else:
            # Close even when metadata, ownership, or CAS preflight fails before
            # consuming the body; unread bytes can never frame a next request.
            self.close_connection = True
            length = self._authoring_content_length(
                maximum=STUDIO_BENCHMARK_AUTHORING_MAX_RESOURCE_BYTES
            )
            media_type = self._authoring_content_type()
            stream = _ExactContentLengthStream(self.rfile, length)
            if operation == "upload":
                upload = parse_authoring_content_upload_query(
                    resource_id=resource_id,
                    media_type=media_type,
                    query=query,
                )
                result = service.upload(draft_id, upload, stream)
            else:
                replacement = parse_authoring_content_replace_query(
                    resource_id=resource_id,
                    media_type=media_type,
                    query=query,
                )
                result = service.replace(draft_id, replacement, stream)
        self._send_json(
            result.model_dump(
                mode="json",
                by_alias=True,
                exclude_none=True,
            ),
            201 if result.created else 200,
        )
        return True

    def _handle_authoring_export_content(
        self,
        path: str,
        query: Mapping[str, list[str]],
        *,
        head_only: bool,
    ) -> bool:
        """Serve one exact verified Package archive through full ownership.

        Args:
            path: Normalized Studio request path.
            query: Parsed query parameters, which must be empty.
            head_only: Whether to emit identical headers without body bytes.

        Raises:
            StudioBenchmarkError: Ownership, metadata, or archive integrity fails.

        Returns:
            True when the path is the exact Package export content route.
        """
        segments = self._path_segments(path)
        if not (
            len(segments) == 9
            and segments[:3]
            == ("studio", "benchmark-authoring", "drafts")
            and segments[4] == "package-revisions"
            and segments[6] == "exports"
            and segments[8] == "content"
        ):
            return False
        if query:
            raise StudioBenchmarkValidationError(
                "benchmark.authoring.export_query_invalid",
                "Benchmark Package export content does not accept query fields",
            )
        package_export, stream = (
            self._require_benchmark_authoring_release_service().open_export(
                segments[3], segments[5], segments[7]
            )
        )
        self._send_binary(
            stream,
            content_type=package_export.archive_media_type,
            content_length=package_export.size,
            disposition=f'attachment; filename="{package_export.filename}"',
            head_only=head_only,
            digest=package_export.sha256,
        )
        return True

    def _handle_head(
        self,
        path: str,
        query: Mapping[str, list[str]],
    ) -> None:
        """Handle HEAD only for exact managed Benchmark content routes.

        Args:
            path: Normalized Studio request path.
            query: Parsed query parameters.

        Raises:
            StudioBenchmarkError: Managed content cannot be opened safely.

        Returns:
            None.
        """
        if self._handle_authoring_export_content(
            path,
            query,
            head_only=True,
        ):
            return
        if self._handle_authoring_content_read(
            path,
            query,
            head_only=True,
        ):
            return
        if self._handle_benchmark_content(path, head_only=True):
            return
        self._send_json(
            _error_payload(
                "studio.http.method_not_allowed",
                "HTTP method is not supported for this resource",
            ),
            405,
        )

    def _handle_get(
        self,
        path: str,
        query: Mapping[str, list[str]],
    ) -> None:
        """Handle read-only Catalog, Agent, and compatibility routes.

        Args:
            path (str): Parsed URL path.
            query (Mapping[str, list[str]]): Parsed query parameters.

        Raises:
            KeyError: Template is absent.
            AgentNotFoundError: Agent is absent.
            AgentRevisionNotFoundError: Revision is absent.
            ValueError: Pagination is invalid.

        Returns:
            None.
        """
        service = self.studio_server.application_service
        segments = self._path_segments(path)
        if path == "/studio/runtime-readiness":
            if query:
                raise StudioRunValidationError(
                    "studio.readiness.query_invalid",
                    "Runtime readiness does not accept query fields",
                )
            composition = self.studio_server.run_composition
            if composition is None:
                raise StudioRunNotFoundError(
                    "studio.readiness.unavailable",
                    "Studio runtime readiness service is not configured",
                )
            result = composition.readiness.process_readiness()
            self._send_json(
                result.model_dump(mode="json", by_alias=True, exclude_none=True),
                private=True,
            )
            return
        if (
            len(segments) == 6
            and segments[:2] == ("studio", "agents")
            and segments[3] == "revisions"
            and segments[5] == "run-readiness"
        ):
            values = query.get("deviceProfileId") or []
            if len(values) != 1 or len(query) != 1:
                raise StudioRunValidationError(
                    "studio.readiness.profile_required",
                    "Exact run readiness requires one Device Profile identity",
                )
            composition = self.studio_server.run_composition
            if composition is None:
                raise StudioRunNotFoundError(
                    "studio.readiness.unavailable",
                    "Studio runtime readiness service is not configured",
                )
            result = composition.readiness.revision_readiness(
                segments[2],
                segments[4],
                values[0],
            )
            self._send_json(
                result.model_dump(mode="json", by_alias=True, exclude_none=True),
                private=True,
            )
            return
        if self._handle_authoring_export_content(
            path,
            query,
            head_only=False,
        ):
            return
        if self._handle_authoring_content_read(
            path,
            query,
            head_only=False,
        ):
            return
        if self._handle_benchmark_content(path, head_only=False):
            return
        if path == "/studio/benchmark-authoring/contract-test-profiles":
            if query:
                raise StudioBenchmarkValidationError(
                    "benchmark.authoring.contract_test_profile_query_invalid",
                    "Benchmark Contract Test profiles do not accept query fields",
                )
            page = (
                self._require_benchmark_authoring_contract_test_service()
                .list_profiles()
            )
            self._send_json(
                page.model_dump(
                    mode="json",
                    by_alias=True,
                    exclude_none=True,
                ),
                private=True,
            )
            return
        if path == "/studio/benchmark-authoring/drafts":
            limit, cursor = self._benchmark_page_query(
                query,
                resource="authoring",
            )
            page = self._require_benchmark_authoring_service().list_drafts(
                limit=limit,
                cursor=cursor,
            )
            self._send_json(
                page.model_dump(
                    mode="json",
                    by_alias=True,
                    exclude_none=True,
                )
            )
            return
        if (
            len(segments) == 5
            and segments[:3]
            == ("studio", "benchmark-authoring", "drafts")
            and segments[4] == "package-revisions"
        ):
            limit, cursor = self._benchmark_page_query(
                query,
                resource="package_revision",
            )
            page = (
                self._require_benchmark_authoring_release_service()
                .list_package_revisions(
                    segments[3],
                    limit=limit,
                    cursor=cursor,
                )
            )
            self._send_json(
                page.model_dump(
                    mode="json",
                    by_alias=True,
                    exclude_none=True,
                ),
                private=True,
            )
            return
        if (
            len(segments) == 6
            and segments[:3]
            == ("studio", "benchmark-authoring", "drafts")
            and segments[4] == "package-revisions"
        ):
            if query:
                raise StudioBenchmarkValidationError(
                    "benchmark.authoring.freeze_query_invalid",
                    "Benchmark PackageRevision detail does not accept query fields",
                )
            detail = (
                self._require_benchmark_authoring_freeze_service()
                .get_package_revision(segments[3], segments[5])
            )
            self._send_json(
                detail.model_dump(
                    mode="json",
                    by_alias=True,
                    exclude_none=True,
                ),
                private=True,
            )
            return
        if (
            len(segments) == 8
            and segments[:3]
            == ("studio", "benchmark-authoring", "drafts")
            and segments[4] == "package-revisions"
            and segments[6] in {"publications", "exports"}
        ):
            if query:
                raise StudioBenchmarkValidationError(
                    "benchmark.authoring.release_query_invalid",
                    "Benchmark Package release detail does not accept query fields",
                )
            release = self._require_benchmark_authoring_release_service()
            result = (
                release.get_publication(
                    segments[3], segments[5], segments[7]
                )
                if segments[6] == "publications"
                else release.get_export(
                    segments[3], segments[5], segments[7]
                )
            )
            self._send_json(
                result.model_dump(
                    mode="json",
                    by_alias=True,
                    exclude_none=True,
                ),
                private=True,
            )
            return
        if (
            len(segments) == 6
            and segments[:3]
            == ("studio", "benchmark-authoring", "drafts")
            and segments[4] == "revisions"
        ):
            if query:
                raise StudioBenchmarkValidationError(
                    "benchmark.authoring.query_invalid",
                    "Benchmark authoring detail query is invalid",
                )
            revision = (
                self._require_benchmark_authoring_service().get_revision(
                    segments[3],
                    segments[5],
                )
            )
            self._send_json(
                revision.model_dump(
                    mode="json",
                    by_alias=True,
                    exclude_none=True,
                )
            )
            return
        if (
            len(segments) == 4
            and segments[:3]
            == ("studio", "benchmark-authoring", "drafts")
        ):
            if query:
                raise StudioBenchmarkValidationError(
                    "benchmark.authoring.query_invalid",
                    "Benchmark authoring detail query is invalid",
                )
            detail = self._require_benchmark_authoring_service().get_draft(
                segments[3]
            )
            self._send_json(
                detail.model_dump(
                    mode="json",
                    by_alias=True,
                    exclude_none=True,
                )
            )
            return
        if path == "/studio/benchmark-experiments":
            limit, cursor, filters = (
                self._benchmark_experiment_history_query(query)
            )
            page = (
                self._require_benchmark_experiment_service().list_experiments(
                    limit=limit,
                    cursor=cursor,
                    filters=filters,
                )
            )
            self._send_json(
                page.model_dump(
                    mode="json",
                    by_alias=True,
                    exclude_none=True,
                )
            )
            return
        if (
            len(segments) == 4
            and segments[:2] == ("studio", "benchmark-experiments")
            and segments[3] == "artifacts"
        ):
            limit, cursor = self._benchmark_page_query(
                query,
                resource="artifact",
            )
            page = (
                self._require_benchmark_experiment_service()
                .list_artifact_inventory(
                    segments[2],
                    limit=limit,
                    cursor=cursor,
                )
            )
            self._send_json(
                page.model_dump(
                    mode="json",
                    by_alias=True,
                    exclude_none=True,
                )
            )
            return
        if (
            len(segments) == 6
            and segments[:2] == ("studio", "benchmark-experiments")
            and segments[3] == "task-runs"
            and segments[5] == "artifacts"
        ):
            experiment_id = (
                self._require_benchmark_experiment_service()
                .validate_experiment_id(segments[2])
            )
            task_run_id = (
                self._require_benchmark_experiment_service()
                .validate_task_run_id(segments[4])
            )
            composition = self.studio_server.benchmark_composition
            if composition is None or composition.publications is None:
                raise StudioBenchmarkNotFoundError(
                    "benchmark.publication.unavailable",
                    "Benchmark publication service is not configured",
                )
            records = composition.publications.list_artifacts(
                experiment_id,
                task_run_id=task_run_id,
            )
            self._send_json(
                {
                    "schemaVersion": 1,
                    "experimentId": experiment_id,
                    "taskRunId": task_run_id,
                    "items": [
                        record.descriptor.model_dump(
                            mode="json",
                            by_alias=True,
                            exclude_none=True,
                        )
                        for record in records
                    ],
                }
            )
            return
        if (
            len(segments) == 5
            and segments[:2] == ("studio", "benchmark-experiments")
            and segments[3] == "task-runs"
        ):
            task_run = self._require_benchmark_experiment_service().get_task_run(
                segments[2],
                segments[4],
            )
            self._send_json(
                task_run.model_dump(
                    mode="json",
                    by_alias=True,
                    exclude_none=True,
                )
            )
            return
        if (
            len(segments) == 5
            and segments[:2] == ("studio", "benchmark-experiments")
            and segments[3:] == ("events", "stream")
        ):
            experiment_id = (
                self._require_benchmark_experiment_service()
                .validate_experiment_id(segments[2])
            )
            self._send_benchmark_events_sse(experiment_id, query)
            return
        if (
            len(segments) == 4
            and segments[:2] == ("studio", "benchmark-experiments")
            and segments[3] == "events"
        ):
            experiment_id = (
                self._require_benchmark_experiment_service()
                .validate_experiment_id(segments[2])
            )
            after_values = query.get("after") or ["0"]
            limit_values = query.get("limit") or ["100"]
            if len(after_values) != 1 or len(limit_values) != 1:
                raise StudioBenchmarkValidationError(
                    "benchmark.event.cursor_invalid",
                    "Benchmark event cursor or limit is invalid",
                )
            try:
                after = int(after_values[0])
                limit = int(limit_values[0])
            except ValueError as error:
                raise StudioBenchmarkValidationError(
                    "benchmark.event.cursor_invalid",
                    "Benchmark event cursor or limit is invalid",
                ) from error
            page = self._require_benchmark_event_service().query(
                experiment_id,
                after=after,
                limit=limit,
            )
            self._send_json(
                page.model_dump(
                    mode="json",
                    by_alias=True,
                    exclude_none=True,
                )
            )
            return
        if (
            len(segments) == 4
            and segments[:2] == ("studio", "benchmark-experiments")
            and segments[3] == "task-runs"
        ):
            try:
                limit = int((query.get("limit") or ["50"])[0])
            except ValueError as error:
                raise StudioBenchmarkValidationError(
                    "benchmark.task_run.limit_invalid",
                    "Benchmark TaskRun page limit is invalid",
                ) from error
            page = (
                self._require_benchmark_experiment_service().list_task_runs(
                    segments[2],
                    limit=limit,
                    cursor=(query.get("cursor") or [None])[0],
                )
            )
            self._send_json(
                page.model_dump(
                    mode="json",
                    by_alias=True,
                    exclude_none=True,
                )
            )
            return
        if (
            len(segments) == 3
            and segments[:2] == ("studio", "benchmark-experiments")
        ):
            experiment = (
                self._require_benchmark_experiment_service().get_experiment(
                    segments[2]
                )
            )
            self._send_json(
                experiment.model_dump(
                    mode="json",
                    by_alias=True,
                    exclude_none=True,
                )
            )
            return
        if path == "/studio/benchmarks":
            try:
                limit = int((query.get("limit") or ["50"])[0])
            except ValueError as error:
                raise StudioBenchmarkValidationError(
                    "benchmark.catalog.limit_invalid",
                    "Benchmark page limit is invalid",
                ) from error
            page = self._require_benchmark_service().catalog.list_entries(
                limit=limit,
                cursor=(query.get("cursor") or [None])[0],
                query=(query.get("query") or [""])[0],
                platform=(query.get("platform") or [""])[0],
                source_kind=(query.get("sourceKind") or [""])[0],
            )
            self._send_json(
                page.model_dump(
                    mode="json",
                    by_alias=True,
                    exclude_none=True,
                )
            )
            return
        if path == "/studio/device-profiles":
            composition = self.studio_server.run_composition
            if composition is not None:
                result = composition.readiness.process_readiness()
                self._send_json(
                    {
                        "schemaVersion": 1,
                        "items": [
                            item.model_dump(
                                mode="json", by_alias=True, exclude_none=True
                            )
                            for item in result.device_profiles
                        ],
                    }
                )
            else:
                page = self._require_benchmark_service().device_profiles()
                self._send_json(
                    page.model_dump(
                        mode="json",
                        by_alias=True,
                        exclude_none=True,
                    )
                )
            return
        if (
            len(segments) == 4
            and segments[:2] == ("studio", "benchmarks")
            and segments[3] == "tasks"
        ):
            split = (query.get("split") or [""])[0]
            try:
                limit = int((query.get("limit") or ["50"])[0])
            except ValueError as error:
                raise StudioBenchmarkValidationError(
                    "benchmark.catalog.limit_invalid",
                    "Benchmark task page limit is invalid",
                ) from error
            page = self._require_benchmark_service().catalog.list_tasks(
                segments[2],
                split=split,
                limit=limit,
                cursor=(query.get("cursor") or [None])[0],
            )
            self._send_json(
                page.model_dump(
                    mode="json",
                    by_alias=True,
                    exclude_none=True,
                )
            )
            return
        if len(segments) == 3 and segments[:2] == ("studio", "benchmarks"):
            detail = self._require_benchmark_service().catalog.detail(segments[2])
            self._send_json(
                detail.model_dump(
                    mode="json",
                    by_alias=True,
                    exclude_none=True,
                )
            )
            return
        if (
            len(segments) == 5
            and segments[:2] == ("studio", "runs")
            and segments[3:] == ("events", "stream")
        ):
            run_id = self._validate_run_id(segments[2])
            self._send_run_events_sse(run_id, query)
            return
        if (
            len(segments) == 4
            and segments[:2] == ("studio", "runs")
            and segments[3] == "events"
        ):
            run_id = self._validate_run_id(segments[2])
            try:
                after = int((query.get("after") or ["0"])[0])
                limit = int((query.get("limit") or ["100"])[0])
            except ValueError as error:
                raise StudioRunValidationError(
                    "studio.run.event_cursor_invalid",
                    "Run event cursor or limit is invalid",
                ) from error
            page = self._require_run_service().query_events(
                run_id,
                after=after,
                limit=limit,
            )
            self._send_json(
                page.model_dump(
                    mode="json",
                    by_alias=True,
                    exclude_none=True,
                )
            )
            return
        if (
            len(segments) == 5
            and segments[:2] == ("studio", "runs")
            and segments[3] == "artifacts"
        ):
            run_id = self._validate_run_id(segments[2])
            artifact_id = self._validate_artifact_id(segments[4])
            descriptor, stream = self._require_run_artifacts().open_artifact(
                run_id,
                artifact_id,
            )
            self._send_binary(
                stream,
                content_type=descriptor.content_type,
                content_length=descriptor.size,
                disposition=f'inline; filename="{descriptor.artifact_id}"',
            )
            return
        if len(segments) == 3 and segments[:2] == ("studio", "runs"):
            resource = self._require_run_service().get_run(
                self._validate_run_id(segments[2])
            )
            self._send_json(
                resource.model_dump(
                    mode="json",
                    by_alias=True,
                    exclude_none=True,
                )
            )
            return
        if path == "/studio/replays":
            limit = int((query.get("limit") or ["50"])[0])
            cursor = (query.get("cursor") or [None])[0]
            agent_id = (query.get("agentId") or [None])[0]
            if agent_id is not None and (
                re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}", agent_id) is None
            ):
                raise ValueError("Replay Agent filter is invalid")
            page = service.list_replays(
                limit=limit,
                cursor=cursor,
                agent_id=agent_id,
            )
            self._send_json(
                {
                    "schemaVersion": 1,
                    "items": [
                        item.model_dump(
                            mode="json",
                            by_alias=True,
                            exclude_none=True,
                        )
                        for item in page.items
                    ],
                    "nextCursor": page.next_cursor,
                }
            )
            return
        if (
            len(segments) == 5
            and segments[:2] == ("studio", "replays")
            and segments[3] == "artifacts"
        ):
            descriptor, stream = service.open_replay_artifact(
                segments[2],
                segments[4],
            )
            self._send_binary(
                stream,
                content_type=descriptor.content_type,
                content_length=descriptor.size,
                disposition=f'inline; filename="{descriptor.artifact_id}"',
            )
            return
        if (
            len(segments) == 4
            and segments[:2] == ("studio", "replays")
            and segments[3] == "bundle"
        ):
            bundle = service.export_replay_bundle(segments[2])
            stream = bundle.open("rb")
            self._send_binary(
                stream,
                content_type="application/zip",
                content_length=bundle.stat().st_size,
                disposition=f'attachment; filename="{segments[2]}.replay.zip"',
            )
            return
        if len(segments) == 3 and segments[:2] == ("studio", "replays"):
            envelope = service.get_replay(segments[2])
            self._send_json(
                envelope.model_dump(
                    mode="json",
                    by_alias=True,
                    exclude_none=True,
                )
            )
            return
        if path == "/studio/components/catalog":
            self._send_json(service.catalog.to_safe_dict())
            return
        if path == "/studio/agents":
            limit = int((query.get("limit") or ["50"])[0])
            cursor = (query.get("cursor") or [None])[0]
            page = service.list_agents(limit=limit, cursor=cursor)
            self._send_json(
                {
                    "schemaVersion": 1,
                    "items": [
                        agent_record_payload(item) for item in page.items
                    ],
                    "nextCursor": page.next_cursor,
                }
            )
            return
        if len(segments) == 3 and segments[:2] == ("studio", "agents"):
            agent, revision = service.get_agent(segments[2])
            self._send_json(
                {
                    "schemaVersion": 1,
                    "agent": agent_record_payload(agent),
                    "currentRevision": (
                        revision_record_payload(revision)
                        if revision is not None
                        else None
                    ),
                }
            )
            return
        if (
            len(segments) == 5
            and segments[:2] == ("studio", "agents")
            and segments[3] == "revisions"
        ):
            revision = service.get_revision(segments[2], segments[4])
            self._send_json(
                {
                    "schemaVersion": 1,
                    "revision": revision_record_payload(revision),
                }
            )
            return
        if path == "/studio/nav-modules":
            self._send_json(
                {
                    "modules": [
                        {
                            "id": "builder",
                            "name": "Agent 构建",
                            "iconKey": "bot",
                            "order": 10,
                            "path": "/builder",
                            "allowed": True,
                        },
                        {
                            "id": "benchmark",
                            "name": "试车场",
                            "iconKey": "lineChart",
                            "order": 20,
                            "path": "/benchmarks",
                            "allowed": True,
                        },
                        {
                            "id": "history",
                            "name": "历史",
                            "iconKey": "history",
                            "order": 30,
                            "path": "/history",
                            "allowed": True,
                        },
                        {
                            "id": "settings",
                            "name": "设置",
                            "iconKey": "settings",
                            "order": 40,
                            "path": "/settings",
                            "allowed": True,
                        },
                    ]
                }
            )
            return
        if path == "/studio/module-config":
            module_id = (query.get("moduleId") or ["unknown"])[0]
            self._send_json(
                {
                    "moduleId": module_id,
                    "permission": "allow",
                    "sidebarItems": [],
                }
            )
            return
        if path == "/studio/builder/flows":
            self._send_json({"flows": []})
            return
        if path == "/studio/builder/agent-registry":
            self._send_json(build_agent_registry_payload())
            return
        if path == "/studio/flow-templates":
            self._send_json(
                {
                    "templates": [
                        {
                            "id": item.template_id,
                            "name": item.name,
                            "description": item.description,
                        }
                        for item in list_flow_templates()
                    ]
                }
            )
            return
        if (
            len(segments) == 4
            and segments[:2] == ("studio", "flow-templates")
            and segments[3] == "document"
        ):
            self._send_json(get_flow_template_document(segments[2]))
            return
        self._send_json(
            _error_payload(
                "studio.resource.not_found",
                "Requested Studio resource was not found",
            ),
            404,
        )

    def _handle_post(
        self,
        path: str,
        query: Mapping[str, list[str]],
    ) -> None:
        """Handle compile, Agent create, and revision save routes.

        Args:
            path (str): Parsed URL path.
            query: Parsed query parameters for binary authoring commands.

        Raises:
            StudioApplicationError: Request envelope is invalid.
            AgentRevisionConflictError: Save base is stale.
            AgentNotFoundError: Agent is absent.

        Returns:
            None.
        """
        if self._handle_authoring_content_command(path, query):
            return
        service = self.studio_server.application_service
        payload = self._read_json()
        self._require_schema_version(payload)
        segments = self._path_segments(path)
        if path in {
            "/studio/benchmark-authoring/legacy-migrations/preview",
            "/studio/benchmark-authoring/legacy-migrations/confirm",
        }:
            if query:
                raise StudioBenchmarkValidationError(
                    "benchmark.migration.query_invalid",
                    "Benchmark legacy migration does not accept query fields",
                )
            migration = self._require_benchmark_authoring_migration_service()
            if path.endswith("/preview"):
                request = migration.parse_preview_request(payload)
                result = migration.preview(request)
                status = 200
            else:
                request = migration.parse_confirm_request(payload)
                result = migration.confirm(request)
                status = 201 if result.created else 200
            self._send_json(
                result.model_dump(
                    mode="json",
                    by_alias=True,
                    exclude_none=True,
                ),
                status,
                private=True,
            )
            return
        if (
            len(segments) == 7
            and segments[:3]
            == ("studio", "benchmark-authoring", "drafts")
            and segments[4] == "package-revisions"
            and segments[6] in {"publications", "exports"}
        ):
            if query:
                raise StudioBenchmarkValidationError(
                    "benchmark.authoring.release_query_invalid",
                    "Benchmark Package release commands do not accept query fields",
                )
            release = self._require_benchmark_authoring_release_service()
            request = release.parse_command(payload)
            result = (
                release.publish(segments[3], segments[5], request)
                if segments[6] == "publications"
                else release.export_package(segments[3], segments[5], request)
            )
            self._send_json(
                result.model_dump(
                    mode="json",
                    by_alias=True,
                    exclude_none=True,
                ),
                201 if result.created else 200,
                private=True,
            )
            return
        if (
            len(segments) == 5
            and segments[:3]
            == ("studio", "benchmark-authoring", "drafts")
            and segments[4] == "package-revisions"
        ):
            if query:
                raise StudioBenchmarkValidationError(
                    "benchmark.authoring.freeze_query_invalid",
                    "Benchmark validated freeze does not accept query fields",
                )
            freeze_service = (
                self._require_benchmark_authoring_freeze_service()
            )
            request = freeze_service.parse_request(payload)
            result = freeze_service.freeze(segments[3], request)
            self._send_json(
                result.model_dump(
                    mode="json",
                    by_alias=True,
                    exclude_none=True,
                ),
                201 if result.created else 200,
                private=True,
            )
            return
        if (
            len(segments) == 5
            and segments[:3]
            == ("studio", "benchmark-authoring", "drafts")
            and segments[4] in {"validate", "dry-run"}
        ):
            if query:
                raise StudioBenchmarkValidationError(
                    "benchmark.authoring.analysis_query_invalid",
                    "Benchmark authoring analysis does not accept query fields",
                )
            analysis = self._require_benchmark_authoring_analysis_service()
            if segments[4] == "validate":
                request = analysis.parse_validation_request(payload)
                result = analysis.validate(segments[3], request)
            else:
                request = analysis.parse_dry_run_request(payload)
                result = analysis.dry_run(segments[3], request)
            self._send_json(
                result.model_dump(
                    mode="json",
                    by_alias=True,
                    exclude_none=True,
                ),
                private=True,
            )
            return
        if (
            len(segments) == 5
            and segments[:3]
            == ("studio", "benchmark-authoring", "drafts")
            and segments[4] == "contract-tests"
        ):
            if query:
                raise StudioBenchmarkValidationError(
                    "benchmark.authoring.contract_test_query_invalid",
                    "Benchmark Contract Tests do not accept query fields",
                )
            contract_tests = (
                self._require_benchmark_authoring_contract_test_service()
            )
            request = contract_tests.parse_request(payload)
            result = contract_tests.run(segments[3], request)
            self._send_json(
                result.model_dump(
                    mode="json",
                    by_alias=True,
                    exclude_none=True,
                ),
                private=True,
            )
            return
        if path == "/studio/benchmark-authoring/drafts":
            result = (
                self._require_benchmark_authoring_service().create_draft(
                    payload
                )
            )
            self._send_json(
                result.model_dump(
                    mode="json",
                    by_alias=True,
                    exclude_none=True,
                ),
                201 if result.created else 200,
            )
            return
        if (
            len(segments) == 5
            and segments[:3]
            == ("studio", "benchmark-authoring", "drafts")
            and segments[4] == "revisions"
        ):
            result = (
                self._require_benchmark_authoring_service().save_revision(
                    segments[3],
                    payload,
                )
            )
            self._send_json(
                result.model_dump(
                    mode="json",
                    by_alias=True,
                    exclude_none=True,
                ),
                201 if result.created else 200,
            )
            return
        if path == "/studio/benchmark-experiments":
            result = (
                self._require_benchmark_experiment_service().create_experiment(
                    payload
                )
            )
            self._send_json(
                result.model_dump(
                    mode="json",
                    by_alias=True,
                    exclude_none=True,
                ),
                202,
            )
            return
        if (
            len(segments) == 4
            and segments[:2] == ("studio", "benchmark-experiments")
            and segments[3] == "cancel"
        ):
            experiment = (
                self._require_benchmark_experiment_service().cancel_experiment(
                    segments[2],
                    payload,
                )
            )
            self._send_json(
                experiment.model_dump(
                    mode="json",
                    by_alias=True,
                    exclude_none=True,
                ),
                202,
            )
            return
        if path == "/studio/benchmark-experiments/preview":
            preview = self._require_benchmark_service().preview(payload)
            self._send_json(
                preview.model_dump(
                    mode="json",
                    by_alias=True,
                    exclude_none=True,
                )
            )
            return
        if (
            len(segments) == 4
            and segments[:2] == ("studio", "benchmarks")
            and segments[3] == "validate"
        ):
            unknown = set(payload) - {"schemaVersion", "split"}
            if unknown:
                raise StudioBenchmarkValidationError(
                    "benchmark.validation.request_invalid",
                    "Benchmark validation request contains unknown fields",
                )
            split = payload.get("split")
            if split is not None and not isinstance(split, str):
                raise StudioBenchmarkValidationError(
                    "benchmark.validation.request_invalid",
                    "Benchmark validation split must be a string or null",
                )
            result = self._require_benchmark_service().catalog.validate_entry(
                segments[2],
                split=split,
            )
            self._send_json(
                result.model_dump(
                    mode="json",
                    by_alias=True,
                    exclude_none=True,
                )
            )
            return
        if path == "/studio/runs":
            resource, created = self._require_run_service().create_run(payload)
            response = resource.model_dump(
                mode="json",
                by_alias=True,
                exclude_none=True,
            )
            response["created"] = created
            self._send_json(response, 202)
            return
        if (
            len(segments) == 4
            and segments[:2] == ("studio", "runs")
            and segments[3] == "cancel"
        ):
            resource = self._require_run_service().cancel_run(
                self._validate_run_id(segments[2])
            )
            self._send_json(
                resource.model_dump(
                    mode="json",
                    by_alias=True,
                    exclude_none=True,
                ),
                202,
            )
            return
        if path == "/studio/agent-graphs/compile":
            document = payload.get("document")
            if not isinstance(document, Mapping):
                raise StudioApplicationError(
                    "studio.compile.document_required",
                    "Compile request requires a document object",
                )
            expected = payload.get("catalogVersion")
            if expected is not None and not isinstance(expected, str):
                raise StudioApplicationError(
                    "studio.compile.catalog_version_invalid",
                    "catalogVersion must be a string",
                )
            self._send_json(
                service.compile_response(
                    document,
                    expected_catalog_version=expected,
                )
            )
            return
        if path == "/studio/flow-documents/migrate":
            document = payload.get("document")
            if not isinstance(document, Mapping):
                raise StudioApplicationError(
                    "studio.migration.document_required",
                    "Migration request requires a document object",
                )
            agent_id = payload.get("agentId")
            if agent_id is not None and not isinstance(agent_id, str):
                raise StudioApplicationError(
                    "studio.migration.agent_id_invalid",
                    "agentId must be a string",
                )
            result = service.migrate_document(document, agent_id=agent_id)
            self._send_json(
                {
                    "schemaVersion": 1,
                    **result.to_safe_dict(),
                }
            )
            return
        if path == "/studio/agents":
            name = payload.get("name")
            if not isinstance(name, str):
                raise StudioApplicationError(
                    "studio.agent.name_required",
                    "Create Agent request requires a name",
                )
            initial = payload.get("initialDocument")
            if initial is not None and not isinstance(initial, Mapping):
                raise StudioApplicationError(
                    "studio.agent.document_invalid",
                    "initialDocument must be an object",
                )
            agent, revision = service.create_agent(
                name,
                initial_document=initial,
            )
            self._send_json(
                {
                    "schemaVersion": 1,
                    "agent": agent_record_payload(agent),
                    "currentRevision": revision_record_payload(revision),
                },
                201,
            )
            return
        if (
            len(segments) == 4
            and segments[:2] == ("studio", "agents")
            and segments[3] == "revisions"
        ):
            document = payload.get("document")
            if not isinstance(document, Mapping):
                raise StudioApplicationError(
                    "studio.revision.document_required",
                    "Save revision request requires a document object",
                )
            base_revision_id = payload.get("baseRevisionId")
            if base_revision_id is not None and not isinstance(
                base_revision_id,
                str,
            ):
                raise StudioApplicationError(
                    "studio.revision.base_invalid",
                    "baseRevisionId must be a string or null",
                )
            agent, revision = service.save_revision(
                segments[2],
                base_revision_id=base_revision_id,
                raw_document=document,
            )
            self._send_json(
                {
                    "schemaVersion": 1,
                    "agent": agent_record_payload(agent),
                    "revision": revision_record_payload(revision),
                },
                201,
            )
            return
        self._send_json(
            _error_payload(
                "studio.resource.not_found",
                "Requested Studio resource was not found",
            ),
            404,
        )

    def _handle_patch(self, path: str) -> None:
        """Handle Agent metadata updates.

        Args:
            path (str): Parsed URL path.

        Raises:
            StudioApplicationError: Request envelope is invalid.
            AgentNotFoundError: Agent is absent.

        Returns:
            None.
        """
        payload = self._read_json()
        self._require_schema_version(payload)
        segments = self._path_segments(path)
        if len(segments) == 3 and segments[:2] == ("studio", "agents"):
            name = payload.get("name")
            if not isinstance(name, str):
                raise StudioApplicationError(
                    "studio.agent.name_required",
                    "Rename Agent request requires a name",
                )
            agent = self.studio_server.application_service.rename_agent(
                segments[2],
                name,
            )
            self._send_json(
                {
                    "schemaVersion": 1,
                    "agent": agent_record_payload(agent),
                }
            )
            return
        self._send_json(
            _error_payload(
                "studio.resource.not_found",
                "Requested Studio resource was not found",
            ),
            404,
        )


def create_http_server(
    host: str,
    port: int,
    *,
    application_service: StudioApplicationService,
    allowed_origins: frozenset[str] = _DEFAULT_ALLOWED_ORIGINS,
    run_composition: StudioRunComposition | None = None,
    benchmark_composition: StudioBenchmarkComposition | None = None,
    sse_heartbeat_seconds: float = 15.0,
    sse_write_timeout_seconds: float = 20.0,
    benchmark_sse_max_connections: int = 32,
) -> StudioHTTPServer:
    """Create a configured HTTP server without starting its loop.

    Args:
        host (str): Bind host.
        port (int): Bind port; zero requests an ephemeral test port.
        application_service (StudioApplicationService): Explicit application
            boundary.
        allowed_origins (frozenset[str]): Browser origin allowlist.
        run_composition (StudioRunComposition | None): Optional shared Stage 3
            Run dependencies.
        benchmark_composition (StudioBenchmarkComposition | None):
            Optional shared Stage 5.1 definition dependencies.
        sse_heartbeat_seconds (float): Empty-stream heartbeat interval.
        sse_write_timeout_seconds (float): Per-connection socket timeout.
        benchmark_sse_max_connections (int): Maximum concurrent Benchmark
            Experiment SSE connections.

    Raises:
        ValueError: An SSE timeout is outside its bounded range.
        OSError: Socket binding fails.

    Returns:
        StudioHTTPServer: Configured server.
    """
    allowed_hosts = frozenset(
        {
            "127.0.0.1",
            "localhost",
            "::1",
            host.lower(),
        }
    )
    return StudioHTTPServer(
        (host, port),
        StudioHTTPRequestHandler,
        application_service=application_service,
        allowed_origins=allowed_origins,
        allowed_hosts=allowed_hosts,
        run_composition=run_composition,
        benchmark_composition=benchmark_composition,
        sse_heartbeat_seconds=sse_heartbeat_seconds,
        sse_write_timeout_seconds=sse_write_timeout_seconds,
        benchmark_sse_max_connections=benchmark_sse_max_connections,
    )


def run_httpd(
    host: str = "127.0.0.1",
    port: int = 8765,
    *,
    workspace: str | Path | None = None,
    database_path: str | Path | None = None,
    benchmark_package_dirs: tuple[str | Path, ...] = (),
    benchmark_catalog_roots: tuple[str | Path, ...] = (),
    include_installed_benchmarks: bool = True,
    device_profiles: AndroidDeviceProfileResolver | None = None,
    secret_provider: Mapping[str, Any] | None = None,
) -> None:
    """Run the default local SQLite-backed Studio HTTP service.

    Args:
        host (str): Bind host.
        port (int): Bind port.
        workspace (str | Path | None): Workspace used for opaque database
            isolation; defaults to the current directory.
        database_path (str | Path | None): Explicit storage override.
        benchmark_package_dirs (tuple[str | Path, ...]): Explicit Package roots.
        benchmark_catalog_roots (tuple[str | Path, ...]): Explicit Catalog roots.
        include_installed_benchmarks (bool): Discover installed metadata.
        device_profiles (AndroidDeviceProfileResolver | None): Already-loaded
            trusted static profile authority; omitted means an empty directory.
        secret_provider (Mapping[str, Any] | None): Process-scoped trusted
            SecretRef values; never serialized or persisted.

    Raises:
        OSError: Database or socket setup fails.
        sqlite3.Error: Database migration fails.

    Returns:
        None.
    """
    workspace_path = Path(workspace or Path.cwd())
    resolved_database = (
        Path(database_path)
        if database_path is not None
        else default_studio_database_path(workspace_path)
    )
    catalog = build_studio_component_catalog()
    agents = SQLiteAgentDocumentRepository(resolved_database)
    replay_service = build_default_replay_service(resolved_database)
    profiles = device_profiles or AndroidDeviceProfileResolver()
    components = ProductionComponentResolverFactory(
        secret_provider=secret_provider or {},
    )
    device_leases = DeviceLeaseRegistry()
    service = StudioApplicationService(
        catalog=catalog,
        repository=agents,
        replay_service=replay_service,
    )
    run_composition = build_default_studio_run_composition(
        resolved_database,
        agents=agents,
        replay_service=replay_service,
        contract_catalog=catalog.node_contract_catalog(),
        profiles=profiles,
        leases=device_leases,
        components=components,
        component_catalog=catalog,
        runtime_secrets=secret_provider,
    )
    benchmark_composition = build_default_studio_benchmark_composition(
        workspace_path,
        agents=agents,
        profiles=profiles,
        contract_catalog=catalog.node_contract_catalog(),
        component_catalog=catalog,
        package_dirs=benchmark_package_dirs,
        catalog_roots=benchmark_catalog_roots,
        include_installed=include_installed_benchmarks,
        database_path=resolved_database,
        leases=device_leases,
        component_resolvers=components,
    )
    server = create_http_server(
        host,
        port,
        application_service=service,
        run_composition=run_composition,
        benchmark_composition=benchmark_composition,
    )
    logger.info("ZhiXing Studio HTTP listening on http://%s:%s", host, port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down Studio HTTP")
    finally:
        server.server_close()
__all__ = [
    "StudioHTTPRequestHandler",
    "StudioHTTPServer",
    "create_http_server",
    "run_httpd",
]
