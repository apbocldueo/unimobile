"""Pure analysis and confirmed persistence for legacy BenchmarkTask migration."""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from pydantic import ValidationError

from zhixing.benchmark.compiler import collect_task_plugin_ids
from zhixing.benchmark.identity import canonical_hash
from zhixing.config.contracts import (
    BenchmarkSuite,
    BenchmarkTask,
    validate_benchmark_semantics,
)

from .benchmark_authoring_errors import (
    StudioBenchmarkAuthoringCapacityError,
    StudioBenchmarkAuthoringDriftError,
    StudioBenchmarkAuthoringValidationError,
)
from .benchmark_authoring_migration_models import (
    STUDIO_BENCHMARK_MIGRATION_CONTRACT_IDENTITY,
    STUDIO_BENCHMARK_MIGRATION_MAX_DIAGNOSTICS,
    STUDIO_BENCHMARK_MIGRATION_MAX_SOURCE_BYTES,
    STUDIO_BENCHMARK_MIGRATION_MAX_TASKS,
    StudioBenchmarkLegacyMigrationConfirmRequestV1,
    StudioBenchmarkLegacyMigrationConfirmResponseV1,
    StudioBenchmarkLegacyMigrationDiagnosticV1,
    StudioBenchmarkLegacyMigrationDiffEntryV1,
    StudioBenchmarkLegacyMigrationDiffV1,
    StudioBenchmarkLegacyMigrationPostWorkV1,
    StudioBenchmarkLegacyMigrationPreviewV1,
    StudioBenchmarkLegacyMigrationSourceFactsV1,
    StudioBenchmarkLegacyMigrationSourceRequestV1,
    StudioBenchmarkLegacyMigrationTargetV1,
    StudioBenchmarkLegacyMigrationTaskChangesV1,
)
from .benchmark_authoring_models import (
    StudioBenchmarkAuthoringDocumentV1,
    StudioBenchmarkAuthoringManifestV1,
    StudioBenchmarkAuthoringProvenanceV1,
    StudioBenchmarkAuthoringTaskFileV1,
    validate_benchmark_authoring_safe_json,
)
from .benchmark_authoring_protocols import StudioBenchmarkAuthoringRepository


@dataclass(frozen=True)
class StudioBenchmarkLegacyMigrationAnalysis:
    """Internal pure analysis retaining the candidate outside public DTOs."""

    preview: StudioBenchmarkLegacyMigrationPreviewV1
    candidate_document: StudioBenchmarkAuthoringDocumentV1 | None


def _source_fingerprint(source_text: str) -> str:
    """Hash exact submitted UTF-8 source bytes without JSON normalization.

    Args:
        source_text: Exact browser-submitted source text.

    Raises:
        UnicodeEncodeError: Text cannot be represented as UTF-8.

    Returns:
        Prefixed SHA-256 source identity.
    """
    return f"sha256:{hashlib.sha256(source_text.encode('utf-8')).hexdigest()}"


def _safe_task_id(value: Any) -> str | None:
    """Return a bounded display-safe task ID or no public task identity.

    Args:
        value: Untrusted parsed task ID value.

    Raises:
        None.

    Returns:
        The original bounded task ID when safe for a diagnostic.
    """
    if (
        isinstance(value, str)
        and value.strip()
        and len(value) <= 160
        and not any(ord(character) < 32 for character in value)
    ):
        return value
    return None


def _diagnostic(
    code: str,
    message: str,
    *,
    severity: str = "error",
    source_index: int | None = None,
    field_path: Sequence[str | int] = (),
    task_id: str | None = None,
) -> StudioBenchmarkLegacyMigrationDiagnosticV1:
    """Create one sanitized migration diagnostic from stable literals.

    Args:
        code: Stable public diagnostic code.
        message: Bounded value-free public explanation.
        severity: Error or warning classification.
        source_index: Optional source array index.
        field_path: Stable source-relative field path.
        task_id: Optional bounded safe task identity.

    Raises:
        ValidationError: A programmer supplies an invalid public literal.

    Returns:
        Strict public migration diagnostic.
    """
    return StudioBenchmarkLegacyMigrationDiagnosticV1(
        code=code,
        severity=severity,
        message=message,
        source_index=source_index,
        field_path=tuple(field_path),
        task_id=task_id,
    )


