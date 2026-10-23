"""Application services for Studio Catalog, compilation, and Agent revisions."""

from __future__ import annotations

import uuid
from copy import deepcopy
from pathlib import Path
from typing import Any, BinaryIO, Mapping

from pydantic import ValidationError

from zhixing.graph import CompilationResult, compile_studio_flow_document

from .catalog import StudioComponentCatalog
from .migration import StudioMigrationResult, migrate_studio_flow_document
from .models import (
    STUDIO_CAPABILITY_AUTHORING_POLICY,
    STUDIO_CAPABILITY_LOWERING_PROFILE,
    StudioAuthoringDocument,
    parse_studio_authoring_document,
)
from .repository import (
    AgentDocumentRepository,
    AgentPage,
    AgentRecord,
    AgentRevisionRecord,
    CompileSnapshot,
)
from .replay_models import ReplayArtifactDescriptor, ReplayEvidenceEnvelope, ReplayPage
from .replay_service import ReplayApplicationService


class StudioApplicationError(ValueError):
    """Stable safe application-layer error."""

    def __init__(self, code: str, message: str) -> None:
        """Create one bounded application error.

        Args:
            code (str): Stable machine-readable code.
            message (str): Safe bounded explanation.

        Raises:
            None.

        Returns:
            None.
        """
        super().__init__(str(message).replace("\n", " ")[:500])
        self.code = code


