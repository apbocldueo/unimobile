# 🔌Plugin Development Guide

This guide explains **how to extend ZhiXing by implementing your own components**.

If you only want to **use existing components**, see:

👉 YAML Guide → [configuration](yaml.md)
👉 Components Reference → [components](components.md)

This document is for **developers and researchers** who want to build new algorithms.

## 🧠 Core Idea

In ZhiXing, everything is a **plugin**.

Perception, Planner, Reasoning, Memory, Verifier, and Action all follow the same mechanism:

1️⃣ implement an interface 
2️⃣ register the class 
3️⃣ reference it in YAML  

## 📂 Directory Structure

ZhiXing uses a **registry-based plugin system**. To be discovered automatically, plugins must follow a directory convention.

```bash
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

### ⚙️ Plugin Lifecycle

At runtime, the framework executes the following lifecycle for plugins:

1. **Scanning**: Scans the plugins/ directory for .py files.
2. **Loading**: Imports modules dynamically.
3. **Registration**: Decorators register plugin classes into the global REGISTRY.
4. **Instantiation**: Based on the YAML configuration, the framework initializes the specific plugin class.
5. **Execution**: The plugin instance is invoked during the agent's run loop.

## 🚀 How to Create Any Plugin (3 Steps)

#### Step 1 — Inherit the base class

Example (Perception):

```python
from unimobile.core.interfaces import BasePerception
from unimobile.core.protocol import PerceptionResult, PerceptionInput
from unimobile.utils.registry import register_perception
```

#### Step 2 — Register

```python
@register_perception("my_perception")
class MyPerception(BasePerception):
    ...
```

The string `"my_perception"` is what you use in YAML.

#### Step 3 — Use in YAML

```yaml
perception:
  name: "my_perception"
```

Done. No core modification required.

## 📦 Plugin Examples by Type

Detailed implementation guides for each component type:

| Type         | Guide                                 |
| ------------ | ------------------------------------- |
| 👀 Perception | 👉 [perception](plugins/perception.md) |
| 🗺️ Planner    | 👉  [planner](plugins/planner.md)      |
| 🧠 Reasoning  | Coming soon                           |
| 💾 Memory     | Coming soon                           |
| 🦾 Action     | Coming soon                           |
| 🛡️ Verifier   | Coming soon                           |