def _bounded_diagnostics(
    values: Sequence[StudioBenchmarkLegacyMigrationDiagnosticV1],
) -> tuple[StudioBenchmarkLegacyMigrationDiagnosticV1, ...]:
    """Bound diagnostic output and make truncation itself non-confirmable.

    Args:
        values: Ordered sanitized diagnostics.

    Raises:
        None.

    Returns:
        At most 100 diagnostics with an explicit overflow error.
    """
    if len(values) <= STUDIO_BENCHMARK_MIGRATION_MAX_DIAGNOSTICS:
        return tuple(values)
    return (
        *values[: STUDIO_BENCHMARK_MIGRATION_MAX_DIAGNOSTICS - 1],
        _diagnostic(
            "benchmark.migration.diagnostic_limit_exceeded",
            "Additional migration diagnostics were omitted by the safe limit.",
        ),
    )


def _relative_resource_indexes(tasks: Sequence[Mapping[str, Any]]) -> tuple[int, ...]:
    """Find tasks with explicit relative path-like values needing author repair.

    Args:
        tasks: Structurally valid raw task mappings.

    Raises:
        None.

    Returns:
        Source indexes containing a relative path-like resource value.
    """
    found: set[int] = set()

    def visit(value: Any, key: str | None, source_index: int) -> None:
        """Traverse JSON while classifying only explicit path-like keys.

        Args:
            value: Current parsed JSON value.
            key: Owning mapping key when available.
            source_index: Source task index.

        Raises:
            None.

        Returns:
            None.
        """
        if isinstance(value, Mapping):
            for child_key, child in value.items():
                visit(child, str(child_key), source_index)
            return
        if isinstance(value, (list, tuple)):
            for child in value:
                visit(child, key, source_index)
            return
        normalized = (key or "").lower()
        path_key = any(
            token in normalized
            for token in ("path", "file", "resource", "image", "folder")
        )
        if (
            path_key
            and isinstance(value, str)
            and value
            and not value.startswith(
                (
                    "/data/local/tmp/",
                    "/sdcard/",
                    "/storage/emulated/",
                    "asset://",
                    "groundtruth://",
                    "${",
                )
            )
            and "://" not in value
        ):
            found.add(source_index)

    for index, task in enumerate(tasks):
        visit(task, None, index)
    return tuple(sorted(found))


def _project_apps(
    tasks: Sequence[Mapping[str, Any]],
    platform: str,
) -> tuple[tuple[dict[str, Any], ...], tuple[int, ...]]:
    """Project only App login facts determined by explicit V1 declarations.

    Args:
        tasks: Structurally valid raw task mappings.
        platform: Explicit target Package platform.

    Raises:
        None.

    Returns:
        Sorted manifest App declarations and unresolved source indexes.
    """
    occurrences: dict[str, list[tuple[int, bool | None, bool]]] = {}
    for index, task in enumerate(tasks):
        app = task.get("app")
        if not isinstance(app, str):
            continue
        explicit = "requires_login" in task and task.get("requires_login") is not None
        login = task.get("requires_login") if explicit else None
        occurrences.setdefault(app, []).append((index, login, explicit))

    declarations: list[dict[str, Any]] = []
    unresolved: set[int] = set()
    for app in sorted(occurrences):
        facts = occurrences[app]
        if any(login is True for _, login, _ in facts):
            requires_login = True
        elif all(explicit and login is False for _, login, explicit in facts):
            requires_login = False
        else:
            unresolved.update(index for index, _, _ in facts)
            continue
        declarations.append(
            {
                "id": app,
                "platform": platform,
                "requires_login": requires_login,
            }
        )
    return tuple(declarations), tuple(sorted(unresolved))


