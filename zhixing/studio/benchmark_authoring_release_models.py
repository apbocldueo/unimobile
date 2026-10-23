"""Strict contracts for immutable Benchmark Package publication and export."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import Field, StrictBool, StrictInt, field_validator, model_validator

from zhixing.benchmark.identity import canonical_hash

from .benchmark_authoring_freeze_models import (
    StudioBenchmarkPackageRevisionV1,
    validate_benchmark_package_revision_id,
    validate_benchmark_validation_attestation_id,
)
from .benchmark_authoring_models import validate_benchmark_draft_id
from .models import StudioModel


STUDIO_BENCHMARK_PACKAGE_EXPORT_CONTRACT = "studio-benchmark-package-zip-v1"
STUDIO_BENCHMARK_MANAGED_SOURCE_ID = "studio-managed-benchmark-publications"
STUDIO_BENCHMARK_PACKAGE_REVISION_PAGE_MAX = 100
STUDIO_BENCHMARK_PACKAGE_EXPORT_MAX_BYTES = 272 * 1024 * 1024

_CLIENT_REQUEST_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}$")
_PUBLICATION_ID = re.compile(r"^benchmark-package-publication-[a-f0-9]{32}$")
_EXPORT_ID = re.compile(r"^benchmark-package-export-[a-f0-9]{32}$")
_CATALOG_ENTRY_ID = re.compile(r"^benchmark-entry-[a-f0-9]{32}$")
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_SAFE_FILENAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,199}\.zip$")
_SAFE_LINK = re.compile(
    r"^/api/studio/benchmark-authoring/drafts/[^/]+/package-revisions/"
    r"[^/]+/exports/[^/]+/content$"
)
_PRIVATE_TEXT = re.compile(
    r"(?:^|[\s\"'(])(?:/[A-Za-z0-9_.~/-]+|[A-Za-z]:[\\/][^\s\"']+)"
    r"|(?i:(?:api[_-]?key|password|secret|token)\s*[:=])"
)


def validate_benchmark_package_publication_id(value: str) -> str:
    """Validate one opaque managed publication identity.

    Args:
        value: Candidate public identity.

    Raises:
        ValueError: Identity is malformed.

    Returns:
        Validated identity.
    """
    if _PUBLICATION_ID.fullmatch(value) is None:
        raise ValueError("invalid Benchmark Package publication identity")
    return value


def validate_benchmark_package_export_id(value: str) -> str:
    """Validate one opaque deterministic export identity.

    Args:
        value: Candidate public identity.

    Raises:
        ValueError: Identity is malformed.

    Returns:
        Validated identity.
    """
    if _EXPORT_ID.fullmatch(value) is None:
        raise ValueError("invalid Benchmark Package export identity")
    return value


def _safe_text(value: str, *, limit: int) -> str:
    """Validate one bounded public release fact.

    Args:
        value: Candidate reader-facing text.
        limit: Inclusive character limit.

    Raises:
        ValueError: Text is blank, unsafe, multiline, or oversized.

    Returns:
        Validated text.
    """
    if (
        not value
        or len(value) > limit
        or "\r" in value
        or "\n" in value
        or "\x00" in value
        or _PRIVATE_TEXT.search(value) is not None
    ):
        raise ValueError("public release text is unsafe or outside its bound")
    return value


class StudioBenchmarkReleaseModel(StudioModel):
    """Strict immutable base for release wire and durable records."""


class StudioBenchmarkReleaseCommandV1(StudioBenchmarkReleaseModel):
    """Minimal idempotent command shared by publication and export."""

    schema_version: StrictInt = Field(default=1, ge=1, le=1)
    client_request_id: str

    @field_validator("client_request_id")
    @classmethod
    def _request_id(cls, value: str) -> str:
        """Validate one stable bounded command identity.

        Args:
            value: Candidate client request identity.

        Raises:
            ValueError: Identity is malformed.

        Returns:
            Validated identity.
        """
        if _CLIENT_REQUEST_ID.fullmatch(value) is None:
            raise ValueError("invalid client request identity")
        return value


def benchmark_release_request_fingerprint(
    *,
    operation: Literal["publish", "export"],
    draft_id: str,
    package_revision_id: str,
    request: StudioBenchmarkReleaseCommandV1,
) -> str:
    """Compute an operation- and owner-scoped release command fingerprint.

    Args:
        operation: Explicit publication or export operation.
        draft_id: Owning draft identity from the resource route.
        package_revision_id: Exact immutable Package revision identity.
        request: Strict command body.

    Raises:
        ValueError: An owning identity is malformed.

    Returns:
        Canonical SHA-256 request fingerprint.
    """
    validate_benchmark_draft_id(draft_id)
    validate_benchmark_package_revision_id(package_revision_id)
    return canonical_hash(
        {
            "operation": operation,
            "draftId": draft_id,
            "packageRevisionId": package_revision_id,
            "request": request.model_dump(mode="json", by_alias=True),
            "exportContractVersion": (
                STUDIO_BENCHMARK_PACKAGE_EXPORT_CONTRACT
                if operation == "export"
                else None
            ),
        }
    )


class StudioBenchmarkPublicationSafetyV1(StudioBenchmarkReleaseModel):
    """Fixed evidence boundary for one managed Catalog publication."""

    frozen_closure_verified: StrictBool = True
    publication_evidence: StrictBool = True
    contract_test_evidence: StrictBool = False
    execution_evidence: StrictBool = False
    real_device_evidence: StrictBool = False
    model_evidence: StrictBool = False
    package_plugin_evidence: StrictBool = False

    @model_validator(mode="after")
    def _fixed_boundary(self) -> "StudioBenchmarkPublicationSafetyV1":
        """Prevent publication metadata from claiming runtime evidence.

        Raises:
            ValueError: Fixed evidence facts are broadened or weakened.

        Returns:
            Validated safety facts.
        """
        if not self.frozen_closure_verified or not self.publication_evidence:
            raise ValueError("publication must verify the frozen closure")
        if any(
            (
                self.contract_test_evidence,
                self.execution_evidence,
                self.real_device_evidence,
                self.model_evidence,
                self.package_plugin_evidence,
            )
        ):
            raise ValueError("publication cannot claim runtime evidence")
        return self


class StudioBenchmarkExportSafetyV1(StudioBenchmarkReleaseModel):
    """Fixed evidence boundary for one deterministic Package export."""

    frozen_closure_verified: StrictBool = True
    archive_integrity_verified: StrictBool = True
    publication_evidence: StrictBool = False
    contract_test_evidence: StrictBool = False
    execution_evidence: StrictBool = False
    real_device_evidence: StrictBool = False
    model_evidence: StrictBool = False
    package_plugin_evidence: StrictBool = False

    @model_validator(mode="after")
    def _fixed_boundary(self) -> "StudioBenchmarkExportSafetyV1":
        """Prevent archive integrity from being interpreted as execution proof.

        Raises:
            ValueError: Fixed evidence facts are broadened or weakened.

        Returns:
            Validated safety facts.
        """
        if not self.frozen_closure_verified or not self.archive_integrity_verified:
            raise ValueError("export must verify closure and archive integrity")
        if any(
            (
                self.publication_evidence,
                self.contract_test_evidence,
                self.execution_evidence,
                self.real_device_evidence,
                self.model_evidence,
                self.package_plugin_evidence,
            )
        ):
            raise ValueError("Package export cannot claim release or runtime evidence")
        return self


class StudioBenchmarkPackagePublicationV1(StudioBenchmarkReleaseModel):
    """Immutable authority that one frozen Package is visible in Catalog."""

    schema_version: StrictInt = Field(default=1, ge=1, le=1)
    publication_id: str
    draft_id: str
    package_revision_id: str
    validation_attestation_id: str
    package_identity: str = Field(min_length=1, max_length=384)
    package_content_identity: str
    closure_identity: str
    catalog_entry_id: str
    source_id: Literal["studio-managed-benchmark-publications"] = (
        STUDIO_BENCHMARK_MANAGED_SOURCE_ID
    )
    source_kind: Literal["catalog"] = "catalog"
    created_at: StrictInt = Field(ge=0)
    safety: StudioBenchmarkPublicationSafetyV1 = Field(
        default_factory=StudioBenchmarkPublicationSafetyV1
    )

    @field_validator("publication_id")
    @classmethod
    def _publication_id(cls, value: str) -> str:
        """Validate the opaque publication identity.

        Args:
            value: Candidate identity.

        Raises:
            ValueError: Identity is malformed.

        Returns:
            Validated identity.
        """
        return validate_benchmark_package_publication_id(value)

    @field_validator("draft_id")
    @classmethod
    def _draft_id(cls, value: str) -> str:
        """Validate the owning draft identity.

        Args:
            value: Candidate identity.

        Raises:
            ValueError: Identity is malformed.

        Returns:
            Validated identity.
        """
        return validate_benchmark_draft_id(value)

    @field_validator("package_revision_id")
    @classmethod
    def _package_revision_id(cls, value: str) -> str:
        """Validate the exact frozen Package revision identity.

        Args:
            value: Candidate identity.

        Raises:
            ValueError: Identity is malformed.

        Returns:
            Validated identity.
        """
        return validate_benchmark_package_revision_id(value)

    @field_validator("validation_attestation_id")
    @classmethod
    def _attestation_id(cls, value: str) -> str:
        """Validate the linked successful validation authority.

        Args:
            value: Candidate attestation identity.

        Raises:
            ValueError: Identity is malformed.

        Returns:
            Validated identity.
        """
        return validate_benchmark_validation_attestation_id(value)

    @field_validator("catalog_entry_id")
    @classmethod
    def _catalog_entry_id(cls, value: str) -> str:
        """Validate the stable managed Catalog entry identity.

        Args:
            value: Candidate identity.

        Raises:
            ValueError: Identity is malformed.

        Returns:
            Validated identity.
        """
        if _CATALOG_ENTRY_ID.fullmatch(value) is None:
            raise ValueError("invalid Benchmark Catalog entry identity")
        return value

    @field_validator("package_identity")
    @classmethod
    def _package_identity(cls, value: str) -> str:
        """Validate the safe readable Package identity.

        Args:
            value: Candidate Package identity.

        Raises:
            ValueError: Identity is unsafe.

        Returns:
            Validated identity.
        """
        return _safe_text(value, limit=384)

    @field_validator("package_content_identity", "closure_identity")
    @classmethod
    def _digests(cls, value: str) -> str:
        """Validate one semantic release digest.

        Args:
            value: Candidate prefixed SHA-256 digest.

        Raises:
            ValueError: Digest is malformed.

        Returns:
            Validated digest.
        """
        if _DIGEST.fullmatch(value) is None:
            raise ValueError("release identity must be a SHA-256 digest")
        return value


class StudioBenchmarkPackageExportV1(StudioBenchmarkReleaseModel):
    """Immutable descriptor for one deterministic downloadable Package ZIP."""

    schema_version: StrictInt = Field(default=1, ge=1, le=1)
    export_id: str
    draft_id: str
    package_revision_id: str
    validation_attestation_id: str
    package_identity: str = Field(min_length=1, max_length=384)
    package_content_identity: str
    closure_identity: str
    export_contract_version: Literal["studio-benchmark-package-zip-v1"] = (
        STUDIO_BENCHMARK_PACKAGE_EXPORT_CONTRACT
    )
    member_count: StrictInt = Field(ge=1, le=256)
    archive_media_type: Literal["application/zip"] = "application/zip"
    filename: str
    size: StrictInt = Field(ge=1, le=STUDIO_BENCHMARK_PACKAGE_EXPORT_MAX_BYTES)
    sha256: str
    content_link: str
    availability: Literal["available"] = "available"
    created_at: StrictInt = Field(ge=0)
    safety: StudioBenchmarkExportSafetyV1 = Field(
        default_factory=StudioBenchmarkExportSafetyV1
    )

    @field_validator("export_id")
    @classmethod
    def _export_id(cls, value: str) -> str:
        """Validate the opaque export identity.

        Args:
            value: Candidate identity.

        Raises:
            ValueError: Identity is malformed.

        Returns:
            Validated identity.
        """
        return validate_benchmark_package_export_id(value)

    @field_validator("draft_id")
    @classmethod
    def _draft_id(cls, value: str) -> str:
        """Validate the owning draft identity.

        Args:
            value: Candidate identity.

        Raises:
            ValueError: Identity is malformed.

        Returns:
            Validated identity.
        """
        return validate_benchmark_draft_id(value)

    @field_validator("package_revision_id")
    @classmethod
    def _package_revision_id(cls, value: str) -> str:
        """Validate the exact frozen Package revision identity.

        Args:
            value: Candidate identity.

        Raises:
            ValueError: Identity is malformed.

        Returns:
            Validated identity.
        """
        return validate_benchmark_package_revision_id(value)

    @field_validator("validation_attestation_id")
    @classmethod
    def _attestation_id(cls, value: str) -> str:
        """Validate the linked successful validation authority.

        Args:
            value: Candidate attestation identity.

        Raises:
            ValueError: Identity is malformed.

        Returns:
            Validated identity.
        """
        return validate_benchmark_validation_attestation_id(value)

    @field_validator("package_identity")
    @classmethod
    def _package_identity(cls, value: str) -> str:
        """Validate the safe readable Package identity.

        Args:
            value: Candidate Package identity.

        Raises:
            ValueError: Identity is unsafe.

        Returns:
            Validated identity.
        """
        return _safe_text(value, limit=384)

    @field_validator("package_content_identity", "closure_identity", "sha256")
    @classmethod
    def _digests(cls, value: str) -> str:
        """Validate a semantic or archive SHA-256 digest.

        Args:
            value: Candidate prefixed digest.

        Raises:
            ValueError: Digest is malformed.

        Returns:
            Validated digest.
        """
        if _DIGEST.fullmatch(value) is None:
            raise ValueError("export identity must be a SHA-256 digest")
        return value

    @field_validator("filename")
    @classmethod
    def _filename(cls, value: str) -> str:
        """Validate the deterministic attachment filename.

        Args:
            value: Candidate basename.

        Raises:
            ValueError: Filename is unsafe.

        Returns:
            Validated filename.
        """
        if _SAFE_FILENAME.fullmatch(value) is None or ".." in value:
            raise ValueError("Package export filename is unsafe")
        return value

    @field_validator("content_link")
    @classmethod
    def _content_link(cls, value: str) -> str:
        """Validate the exact relative HTTP content capability.

        Args:
            value: Candidate server-generated link.

        Raises:
            ValueError: Link is not an exact relative content route.

        Returns:
            Validated link.
        """
        if _SAFE_LINK.fullmatch(value) is None or ".." in value or "?" in value:
            raise ValueError("Package export content link is unsafe")
        return value

    @model_validator(mode="after")
    def _scoped_content_link(self) -> "StudioBenchmarkPackageExportV1":
        """Bind the download capability to the descriptor's exact owners.

        Raises:
            ValueError: The relative capability names different resources.

        Returns:
            Validated exact export descriptor.
        """
        expected = (
            "/api/studio/benchmark-authoring/drafts/"
            f"{self.draft_id}/package-revisions/{self.package_revision_id}/"
            f"exports/{self.export_id}/content"
        )
        if self.content_link != expected:
            raise ValueError("Package export content link does not match ownership")
        return self


class StudioBenchmarkPublicationResultV1(StudioBenchmarkReleaseModel):
    """Publication command response including creation disposition."""

    schema_version: StrictInt = Field(default=1, ge=1, le=1)
    created: StrictBool
    publication: StudioBenchmarkPackagePublicationV1


class StudioBenchmarkExportResultV1(StudioBenchmarkReleaseModel):
    """Export command response including creation disposition."""

    schema_version: StrictInt = Field(default=1, ge=1, le=1)
    created: StrictBool
    package_export: StudioBenchmarkPackageExportV1


class StudioBenchmarkPackageRevisionReleaseSummaryV1(StudioBenchmarkReleaseModel):
    """Bounded immutable release summary for one Package revision."""

    package_revision_id: str
    authoring_revision_id: str
    validation_attestation_id: str
    package_identity: str = Field(min_length=1, max_length=384)
    package_content_identity: str
    closure_identity: str
    member_count: StrictInt = Field(ge=1, le=256)
    created_at: StrictInt = Field(ge=0)
    detail_link: str = Field(min_length=1, max_length=512)
    publication: StudioBenchmarkPackagePublicationV1 | None = None
    package_export: StudioBenchmarkPackageExportV1 | None = None

    @field_validator("package_revision_id")
    @classmethod
    def _package_revision_id(cls, value: str) -> str:
        """Validate the exact immutable Package identity.

        Args:
            value: Candidate Package revision identity.

        Raises:
            ValueError: Identity is malformed.

        Returns:
            Validated Package revision identity.
        """
        return validate_benchmark_package_revision_id(value)

    @field_validator("authoring_revision_id")
    @classmethod
    def _authoring_revision_id(cls, value: str) -> str:
        """Validate the exact immutable authoring revision identity.

        Args:
            value: Candidate authoring revision identity.

        Raises:
            ValueError: Identity is malformed.

        Returns:
            Validated authoring revision identity.
        """
        from .benchmark_authoring_models import (
            validate_benchmark_authoring_revision_id,
        )

        return validate_benchmark_authoring_revision_id(value)

    @field_validator("validation_attestation_id")
    @classmethod
    def _attestation_id(cls, value: str) -> str:
        """Validate the linked validation attestation identity.

        Args:
            value: Candidate attestation identity.

        Raises:
            ValueError: Identity is malformed.

        Returns:
            Validated attestation identity.
        """
        return validate_benchmark_validation_attestation_id(value)

    @field_validator("package_identity")
    @classmethod
    def _package_identity(cls, value: str) -> str:
        """Validate a bounded readable Package identity.

        Args:
            value: Candidate Package identity.

        Raises:
            ValueError: Identity contains private or unsafe text.

        Returns:
            Validated readable identity.
        """
        return _safe_text(value, limit=384)

    @field_validator("package_content_identity", "closure_identity")
    @classmethod
    def _digests(cls, value: str) -> str:
        """Validate one Package semantic SHA-256 identity.

        Args:
            value: Candidate prefixed digest.

        Raises:
            ValueError: Digest is malformed.

        Returns:
            Validated digest.
        """
        if _DIGEST.fullmatch(value) is None:
            raise ValueError("release summary identity must be a SHA-256 digest")
        return value

    @model_validator(mode="after")
    def _scoped_links_and_resources(
        self,
    ) -> "StudioBenchmarkPackageRevisionReleaseSummaryV1":
        """Bind the detail link and optional release facts to one Package.

        Raises:
            ValueError: A link or nested immutable resource changes ownership.

        Returns:
            Validated release summary.
        """
        expected_link = (
            "/api/studio/benchmark-authoring/drafts/"
            f"{self.publication.draft_id if self.publication else self.package_export.draft_id if self.package_export else ''}"
            f"/package-revisions/{self.package_revision_id}"
        )
        # The summary does not repeat draftId, so derive it from an attached
        # resource when present and otherwise enforce the exact route shape.
        if self.publication is None and self.package_export is None:
            parts = self.detail_link.split("/")
            if (
                len(parts) != 8
                or parts[:5]
                != ["", "api", "studio", "benchmark-authoring", "drafts"]
                or validate_benchmark_draft_id(parts[5]) != parts[5]
                or parts[6] != "package-revisions"
                or parts[7] != self.package_revision_id
            ):
                raise ValueError("Package revision detail link is unsafe")
        elif self.detail_link != expected_link:
            raise ValueError("Package revision detail link changes ownership")
        for resource in (self.publication, self.package_export):
            if resource is not None and (
                resource.package_revision_id != self.package_revision_id
                or resource.validation_attestation_id
                != self.validation_attestation_id
                or resource.package_identity != self.package_identity
                or resource.package_content_identity
                != self.package_content_identity
                or resource.closure_identity != self.closure_identity
            ):
                raise ValueError("release summary resource does not match Package")
        if (
            self.publication is not None
            and self.package_export is not None
            and self.publication.draft_id != self.package_export.draft_id
        ):
            raise ValueError("release summary resources disagree on ownership")
        return self

    @classmethod
    def from_package_revision(
        cls,
        package: StudioBenchmarkPackageRevisionV1,
        *,
        publication: StudioBenchmarkPackagePublicationV1 | None = None,
        package_export: StudioBenchmarkPackageExportV1 | None = None,
    ) -> "StudioBenchmarkPackageRevisionReleaseSummaryV1":
        """Project one immutable revision into a bounded release list item.

        Args:
            package: Exact owned frozen Package revision.
            publication: Optional durable publication for this revision.
            package_export: Optional durable export for this revision.

        Raises:
            ValueError: Linked release resources disagree with the Package.

        Returns:
            Strict bounded release summary.
        """
        for item in (publication, package_export):
            if item is not None and (
                item.draft_id != package.draft_id
                or item.package_revision_id != package.package_revision_id
                or item.package_identity != package.package_identity
                or item.package_content_identity != package.package_content_identity
                or item.closure_identity != package.closure_identity
            ):
                raise ValueError("release summary resources do not match Package")
        return cls(
            packageRevisionId=package.package_revision_id,
            authoringRevisionId=package.authoring_revision_id,
            validationAttestationId=package.validation_attestation_id,
            packageIdentity=package.package_identity,
            packageContentIdentity=package.package_content_identity,
            closureIdentity=package.closure_identity,
            memberCount=len(package.members),
            createdAt=package.created_at,
            detailLink=(
                "/api/studio/benchmark-authoring/drafts/"
                f"{package.draft_id}/package-revisions/{package.package_revision_id}"
            ),
            publication=publication,
            packageExport=package_export,
        )


class StudioBenchmarkPackageRevisionPageV1(StudioBenchmarkReleaseModel):
    """Stable draft-scoped page of immutable Package release candidates."""

    schema_version: StrictInt = Field(default=1, ge=1, le=1)
    items: tuple[StudioBenchmarkPackageRevisionReleaseSummaryV1, ...] = Field(
        max_length=STUDIO_BENCHMARK_PACKAGE_REVISION_PAGE_MAX
    )
    next_cursor: str | None = Field(default=None, max_length=2048)


class StudioBenchmarkStoredPublicationV1(StudioBenchmarkReleaseModel):
    """Private storage-neutral publication row with an opaque locator."""

    publication: StudioBenchmarkPackagePublicationV1
    managed_locator: str

    @field_validator("managed_locator")
    @classmethod
    def _locator(cls, value: str) -> str:
        """Restrict a managed Package locator to the publication identity.

        Args:
            value: Candidate opaque private locator.

        Raises:
            ValueError: Locator is malformed or does not match the record.

        Returns:
            Validated opaque locator.
        """
        return validate_benchmark_package_publication_id(value)

    @model_validator(mode="after")
    def _matching_locator(self) -> "StudioBenchmarkStoredPublicationV1":
        """Require the storage locator to carry no authority beyond the ID.

        Raises:
            ValueError: Locator and publication identity disagree.

        Returns:
            Validated durable publication row.
        """
        if self.managed_locator != self.publication.publication_id:
            raise ValueError("managed publication locator does not match identity")
        return self


class StudioBenchmarkStoredExportV1(StudioBenchmarkReleaseModel):
    """Private storage-neutral export row with an opaque archive locator."""

    package_export: StudioBenchmarkPackageExportV1
    archive_locator: str

    @field_validator("archive_locator")
    @classmethod
    def _locator(cls, value: str) -> str:
        """Restrict an archive locator to the export identity.

        Args:
            value: Candidate opaque private locator.

        Raises:
            ValueError: Locator is malformed.

        Returns:
            Validated opaque locator.
        """
        return validate_benchmark_package_export_id(value)

    @model_validator(mode="after")
    def _matching_locator(self) -> "StudioBenchmarkStoredExportV1":
        """Require the storage locator to carry no authority beyond the ID.

        Raises:
            ValueError: Locator and export identity disagree.

        Returns:
            Validated durable export row.
        """
        if self.archive_locator != self.package_export.export_id:
            raise ValueError("managed archive locator does not match identity")
        return self


__all__ = [
    "STUDIO_BENCHMARK_MANAGED_SOURCE_ID",
    "STUDIO_BENCHMARK_PACKAGE_EXPORT_CONTRACT",
    "STUDIO_BENCHMARK_PACKAGE_EXPORT_MAX_BYTES",
    "STUDIO_BENCHMARK_PACKAGE_REVISION_PAGE_MAX",
    "StudioBenchmarkExportResultV1",
    "StudioBenchmarkExportSafetyV1",
    "StudioBenchmarkPackageExportV1",
    "StudioBenchmarkPackagePublicationV1",
    "StudioBenchmarkPackageRevisionPageV1",
    "StudioBenchmarkPackageRevisionReleaseSummaryV1",
    "StudioBenchmarkPublicationResultV1",
    "StudioBenchmarkPublicationSafetyV1",
    "StudioBenchmarkReleaseCommandV1",
    "StudioBenchmarkStoredExportV1",
    "StudioBenchmarkStoredPublicationV1",
    "benchmark_release_request_fingerprint",
    "validate_benchmark_package_export_id",
    "validate_benchmark_package_publication_id",
]
