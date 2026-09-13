"""Clean-wheel acceptance for Studio Benchmark authoring resources."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest


@pytest.mark.packaging_acceptance
def test_installed_wheel_runs_no_device_authoring_restart_journey(
    isolated_install: tuple[Path, Path, dict[str, str]],
) -> None:
    """Create/import/save/restart using only an isolated installed wheel.

    Args:
        isolated_install: Isolated Python, unrelated workdir, and clean env.

    Raises:
        AssertionError: Packaging isolation or authoring behavior fails.

    Returns:
        None.
    """
    python, workdir, clean_env = isolated_install
    scenario = workdir / "benchmark-authoring"
    scenario.mkdir()
    script = r"""
import json
import pathlib
import sys
from io import BytesIO

import zhixing
from zhixing.benchmark import scaffold_benchmark_package
from zhixing.studio import (
    LocalStudioBenchmarkManagedContent,
    SQLiteStudioBenchmarkAuthoringRepository,
    StudioBenchmarkAuthoringApplicationService,
    StudioBenchmarkAuthoringContentApplicationService,
    StudioBenchmarkAuthoringContentRemoveRequestV1,
    StudioBenchmarkAuthoringContentReplaceRequestV1,
    StudioBenchmarkAuthoringContentUploadRequestV1,
    StudioBenchmarkAuthoringIdempotencyConflictError,
    StudioBenchmarkAuthoringNotFoundError,
    StudioBenchmarkAuthoringPackageAdapter,
    StudioBenchmarkCatalogService,
    StudioBenchmarkSource,
    default_studio_benchmark_authoring_root,
)

workdir = pathlib.Path(sys.argv[1])
assert pathlib.Path(zhixing.__file__).resolve().is_relative_to(
    pathlib.Path(sys.prefix).resolve()
)
package = scaffold_benchmark_package(
    workdir / "catalog-package",
    name="installed-catalog-source",
    publisher="tests",
    template="dynamic-task",
)
catalog = StudioBenchmarkCatalogService(
    (
        StudioBenchmarkSource(
            source_id="installed-wheel-fixture",
            kind="package",
            locator=package,
        ),
    )
)
database = workdir / "studio.sqlite3"


def build_service():
    '''Build one restartable installed authoring composition.

    Returns:
        Definition service, managed-content service, and repository.
    '''
    repository = SQLiteStudioBenchmarkAuthoringRepository(database)
    content = LocalStudioBenchmarkManagedContent(
        default_studio_benchmark_authoring_root(database)
    )
    return (
        StudioBenchmarkAuthoringApplicationService(
            repository=repository,
            packages=StudioBenchmarkAuthoringPackageAdapter(
                content,
                staging_root=content.staging_root,
            ),
            catalog=catalog,
        ),
        StudioBenchmarkAuthoringContentApplicationService(
            repository=repository,
            content=content,
        ),
        repository,
    )


service, content_service, repository = build_service()
template = service.create_draft(
    {
        "schemaVersion": 1,
        "clientRequestId": "wheel-template",
        "name": "Wheel Template",
        "source": {
            "kind": "template",
            "template": "minimal",
            "publisher": "tests",
            "packageName": "wheel-template",
            "version": "0.1.0",
        },
    }
)
entry_id = catalog.list_entries().items[0].catalog_entry_id
imported = service.create_draft(
    {
        "schemaVersion": 1,
        "clientRequestId": "wheel-catalog",
        "name": "Wheel Import",
        "source": {
            "kind": "catalog",
            "catalogEntryId": entry_id,
        },
    }
)
document = template.revision.document.model_dump(
    mode="json",
    by_alias=True,
    exclude_none=True,
)
document["manifest"]["document"]["title"] = "Saved after install"
saved = service.save_revision(
    template.draft.draft_id,
    {
        "schemaVersion": 1,
        "clientRequestId": "wheel-save",
        "baseRevisionId": template.revision.revision_id,
        "document": document,
    },
)
upload_request = StudioBenchmarkAuthoringContentUploadRequestV1(
    clientRequestId="wheel-content-upload",
    baseRevisionId=saved.revision.revision_id,
    resourceId="wheel-asset",
    kind="asset",
    path="assets/wheel.txt",
    mediaType="text/plain",
)
uploaded = content_service.upload(
    template.draft.draft_id,
    upload_request,
    BytesIO(b"installed upload"),
)
replacement_request = StudioBenchmarkAuthoringContentReplaceRequestV1(
    clientRequestId="wheel-content-replace",
    baseRevisionId=uploaded.revision.revision_id,
    resourceId="wheel-asset",
    mediaType="text/markdown",
)
replaced = content_service.replace(
    template.draft.draft_id,
    replacement_request,
    BytesIO(b"installed replacement"),
)
old_read = content_service.open_content(
    template.draft.draft_id,
    uploaded.revision.revision_id,
    "wheel-asset",
)
try:
    assert old_read.stream.read() == b"installed upload"
finally:
    old_read.stream.close()
removed = content_service.remove(
    template.draft.draft_id,
    StudioBenchmarkAuthoringContentRemoveRequestV1(
        clientRequestId="wheel-content-remove",
        baseRevisionId=replaced.revision.revision_id,
        resourceId="wheel-asset",
    ),
)
late_retry = content_service.upload(
    template.draft.draft_id,
    upload_request,
    BytesIO(b"installed upload"),
)
assert late_retry.created is False
assert late_retry.revision == uploaded.revision
try:
    content_service.upload(
        template.draft.draft_id,
        upload_request,
        BytesIO(b"different installed retry"),
    )
except StudioBenchmarkAuthoringIdempotencyConflictError:
    pass