def _build_diff(
    *,
    entry_count: int,
    target: StudioBenchmarkLegacyMigrationTargetV1,
    plugin_ids: tuple[str, ...],
    app_ids: tuple[str, ...],
) -> StudioBenchmarkLegacyMigrationDiffV1:
    """Build the deterministic bounded semantic migration diff.

    Args:
        entry_count: Original source array member count.
        target: Explicit Package wrapper intent.
        plugin_ids: Mechanically derived plugin declarations.
        app_ids: Conservatively derived App declarations.

    Raises:
        ValidationError: A programmer emits an invalid diff literal.

    Returns:
        Strict semantic diff with zero task mutation counts.
    """
    entries = [
        StudioBenchmarkLegacyMigrationDiffEntryV1(
            code="benchmark.migration.wrapper.manifest_added",
            category="wrapper",
            path=("benchmark.yaml",),
            message="A schema-1 Package manifest is added from explicit target intent.",
        ),
        StudioBenchmarkLegacyMigrationDiffEntryV1(
            code="benchmark.migration.wrapper.task_file_added",
            category="wrapper",
            path=(target.task_file_path,),
            message="Source tasks are placed in one deterministic Package task member.",
        ),
        StudioBenchmarkLegacyMigrationDiffEntryV1(
            code="benchmark.migration.representation.normalized",
            category="representation",
            path=(target.task_file_path,),
            message="JSON whitespace and object-key representation may be canonicalized.",
        ),
        StudioBenchmarkLegacyMigrationDiffEntryV1(
            code="benchmark.migration.omission.protocol",
            category="omission",
            path=("protocols",),
            message="No Protocol or default Protocol is invented.",
        ),
        StudioBenchmarkLegacyMigrationDiffEntryV1(
            code="benchmark.migration.omission.ground_truth",
            category="omission",
            path=("ground_truth",),
            message="No ground-truth binding is invented.",
        ),
        StudioBenchmarkLegacyMigrationDiffEntryV1(
            code="benchmark.migration.omission.resources",
            category="omission",
            path=("resources",),
            message="No resource declaration or managed byte is invented.",
        ),
    ]
    if plugin_ids:
        entries.append(
            StudioBenchmarkLegacyMigrationDiffEntryV1(
                code="benchmark.migration.declaration.plugins",
                category="declaration",
                path=("benchmark.yaml", "plugins"),
                message="Plugin declarations are derived from explicit V1 references.",
            )
        )
    if app_ids:
        entries.append(
            StudioBenchmarkLegacyMigrationDiffEntryV1(
                code="benchmark.migration.declaration.apps",
                category="declaration",
                path=("benchmark.yaml", "apps"),
                message="App declarations include only determined login requirements.",
            )
        )
    return StudioBenchmarkLegacyMigrationDiffV1(
        task_changes=StudioBenchmarkLegacyMigrationTaskChangesV1(
            retained=entry_count
        ),
        entries=tuple(entries),
        plugin_ids=plugin_ids,
        app_ids=app_ids,
    )


def _post_work(
    *,
    unresolved_app_indexes: tuple[int, ...],
    relative_resource_indexes: tuple[int, ...],
) -> tuple[StudioBenchmarkLegacyMigrationPostWorkV1, ...]:
    """Describe required author work without presenting it as migration error.

    Args:
        unresolved_app_indexes: Tasks whose App login requirement is unknown.
        relative_resource_indexes: Tasks containing relative path-like values.

    Raises:
        ValidationError: A programmer emits an invalid stable work item.

    Returns:
        Ordered explicit post-migration work.
    """
    values = [
        StudioBenchmarkLegacyMigrationPostWorkV1(
            code="benchmark.migration.work.protocol_required",
            message="Author and select an Experiment Protocol before execution.",
        ),
        StudioBenchmarkLegacyMigrationPostWorkV1(
            code="benchmark.migration.work.ground_truth_review",
            message="Review and author ground-truth bindings when the suite requires them.",
        ),
        StudioBenchmarkLegacyMigrationPostWorkV1(
            code="benchmark.migration.work.resource_inventory",
            message="Review resource references and upload managed bytes explicitly.",
            source_indexes=relative_resource_indexes,
        ),
    ]
    if unresolved_app_indexes:
        values.append(
            StudioBenchmarkLegacyMigrationPostWorkV1(
                code="benchmark.migration.work.app_login_unknown",
                message="Declare App login requirements that source tasks do not determine.",
                source_indexes=unresolved_app_indexes,
            )
        )
    return tuple(values)


def _empty_diff(
    target: StudioBenchmarkLegacyMigrationTargetV1,
    entry_count: int,
) -> StudioBenchmarkLegacyMigrationDiffV1:
    """Build a stable diff shell for source that cannot be projected.

    Args:
        target: Validated target intent.
        entry_count: Known source entry count, if any.

    Raises:
        ValidationError: A fixed diff literal is invalid.

    Returns:
        Diff with task mutation counts still explicitly zero.
    """
    return _build_diff(
        entry_count=entry_count,
        target=target,
        plugin_ids=(),
        app_ids=(),
    )


