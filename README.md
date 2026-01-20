# ZhiXing: OS infrastructure in the Mobile Agent

ZhiXing is a configuration-driven, modular framework for Mobile Agent development, designed to help researchers rapidly build, test, and benchmark diverse Mobile Agent architectures. It provides a comprehensive library of modular components covering Perception, Planning and Execution, along with out-of-the-box presets that allow researchers to instantiate various agent styles on both Android and HarmonyOS platforms instantly.

With ZhiXing and its rich resources, you can build and verify a Mobile Agent prototype in minutes, transforming your algorithmic ideas into executable actions on real devices.

> **Our Vision**: Starting as a flexible development framework, ZhiXing aims to evolve into a full-stack research platform covering **Automated Data Generation** and **Standardized Full-Link Evaluation**.



## ⚡ Showcase: Assemble **Your** Mobile Agent in 3 Minutes (No Code)

**Scenario:**
 *Search for Bluetooth headphones in the Huawei Mall and share the most expensive one with Xiao Zhang via wechat.*

ZhiXing enables you to **assemble your own mobile agent** by declaratively selecting components in a YAML configuration — no core code required. The demo below shows **one possible agent.**

```yaml
agent:
  components:
    perception: 
     name: "omniparser"
     
    planner: 
     name: "universal_planner" 
     params:
       preset: "mobimind_style"
        
    reasoning:
      name: "universal_reasoning"
      params:
        preset: "general_vlm_type"
        
    memory:
      name: "summary_memory"
    action:
      name: "harmony_action"
```



https://github.com/user-attachments/assets/6e5747fb-a05e-4326-8a87-19a568b02b42