else:
    raise AssertionError("different-byte command reuse did not conflict")

restarted, restarted_content, _repository = build_service()
assert restarted.get_draft(template.draft.draft_id).current_revision == (
    removed.revision
)
assert restarted.get_draft(imported.draft.draft_id).current_revision == (
    imported.revision
)
historical = restarted_content.open_content(
    template.draft.draft_id,
    replaced.revision.revision_id,
    "wheel-asset",
)
try:
    assert historical.stream.read() == b"installed replacement"
finally:
    historical.stream.close()
try:
    restarted_content.open_content(
        template.draft.draft_id,
        removed.revision.revision_id,
        "wheel-asset",
    )
except StudioBenchmarkAuthoringNotFoundError:
    pass
else:
    raise AssertionError("removed current resource remained readable")
retry = restarted.create_draft(
    {
        "schemaVersion": 1,
        "clientRequestId": "wheel-catalog",
        "name": "Wheel Import",
        "source": {
            "kind": "catalog",
            "catalogEntryId": entry_id,
        },
    }
)
assert retry.created is False
assert len(restarted.list_drafts().items) == 2
print(
    json.dumps(
        {
            "drafts": 2,
            "savedOrdinal": saved.revision.ordinal,
            "retryCreated": retry.created,
            "contentRetryCreated": late_retry.created,
            "contentOrdinal": removed.revision.ordinal,
            "historicalRead": True,
            "deviceAccessed": False,
            "experimentCreated": False,
            "reportCreated": False,
            "replayCreated": False,
        },
        sort_keys=True,
    )
)
"""
    completed = subprocess.run(
        [str(python), "-c", script, str(scenario)],
        cwd=workdir,
        env=clean_env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result == {
        "deviceAccessed": False,
        "drafts": 2,
        "contentOrdinal": 5,
        "contentRetryCreated": False,
        "experimentCreated": False,
        "historicalRead": True,
        "reportCreated": False,
        "replayCreated": False,
        "retryCreated": False,
        "savedOrdinal": 2,
    }


@pytest.mark.packaging_acceptance
def test_installed_wheel_runs_revision_bound_validation_and_dry_run(
    isolated_openai_install: tuple[Path, Path, dict[str, str]],
) -> None:
    """Analyze exact authoring revisions from a repository-independent wheel.

    Args:
        isolated_openai_install: Isolated wheel plus its declared OpenAI extra.

    Raises:
        AssertionError: Packaging isolation, exact-current validation, Agent
            verification, schedule bounds, or restart behavior fails.

    Returns:
        None.
    """
    python, workdir, clean_env = isolated_openai_install
    scenario = workdir / "benchmark-authoring-analysis"
    scenario.mkdir()
    script = r"""
import json
import pathlib
import sqlite3
import sys

import zhixing
from zhixing.studio import (
    LocalStudioBenchmarkManagedContent,
    SQLiteAgentDocumentRepository,
    SQLiteStudioBenchmarkAuthoringRepository,
    StudioApplicationService,
    StudioBenchmarkAuthoringApplicationService,
    StudioBenchmarkAuthoringPackageAdapter,
    StudioBenchmarkCatalogService,
    build_studio_component_catalog,
    default_studio_benchmark_authoring_root,
)
from zhixing.studio.benchmark_authoring_analysis import (
    StudioBenchmarkValidationDryRunApplicationService,
)
from zhixing.studio.benchmark_authoring_errors import (
    StudioBenchmarkAuthoringRevisionConflictError,
)
from zhixing.studio.benchmark_authoring_materializer import (
    StudioBenchmarkAuthoringPackageMaterializer,
)
from zhixing.studio.flow_template_loader import get_flow_template_document

workdir = pathlib.Path(sys.argv[1])
installed_root = pathlib.Path(sys.prefix).resolve()
assert pathlib.Path(zhixing.__file__).resolve().is_relative_to(installed_root)
database = workdir / "studio.sqlite3"
components = build_studio_component_catalog()


def build_services():
    '''Build restartable definition and analysis services from installed code.

    Returns:
        Definition service, analysis service, repository, content store, and
        immutable Agent repository.
    '''
    repository = SQLiteStudioBenchmarkAuthoringRepository(database)
    content = LocalStudioBenchmarkManagedContent(
        default_studio_benchmark_authoring_root(database)
    )
    agents = SQLiteAgentDocumentRepository(database)
    definition = StudioBenchmarkAuthoringApplicationService(
        repository=repository,
        packages=StudioBenchmarkAuthoringPackageAdapter(
            content,
            staging_root=content.staging_root,
        ),
        catalog=StudioBenchmarkCatalogService(),
    )
    analysis = StudioBenchmarkValidationDryRunApplicationService(
        repository=repository,
        materializer=StudioBenchmarkAuthoringPackageMaterializer(
            content,
            staging_root=content.staging_root / "analysis",
        ),
        agents=agents,
        contract_catalog=components.node_contract_catalog(),
    )
    return definition, analysis, repository, content, agents


def create_draft(definition, name, request_id):
    '''Create one independent installed-wheel minimal draft.

    Args:
        definition: Installed definition application service.
        name: Package and display-name suffix.
        request_id: Unique idempotency identity.

    Returns:
        Newly created draft and immutable revision response.
    '''
    return definition.create_draft(
        {
            "schemaVersion": 1,
            "clientRequestId": request_id,
            "name": name,
            "source": {
                "kind": "template",
                "template": "minimal",
                "publisher": "tests",
                "packageName": name,
                "version": "0.1.0",
            },
        }
    )


