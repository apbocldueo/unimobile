from __future__ import annotations

from pathlib import Path

import pytest

from zhixing.resources import ZhiXingResourceError, prompt_path, read_prompt
from zhixing.studio.flow_template_loader import get_flow_template_document, list_flow_templates


ROOT = Path(__file__).resolve().parents[2]
PROMPT_NAMES = sorted(path.name for path in (ROOT / "zhixing" / "prompts").glob("*.md"))


def test_all_builtin_prompts_are_packaged_and_readable():
    assert len(PROMPT_NAMES) == 15
    for name in PROMPT_NAMES:
        assert read_prompt(name).strip(), name


def test_prompt_lookup_is_cwd_independent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    expected = read_prompt("reasoning_general.md")
    monkeypatch.chdir(tmp_path)
    assert not (tmp_path / "zhixing" / "prompts").exists()
    assert read_prompt("reasoning_general.md") == expected


def test_existing_external_prompt_takes_precedence(tmp_path: Path):
    custom = tmp_path / "reasoning_general.md"
    custom.write_text("caller override", encoding="utf-8")
    assert read_prompt(custom) == "caller override"
    with prompt_path(custom) as materialized:
        assert materialized == custom.resolve()


def test_packaged_prompt_can_be_materialized():
    with prompt_path("reasoning_general.md") as materialized:
        assert materialized.is_file()
        assert materialized.read_text(encoding="utf-8") == read_prompt("reasoning_general.md")


@pytest.mark.parametrize("missing", ["missing.md", "nested/missing.md", "../missing.md"])
def test_missing_prompt_has_deterministic_error(missing: str):
    with pytest.raises(ZhiXingResourceError, match="Prompt resource not found"):
        read_prompt(missing)


def test_retained_studio_metadata_is_available():
    templates = list_flow_templates()
    assert templates
    first = templates[0]
    document = get_flow_template_document(first.template_id)
    assert isinstance(document, dict)