To view more scenes, please jump to [Run Demo](#runDemo)

## 🏗️ Architecture & Components

### 🌍 System Overview

ZhiXing adopts a five-layer architecture, covering full-stack capabilities from low-level device interfaces to top-level application configurations. 

![architecture](asset/architecture.png)

*Note: Solid blocks represent modules implemented in v0.1, while dashed blocks indicate planned features.*

### 🧠 Design Principles

ZhiXing decomposes mobile agents from a **system engineering perspective**. Instead of designing a single task-specific agent algorithm, we explicitly separate perception, planning, reasoning, memory, execution, and verification based on their **different responsibilities**.

Our core design goal is to build a **configuration-driven, extensible, and verifiable mobile agent infrastructure**, rather than a single hard-coded agent implementation.To achieve this, we decompose an agent into functionally orthogonal components, each with a clear responsibility boundary, minimal coupling, and independent evolvability.

#### Why This Decomposition?

The decomposition is guided by the following principles:

1. **Single Responsibility**
    Each component solves one well-defined problem (e.g., perception, planning, execution), avoiding entangled logic.
2. **Replaceability**
    Any component (e.g., perception model, planner strategy, memory policy) can be swapped or upgraded without affecting others.
3. **Configuration over Code**
    Agent behaviors should be assembled declaratively (via YAML), not hard-coded in Python logic.

### 🧩  Core Component

Based on the above principles, a mobile agent is decomposed into **six core components** (corresponding to Layer 2 in the architecture diagram).

Each component operates independently, communicates only through well-defined interfaces, and has no strong runtime dependencies on others.

| **Module**       | **Responsibility & Function**                                |
| ---------------- | ------------------------------------------------------------ |
| **👀 Perception** | The **Eye** of the agent. It parses multi-modal inputs from the mobile end and serves as the sole entry point for acquiring environmental information from physical devices. |
| **🧠 Reasoning**  | The **Decision Core**. It is the central module of the agent, accepting sub-task sequences from the Planner and combining perception + memory information to output precise decisions for each step. |
| **🗺️ Planner**    | The **Planner**. It decomposes the user's high-level goal into an executable, ordered, and fine-grained sequence of sub-tasks. |
| **💾 Memory**     | The **Memory Hub**. It manages both short-term and long-term memory in an integrated manner, serving as the core state storage for the agent. |
| **🛡️ Verifier**   | The **Quality Inspector**. It verifies whether the result of the previous action was correct, effective, and achieved the expected goal, serving as the core of self-correction. |
| **🦾 Action**     | The **Hands & Feet**. It is solely responsible for translating the decisions output by the brain into real operations on the mobile phone, serving as the core execution component. |

### ⚙️ Running Mechanism

Once instantiated, the agent enters a closed-loop operation. The diagram below illustrates the data flow and interaction mechanism between components.

![run](asset/run.png)

## 🔥 Key Features

### 1. True Architectural Decoupling

We solved the engineering challenge of inconsistent interfaces between fine-tuned models and general-purpose models.

- **Universal Reasoning & Planner**：Through our unique **Preset** mechanism, we dynamically bind Prompt templates, model calls, and result parsers.

### 2.  Extreme Configuration-Driven

Simplifying the Mobile Agent construction process from 'Writing Code' to 'Defining Configuration'.

- **Zero-Code Assembly**：Define the entire agent via a YAML file. Even non-developers can quickly assemble a dedicated Mobile Agent instance like building LEGO blocks.

- **Swappable Components**：Designed for research experiments. Want to compare the perception difference between **OmniParser** and **Grid**? Just modify a single parameter in the config file to realize controlled variable experiments.

### 3. Extending ZhiXing with Plugins

ZhiXing is designed as a **configuration-driven research infrastructure**. Beyond built-in components, researchers can easily extend the framework by developing custom plugins, without modifying any core code.

Supported plugin types include:
- Perception
- Planner
- Reasoning
- Memory
- Verifier

📘 **Plugin Development Guide**  → See [guide.md](docs/plugin_guide.md)



## 🚀 Quick Start

### 1. Installation

```Bash
# 1.  Create and activate virtual environment
conda create -n unimobile python=3.10
conda activate unimobile

# 2. Clone the repository
git clone https://github.com/apbocldueo/unimobile.git
cd unimobile

# 3. Install dependencies
pip install -r requirements.txt
```

### 2. Connect Device

ZhiXing supports both Android and HarmonyOS platforms.

#### Connect Android Device

1. Download and install [ADBKeyboard](https://github.com/senzhk/ADBKeyBoard/blob/master/ADBKeyboard.apk) on your Android device.

2. On the phone: Settings → About Phone → Tap "Build Number" 7 times to enable "Developer Options".

3. In Developer Options, enable "USB Debugging".

4. Connect the phone to your computer via USB and authorize debugging.

5. Verify connection:

   ```bash
   adb devices
   ```

#### Connect HarmonyOS Device

1. Ensure the **HDC toolchain** is installed. Download here: [HDC](https://developer.huawei.com/consumer/cn/download/command-line-tools-for-hmos). Add HDC to your system environment variables.

2. Enable "USB Debugging" on the phone.

3. Verify connection:

   ```bash
   hdc list targets
   ```

### 3. Configuration

We define agents via YAML. Below is an example configuration for a **"Classic Android Agent"**:

```yaml
# ====================================================
# [Case] Building a Vision-based Classic Android Agent
# ====================================================

# 1. Top-level Definition: Define Agent Strategy
# Naming logic: [strategy_type]_agent
agent_type: "modular_agent"  # Currently supports modular assembly strategy

agent:
  components:
    # 2. Action Component: Responsible for implementing instructions on devices
    # Naming logic: [device]_action
    action:
      name: "android_action" # Android executor
      params: {}

    # 3. Perception Component: Responsible for parsing screen information
    # Naming logic: [algorithm_name]_perception
    perception:
      name: "grid_perception" # Grid coordinate perception
      params: {}
        
    # 4. Reasoning Component (Brain): Responsible for single-step decision-making
    # Naming logic: universal_reasoning (general reasoning) + preset (preset style)
    reasoning:
      name: "universal_reasoning"
      params:
        preset: "general_vlm_type" # Preset: General Vision-Language Model style
      llm:  # Model configuration
      	name: "openai_llm" # OpenAI model
        params:
          api_key: "sk-xxx"  # Your OpenAI API key
          base_url: "https://api.openai.com/v1"
          model: "gpt-4o"
          temperature: 0.1
          max_tokens: 2048

    # 5. Memory Component: Responsible for context management
    # Naming logic: [strategy_name]_memory
    memory:
      name: "sliding_window_memory" # Sliding window memory strategy
      params: { window_size: 6 }

    # 6. Planner Component: Responsible for long-range task decomposition
    # Naming logic: universal_planner (general planning) + preset (preset style)
    planner:
      name: "universal_planner" 
      params:
        preset: "manager_style" # Preset: Step-by-step decomposition style
      llm:  # Model configuration
      	name: "openai_llm" # OpenAI model
        params:
          api_key: "sk-xxx"  # Your OpenAI API key
          base_url: "https://api.openai.com/v1"
          model: "gpt-4o"
          temperature: 0.1
          max_tokens: 2048

```

### 4. Existing Component List

The v0.1 version has built-in the following core components, supporting free combination:

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

<a id="runDemo"></a>

## 🚀 Run Demo

To verify the flexibility of UniMobile, we built two completely different Agent architectures and tested them in three scenarios of varying difficulty.

> 💡  **Tip**:
>
> 1. Before running the examples, please fill in your api_key and base_url in the YAML file.
> 2. If using OmniParser for perception, you must start the OmniParser model service first. Visit [OmniParser](https://github.com/microsoft/OmniParser) and fill in your omniparser-url in the YAML.

### 🎬 Scenarios

**Scenario A: Send an email on Android**

- **Configuration**: Manager Planner + Grid Perception + Sliding Window Memory.
- **Feature**: Simulates the standard paradigm of general LLMs handling mobile tasks.

```bash
# Prerequisite: Email installed on the phone and logged in
# Task: Search for 'send an email to lusanedevereaux@gmail.com to ask how her work has been going recently'
python run.py --config configs/agent_android_classic.yaml \
  --task "send an email to lusanedevereaux@gmail.com to ask how her work has been going recently"
```



https://github.com/user-attachments/assets/214e7a28-c038-4b5c-b463-0af0bab2ba08



**Scenario B: High-Precision Agent on HarmonyOS**

- **Configuration**: MobiMind Planner + OmniParser + Summary Memory
- **Features**: Utilizes the more advanced OmniParser screen parser and structured output, enabling more accurate and efficient execution

```bash
# Prerequisite: Meituan is installed on the phone and logged in
# Task: 使用美团点一份黄焖鸡米饭，口味选择微辣, 最终停到支付界面即可
python run.py --config configs/agent_harmony_advanced.yaml \
  --task "使用美团点一份黄焖鸡米饭，口味选择微辣, 最终停到支付界面即可"
```

https://github.com/user-attachments/assets/59325b57-927e-4b07-820b-0e271196e3d3



## 🗺️ Roadmap

### **v0.1 - The Foundation**
- [x] **Hardware Layer**: Unified encapsulation for HarmonyOS/Android dual platforms.
- [x] **Application Layer**: Implemented core ConfigLoader engine for rapid Mobile Agent construction via YAML.
- [x] **Component Ecosystem**: Integrated basic components like OmniParser, OpenAI LLM, summary_memory.

### **v1.0 - Enhancement**
- [ ] **Advanced Strategies**: Implement **Exploration** and **Reflection** strategies for agent self-evolution.
- [ ] **Knowledge Base**: Preliminary support for RAG knowledge base.
- [ ] **External Adapters**: Fully reproduce SOTA algorithms like AppAgent / Mobile-Agent v2.
- [ ] **Developer SDK**: Open component registration interface to support community contributions.



## 📄  License

This project is licensed under the [Apache License](./LICENSE).


If this framework helps your research, please give us a Star! 🌟