def validation_request(revision_id):
    '''Return one strict exact-current validation envelope.'''
    return {"schemaVersion": 1, "revisionId": revision_id, "split": "test"}


def dry_run_request(revision_id, agent_id, agent_revision_id):
    '''Return one strict exact-current dry-run envelope.'''
    return {
        "schemaVersion": 1,
        "revisionId": revision_id,
        "split": "test",
        "taskIds": [],
        "agentRevisions": [
            {"agentId": agent_id, "revisionId": agent_revision_id}
        ],
    }


definition, analysis, repository, content, agents = build_services()
agent_service = StudioApplicationService(catalog=components, repository=agents)
agent, agent_revision = agent_service.create_agent(
    "Installed Analysis Agent",
    initial_document=get_flow_template_document("modular_baseline"),
)
assert agent_revision.compile_snapshot.status == "valid"

valid_created = create_draft(definition, "wheel-analysis", "wheel-analysis-valid")
valid_request = analysis.parse_validation_request(
    validation_request(valid_created.revision.revision_id)
)
first_valid = analysis.validate(valid_created.draft.draft_id, valid_request)
second_valid = analysis.validate(valid_created.draft.draft_id, valid_request)
assert first_valid == second_valid
assert first_valid.valid
assert first_valid.identities.package == "tests/wheel-analysis@0.1.0"
assert first_valid.identities.package_content.startswith("sha256:")
assert first_valid.identities.benchmark_plan.startswith("sha256:")
assert first_valid.identities.experiment_protocol.startswith("sha256:")

valid_dry_run = analysis.dry_run(
    valid_created.draft.draft_id,
    analysis.parse_dry_run_request(
        dry_run_request(
            valid_created.revision.revision_id,
            agent.agent_id,
            agent_revision.revision_id,
        )
    ),
)
assert valid_dry_run.ok
assert len(valid_dry_run.schedule) == 1
assert valid_dry_run.agent_revisions[0].agent_graph_identity.startswith("sha256:")

missing_agent = analysis.dry_run(
    valid_created.draft.draft_id,
    analysis.parse_dry_run_request(
        dry_run_request(
            valid_created.revision.revision_id,
            "agent-" + "a" * 32,
            "revision-" + "b" * 32,
        )
    ),
)
assert not missing_agent.ok
assert missing_agent.schedule == ()
assert any(item.member_kind == "agent" for item in missing_agent.diagnostics)

invalid_created = create_draft(definition, "wheel-invalid", "wheel-analysis-invalid")
invalid_document = invalid_created.revision.document.model_dump(
    mode="json", by_alias=True
)
invalid_document["taskFiles"][0]["tasks"][0]["max_steps"] = 0
invalid_saved = definition.save_revision(
    invalid_created.draft.draft_id,
    {
        "schemaVersion": 1,
        "clientRequestId": "wheel-analysis-invalid-save",
        "baseRevisionId": invalid_created.revision.revision_id,
        "document": invalid_document,
    },
)
invalid = analysis.validate(
    invalid_created.draft.draft_id,
    analysis.parse_validation_request(
        validation_request(invalid_saved.revision.revision_id)
    ),
)
assert not invalid.valid
assert invalid.identities.package == "tests/wheel-invalid@0.1.0"
assert invalid.identities.benchmark_plan is None

try:
    analysis.validate(
        invalid_created.draft.draft_id,
        analysis.parse_validation_request(
            validation_request(invalid_created.revision.revision_id)
        ),
    )
except StudioBenchmarkAuthoringRevisionConflictError as error:
    assert error.current_revision_id == invalid_saved.revision.revision_id
else:
    raise AssertionError("installed analysis accepted a stale revision")

missing_created = create_draft(definition, "wheel-missing", "wheel-analysis-missing")
missing_document = missing_created.revision.document.model_dump(
    mode="json", by_alias=True
)
missing_digest = "c" * 64
missing_document["manifest"]["document"]["resources"] = [
    {
        "id": "missing",
        "kind": "asset",
        "path": "assets/missing.txt",
        "media_type": "text/plain",
        "sha256": "sha256:" + missing_digest,
        "size": 7,
    }
]
missing_document["resources"] = [
    {
        "id": "missing",
        "kind": "asset",
        "path": "assets/missing.txt",
        "mediaType": "text/plain",
        "sha256": "sha256:" + missing_digest,
        "size": 7,
        "contentIdentity": "benchmark-content-" + missing_digest,
    }
]
missing_saved = definition.save_revision(
    missing_created.draft.draft_id,
    {
        "schemaVersion": 1,
        "clientRequestId": "wheel-analysis-missing-save",
        "baseRevisionId": missing_created.revision.revision_id,
        "document": missing_document,
    },
)
missing = analysis.validate(
    missing_created.draft.draft_id,
    analysis.parse_validation_request(
        validation_request(missing_saved.revision.revision_id)
    ),
)
assert not missing.valid
assert any(
    item.code == "benchmark.resource.content_unavailable"
    for item in missing.diagnostics
)

bounded_created = create_draft(definition, "wheel-bounded", "wheel-analysis-bounded")
bounded_document = bounded_created.revision.document.model_dump(
    mode="json", by_alias=True
)
bounded_document["protocolFiles"][0]["document"]["repeats"] = 10_000
bounded_saved = definition.save_revision(
    bounded_created.draft.draft_id,
    {
        "schemaVersion": 1,
        "clientRequestId": "wheel-analysis-bounded-save",
        "baseRevisionId": bounded_created.revision.revision_id,
        "document": bounded_document,
    },
)
bounded = analysis.dry_run(
    bounded_created.draft.draft_id,
    analysis.parse_dry_run_request(
        dry_run_request(
            bounded_saved.revision.revision_id,
            agent.agent_id,
            agent_revision.revision_id,
        )
    ),
)
assert bounded.ok
assert len(bounded.schedule) == 10_000

