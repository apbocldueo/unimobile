## Developing a Reasoning Plugin
### 1 Role & Responsibilities

A Reasoning Plugin is responsible for deciding the next executable action given the current context.

It sits between planning and execution, translating abstract intent into a concrete Action.

In ZhiXing, reasoning is responsible for:

Interpreting the current plan step

Grounding decisions in perception results

Incorporating memory context

Producing a single atomic Action

### 2 Reasoning Design Pattern
Reasoning plugins follow a context-to-action decision pattern:
```bash
Task + Plan
   ↓
Perception Result
   ↓
Memory Context
   ↓
Reasoning.think(...)
   ↓
Action
```
Each reasoning step produces exactly one action, keeping the control loop explicit and traceable.
### 3 Production Example: UniversalReasoning
UniversalReasoning is a general-purpose reasoning module that supports multiple perception modes and action spaces.

File location
```bash
docs/plugins/reasoning/universal_reasoning.py
```