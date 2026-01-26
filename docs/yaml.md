# ⚙️ YAML Configuration Guide

ZhiXing agents are built **entirely through configuration files**.

You do NOT write agent logic in code. 
Instead, you:

1️⃣ choose components 
2️⃣ write a YAML file 
3️⃣ run the agent  

A ZhiXing agent is like LEGO blocks: Each block can be replaced independently. In YAML, you simply **pick which block to use**.

## 🚀 Step 1 — Minimal Working Example

Create a file: `demo.yaml`

```yaml
agent_type: modular_agent

agent:
  components:

    action:
      name: android_action      # how to control the phone

    perception:
      name: grid_perception    # how to read the screen

    reasoning:
      name: universal_reasoning # how the agent makes decisions

    memory:
      name: sliding_window_memory # how history is stored

    planner:
      name: universal_planner  # how tasks are decomposed
     
    verifier:
      name: screen_diff_verifier # how tasks are verified
```

Run:

```yaml
python run.py --config demo.yaml
```

If everything is connected correctly,  your first mobile agent is now running.

## 🧩 Step 2 — Understanding Each Section

You don’t need to understand internals.
 Just remember:

| Part       | What it controls            |
| ---------- | --------------------------- |
| action     | Android or HarmonyOS        |
| perception | screen understanding method |
| reasoning  | decision logic              |
| memory     | history strategy            |
| planner    | task planning style         |
| verifier   | task evaluation             |

👉 In most cases, you only change **one or two lines**.

## 🔁 Step 3 —  Full Example

```yaml
# ====================================================
# [Case] Building a Vision-based Classic Android Agent
# ====================================================

# 1. Agent Strategy
# Naming logic: [strategy_type]_agent
agent_type: "modular_agent"  # Currently supports modular assembly strategy

agent:
  components:
    # 2. Action Component: Responsible for implementing instructions on devices
    # Naming logic: [device]_action
    # This reflects that Action mainly varies by device / OS backend
    action:
      name: "android_action" # Android executor
      params: {}

    # 3. Perception Component: Responsible for parsing screen information
    # Naming logic: [algorithm_name]_perception
    # This reflects that Perception mainly varies by perception algorithm
    perception:
      name: "grid_perception" # Grid coordinate perception
      params: {}
        
    # 4. Reasoning Component (Brain): Responsible for single-step decision-making
    # Naming logic: 
    #   - universal_reasoning: shared reasoning logic
    #   - preset: configurable decision style
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
    # Memory components used mainly to state management
    memory:
      name: "sliding_window_memory" # Sliding window memory strategy
      params: { window_size: 6 }

    # 6. Planner Component: Responsible for long-range task decomposition
    # Naming logic:
    #   - universal_planner: shared planning algorithm
    #   - preset: configurable task decomposition style
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

**🔖 Naming Principles (Derived from the Example)**

From the YAML example above, ZhiXing follows two **practical and developer-friendly** naming principles:

1. Component names reflect what changes most often
   + Perception components change mainly by **algorithm** → `grid_perception`
   + Action components change mainly by **platform** → `android_action`
   + Memory components change mainly by **state strategy** → `sliding_window_memory`
2. Stable logic is reused, behavior is configured
   - Planner and Reasoning share **stable algorithmic workflows**
   - Differences are expressed via `preset`: prompt and parsers
   - This avoids creating many similar classes for minor variations