restarted_definition, restarted_analysis, _, _, _ = build_services()
restarted_valid = restarted_analysis.validate(
    valid_created.draft.draft_id,
    restarted_analysis.parse_validation_request(
        validation_request(valid_created.revision.revision_id)
    ),
)
assert restarted_valid.identities == first_valid.identities
assert (
    restarted_definition.get_draft(valid_created.draft.draft_id).current_revision
    == valid_created.revision
)
with sqlite3.connect(database) as connection:
    schema_version = connection.execute(
        "SELECT MAX(version) FROM studio_schema_migrations"
    ).fetchone()[0]
assert schema_version == 12
assert not tuple((content.staging_root / "analysis").iterdir())
print(
    json.dumps(
        {
            "agentRevisionVerified": (
                valid_dry_run.agent_revisions[0].revision_id
                == agent_revision.revision_id
            ),
            "boundedSchedule": len(bounded.schedule),
            "deterministicIdentities": first_valid == second_valid,
            "invalid": not invalid.valid,
            "missingAgentRejected": not missing_agent.ok,
            "missingResource": not missing.valid,
            "restart": restarted_valid.identities == first_valid.identities,
            "schemaVersion": schema_version,
            "sourceIsInstalledWheel": True,
            "staleRejected": True,
            "valid": first_valid.valid,
        },
        sort_keys=True,
    )
)
"""
    completed = subprocess.run(
        [str(python), "-c", script, str(scenario)],
        cwd=workdir,
        env=clean_env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result == {
        "agentRevisionVerified": True,
        "boundedSchedule": 10_000,
        "deterministicIdentities": True,
        "invalid": True,
        "missingAgentRejected": True,
        "missingResource": True,
        "restart": True,
        "schemaVersion": 12,
        "sourceIsInstalledWheel": True,
        "staleRejected": True,
        "valid": True,
    }


@pytest.mark.packaging_acceptance
def test_installed_wheel_runs_exact_revision_contract_tests(
    isolated_install: tuple[Path, Path, dict[str, str]],
) -> None:
    """Run the reviewed profile against one exact installed-wheel revision.

    Args:
        isolated_install: Isolated Python, unrelated workdir, and clean env.

    Raises:
        AssertionError: Profile discovery, exact-revision compilation, fixture
            execution, packaging isolation, or side-effect bounds fail.

    Returns:
        None.
    """
    python, workdir, clean_env = isolated_install
    scenario = workdir / "benchmark-authoring-contract-tests"
    scenario.mkdir()
    script = r"""
import json
import pathlib
import sqlite3
import sys

import zhixing
from zhixing.benchmark.authoring import studio_fixture_profile_registry
from zhixing.studio import (
    LocalStudioBenchmarkManagedContent,
    SQLiteAgentDocumentRepository,
    SQLiteStudioBenchmarkAuthoringRepository,
    StudioBenchmarkAuthoringApplicationService,
    StudioBenchmarkAuthoringPackageAdapter,
    StudioBenchmarkCatalogService,
    default_studio_benchmark_authoring_root,
)
from zhixing.studio.benchmark_authoring_analysis import (
    StudioBenchmarkAuthoringRevisionCompiler,
)
from zhixing.studio.benchmark_authoring_contracts import (
    StudioBenchmarkContractTestApplicationService,
)
from zhixing.studio.benchmark_authoring_materializer import (
    StudioBenchmarkAuthoringPackageMaterializer,
)

workdir = pathlib.Path(sys.argv[1])
installed_root = pathlib.Path(sys.prefix).resolve()
assert pathlib.Path(zhixing.__file__).resolve().is_relative_to(installed_root)
database = workdir / "studio.sqlite3"
repository = SQLiteStudioBenchmarkAuthoringRepository(database)
content = LocalStudioBenchmarkManagedContent(
    default_studio_benchmark_authoring_root(database)
)
definition = StudioBenchmarkAuthoringApplicationService(
    repository=repository,
    packages=StudioBenchmarkAuthoringPackageAdapter(
        content,
        staging_root=content.staging_root,
    ),
    catalog=StudioBenchmarkCatalogService(),
)
created = definition.create_draft(
    {
        "schemaVersion": 1,
        "clientRequestId": "wheel-contract-tests",
        "name": "Wheel Contract Tests",
        "source": {
            "kind": "template",
            "template": "minimal",
            "publisher": "tests",
            "packageName": "wheel-contract-tests",
            "version": "0.1.0",
        },
    }
)
compiler = StudioBenchmarkAuthoringRevisionCompiler(
    repository=repository,
    materializer=StudioBenchmarkAuthoringPackageMaterializer(
        content,
        staging_root=content.staging_root / "contract-tests",
    ),
    agents=SQLiteAgentDocumentRepository(database),
)
service = StudioBenchmarkContractTestApplicationService(
    compiler=compiler,
    profiles=studio_fixture_profile_registry(),
)
profiles = service.list_profiles()
assert len(profiles.profiles) == 1
assert profiles.profiles[0].profile_id == "studio-safe-v1"
assert profiles.profiles[0].version == "1.0.0"
before = repository.get_draft(created.draft.draft_id)
request = service.parse_request(
    {
        "schemaVersion": 1,
        "revisionId": created.revision.revision_id,
        "split": "test",
        "seed": 55,
        "fixtureProfileId": "studio-safe-v1",
    }
)
first = service.run(created.draft.draft_id, request)
second = service.run(created.draft.draft_id, request)
after = repository.get_draft(created.draft.draft_id)
assert first == second
assert first.valid_definition
assert first.revision_id == created.revision.revision_id
assert first.identities.package == "tests/wheel-contract-tests@0.1.0"
assert first.identities.benchmark_plan.startswith("sha256:")
assert first.coverage.total == 1
assert first.coverage.passed == 1
assert first.coverage.complete
assert first.coverage.executed_checks_passed
assert first.cases[0].logical_name == "file_exist"
assert first.cases[0].status == "passed"
assert first.safety.package_code_executed is False
assert first.safety.real_device_evidence is False
assert first.safety.process_sandbox is False
assert first.safety.device_capability is False
assert first.safety.model_capability is False
assert first.safety.network_capability is False
assert first.safety.secret_capability is False
assert first.safety.runtime_capability is False
assert first.safety.experiment_capability is False
assert first.safety.output_path_capability is False
assert first.safety.benchmark_execution is False
assert first.safety.agent_execution is False
assert first.safety.publication_eligibility is False
assert first.safety.result_persisted is False
assert before == after
with sqlite3.connect(database) as connection:
    schema_version = connection.execute(
        "SELECT MAX(version) FROM studio_schema_migrations"
    ).fetchone()[0]