class StudioApplicationService:
    """Orchestrate side-effect-free compilation and repository transactions."""

    def __init__(
        self,
        *,
        catalog: StudioComponentCatalog,
        repository: AgentDocumentRepository,
        replay_service: ReplayApplicationService | None = None,
    ) -> None:
        """Configure explicit Catalog and storage boundaries.

        Args:
            catalog (StudioComponentCatalog): Safe authoring Catalog.
            repository (AgentDocumentRepository): Database-neutral persistence.
            replay_service (ReplayApplicationService | None): Optional
                read-only Replay application boundary.

        Raises:
            ValueError: Catalog contracts conflict.

        Returns:
            None.
        """
        self._catalog = catalog
        self._repository = repository
        self._replay_service = replay_service
        self._contract_catalog = catalog.node_contract_catalog()

    def _require_replay_service(self) -> ReplayApplicationService:
        """Return the configured Replay boundary or a stable application error.

        Args:
            None.

        Raises:
            StudioApplicationError: Replay persistence is not configured.

        Returns:
            ReplayApplicationService: Configured Replay service.
        """
        if self._replay_service is None:
            raise StudioApplicationError(
                "studio.replay.unavailable",
                "Replay service is not configured",
            )
        return self._replay_service

    def list_replays(
        self,
        *,
        limit: int = 50,
        cursor: str | None = None,
        agent_id: str | None = None,
    ) -> ReplayPage:
        """List bounded persisted Replay summaries.

        Args:
            limit (int): Page size from 1 through 100.
            cursor (str | None): Optional opaque pagination cursor.
            agent_id (str | None): Optional exact Agent identity filter.

        Raises:
            StudioApplicationError: Replay service is unavailable.
            ValueError: Pagination is invalid.

        Returns:
            ReplayPage: Stable newest-first page.
        """
        return self._require_replay_service().list_replays(
            limit=limit,
            cursor=cursor,
            agent_id=agent_id,
        )

    def get_replay(self, run_id: str) -> ReplayEvidenceEnvelope:
        """Read one immutable Replay envelope.

        Args:
            run_id (str): Stable opaque run identity.

        Raises:
            StudioApplicationError: Replay service is unavailable.
            ReplayNotFoundError: Run is absent.

        Returns:
            ReplayEvidenceEnvelope: Persisted normalized evidence.
        """
        return self._require_replay_service().get_replay(run_id)

    def open_replay_artifact(
        self,
        run_id: str,
        artifact_id: str,
    ) -> tuple[ReplayArtifactDescriptor, BinaryIO]:
        """Open one verified replay-scoped artifact.

        Args:
            run_id (str): Owning run identity.
            artifact_id (str): Opaque artifact identity.

        Raises:
            StudioApplicationError: Replay service is unavailable.
            ReplayArtifactNotFoundError: Artifact pair is absent.
            ReplayImportError: Stored content fails safety checks.

        Returns:
            tuple[ReplayArtifactDescriptor, BinaryIO]: Metadata and stream.
        """
        return self._require_replay_service().open_artifact(run_id, artifact_id)

    def export_replay_bundle(self, run_id: str) -> Path:
        """Create one verified default Replay bundle.

        Args:
            run_id (str): Persisted run identity.

        Raises:
            StudioApplicationError: Replay service is unavailable.
            ReplayNotFoundError: Run is absent.
            ReplayImportError: Included content is corrupt.
            OSError: Bundle cannot be written.

        Returns:
            Path: Managed bundle path for immediate streaming.
        """
        return self._require_replay_service().export_bundle(run_id)

    @property
    def catalog(self) -> StudioComponentCatalog:
        """Return the immutable safe Component Catalog.

        Args:
            None.

        Raises:
            None.

        Returns:
            StudioComponentCatalog: Configured Catalog.
        """
        return self._catalog

    def compile_document(
        self,
        document: Mapping[str, Any],
        *,
        expected_catalog_version: str | None = None,
    ) -> CompilationResult:
        """Compile one schema 2 document without writing persistence.

        Args:
            document (Mapping[str, Any]): Raw Studio document mapping.
            expected_catalog_version (str | None): Client-observed Catalog
                identity.

        Raises:
            None: Structural and graph errors are returned as diagnostics.

        Returns:
            CompilationResult: Graph, diagnostics, and source map.
        """
        return compile_studio_flow_document(
            document,
            source_id="studio-api",
            contract_catalog=self._contract_catalog,
            component_catalog=self._catalog,
            expected_catalog_version=expected_catalog_version,
            catalog_version=self._catalog.catalog_version,
        )

    def compile_response(
        self,
        document: Mapping[str, Any],
        *,
        expected_catalog_version: str | None = None,
    ) -> dict[str, Any]:
        """Return the versioned safe HTTP compile response.

        Args:
            document (Mapping[str, Any]): Raw Studio document mapping.
            expected_catalog_version (str | None): Client-observed Catalog
                identity.

        Raises:
            None.

        Returns:
            dict[str, Any]: Versioned compile result.
        """
        result = self.compile_document(
            document,
            expected_catalog_version=expected_catalog_version,
        )
        graph = result.graph if result.is_success else None
        canonical_hash = (
            graph.canonical_hash(contract_catalog=self._contract_catalog)
            if graph is not None
            else None
        )
        return {
            "schemaVersion": 1,
            "isSuccess": result.is_success,
            "contractVersion": graph.contract_version if graph else "1.1",
            "catalogVersion": self._catalog.catalog_version,
            "canonicalHash": canonical_hash,
            "authoringPolicy": getattr(result, "authoring_policy", None),
            "loweringProfile": getattr(result, "lowering_profile", None),
            "capabilityHash": getattr(result, "capability_hash", None),
            "agentGraph": (
                graph.model_dump(mode="json", exclude_none=True)
                if graph is not None
                else None
            ),
            "diagnostics": [item.to_safe_dict() for item in result.diagnostics],
            "sourceMap": [
                item.model_dump(mode="json", exclude_none=True)
                for item in result.source_map
            ],
            "projectionMap": [
                item.model_dump(mode="json", by_alias=True, exclude_none=True)
                for item in getattr(result, "projection_map", ())
            ],
            "summary": {
                "errorCount": len(
                    [
                        item
                        for item in result.diagnostics
                        if item.severity.value == "error"
                    ]
                ),
                "warningCount": len(
                    [
                        item
                        for item in result.diagnostics
                        if item.severity.value == "warning"
                    ]
                ),
                "nodeCount": len(graph.nodes) if graph else 0,
                "edgeCount": len(graph.edges) if graph else 0,
            },
        }

    def migrate_document(
        self,
        document: Mapping[str, Any],
        *,
        agent_id: str | None = None,
    ) -> StudioMigrationResult:
        """Purely parse or migrate one Studio document without persistence.

        Args:
            document (Mapping[str, Any]): Schema 1 or schema 2 document.
            agent_id (str | None): Optional target Agent identity for legacy
                input.

        Raises:
            None: Migration failures are returned as diagnostics.

        Returns:
            StudioMigrationResult: Migrated document or safe diagnostics.
        """
        return migrate_studio_flow_document(
            document,
            source_id="studio-api-migration",
            agent_id=agent_id,
        )

    def _snapshot(self, result: CompilationResult) -> CompileSnapshot:
        """Convert a compiler result into persistence-safe evidence.

        Args:
            result (CompilationResult): Authoritative compile output.

        Raises:
            ValueError: Canonical identity cannot be computed for a reported
                valid graph.

        Returns:
            CompileSnapshot: Valid or invalid immutable snapshot.
        """
        if result.is_success and result.graph is not None:
            return CompileSnapshot(
                status="valid",
                diagnostics=result.diagnostics,
                source_map=result.source_map,
                agent_graph=result.graph.model_dump(
                    mode="json",
                    exclude_none=True,
                ),
                canonical_hash=result.graph.canonical_hash(
                    contract_catalog=self._contract_catalog
                ),
                authoring_policy=getattr(result, "authoring_policy", None),
                lowering_profile=getattr(result, "lowering_profile", None),
                capability_hash=getattr(result, "capability_hash", None),
                projection_map=getattr(result, "projection_map", ()),
            )
        return CompileSnapshot(
            status="invalid",
            diagnostics=result.diagnostics,
            source_map=result.source_map,
            authoring_policy=getattr(result, "authoring_policy", None),
            lowering_profile=getattr(result, "lowering_profile", None),
            capability_hash=getattr(result, "capability_hash", None),
            projection_map=getattr(result, "projection_map", ()),
        )

    @staticmethod
    def _parse_document(
        raw: Mapping[str, Any],
        *,
        agent_id: str | None = None,
        name: str | None = None,
        allow_identity_rebind: bool = False,
    ) -> StudioAuthoringDocument:
        """Strictly parse a schema-2 or schema-3 document before persistence.

        Args:
            raw (Mapping[str, Any]): Raw schema-2 or schema-3 mapping.
            agent_id (str | None): Expected or generated Agent identity.
            name (str | None): Optional created Agent name.
            allow_identity_rebind (bool): Whether create flow may replace the
                provisional Agent identity.

        Raises:
            StudioApplicationError: Structure or identity is invalid.

        Returns:
            StudioAuthoringDocument: Strict immutable document.
        """
        candidate = deepcopy(dict(raw))
        if allow_identity_rebind and agent_id is not None:
            candidate["agentId"] = agent_id
            candidate.setdefault("documentId", f"document-{uuid.uuid4().hex}")
            if name is not None:
                candidate["name"] = name
        try:
            document = parse_studio_authoring_document(candidate)
        except ValidationError as error:
            first = error.errors(include_url=False)[0]
            path = ".".join(str(item) for item in first["loc"])
            raise StudioApplicationError(
                "studio.document.invalid",
                f"Invalid Studio document at {path}: {first['msg']}",
            ) from error
        except ValueError as error:
            raise StudioApplicationError(
                "studio.document.invalid",
                f"Invalid Studio document: {error}",
            ) from error
        if agent_id is not None and document.agent_id != agent_id:
            raise StudioApplicationError(
                "studio.document.agent_mismatch",
                "Document agentId does not match the requested Agent",
            )
        return document

    def create_agent(
        self,
        name: str,
        *,
        initial_document: Mapping[str, Any] | None = None,
    ) -> tuple[AgentRecord, AgentRevisionRecord]:
        """Create an Agent with one initial valid or invalid revision.

        Args:
            name (str): Agent display name.
            initial_document (Mapping[str, Any] | None): Optional schema-3
                authoring document.

        Raises:
            StudioApplicationError: Document is structurally invalid.
            ValueError: Name is invalid.
            AgentDocumentRepositoryError: Persistence fails.

        Returns:
            tuple[AgentRecord, AgentRevisionRecord]: Created Agent and initial
            immutable revision.
        """
        agent_id = f"agent-{uuid.uuid4().hex}"
        raw = (
            deepcopy(dict(initial_document))
            if initial_document is not None
            else {
                "schemaVersion": 3,
                "contractVersion": "1.1",
                "authoringPolicy": STUDIO_CAPABILITY_AUTHORING_POLICY,
                "loweringProfile": STUDIO_CAPABILITY_LOWERING_PROFILE,
                "documentId": f"document-{uuid.uuid4().hex}",
                "agentId": agent_id,
                "name": name,
                "input": {
                    "canvasId": "input",
                    "logicalId": "input",
                    "kind": "input",
                },
                "output": {
                    "canvasId": "output",
                    "logicalId": "output",
                    "kind": "output",
                },
                "capabilities": [],
                "relations": [],
                "policies": {},
                "presentation": {
                    "nodes": {
                        "input": {"x": 0, "y": 0, "label": "Input"},
                        "output": {"x": 400, "y": 0, "label": "Output"},
                    },
                    "viewport": {},
                },
                "authoring": {},
            }
        )
        document = self._parse_document(
            raw,
            agent_id=agent_id,
            name=name,
            allow_identity_rebind=True,
        )
        result = self.compile_document(document.to_json_dict())
        return self._repository.create_agent(
            name,
            document,
            self._snapshot(result),
        )

    def list_agents(
        self,
        *,
        limit: int = 50,
        cursor: str | None = None,
    ) -> AgentPage:
        """List Agent metadata through the repository contract.

        Args:
            limit (int): Page size.
            cursor (str | None): Opaque continuation cursor.

        Raises:
            ValueError: Pagination is invalid.
            AgentDocumentRepositoryError: Query fails.

        Returns:
            AgentPage: Stable Agent page.
        """
        return self._repository.list_agents(limit=limit, cursor=cursor)

    def get_agent(
        self,
        agent_id: str,
    ) -> tuple[AgentRecord, AgentRevisionRecord | None]:
        """Read Agent metadata and its current revision.

        Args:
            agent_id (str): Stable Agent identity.

        Raises:
            AgentNotFoundError: Agent does not exist.
            AgentRevisionNotFoundError: Current pointer is corrupted.

        Returns:
            tuple[AgentRecord, AgentRevisionRecord | None]: Agent and current
            immutable revision.
        """
        agent = self._repository.get_agent(agent_id)
        revision = (
            self._repository.get_revision(
                agent_id,
                agent.current_revision_id,
            )
            if agent.current_revision_id is not None
            else None
        )
        return agent, revision

    def rename_agent(self, agent_id: str, name: str) -> AgentRecord:
        """Rename one Agent without altering any revision.

        Args:
            agent_id (str): Stable Agent identity.
            name (str): New display name.

        Raises:
            ValueError: Name is invalid.
            AgentNotFoundError: Agent does not exist.

        Returns:
            AgentRecord: Updated Agent metadata.
        """
        return self._repository.rename_agent(agent_id, name)

    def get_revision(
        self,
        agent_id: str,
        revision_id: str,
    ) -> AgentRevisionRecord:
        """Read one immutable revision.

        Args:
            agent_id (str): Stable Agent identity.
            revision_id (str): Stable revision identity.

        Raises:
            AgentRevisionNotFoundError: Revision is absent.

        Returns:
            AgentRevisionRecord: Immutable revision.
        """
        return self._repository.get_revision(agent_id, revision_id)

    def save_revision(
        self,
        agent_id: str,
        *,
        base_revision_id: str | None,
        raw_document: Mapping[str, Any],
    ) -> tuple[AgentRecord, AgentRevisionRecord]:
        """Compile and append one structurally valid schema 2 revision.

        Args:
            agent_id (str): Stable Agent identity.
            base_revision_id (str | None): Client-observed current revision.
            raw_document (Mapping[str, Any]): Raw schema 2 document.

        Raises:
            StudioApplicationError: Document structure/identity is invalid.
            AgentRevisionConflictError: Base revision is stale.
            AgentNotFoundError: Agent does not exist.

        Returns:
            tuple[AgentRecord, AgentRevisionRecord]: Updated Agent and new
            revision.
        """
        document = self._parse_document(raw_document, agent_id=agent_id)
        result = self.compile_document(document.to_json_dict())
        return self._repository.save_revision(
            agent_id,
            base_revision_id=base_revision_id,
            document=document,
            snapshot=self._snapshot(result),
        )


def agent_record_payload(agent: AgentRecord) -> dict[str, Any]:
    """Serialize Agent metadata for versioned HTTP responses.

    Args:
        agent (AgentRecord): Agent metadata.

    Raises:
        None.

    Returns:
        dict[str, Any]: Camel-case JSON payload.
    """
    return agent.model_dump(mode="json", by_alias=True, exclude_none=True)


def revision_record_payload(revision: AgentRevisionRecord) -> dict[str, Any]:
    """Serialize an immutable revision for versioned HTTP responses.

    Args:
        revision (AgentRevisionRecord): Revision DTO.

    Raises:
        None.

    Returns:
        dict[str, Any]: Camel-case JSON payload.
    """
    return revision.model_dump(mode="json", by_alias=True, exclude_none=True)


__all__ = [
    "StudioApplicationError",
    "StudioApplicationService",
    "agent_record_payload",
    "revision_record_payload",
]
