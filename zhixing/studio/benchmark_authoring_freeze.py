"""Canonical closed-content preparation for validated Benchmark freezes."""

from __future__ import annotations

import json
from dataclasses import dataclass

from pydantic import ValidationError

from zhixing.benchmark import BenchmarkPackageManifest

from .benchmark_authoring_errors import (
    StudioBenchmarkAuthoringCapacityError,
    StudioBenchmarkAuthoringStorageError,
    StudioBenchmarkAuthoringValidationError,
)
from .benchmark_authoring_freeze_models import (
    StudioBenchmarkFrozenMemberV1,
    benchmark_frozen_closure_identity,
)
from .benchmark_authoring_models import (
    STUDIO_BENCHMARK_AUTHORING_MAX_DEFINITION_BYTES,
    STUDIO_BENCHMARK_AUTHORING_MAX_MEMBERS,
    STUDIO_BENCHMARK_AUTHORING_MAX_RESOURCE_BYTES,
    STUDIO_BENCHMARK_AUTHORING_MAX_TOTAL_IMPORT_BYTES,
    StudioBenchmarkAuthoringDocumentV1,
)
from .benchmark_authoring_protocols import StudioBenchmarkManagedContent


def _canonical_json_bytes(value: object) -> bytes:
    """Encode one parsed definition member as deterministic UTF-8 JSON.

    Args:
        value: Safe JSON-compatible authoring value.

    Raises:
        StudioBenchmarkAuthoringCapacityError: The encoded member is too large.
        StudioBenchmarkAuthoringStorageError: Encoding fails.

    Returns:
        Compact canonical JSON followed by one newline.
    """
    try:
        payload = (
            json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise StudioBenchmarkAuthoringStorageError(
            "benchmark.authoring.freeze_encoding_failed",
            "Benchmark freeze definition could not be encoded safely",
        ) from error
    if len(payload) > STUDIO_BENCHMARK_AUTHORING_MAX_DEFINITION_BYTES:
        raise StudioBenchmarkAuthoringCapacityError(
            "benchmark.authoring.freeze_definition_too_large",
            "Benchmark freeze definition exceeds its safe limit",
        )
    return payload


@dataclass(frozen=True)
class StudioBenchmarkFrozenClosure:
    """Prepared immutable member closure and its canonical identity."""

    members: tuple[StudioBenchmarkFrozenMemberV1, ...]
    closure_identity: str


class StudioBenchmarkFrozenClosureBuilder:
    """Build closed Package members from one exact validated document."""

    def __init__(self, content: StudioBenchmarkManagedContent) -> None:
        """Bind the private immutable managed-content boundary.

        Args:
            content: Server-owned content-addressed storage.

        Returns:
            None.
        """
        self._content = content

    @staticmethod
    def _manifest(
        document: StudioBenchmarkAuthoringDocumentV1,
    ) -> BenchmarkPackageManifest:
        """Parse the already validated authoring manifest defensively.

        Args:
            document: Exact authoring document.

        Raises:
            StudioBenchmarkAuthoringValidationError: Manifest is not valid.

        Returns:
            Strict Core Package manifest.
        """
        try:
            return BenchmarkPackageManifest.model_validate(
                document.manifest.document
            )
        except ValidationError as error:
            raise StudioBenchmarkAuthoringValidationError(
                "benchmark.authoring.freeze_manifest_invalid",
                "Benchmark Package manifest is not eligible for freeze",
            ) from error

    def _definition_member(
        self,
        *,
        kind: str,
        path: str,
        value: object,
    ) -> StudioBenchmarkFrozenMemberV1:
        """Store one canonical definition and create its member descriptor.

        Args:
            kind: Manifest, task, or Protocol member kind.
            path: Safe Package-relative logical path.
            value: Parsed definition payload.

        Raises:
            StudioBenchmarkAuthoringError: Encoding or storage fails.

        Returns:
            Frozen descriptor with a temporary ordinal replaced after sorting.
        """
        payload = _canonical_json_bytes(value)
        content_identity, sha256, size = self._content.store_bytes(
            payload,
            max_bytes=STUDIO_BENCHMARK_AUTHORING_MAX_DEFINITION_BYTES,
        )
        return StudioBenchmarkFrozenMemberV1(
            ordinal=0,
            kind=kind,
            path=path,
            media_type="application/json",
            size=size,
            sha256=sha256,
            content_identity=content_identity,
        )

    def build(
        self,
        document: StudioBenchmarkAuthoringDocumentV1,
    ) -> StudioBenchmarkFrozenClosure:
        """Verify and freeze the manifest-declared Package member closure.

        Args:
            document: Exact authoring revision document that passed analysis.

        Raises:
            StudioBenchmarkAuthoringCapacityError: Closure exceeds a bound.
            StudioBenchmarkAuthoringStorageError: Managed content is unavailable
                or inconsistent.
            StudioBenchmarkAuthoringValidationError: Definition/resource
                inventories disagree.

        Returns:
            Deterministically ordered immutable members and closure identity.
        """
        manifest = self._manifest(document)
        task_by_path = {item.path: item for item in document.task_files}
        protocol_by_path = {item.path: item for item in document.protocol_files}
        resource_by_id = {item.id: item for item in document.resources}

        task_paths: list[str] = []
        for split in manifest.splits.values():
            for path in split.files:
                if path not in task_paths:
                    task_paths.append(path)
        missing_tasks = [path for path in task_paths if path not in task_by_path]
        if missing_tasks:
            raise StudioBenchmarkAuthoringValidationError(
                "benchmark.authoring.freeze_closure_invalid",
                "Benchmark freeze task closure is incomplete",
            )

        protocol_paths = [item.path for item in document.protocol_files]
        if (
            manifest.default_protocol is not None
            and manifest.default_protocol not in protocol_by_path
        ):
            raise StudioBenchmarkAuthoringValidationError(
                "benchmark.authoring.freeze_closure_invalid",
                "Benchmark freeze Protocol closure is incomplete",
            )

        definitions: list[StudioBenchmarkFrozenMemberV1] = [
            self._definition_member(
                kind="manifest",
                path=document.manifest.path,
                value=document.manifest.document,
            )
        ]
        definitions.extend(
            self._definition_member(
                kind="task",
                path=path,
                value=task_by_path[path].tasks,
            )
            for path in task_paths
        )
        definitions.extend(
            self._definition_member(
                kind="protocol",
                path=path,
                value=protocol_by_path[path].document,
            )
            for path in protocol_paths
        )

        resources: list[StudioBenchmarkFrozenMemberV1] = []
        for declared in manifest.resources:
            resource = resource_by_id.get(declared.id)
            if (
                resource is None
                or resource.kind != declared.kind.value
                or resource.path != declared.path
                or resource.media_type != declared.media_type
                or resource.sha256 != declared.sha256
                or resource.size != declared.size
            ):
                raise StudioBenchmarkAuthoringValidationError(
                    "benchmark.authoring.freeze_closure_invalid",
                    "Benchmark freeze resource closure is inconsistent",
                )
            if resource.size > STUDIO_BENCHMARK_AUTHORING_MAX_RESOURCE_BYTES:
                raise StudioBenchmarkAuthoringCapacityError(
                    "benchmark.authoring.freeze_resource_too_large",
                    "Benchmark freeze resource exceeds its safe limit",
                )
            with self._content.open_verified(
                resource.content_identity,
                expected_sha256=resource.sha256,
                expected_size=resource.size,
            ):
                pass
            resources.append(
                StudioBenchmarkFrozenMemberV1(
                    ordinal=0,
                    kind=resource.kind,
                    path=resource.path,
                    media_type=resource.media_type,
                    size=resource.size,
                    sha256=resource.sha256,
                    content_identity=resource.content_identity,
                )
            )

        raw_members = [*definitions, *resources]
        if len(raw_members) > STUDIO_BENCHMARK_AUTHORING_MAX_MEMBERS:
            raise StudioBenchmarkAuthoringCapacityError(
                "benchmark.authoring.freeze_members_too_many",
                "Benchmark freeze member closure exceeds its safe limit",
            )
        if sum(item.size for item in raw_members) > (
            STUDIO_BENCHMARK_AUTHORING_MAX_TOTAL_IMPORT_BYTES
        ):
            raise StudioBenchmarkAuthoringCapacityError(
                "benchmark.authoring.freeze_content_too_large",
                "Benchmark freeze content exceeds its safe aggregate limit",
            )
        ordered_raw = sorted(raw_members, key=lambda item: item.path)
        if len({item.path for item in ordered_raw}) != len(ordered_raw):
            raise StudioBenchmarkAuthoringValidationError(
                "benchmark.authoring.freeze_closure_invalid",
                "Benchmark freeze member paths are duplicated",
            )
        members = tuple(
            item.model_copy(update={"ordinal": ordinal})
            for ordinal, item in enumerate(ordered_raw)
        )
        return StudioBenchmarkFrozenClosure(
            members=members,
            closure_identity=benchmark_frozen_closure_identity(members),
        )


__all__ = [
    "StudioBenchmarkFrozenClosure",
    "StudioBenchmarkFrozenClosureBuilder",
]