assert schema_version == 12
assert not tuple((content.staging_root / "contract-tests").iterdir())
serialized = first.model_dump_json(by_alias=True)
assert str(pathlib.Path.cwd()) not in serialized
print(
    json.dumps(
        {
            "cases": first.coverage.total,
            "deterministic": first == second,
            "profile": profiles.profiles[0].profile_id,
            "revisionUnchanged": before == after,
            "schemaVersion": schema_version,
            "sourceIsInstalledWheel": True,
            "zeroExternalCapabilities": (
                not first.safety.device_capability
                and not first.safety.model_capability
                and not first.safety.network_capability
                and not first.safety.secret_capability
                and not first.safety.runtime_capability
            ),
        },
        sort_keys=True,
    )
)
"""
    completed = subprocess.run(
        [str(python), "-c", script, str(scenario)],
        cwd=workdir,
        env=clean_env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result == {
        "cases": 1,
        "deterministic": True,
        "profile": "studio-safe-v1",
        "revisionUnchanged": True,
        "schemaVersion": 12,
        "sourceIsInstalledWheel": True,
        "zeroExternalCapabilities": True,
    }


@pytest.mark.packaging_acceptance
def test_installed_wheel_freezes_and_reconstructs_exact_current_package(
    isolated_install: tuple[Path, Path, dict[str, str]],
) -> None:
    """Freeze a managed multi-split Package from an unrelated working tree.

    Args:
        isolated_install: Isolated Python, unrelated workdir, and clean env.

    Raises:
        AssertionError: Installed imports, freeze integrity, restart, schema,
            or excluded runtime boundaries fail.

    Returns:
        None.
    """
    python, workdir, clean_env = isolated_install
    scenario = workdir / "benchmark-authoring-freeze"
    scenario.mkdir()
    script = r"""
import copy
import json
import pathlib
import sqlite3
import sys

import zhixing
from zhixing.studio import (
    LocalStudioBenchmarkManagedContent,
    SQLiteAgentDocumentRepository,
    SQLiteStudioBenchmarkAuthoringRepository,
    StudioBenchmarkAuthoringApplicationService,
    StudioBenchmarkAuthoringPackageAdapter,
    StudioBenchmarkCatalogService,
    default_studio_benchmark_authoring_root,
)
from zhixing.studio.benchmark_authoring_analysis import (
    StudioBenchmarkAuthoringRevisionCompiler,
)
from zhixing.studio.benchmark_authoring_freeze import (
    StudioBenchmarkFrozenClosureBuilder,
)
from zhixing.studio.benchmark_authoring_freeze_service import (
    StudioBenchmarkValidatedFreezeAnalyzer,
    StudioBenchmarkValidatedFreezeApplicationService,
)
from zhixing.studio.benchmark_authoring_materializer import (
    StudioBenchmarkAuthoringPackageMaterializer,
)

workdir = pathlib.Path(sys.argv[1])
installed_root = pathlib.Path(sys.prefix).resolve()
assert pathlib.Path(zhixing.__file__).resolve().is_relative_to(installed_root)
database = workdir / "studio.sqlite3"


def build_services():
    '''Build one restartable exact-current validated-freeze composition.

    Returns:
        Definition service, freeze service, repository, and managed content.
    '''
    repository = SQLiteStudioBenchmarkAuthoringRepository(database)
    content = LocalStudioBenchmarkManagedContent(
        default_studio_benchmark_authoring_root(database)
    )
    definition = StudioBenchmarkAuthoringApplicationService(
        repository=repository,
        packages=StudioBenchmarkAuthoringPackageAdapter(
            content,
            staging_root=content.staging_root,
        ),
        catalog=StudioBenchmarkCatalogService(),
    )
    compiler = StudioBenchmarkAuthoringRevisionCompiler(
        repository=repository,
        materializer=StudioBenchmarkAuthoringPackageMaterializer(
            content,
            staging_root=content.staging_root / "freeze-analysis",
        ),
        agents=SQLiteAgentDocumentRepository(database),
    )
    freeze = StudioBenchmarkValidatedFreezeApplicationService(
        repository=repository,
        analyzer=StudioBenchmarkValidatedFreezeAnalyzer(compiler),
        closure_builder=StudioBenchmarkFrozenClosureBuilder(content),
    )
    return definition, freeze, repository, content