class StudioBenchmarkLegacyMigrationAnalyzer:
    """Analyze legacy source through a deterministic side-effect-free boundary."""

    def analyze(
        self,
        request: StudioBenchmarkLegacyMigrationSourceRequestV1,
    ) -> StudioBenchmarkLegacyMigrationAnalysis:
        """Analyze and project one exact submitted standalone V1 JSON source.

        Args:
            request: Strict source text and explicit target wrapper intent.

        Raises:
            None: Source problems are returned as bounded diagnostics.

        Returns:
            Public transient preview and private candidate document when safe.
        """
        source_bytes = request.source_text.encode("utf-8")
        source_fingerprint = _source_fingerprint(request.source_text)
        diagnostics: list[StudioBenchmarkLegacyMigrationDiagnosticV1] = []
        parsed: Any = None
        try:
            parsed = json.loads(
                request.source_text,
                parse_constant=lambda _value: (_ for _ in ()).throw(
                    ValueError("non-finite JSON number")
                ),
            )
        except (json.JSONDecodeError, ValueError, TypeError):
            diagnostics.append(
                _diagnostic(
                    "benchmark.migration.json_invalid",
                    "Source text is not strict finite JSON.",
                )
            )

        if parsed is not None and not isinstance(parsed, list):
            diagnostics.append(
                _diagnostic(
                    "benchmark.migration.root_invalid",
                    "Legacy BenchmarkTask JSON must use an array root.",
                )
            )
        tasks = parsed if isinstance(parsed, list) else []
        entry_count = len(tasks)
        safe_ids = [
            _safe_task_id(item.get("id")) if isinstance(item, Mapping) else None
            for item in tasks
        ]
        unique_task_count = len({value for value in safe_ids if value is not None})
        if entry_count > STUDIO_BENCHMARK_MIGRATION_MAX_TASKS:
            diagnostics.append(
                _diagnostic(
                    "benchmark.migration.task_limit_exceeded",
                    "Legacy source exceeds the 100-task migration limit.",
                )
            )
        if not tasks and isinstance(parsed, list):
            diagnostics.append(
                _diagnostic(
                    "benchmark.migration.suite_empty",
                    "Legacy BenchmarkTask JSON must contain at least one task.",
                )
            )

        try:
            if isinstance(parsed, list):
                validate_benchmark_authoring_safe_json(parsed)
        except ValueError:
            diagnostics.append(
                _diagnostic(
                    "benchmark.migration.authoring_value_unsafe",
                    "Source contains a value forbidden by the authoring safety envelope.",
                )
            )

        first_by_id: dict[str, int] = {}
        for index, task_id in enumerate(safe_ids):
            if task_id is None:
                continue
            if task_id in first_by_id:
                diagnostics.append(
                    _diagnostic(
                        "benchmark.migration.task_id_duplicate",
                        "Task identity repeats an earlier source entry; no task was removed or renamed.",
                        source_index=index,
                        field_path=("id",),
                        task_id=task_id,
                    )
                )
            else:
                first_by_id[task_id] = index

        raw_tasks: list[Mapping[str, Any]] = []
        parsed_tasks: list[BenchmarkTask] = []
        if entry_count <= STUDIO_BENCHMARK_MIGRATION_MAX_TASKS:
            for index, item in enumerate(tasks):
                task_id = safe_ids[index]
                if not isinstance(item, Mapping):
                    diagnostics.append(
                        _diagnostic(
                            "benchmark.migration.task_object_required",
                            "Each legacy source entry must be a JSON object.",
                            source_index=index,
                        )
                    )
                    continue
                raw_tasks.append(item)
                try:
                    parsed_tasks.append(BenchmarkTask.model_validate(item))
                except ValidationError as error:
                    for detail in error.errors(
                        include_url=False,
                        include_input=False,
                    ):
                        error_type = str(detail.get("type", ""))
                        diagnostics.append(
                            _diagnostic(
                                (
                                    "benchmark.migration.v1_field_rejected"
                                    if error_type == "extra_forbidden"
                                    else "benchmark.migration.v1_structure_invalid"
                                ),
                                (
                                    "Source contains a field rejected by BenchmarkTask V1."
                                    if error_type == "extra_forbidden"
                                    else "Source entry violates the BenchmarkTask V1 structure."
                                ),
                                source_index=index,
                                field_path=tuple(detail.get("loc", ())),
                                task_id=task_id,
                            )
                        )

        has_duplicate = len(first_by_id) != len([value for value in safe_ids if value])
        if (
            len(parsed_tasks) == entry_count
            and entry_count > 0
            and not has_duplicate
        ):
            suite = BenchmarkSuite(root=parsed_tasks)
            for issue in validate_benchmark_semantics(suite):
                path = tuple(issue.path)
                source_index = path[0] if path and isinstance(path[0], int) else None
                field_path = path[1:] if source_index is not None else path
                diagnostics.append(
                    _diagnostic(
                        "benchmark.migration.v1_semantic_invalid",
                        "Source entry violates BenchmarkTask V1 semantic closure.",
                        severity=issue.severity,
                        source_index=source_index,
                        field_path=field_path,
                        task_id=_safe_task_id(issue.task_id),
                    )
                )

        bounded = _bounded_diagnostics(diagnostics)
        has_error = any(item.severity == "error" for item in bounded)
        document: StudioBenchmarkAuthoringDocumentV1 | None = None
        plugin_ids: tuple[str, ...] = ()
        app_ids: tuple[str, ...] = ()
        unresolved_apps: tuple[int, ...] = ()
        resource_indexes: tuple[int, ...] = ()
        if not has_error and len(raw_tasks) == entry_count:
            try:
                plugin_ids = tuple(sorted(collect_task_plugin_ids(raw_tasks)))
                apps, unresolved_apps = _project_apps(
                    raw_tasks,
                    request.target.platform,
                )
                app_ids = tuple(item["id"] for item in apps)
                resource_indexes = _relative_resource_indexes(raw_tasks)
                manifest = {
                    "schema_version": "1.0",
                    "identity": {
                        "publisher": request.target.publisher,
                        "name": request.target.package_name,
                        "version": request.target.version,
                    },
                    "title": request.target.title,
                    "platforms": [request.target.platform],
                    "splits": {
                        request.target.split: {
                            "files": [request.target.task_file_path]
                        }
                    },
                    "resources": [],
                    "ground_truth": {},
                    "apps": list(apps),
                    "plugins": [
                        {"id": plugin_id, "optional": False}
                        for plugin_id in plugin_ids
                    ],
                }
                document = StudioBenchmarkAuthoringDocumentV1(
                    manifest=StudioBenchmarkAuthoringManifestV1(
                        document=manifest
                    ),
                    task_files=(
                        StudioBenchmarkAuthoringTaskFileV1(
                            path=request.target.task_file_path,
                            tasks=tuple(copy.deepcopy(tasks)),
                        ),
                    ),
                )
            except (ValidationError, ValueError, TypeError):
                bounded = _bounded_diagnostics(
                    [
                        *bounded,
                        _diagnostic(
                            "benchmark.migration.candidate_invalid",
                            "Source and target cannot form a safe schema-1 authoring document.",
                        ),
                    ]
                )
                document = None

        confirmable = document is not None and not any(
            item.severity == "error" for item in bounded
        )
        candidate_fingerprint = document.fingerprint if confirmable else None
        preview_fingerprint = (
            canonical_hash(
                {
                    "schemaVersion": 1,
                    "sourceFingerprint": source_fingerprint,
                    "target": request.target.model_dump(
                        mode="json", by_alias=True, exclude_none=True
                    ),
                    "migrationContractIdentity": (
                        STUDIO_BENCHMARK_MIGRATION_CONTRACT_IDENTITY
                    ),
                    "candidateDocumentFingerprint": candidate_fingerprint,
                }
            )
            if confirmable
            else None
        )
        diff = (
            _build_diff(
                entry_count=entry_count,
                target=request.target,
                plugin_ids=plugin_ids,
                app_ids=app_ids,
            )
            if document is not None
            else _empty_diff(request.target, entry_count)
        )
        post_work = _post_work(
            unresolved_app_indexes=unresolved_apps,
            relative_resource_indexes=resource_indexes,
        )
        preview = StudioBenchmarkLegacyMigrationPreviewV1(
            confirmable=confirmable,
            source=StudioBenchmarkLegacyMigrationSourceFactsV1(
                source_name=request.source_name,
                utf8_size=len(source_bytes),
                source_fingerprint=source_fingerprint,
                entry_count=entry_count,
                unique_task_count=unique_task_count,
            ),
            target=request.target,
            migration_contract_identity=(
                STUDIO_BENCHMARK_MIGRATION_CONTRACT_IDENTITY
            ),
            candidate_document_fingerprint=candidate_fingerprint,
            preview_fingerprint=preview_fingerprint,
            diff=diff,
            diagnostics=bounded,
            post_migration_work=post_work,
        )
        return StudioBenchmarkLegacyMigrationAnalysis(
            preview=preview,
            candidate_document=document if confirmable else None,
        )


