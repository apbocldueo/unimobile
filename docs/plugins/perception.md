# Perception Plugins

### 1 Role & Responsibilities

A **Perception Plugin** acts as the bridge between the raw environment (pixels) and the agent's brain (text/JSON).

- ✅ **DO**: Interpret screenshots, extract UI elements, OCR text.
- ❌ **DON'T**: Make decisions, execute actions, or maintain long-term history.

### 2 Core Interfaces

All perception plugins must inherit from `BasePerception` and implement:

```python
class BasePerception:
    def perceive(self, perception_input) -> PerceptionResult
    def _get_prompt_context(self, result) -> str
```

`perceive(...)`

- Called once per agent step
- Analyzes the current environment state
- Returns a `PerceptionResult` containing all observable facts

This is the **core method** of a perception plugin.

`_get_prompt_context(...)`

- Converts perception results into a textual form
- Controls how observations are presented to the LLM

### 3 Example: `ExamplePerception`

**File location**

```bash
plugins/perception/example.py
```

**Minimal implementation**

```python
@register_perception("example_perception")
class ExamplePerception(BasePerception):

    def perceive(self, perception_input):
        elements = [
            {"index": 0, "text": "微信", "type": "icon"},
            {"index": 1, "text": "通讯录", "type": "icon"},
        ]

        prompt_text = self._get_prompt_context(elements)

        return PerceptionResult(
            mode="example",
            original_screenshot_path=perception_input.screenshot_path,
            elements=elements,
            prompt_representation=prompt_text,
            data={"example": elements},
        )

    def _get_prompt_context(self, result):
        return "\n".join(
            f"ID {e['index']}: {e['text']}" for e in result
        )
```