definition, freeze, repository, content = build_services()
created = definition.create_draft(
    {
        "schemaVersion": 1,
        "clientRequestId": "wheel-freeze-create",
        "name": "Wheel Freeze",
        "source": {
            "kind": "template",
            "template": "minimal",
            "publisher": "tests",
            "packageName": "wheel-freeze",
            "version": "0.1.0",
        },
    }
)
document = created.revision.document.model_dump(mode="json", by_alias=True)
dev_task = copy.deepcopy(document["taskFiles"][0]["tasks"][0])
dev_task["id"] = "wheel-dev-task"
document["manifest"]["document"]["splits"] = {
    "test": {"files": ["tasks/test.json"]},
    "dev": {"files": ["tasks/dev.json"]},
}
document["taskFiles"] = [
    {"path": "tasks/dev.json", "tasks": [dev_task]},
    document["taskFiles"][0],
]
content_identity, sha256, size = content.store_bytes(
    b'{"expected":true}\n', max_bytes=1024
)
manifest_resource = {
    "id": "wheel-truth",
    "kind": "ground_truth",
    "path": "ground_truth/wheel.json",
    "media_type": "application/json",
    "sha256": sha256,
    "size": size,
}
document["manifest"]["document"]["resources"] = [manifest_resource]
document["resources"] = [
    {
        "id": "wheel-truth",
        "kind": "ground_truth",
        "path": "ground_truth/wheel.json",
        "mediaType": "application/json",
        "sha256": sha256,
        "size": size,
        "contentIdentity": content_identity,
    }
]
saved = definition.save_revision(
    created.draft.draft_id,
    {
        "schemaVersion": 1,
        "clientRequestId": "wheel-freeze-save",
        "baseRevisionId": created.revision.revision_id,
        "document": document,
    },
)
request = freeze.parse_request(
    {
        "schemaVersion": 1,
        "clientRequestId": "wheel-freeze-command",
        "revisionId": saved.revision.revision_id,
    }
)
before = repository.get_draft(created.draft.draft_id)
first = freeze.freeze(created.draft.draft_id, request)
retry = freeze.freeze(created.draft.draft_id, request)
after = repository.get_draft(created.draft.draft_id)
assert first.created
assert not retry.created
assert first.detail == retry.detail
assert before == after
assert after.current_revision_id == saved.revision.revision_id
assert saved.revision.status == "unvalidated"
assert len(first.detail.validation_attestation.splits) == 2
assert first.detail.validation_attestation.safety.execution_evidence is False
assert first.detail.validation_attestation.safety.publication_evidence is False
assert len(first.detail.package_revision.members) == 5
for member in first.detail.package_revision.members:
    with content.open_verified(
        member.content_identity,
        expected_sha256=member.sha256,
        expected_size=member.size,
    ) as stream:
        assert len(stream.read()) == member.size

_, restarted_freeze, restarted_repository, restarted_content = build_services()
restarted = restarted_freeze.get_package_revision(
    created.draft.draft_id,
    first.detail.package_revision.package_revision_id,
)
assert restarted == first.detail
assert not tuple((restarted_content.staging_root / "freeze-analysis").iterdir())
assert set(vars(restarted_freeze)) == {
    "_repository",
    "_analyzer",
    "_closure_builder",
    "_clock",
    "_identity_factory",
}
with sqlite3.connect(database) as connection:
    schema_version = connection.execute(
        "SELECT MAX(version) FROM studio_schema_migrations"
    ).fetchone()[0]
    experiments = connection.execute(
        "SELECT COUNT(*) FROM studio_benchmark_experiments"
    ).fetchone()[0]
    artifacts = connection.execute(
        "SELECT COUNT(*) FROM studio_benchmark_artifacts"
    ).fetchone()[0]
    replays = connection.execute(
        "SELECT COUNT(*) FROM studio_replays"
    ).fetchone()[0]
print(
    json.dumps(
        {
            "created": first.created,
            "members": len(first.detail.package_revision.members),
            "restart": restarted == first.detail,
            "retryCreated": retry.created,
            "schemaVersion": schema_version,
            "sourceIsInstalledWheel": True,
            "splits": len(first.detail.validation_attestation.splits),
            "sourceUnchanged": before == after,
            "zeroRuntimeProducts": experiments + artifacts + replays == 0,
        },
        sort_keys=True,
    )
)
"""
    completed = subprocess.run(
        [str(python), "-c", script, str(scenario)],
        cwd=workdir,
        env=clean_env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result == {
        "created": True,
        "members": 5,
        "restart": True,
        "retryCreated": False,
        "schemaVersion": 12,
        "sourceIsInstalledWheel": True,
        "sourceUnchanged": True,
        "splits": 2,
        "zeroRuntimeProducts": True,
    }


@pytest.mark.packaging_acceptance
def test_installed_wheel_migrates_legacy_json_without_runtime_capabilities(
    isolated_install: tuple[Path, Path, dict[str, str]],
) -> None:
    """Preview, Confirm, and restart migration from an unrelated clean wheel.

    Args:
        isolated_install: Isolated Python, unrelated workdir, and clean env.

    Raises:
        AssertionError: Packaging isolation or migration behavior fails.

    Returns:
        None.
    """
    python, workdir, clean_env = isolated_install
    scenario = workdir / "benchmark-legacy-migration"
    scenario.mkdir()
    script = r"""
import hashlib
import json
import pathlib
import sqlite3
import sys

import zhixing
from zhixing.studio import (
    SQLiteStudioBenchmarkAuthoringRepository,
    StudioBenchmarkLegacyMigrationApplicationService,
)

