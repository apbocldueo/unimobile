#  Developing a Planner Plugin

### 1 Role & Responsibilities

A **Planner Plugin** is the strategic center. It translates a high-level goal into a roadmap.

- ✅ **DO**: Decompose tasks, call LLMs for planning, produce PlanResult.
- ❌ **DON'T**: Interact with raw pixels directly or execute atomic actions (like tap).

### 2 Development Patterns

You have two ways to create a planner:

#### 2.1 Prompt + Parser Customization (Recommended)

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

##### #### 2.2 Implementing a New Planner Algorithm

A new planner class should be implemented only if:

- The planning process fundamentally differs from the standard pipeline
- Additional control logic is required
- The planner does not follow the “prompt → LLM → parse” pattern

In this case:

- Inherit from `BasePlanner`
- Implement `make_plan(...)`
- Manage prompts, parsing, and logic explicitly

### 3 Example: `ExamplePlanner`

**File location**

```bash
plugins/planner/example.py
```

```python
class ExamplePlanner(BasePlanner):
    """
    Example Planner
    """
    
    PRESETS = {
        "example_planner_style": {
            "prompt_file": "example_planner_prompt.md",
            "parser_name": "example_planner_parser",
            "use_rag": False
        },
    }

    def __init__(
        self, 
        llm_client, 
        knowledge_source=None, 
        env_info: EnvironmentInfo = None,
        preset: str = "example_planner_style", 
        prompt_file: Union[str, Dict] = None,   
        parser_name: str = None,
        use_rag: bool = None
    ):
        super().__init__(llm_client, knowledge_source, env_info)

        if prompt_file: self.config["prompt_file"] = prompt_file
        if parser_name: self.config["parser_name"] = parser_name
        if use_rag is not None: self.config["use_rag"] = use_rag

        raw_prompt_file = self.config.get("prompt_file")
        if isinstance(raw_prompt_file, dict):
            current_platform = self.env.platform.lower() if (self.env and self.env.platform) else "android"
            target_file = raw_prompt_file.get(current_platform)
            if not target_file:
                target_file = raw_prompt_file.get("default")
                logger.warning(f"ExamplePlanner: '{current_platform}' no specific Prompt, use the default:: {target_file}")
            self.target_prompt_file = target_file
        else:
            self.target_prompt_file = raw_prompt_file

        self.prompt_template = self._load_prompt(self.target_prompt_file)
        
        target_parser_name = self.config.get("parser_name")
        ParserCls = get_parser_class(target_parser_name)
        self.parser = ParserCls()

    def make_plan(self, task: str) -> PlanResult:

        prompt_vars = {
            "task": task,
        }

        prompt = self.prompt_template
        for key, value in prompt_vars.items():
            if value is not None:
                prompt = prompt.replace(f"{{{key}}}", str(value))
        response = self.llm.generate(prompt=prompt, images=[])
        
        return self.parser.parse(response, task=task)

    def _load_prompt(self, filename: str) -> str:
		base_dir = os.path.join(os.getcwd(), "plugins", "planner")
		path = os.path.join(base_dir, filename)
             
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        
        content = content.replace("````markdown", "").replace("````", "")
        return content.strip()
```

**Key ideas demonstrated**

- Use of presets to configure behavior
- Separation of prompt templates and parsing logic
- Reuse of a universal planner algorithm

Although implemented as a separate class, `ExamplePlanner` follows the same
 algorithmic structure as the built-in `universal_planner`, differing only
 in configuration.

