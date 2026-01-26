# 🧩 Components

ZhiXing adopts a **modular agent architecture**. Instead of tightly coupling perception, planning, reasoning, and execution into one large system,we split an agent into **independent, replaceable components**.

## 🏗️ Module Responsibilities

A ZhiXing agent is composed of six core modules:

| **Module**       | **Responsibility & Function**                                |
| ---------------- | ------------------------------------------------------------ |
| **👀 Perception** | The **Eye** of the agent. It parses multi-modal inputs from the mobile end and serves as the sole entry point for acquiring environmental information from physical devices. |
| **🧠 Reasoning**  | The **Decision Core**. It is the central module of the agent, accepting sub-task sequences from the Planner and combining perception + memory information to output precise decisions for each step. |
| **🗺️ Planner**    | The **Planner**. It decomposes the user's high-level goal into an executable, ordered, and fine-grained sequence of sub-tasks. |
| **💾 Memory**     | The **Memory Hub**. It manages both short-term and long-term memory in an integrated manner, serving as the core state storage for the agent. |
| **🛡️ Verifier**   | The **Quality Inspector**. It verifies whether the result of the previous action was correct, effective, and achieved the expected goal, serving as the core of self-correction. |
| **🦾 Action**     | The **Hands & Feet**. It is solely responsible for translating the decisions output by the brain into real operations on the mobile phone, serving as the core execution component. |

## 📦 Built-in Components (v0.1)

ZhiXing ships with the following implementations out of the box.

You can mix and match them freely.

| Module         | Available Component Names                  | Description                                                  |
| :------------- | :----------------------------------------- | :----------------------------------------------------------- |
| **Reasoning**  | `universal_reasoning` (`general_vlm_type`) | **Visual Decision Core**: Based on general MLLMs, capable of directly understanding screenshots and outputting atomic actions in JSON format. |
| **Planner**    | `universal_planner` (`manager_style`)      | **Step-by-Step Planning**: Decomposes complex user instructions into linear sub-tasks, suitable for long-horizon tasks. |
|                | `universal_planner`(`mobimind_style`)      | **Structured Routing**: Combines knowledge base data to intelligently select target apps and generate structured operational intents. |
| **Perception** | `omniparser_perception`                    | **Semantic Parsing**: Uses OmniParser to convert screenshots into a structured list of elements containing text, type, and coordinates. |
|                | `grid_perception`                          | **Grid Localization**: A classic fallback solution that does not rely on element recognition, dividing the screen into a grid. |
|                | `som_perception`                           | **Set-of-Marks**: Overlays numeric tags on UI elements based on SoM technology to assist the model in high-precision ID-based indexing. |
| **Memory**     | `sliding_window_memory`                    | **Sliding Window**: Retains only the most recent N steps of history to balance Token cost and context continuity. |
|                | `summary_memory`                           | **Summary Memory**: Periodically compresses and summarizes long-term history to ensure key information is not forgotten. |
| **Action**     | `android_action`                           | **Android Adapter**: Encapsulates ADB commands to support atomic operations like click, swipe, and type on Android devices. |
|                | `harmony_action`                           | **HarmonyOS Adapter**: Encapsulates HDC protocol to enable automated control on HarmonyOS NEXT devices. |

## ➡️ Next Step

To learn how to configure and use these components in practice,  
see **YAML Configuration Guide** → [docs/yaml.md](yaml.md)