root = pathlib.Path(sys.argv[1])
assert pathlib.Path(zhixing.__file__).resolve().is_relative_to(
    pathlib.Path(sys.prefix).resolve()
)
database = root / "studio.sqlite3"
source_path = root / "legacy.json"
source_path.write_text(json.dumps([{
    "id": "wheel-legacy-task",
    "instruction": "Complete the task",
    "type": "static",
    "task_initializer": {},
    "environment_initializer": [],
    "cleanup_initializer": [],
    "evaluator": {
        "name": "system_state",
        "params": {"method": "file_exist", "file_path": "/sdcard/result.txt"},
    },
    "app": "clock",
    "requires_login": False,
}]), encoding="utf-8")
before = hashlib.sha256(source_path.read_bytes()).hexdigest()
payload = {
    "schemaVersion": 1,
    "sourceName": source_path.name,
    "sourceText": source_path.read_text(encoding="utf-8"),
    "target": {
        "draftName": "Installed legacy migration",
        "publisher": "tests",
        "packageName": "installed-legacy",
        "version": "0.1.0",
        "title": "Installed legacy migration",
        "platform": "android",
        "split": "test",
        "taskFilePath": "tasks/imported.json",
    },
}
service = StudioBenchmarkLegacyMigrationApplicationService(
    repository=SQLiteStudioBenchmarkAuthoringRepository(database)
)
preview = service.preview(service.parse_preview_request(payload))
assert preview.confirmable is True
confirm_payload = {
    **payload,
    "clientRequestId": "wheel-legacy-confirm",
    "previewFingerprint": preview.preview_fingerprint,
    "migrationContractIdentity": preview.migration_contract_identity,
}
created = service.confirm(service.parse_confirm_request(confirm_payload))
restarted = StudioBenchmarkLegacyMigrationApplicationService(
    repository=SQLiteStudioBenchmarkAuthoringRepository(database)
)
replayed = restarted.confirm(restarted.parse_confirm_request(confirm_payload))
with sqlite3.connect(database) as connection:
    runtime_products = sum(
        connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in (
            "studio_benchmark_experiments",
            "studio_benchmark_artifacts",
            "studio_replays",
        )
    )
print(json.dumps({
    "created": created.created,
    "replayed": replayed.created,
    "sourceUnchanged": hashlib.sha256(source_path.read_bytes()).hexdigest() == before,
    "status": replayed.revision.status,
    "provenance": replayed.revision.provenance.source_kind,
    "falseEvidence": set(preview.evidence.model_dump().values()) == {False},
    "runtimeProducts": runtime_products,
    "serviceCapabilities": sorted(vars(service)),
}, sort_keys=True))
"""
    completed = subprocess.run(
        [str(python), "-c", script, str(scenario)],
        cwd=workdir,
        env=clean_env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    result = json.loads(completed.stdout)
    assert result == {
        "created": True,
        "falseEvidence": True,
        "provenance": "legacy_migration",
        "replayed": False,
        "runtimeProducts": 0,
        "serviceCapabilities": ["_analyzer", "_repository"],
        "sourceUnchanged": True,
        "status": "unvalidated",
    }


@pytest.mark.packaging_acceptance
def test_installed_wheel_publishes_and_exports_frozen_package(
    isolated_install: tuple[Path, Path, dict[str, str]],
) -> None:
    """Publish, export, verify, and reconstruct schema-10 release authority.

    Args:
        isolated_install: Isolated Python, unrelated workdir, and clean env.

    Raises:
        AssertionError: Installed release, deterministic archive, restart,
            source immutability, or zero-runtime boundaries fail.

    Returns:
        None.
    """
    python, workdir, clean_env = isolated_install
    scenario = workdir / "benchmark-package-release"
    scenario.mkdir()
    script = r"""
import json
import pathlib
import sqlite3
import sys

import zhixing
from zhixing.studio import (
    LocalStudioBenchmarkManagedContent,
    SQLiteAgentDocumentRepository,
    SQLiteStudioBenchmarkAuthoringRepository,
    StudioBenchmarkAuthoringApplicationService,
    StudioBenchmarkAuthoringPackageAdapter,
    StudioBenchmarkCatalogService,
    default_studio_benchmark_authoring_root,
)
from zhixing.studio.benchmark_authoring_analysis import (
    StudioBenchmarkAuthoringRevisionCompiler,
)
from zhixing.studio.benchmark_authoring_freeze import (
    StudioBenchmarkFrozenClosureBuilder,
)
from zhixing.studio.benchmark_authoring_freeze_service import (
    StudioBenchmarkValidatedFreezeAnalyzer,
    StudioBenchmarkValidatedFreezeApplicationService,
)
from zhixing.studio.benchmark_authoring_materializer import (
    StudioBenchmarkAuthoringPackageMaterializer,
)
from zhixing.studio.benchmark_authoring_release_service import (
    StudioBenchmarkPackageReleaseApplicationService,
)
from zhixing.studio.benchmark_authoring_release_storage import (
    LocalStudioBenchmarkPackageReleaseStore,
    StudioBenchmarkFrozenClosureReader,
    default_studio_benchmark_release_root,
)
from zhixing.studio.benchmark_service import (
    StudioBenchmarkCatalogSnapshotOwner,
)

workdir = pathlib.Path(sys.argv[1])
installed_root = pathlib.Path(sys.prefix).resolve()
assert pathlib.Path(zhixing.__file__).resolve().is_relative_to(installed_root)
database = workdir / "studio.sqlite3"


