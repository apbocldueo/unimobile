# 🔌Plugin Development Guide

This document explains how to develop and use **plugins** in ZhiXing.

Plugins allow developers to extend ZhiXing without modifying the core framework. All built-in components and third-party extensions follow the same plugin mechanism.



### 1. What Is a Plugin?

In ZhiXing, a **plugin** is a modular component that implements a specific role in the agent system.

Currently supported plugin types include: 

+ **👀** **Perception** – The **Eye** of the agent. It parses multi-modal inputs from the mobile end and serves as the sole entry point for acquiring environmental information from physical devices.
+ **🗺️** **Planner** – The **Planner**. It decomposes the user's high-level goal into an executable, ordered, and fine-grained sequence of sub-tasks.
+ **🧠** **Reasoning** – The **Decision Core**. It is the central module of the agent, accepting sub-task sequences from the Planner and combining perception + memory information to output precise decisions for each step. (no guide)
+ **💾** **Memory** – The **Memory Hub**. It manages both short-term and long-term memory in an integrated manner, serving as the core state storage for the agent. (no guide)
+ **🛡️** **Verifier** – The **Quality Inspector**. It verifies whether the result of the previous action was correct, effective, and achieved the expected goal, serving as the core of self-correction. (no guide)

-------



### 2. Plugin Discovery and Directory Structure

ZhiXing uses a **registry-based plugin system**. To be discovered automatically, plugins must follow a directory convention.

```
plugins/
├─ perception/
│  └─ example.py
├─ planner/
│  └─ example.py
├─ memory/
├─ reasoning/
└─ verifier/
```

**📝Each plugin file:**

1. **Standard Python Module**: Each file must be a valid Python script.
2. **Registration**: Classes must be decorated with the corresponding registry decorator (e.g., @register_perception).
3. **Import Safety**: Plugin files **must not raise exceptions** at import time. Failed imports will cause the plugin to be skipped safely.

---



### 3. Plugin Lifecycle

At runtime, the framework executes the following lifecycle for plugins:

1. **Scanning**: Scans the plugins/ directory for .py files.
2. **Loading**: Imports modules dynamically.
3. **Registration**: Decorators register plugin classes into the global REGISTRY.
4. **Instantiation**: Based on the YAML configuration, the framework initializes the specific plugin class.
5. **Execution**: The plugin instance is invoked during the agent's run loop.

---



### 4. Perception Plugins

#### 4.1 Role & Responsibilities

A **Perception Plugin** acts as the bridge between the raw environment (pixels) and the agent's brain (text/JSON).

- ✅ **DO**: Interpret screenshots, extract UI elements, OCR text.
- ❌ **DON'T**: Make decisions, execute actions, or maintain long-term history.

#### 4.2 Core Interfaces

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

#### 4.3 Example: `ExamplePerception`

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

---



### 5. Developing a Planner Plugin

#### 5.1 Role & Responsibilities

A **Planner Plugin** is the strategic center. It translates a high-level goal into a roadmap.

- ✅ **DO**: Decompose tasks, call LLMs for planning, produce PlanResult.
- ❌ **DON'T**: Interact with raw pixels directly or execute atomic actions (like tap).

#### 5.2 Development Patterns

You have two ways to create a planner:

##### 5.2.1 Prompt + Parser Customization (Recommended)

In many cases, planner algorithms share the same structure:

1. Build a prompt from task and context
2. Call an LLM
3. Parse the output into a plan

The main differences are:

- Prompt templates
- Output parsing logic

For this scenario, developers do NOT need to implement a new planner algorithm.

Instead, they can:

- Reuse an existing planner implementation
- Provide a custom prompt template
- Provide a custom parser
- Select or define a preset

##### 5.2.2 Implementing a New Planner Algorithm

A new planner class should be implemented only if:

- The planning process fundamentally differs from the standard pipeline
- Additional control logic is required
- The planner does not follow the “prompt → LLM → parse” pattern

In this case:

- Inherit from `BasePlanner`
- Implement `make_plan(...)`
- Manage prompts, parsing, and logic explicitly

#### 5.3 Example: `ExamplePlanner`

**File location**

```bash
plugins/planner/example.py
```

**Key ideas demonstrated**

- Use of presets to configure behavior
- Separation of prompt templates and parsing logic
- Reuse of a universal planner algorithm

Although implemented as a separate class, `ExamplePlanner` follows the same
 algorithmic structure as the built-in `universal_planner`, differing only
 in configuration.

---



### 6. Using Plugins in YAML Configuration

Once a plugin is registered, it can be referenced by name in YAML.

```yaml
agent:
  components:
  	# Use your custom perception plugin
    perception:
      name: "example_perception" # Matches the @register_perception name
      params: {}
	
	# Use your custom planner plugin
    planner:
      name: "example_planner"
      params:
        preset: "example_planner_style"
      llms: {}
```

**ZhiXing** will automatically:

1. Discover plugins/perception/example_perception.py.
2. Register "my_custom_ocr".
3. Instantiate the class with params.
4. Inject dependencies (e.g., llms, device).