class StudioBenchmarkLegacyMigrationApplicationService:
    """Coordinate pure Preview with exact idempotent confirmed creation."""

    def __init__(
        self,
        *,
        repository: StudioBenchmarkAuthoringRepository,
        analyzer: StudioBenchmarkLegacyMigrationAnalyzer | None = None,
    ) -> None:
        """Bind only the durable authoring repository to migration Confirm.

        Args:
            repository: Existing atomic authoring draft/revision authority.
            analyzer: Optional pure analyzer override for deterministic tests.

        Raises:
            None.

        Returns:
            None.
        """
        self._repository = repository
        self._analyzer = analyzer or StudioBenchmarkLegacyMigrationAnalyzer()

    @staticmethod
    def _check_source_capacity(payload: Mapping[str, Any]) -> None:
        """Map an oversized raw source field to the shared capacity failure.

        Args:
            payload: Untrusted decoded JSON request object.

        Raises:
            StudioBenchmarkAuthoringCapacityError: Source exceeds one MiB.

        Returns:
            None.
        """
        source_text = payload.get("sourceText")
        if (
            isinstance(source_text, str)
            and len(source_text.encode("utf-8"))
            > STUDIO_BENCHMARK_MIGRATION_MAX_SOURCE_BYTES
        ):
            raise StudioBenchmarkAuthoringCapacityError(
                "benchmark.migration.source_too_large",
                "Legacy migration source exceeds the one MiB limit",
            )

    @classmethod
    def parse_preview_request(
        cls,
        payload: Mapping[str, Any],
    ) -> StudioBenchmarkLegacyMigrationSourceRequestV1:
        """Parse a strict Preview request before invoking pure analysis.

        Args:
            payload: Untrusted decoded JSON object.

        Raises:
            StudioBenchmarkAuthoringCapacityError: Source exceeds one MiB.
            StudioBenchmarkAuthoringValidationError: Request is malformed.

        Returns:
            Strict source and target request.
        """
        cls._check_source_capacity(payload)
        try:
            return StudioBenchmarkLegacyMigrationSourceRequestV1.model_validate(
                payload
            )
        except (ValidationError, TypeError, ValueError) as error:
            raise StudioBenchmarkAuthoringValidationError(
                "benchmark.migration.request_invalid",
                "Legacy migration Preview request is invalid",
            ) from error

    @classmethod
    def parse_confirm_request(
        cls,
        payload: Mapping[str, Any],
    ) -> StudioBenchmarkLegacyMigrationConfirmRequestV1:
        """Parse a strict Confirm request before repository access.

        Args:
            payload: Untrusted decoded JSON object.

        Raises:
            StudioBenchmarkAuthoringCapacityError: Source exceeds one MiB.
            StudioBenchmarkAuthoringValidationError: Request is malformed.

        Returns:
            Strict complete Confirm command.
        """
        cls._check_source_capacity(payload)
        try:
            return StudioBenchmarkLegacyMigrationConfirmRequestV1.model_validate(
                payload
            )
        except (ValidationError, TypeError, ValueError) as error:
            raise StudioBenchmarkAuthoringValidationError(
                "benchmark.migration.request_invalid",
                "Legacy migration Confirm request is invalid",
            ) from error

    def preview(
        self,
        request: StudioBenchmarkLegacyMigrationSourceRequestV1,
    ) -> StudioBenchmarkLegacyMigrationPreviewV1:
        """Return transient analysis without accessing durable state.

        Args:
            request: Strict source and target intent.

        Raises:
            None.

        Returns:
            Deterministic bounded Preview.
        """
        return self._analyzer.analyze(request).preview

    @staticmethod
    def _response_from_revision(
        *,
        created: bool,
        draft: Any,
        revision: Any,
    ) -> StudioBenchmarkLegacyMigrationConfirmResponseV1:
        """Project one durable migration revision into its strict response.

        Args:
            created: Whether this command created the aggregate now.
            draft: Durable draft record.
            revision: Durable immutable migration revision.

        Raises:
            StudioBenchmarkAuthoringValidationError: Stored provenance is not
                a complete migration authority.

        Returns:
            Strict fresh or replayed Confirm response.
        """
        provenance = revision.provenance
        if (
            provenance.source_kind != "legacy_migration"
            or provenance.source_fingerprint is None
            or provenance.preview_fingerprint is None
            or provenance.migration_contract_identity is None
            or provenance.candidate_document_fingerprint is None
        ):
            raise StudioBenchmarkAuthoringValidationError(
                "benchmark.migration.authority_invalid",
                "Stored migration authority is incomplete",
            )
        return StudioBenchmarkLegacyMigrationConfirmResponseV1(
            created=created,
            draft=draft,
            revision=revision,
            source_fingerprint=provenance.source_fingerprint,
            preview_fingerprint=provenance.preview_fingerprint,
            migration_contract_identity=provenance.migration_contract_identity,
            candidate_document_fingerprint=(
                provenance.candidate_document_fingerprint
            ),
        )

    def confirm(
        self,
        request: StudioBenchmarkLegacyMigrationConfirmRequestV1,
    ) -> StudioBenchmarkLegacyMigrationConfirmResponseV1:
        """Reanalyze exact intent and atomically create one unvalidated draft.

        Args:
            request: Strict exact source, target, preview, and command identity.

        Raises:
            StudioBenchmarkAuthoringDriftError: Preview authority is stale.
            StudioBenchmarkAuthoringValidationError: Source is non-confirmable.
            StudioBenchmarkError: Idempotency or durable storage fails.

        Returns:
            Fresh or durably replayed migration response.
        """
        existing = self._repository.find_create_result(
            client_request_id=request.client_request_id,
            request_fingerprint=request.fingerprint,
        )
        if existing is not None:
            return self._response_from_revision(
                created=False,
                draft=existing[0],
                revision=existing[1],
            )
        if (
            request.migration_contract_identity
            != STUDIO_BENCHMARK_MIGRATION_CONTRACT_IDENTITY
        ):
            raise StudioBenchmarkAuthoringDriftError(
                "benchmark.migration.preview_stale",
                "Migration contract changed after Preview",
            )
        analysis = self._analyzer.analyze(
            StudioBenchmarkLegacyMigrationSourceRequestV1(
                source_name=request.source_name,
                source_text=request.source_text,
                target=request.target,
            )
        )
        preview = analysis.preview
        if not preview.confirmable or analysis.candidate_document is None:
            raise StudioBenchmarkAuthoringValidationError(
                "benchmark.migration.not_confirmable",
                "Legacy migration source is not confirmable",
            )
        if preview.preview_fingerprint != request.preview_fingerprint:
            raise StudioBenchmarkAuthoringDriftError(
                "benchmark.migration.preview_stale",
                "Migration source or target changed after Preview",
            )
        provenance = StudioBenchmarkAuthoringProvenanceV1(
            source_kind="legacy_migration",
            source_display_name=request.source_name,
            source_fingerprint=preview.source.source_fingerprint,
            preview_fingerprint=request.preview_fingerprint,
            candidate_document_fingerprint=(
                preview.candidate_document_fingerprint
            ),
            migration_contract_identity=(
                preview.migration_contract_identity
            ),
            task_entry_count=preview.source.entry_count,
            unique_task_count=preview.source.unique_task_count,
        )
        draft, revision, created = self._repository.create_draft(
            client_request_id=request.client_request_id,
            request_fingerprint=request.fingerprint,
            name=request.target.draft_name,
            document=analysis.candidate_document,
            provenance=provenance,
        )
        return self._response_from_revision(
            created=created,
            draft=draft,
            revision=revision,
        )


__all__ = [
    "StudioBenchmarkLegacyMigrationAnalysis",
    "StudioBenchmarkLegacyMigrationAnalyzer",
    "StudioBenchmarkLegacyMigrationApplicationService",
]