def build_services():
    '''Build one installed-wheel authoring, freeze, and release composition.

    Returns:
        Definition, freeze, release, repository, content, Catalog owner, store.
    '''
    repository = SQLiteStudioBenchmarkAuthoringRepository(database)
    content = LocalStudioBenchmarkManagedContent(
        default_studio_benchmark_authoring_root(database)
    )
    owner = StudioBenchmarkCatalogSnapshotOwner(StudioBenchmarkCatalogService())
    definition = StudioBenchmarkAuthoringApplicationService(
        repository=repository,
        packages=StudioBenchmarkAuthoringPackageAdapter(
            content,
            staging_root=content.staging_root,
        ),
        catalog=owner,
    )
    compiler = StudioBenchmarkAuthoringRevisionCompiler(
        repository=repository,
        materializer=StudioBenchmarkAuthoringPackageMaterializer(
            content,
            staging_root=content.staging_root / "release-analysis",
        ),
        agents=SQLiteAgentDocumentRepository(database),
    )
    freeze = StudioBenchmarkValidatedFreezeApplicationService(
        repository=repository,
        analyzer=StudioBenchmarkValidatedFreezeAnalyzer(compiler),
        closure_builder=StudioBenchmarkFrozenClosureBuilder(content),
    )
    store = LocalStudioBenchmarkPackageReleaseStore(
        default_studio_benchmark_release_root(database)
    )
    release = StudioBenchmarkPackageReleaseApplicationService(
        repository=repository,
        frozen_reader=StudioBenchmarkFrozenClosureReader(content),
        storage=store,
        catalog=owner,
    )
    release.recover_publications()
    return definition, freeze, release, repository, content, owner, store


definition, freeze, release, repository, content, owner, store = build_services()
created = definition.create_draft(
    {
        "schemaVersion": 1,
        "clientRequestId": "wheel-release-create",
        "name": "Wheel Release",
        "source": {
            "kind": "template",
            "template": "minimal",
            "publisher": "tests",
            "packageName": "wheel-release",
            "version": "0.1.0",
        },
    }
)
before = repository.get_draft(created.draft.draft_id)
frozen = freeze.freeze(
    created.draft.draft_id,
    freeze.parse_request(
        {
            "schemaVersion": 1,
            "clientRequestId": "wheel-release-freeze",
            "revisionId": created.revision.revision_id,
        }
    ),
)
package = frozen.detail.package_revision
publication_request = release.parse_command(
    {"schemaVersion": 1, "clientRequestId": "wheel-publish"}
)
export_request = release.parse_command(
    {"schemaVersion": 1, "clientRequestId": "wheel-export"}
)
published = release.publish(
    package.draft_id,
    package.package_revision_id,
    publication_request,
)
exported = release.export_package(
    package.draft_id,
    package.package_revision_id,
    export_request,
)
descriptor, stream = release.open_export(
    package.draft_id,
    package.package_revision_id,
    exported.package_export.export_id,
)
try:
    archive = stream.read()
finally:
    stream.close()
assert len(archive) == descriptor.size
assert owner.detail(published.publication.catalog_entry_id).package_content_identity == (
    package.package_content_identity
)
assert repository.get_draft(created.draft.draft_id) == before
assert not release.publish(
    package.draft_id,
    package.package_revision_id,
    publication_request,
).created
assert not release.export_package(
    package.draft_id,
    package.package_revision_id,
    export_request,
).created

_, _, restarted_release, restarted_repository, _, restarted_owner, _ = build_services()
restarted_descriptor, restarted_stream = restarted_release.open_export(
    package.draft_id,
    package.package_revision_id,
    descriptor.export_id,
)
try:
    restarted_archive = restarted_stream.read()
finally:
    restarted_stream.close()
assert restarted_descriptor == descriptor
assert restarted_archive == archive
assert restarted_owner.detail(
    published.publication.catalog_entry_id
).package_content_identity == package.package_content_identity
assert set(vars(restarted_release)) == {
    "_repository",
    "_reader",
    "_storage",
    "_catalog",
    "_clock",
    "_identity_factory",
}
with sqlite3.connect(database) as connection:
    schema_version = connection.execute(
        "SELECT MAX(version) FROM studio_schema_migrations"
    ).fetchone()[0]
    release_counts = {
        table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in (
            "studio_benchmark_package_publications",
            "studio_benchmark_publication_commands",
            "studio_benchmark_package_exports",
            "studio_benchmark_export_commands",
        )
    }
    runtime_products = sum(
        connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in (
            "studio_benchmark_experiments",
            "studio_benchmark_artifacts",
            "studio_replays",
        )
    )
print(
    json.dumps(
        {
            "archiveStableAfterRestart": restarted_archive == archive,
            "catalogRecovered": len(restarted_owner.list_entries().items),
            "publicationEvidence": published.publication.safety.publication_evidence,
            "releaseRows": release_counts,
            "schemaVersion": schema_version,
            "sourceIsInstalledWheel": True,
            "sourceUnchanged": restarted_repository.get_draft(
                created.draft.draft_id
            ) == before,
            "zeroRuntimeProducts": runtime_products == 0,
        },
        sort_keys=True,
    )
)
"""
    completed = subprocess.run(
        [str(python), "-c", script, str(scenario)],
        cwd=workdir,
        env=clean_env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    result = json.loads(completed.stdout)
    assert result == {
        "archiveStableAfterRestart": True,
        "catalogRecovered": 1,
        "publicationEvidence": True,
        "releaseRows": {
            "studio_benchmark_export_commands": 1,
            "studio_benchmark_package_exports": 1,
            "studio_benchmark_package_publications": 1,
            "studio_benchmark_publication_commands": 1,
        },
        "schemaVersion": 12,
        "sourceIsInstalledWheel": True,
        "sourceUnchanged": True,
        "zeroRuntimeProducts": True,
    }
