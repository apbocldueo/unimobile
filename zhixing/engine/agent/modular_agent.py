import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

from zhixing.core.factory import PluginRegistry
from zhixing.core.agent.protocol import (
    Action, ActionType, 
    MemoryFragment, FragmentType, 
    PerceptionInput, VerifierInput, PlanInput
)
from zhixing.utils.utils import get_plugin_logger

# logger = logging.getLogger(__name__)


@dataclass
class AgentRuntimeState:
    """Maintains the state between steps for verification and rollback.
    
    Attributes:
        last_screenshot_path: Path to the screenshot of the previous step.
        last_action: The action executed in the previous step.
        current_strategy_idx: Index of the currently active perception strategy.
    """
    last_screenshot_path: Optional[str] = None
    last_action: Optional[Action] = None
    current_strategy_idx: int = 0

@PluginRegistry.register(namespace="agent.type", name="modular_agent")
class ModularAgent:
    """Modular agent：按配置装配 planner、可选 verifier、perception、reasoning、memory 等。

    单步执行顺序以 ``step()`` 为准：可选 Verifier（上一步有 Action 时）→ Perception → Memory 经验命中则短路返回
    → 否则读 Memory 上下文后经 Reasoning 生成 Action 并回写 Memory。初始化（任务、清空记忆、Planner 一次、Plan 入库）
    仅在 ``reset()``。Studio 架构图见前端 ``modularArchitectureGraph``，与上述两阶段一致。
    """

    _pipeline_phase = "🧠 Agent"

    def __init__(self, config: Dict[str, Any], device: Any, context: Dict[str, Any] = None):
        namespace = getattr(self.__class__, '__plugin_namespace__', 'agent.type')
        name = getattr(self.__class__, '__plugin_name__', self.__class__.__name__)
        self.logger = get_plugin_logger(phase=self._pipeline_phase, namespace=namespace, plugin_name=name)
        self.config = config
        self.device = device
        self.context = context or {}
        self.verbose = config.get("verbose", True)
        
        # 1. Dynamically build components from config using the Registry
        self.components = {}
        self._build_components()
        
        # 2. Extract components to instance variables for convenient access
        perception_comp = self.components.get("perception")
        # Support multiple perception strategies for graceful degradation
        self.perceptions = perception_comp if isinstance(perception_comp, list) else [perception_comp]
        
        self.reasoning = self.components.get("reasoning")
        self.memory = self.components.get("memory")
        self.planner = self.components.get("planner")
        self.verifier = self.components.get("verifier")
        
        # 3. Initialize Runtime States
        self.state = AgentRuntimeState()
        self.current_task = ""
        self.current_plan = ""
        # Filled on reset() from runner: device-agnostic catalog text for reasoning prompts
        self._start_app_catalog_text = ""
    
    def _build_components(self) -> None:
        """Dynamically instantiates all components defined in the configuration."""
        components_config = self.config.get("components", {})
        if not components_config:
            self.logger.warning("❌ No 'components' found in agent config. Agent will be empty.")
            return

        # 1. Fetch the global default LLM configuration
        global_llm_config = self.config.get("global_config", {}).get("default_llm")
        
        # 2. Instance Cache: Prevents creating multiple duplicate LLM clients 
        # if multiple components fallback to the same global LLM.
        llm_instance_cache = {}

        for comp_role, comp_info in components_config.items():
            if comp_role == "action":
                self.components[comp_role] = comp_info
                self.logger.info(
                    "Action component config is recorded for compatibility; "
                    "physical execution is handled by AgentRunner and the device backend."
                )
                continue

            if isinstance(comp_info, list):
                self.components[comp_role] = [
                    self._build_one_component(comp_role, one_info, global_llm_config, llm_instance_cache)
                    for one_info in comp_info
                ]
                continue

            self.components[comp_role] = self._build_one_component(
                comp_role, comp_info, global_llm_config, llm_instance_cache
            )

    def _build_one_component(
        self,
        comp_role: str,
        comp_info: Dict[str, Any],
        global_llm_config: Dict[str, Any],
        llm_instance_cache: Dict[str, Any],
    ) -> Any:
        """Instantiate one configured component for a role."""
            
        self.logger.info(f"Loading {comp_role} Component")

        comp_name = comp_info.get("name")
        if not comp_name:
            raise ValueError(f"Missing component name for role: {comp_role}")
        
        namespace = f"agent.{comp_role}"
        kwargs = comp_info.get("params", {}).copy()
        if comp_role == "reasoning":
            kwargs.pop("device", None)

        # =========================================================
        # ✨ Core Logic: Local Override vs Global Fallback
        # =========================================================
        # Prefer local component LLM config; fallback to global if missing
        llm_config = comp_info.get("llm") or global_llm_config
        
        if llm_config:
            
            llm_name = llm_config.get("name")

            self.logger.info(f"{comp_role} custome llm: {llm_name}")
            
            # Create a unique hash/string of the config to use as a cache key
            cache_key = str(llm_config)
            
            if cache_key not in llm_instance_cache:
                # Not in cache? Instantiate it for the first time
                LLMClass = PluginRegistry.get_plugin(namespace="llm", name=llm_name)
                llm_params = llm_config.get("params", {}).copy()
                
                # Instantiate the LLM (e.g., OpenAILLM) using unpacked params
                try:
                    llm_instance_cache[cache_key] = LLMClass(**llm_params, context=self.context)
                    self.logger.info(f"🔗 Initialize new LLM instance: {llm_name}")
                except Exception as e:
                    self.logger.error(f"❌ Failed to initialize LLM [{llm_name}]: {e}")
                    raise
            
            # Dependency Injection: Inject the shared or specific LLM instance
            kwargs["llm_client"] = llm_instance_cache[cache_key]

        # 3. Inject framework global objects (reasoning stays device-free)
        if comp_role != "reasoning":
            kwargs["device"] = self.device
        kwargs["context"] = self.context

        # 4. Instantiate the component using dynamic unpacking
        try:
            CompClass = PluginRegistry.get_plugin(namespace=namespace, name=comp_name)
            component = CompClass(**kwargs)
            self.logger.info(f"✅ Loaded Component [{comp_role.upper()}]: {comp_name}")
            return component
        except Exception as e:
            self.logger.error(f"❌ Failed to load component [{comp_role}::{(comp_name)}]: {e}")
            raise

    def reset(self, runner_input: Dict[str, Any]) -> None:
        """Resets the agent's memory and state for a new task.

        Args:
            runner_input (Dict[str, Any]): Contains task instructions and parameters.
                Expected keys include ``instruction``, optional ``app``, and optional
                ``start_app_catalog_text`` (pre-rendered list from the runner / device).
        """
        task = runner_input.get("instruction", "Unknown Task")
        self.current_task = task
        self.logger.info(f"Agent reset task: {task}")
        
        self.state = AgentRuntimeState()
        
        if self.memory:
            self.memory.clear()
            self.memory.add(MemoryFragment(
                role="system",
                type=FragmentType.TEXT,
                content=f"New task started: {task}"
            ))
        
        if self.planner:
            self.logger.info("Agent generating plan...")
            plan_input = PlanInput(task=task)
            plan_result = self.planner.make_plan(plan_input)
            
            self.current_plan = getattr(plan_result, "content", str(plan_result))
            preview = self.current_plan
            if len(preview) > 300:
                preview = preview[:300] + "…"
            self.logger.info("Plan loaded (%d chars): %s", len(self.current_plan), preview)
            self.logger.debug("Full plan: %s", self.current_plan)
            
            self.memory.add(MemoryFragment(
                role="system",
                type=FragmentType.PLAN,
                content=f"Plan: {self.current_plan}",
                metadata=getattr(plan_result, "data", {})
            ))
        else:
            self.current_plan = "No specific plan, execute step by step."

        self._start_app_catalog_text = runner_input.get("start_app_catalog_text") or ""

    def step(self, screenshot_path: str, width: int, height: int, xml_path: str) -> Action:
        """Executes a single interaction cycle (Verification -> Perception -> Reasoning).

        Args:
            screenshot_path (str): Local path to the current device screenshot.
            width (int): Screen width in pixels.
            height (int): Screen height in pixels.

        Returns:
            Action: The decision formulated by the reasoning component.
        """
        # =================================================
        # 0. Verification Phase
        # =================================================
        if self.verifier and self.state.last_screenshot_path and self.state.last_action:
            # Only verify actions that physically affect the screen
            if self.state.last_action.type in [
                ActionType.TAP,
                ActionType.LONG_PRESS,
                ActionType.SWIPE,
                ActionType.TEXT,
                ActionType.START_APP,
            ]:
                
                verify_input = VerifierInput(
                    task=self.current_task,
                    screenshot_before=self.state.last_screenshot_path,
                    screenshot_after=screenshot_path,
                    action=self.state.last_action
                )
                
                verify_result = self.verifier.verify(verify_input)
                self._record_verifier_result(verify_result)
                
                if not verify_result.is_success:
                    self.logger.warning(f"❌ [Verifier] Previous action verification failed: {verify_result.feedback}")
                    feedback = verify_result.feedback

                    if verify_result.correction_suggestion is not None:
                        correction = verify_result.correction_suggestion
                        self.logger.info(
                            "🔁 [Verifier] Returning correction action: %s %s",
                            correction.type.value,
                            correction.params,
                        )
                        self._save_action_to_memory(correction, feedback, source="verifier_correction")
                        self.state.last_screenshot_path = screenshot_path
                        self.state.last_action = correction
                        return correction

                    # Attempt to downgrade perception strategy
                    if self.state.current_strategy_idx < len(self.perceptions) - 1:
                        self.state.current_strategy_idx += 1
                        new_strategy_name = self.perceptions[self.state.current_strategy_idx].__class__.__name__
                        self.logger.info(f"🔄 [Agent] Auto-switching perception strategy -> {new_strategy_name}")
                        if self.memory:
                            self.memory.add(MemoryFragment(
                                role="system",
                                type=FragmentType.ERROR,
                                content=f"Previous action failed verification. Reason: {feedback}. Switching perception strategy.",
                            ))
                    else:
                        self.logger.warning("⚠️ [Agent] No additional strategies available. Continuing with current strategy.")
                        if self.memory:
                            self.memory.add(MemoryFragment(
                                role="system",
                                type=FragmentType.ERROR,
                                content=(
                                    f"Previous action failed verification. Reason: {feedback}. "
                                    "The UI likely did not change; do not repeat the same tap or grid area—"
                                    "try a different cell or action (e.g. keypad, Swipe)."
                                ),
                            ))
                else:
                    if self.verbose: 
                        self.logger.info(f"✅ [Verifier] Verification passed: {verify_result.feedback}")
                    progress = (verify_result.metadata or {}).get("progress")
                    if progress and self.memory:
                        self.memory.add(MemoryFragment(
                            role="system",
                            type=FragmentType.TEXT,
                            content=f"Completed contents: {progress}",
                            metadata={"source": "verifier_progress"},
                        ))
                    # Recover to primary strategy upon success
                    if self.state.current_strategy_idx != 0:
                        self.logger.info("🔄 [Agent] Action successful, reverting to primary perception strategy.")
                        self.state.current_strategy_idx = 0

        # =================================================
        # 1. Perception Phase
        # =================================================
        current_perception_tool = self.perceptions[self.state.current_strategy_idx]
        perception_result = None
        
        try:
            perception_input = PerceptionInput(
                screenshot_path=screenshot_path,
                width=width,
                height=height,
                ui_path=xml_path
            )
            perception_result = current_perception_tool.perceive(perception_input)
            
            if perception_result is None:
                raise ValueError("Perception returned None")
                
        except Exception as e:
            self.logger.error(
                "perception failed class=%s: %s",
                current_perception_tool.__class__.__name__,
                e,
                exc_info=True,
            )
            if self.state.current_strategy_idx < len(self.perceptions) - 1:
                self.state.current_strategy_idx += 1
                self.logger.info("Agent Perception Error, trying next perception strategy...")
                return self.step(screenshot_path, width, height, xml_path)
            else:
                return Action(type=ActionType.FAIL, thought=f"All perception strategies crashed: {e}")

        if self.verbose:
            self.logger.info(f"Agent perception done (Mode: {getattr(perception_result, 'mode', 'default')})")

        # =================================================
        # 2. Fast Path: Knowledge Traces
        # =================================================
        cached_action = None
        if self.memory:
            cached_action = self.memory.retrieve_experience(screenshot_path, self.current_task)
        
        if cached_action:
            self.logger.info(f"Agent Fast Path execute: {cached_action.type}")
            self._save_action_to_memory(cached_action, "Loaded from cache", source="memory_cache")
            self.state.last_screenshot_path = screenshot_path
            self.state.last_action = cached_action
            return cached_action

        # =================================================
        # 3. Slow Path (Reasoning)
        # =================================================
        context_fragments = []
        if self.memory:
            self.memory.load_knowledge(query=self.current_task)
            context_fragments = self.memory.get_working_context()

        if self.verbose: 
            self.logger.info("Agent Slow Path execute...")
        
        try:
            action, response = self.reasoning.think(
                task=self.current_task,
                plan=self.current_plan,
                perception_result=perception_result,
                memory_context=context_fragments,
                available_apps=self._start_app_catalog_text,
            )
        except Exception as e:
            self.logger.error("reasoning.think failed: %s", e, exc_info=True)
            return Action(type=ActionType.FAIL, thought=f"Brain Error: {e}")

        # =================================================
        # 4. State Update
        # =================================================
        self._save_action_to_memory(action, response, source="brain")
        
        self.state.last_screenshot_path = screenshot_path
        self.state.last_action = action
        self._apply_next_perception_hint(action)
        
        if self.verbose:
            self.logger.info(f"Agent decision generation: {action.type.value} {action.params}")

        return action

    def _is_verifiable_action(self, action: Action) -> bool:
        """Whether an action should be judged against the next screenshot."""
        return action.type in [
            ActionType.TAP,
            ActionType.LONG_PRESS,
            ActionType.SWIPE,
            ActionType.TEXT,
            ActionType.START_APP,
        ]

    def _perceive_current_screen(self, screenshot_path: str, width: int, height: int, xml_path: str):
        """Run the active perception strategy, falling back to the next configured strategy on crash."""
        current_perception_tool = self.perceptions[self.state.current_strategy_idx]

        try:
            perception_input = PerceptionInput(
                screenshot_path=screenshot_path,
                width=width,
                height=height,
                ui_path=xml_path,
            )
            perception_result = current_perception_tool.perceive(perception_input)

            if perception_result is None:
                raise ValueError("Perception returned None")

            if self.verbose:
                self.logger.info(f"Agent perception done (Mode: {getattr(perception_result, 'mode', 'default')})")
            return perception_result

        except Exception as e:
            self.logger.error(
                "perception failed class=%s: %s",
                current_perception_tool.__class__.__name__,
                e,
                exc_info=True,
            )
            if self.state.current_strategy_idx < len(self.perceptions) - 1:
                self.state.current_strategy_idx += 1
                self.logger.info("Agent Perception Error, trying next perception strategy...")
                return self._perceive_current_screen(screenshot_path, width, height, xml_path)
            raise

    def _get_cached_action(self, screenshot_path: str) -> Optional[Action]:
        """Optional experience-memory fast path used by the generic modular pipeline."""
        if not self.memory:
            return None
        return self.memory.retrieve_experience(screenshot_path, self.current_task)

    def _get_reasoning_context(self) -> List[MemoryFragment]:
        """Load optional knowledge and return the working memory visible to reasoning."""
        if not self.memory:
            return []
        self.memory.load_knowledge(query=self.current_task)
        return self.memory.get_working_context()

    def _think_with_reasoning(self, perception_result) -> tuple[Action, str]:
        """Invoke the configured reasoning component with the current task, plan, perception, and memory."""
        context_fragments = self._get_reasoning_context()
        return self.reasoning.think(
            task=self.current_task,
            plan=self.current_plan,
            perception_result=perception_result,
            memory_context=context_fragments,
            available_apps=self._start_app_catalog_text,
        )

    def _commit_action(self, action: Action, response: str, source: str, screenshot_path: str) -> None:
        """Persist an action decision and make it the action to be verified on the next step."""
        self._save_action_to_memory(action, response, source=source)
        self.state.last_screenshot_path = screenshot_path
        self.state.last_action = action
        self._apply_next_perception_hint(action)

    def _record_verifier_result(self, verify_result) -> None:
        if self.memory and hasattr(self.memory, "record_verification"):
            try:
                self.memory.record_verification(verify_result)
            except Exception as e:
                self.logger.warning("memory.record_verification failed: %s", e)

    def _apply_next_perception_hint(self, action: Action) -> None:
        """Allow parsers to request a perception strategy for the next step."""
        hint_name = action.metadata.get("next_perception_name") if action.metadata else None
        hint_index = action.metadata.get("next_perception_index") if action.metadata else None

        if hint_index is not None:
            try:
                idx = int(hint_index)
            except (TypeError, ValueError):
                idx = None
            if idx is not None and 0 <= idx < len(self.perceptions):
                self.state.current_strategy_idx = idx
            return

        if not hint_name:
            return

        for idx, perception in enumerate(self.perceptions):
            plugin_name = getattr(perception.__class__, "__plugin_name__", "")
            class_name = perception.__class__.__name__
            mode_name = getattr(perception, "mode_name", "")
            if hint_name in {plugin_name, class_name, mode_name}:
                self.state.current_strategy_idx = idx
                self.logger.info("Next perception strategy requested: %s", hint_name)
                return

    def _save_action_to_memory(self, action: Action, response: str, source: str) -> None:
        """Persists the executed action and textual reasoning to memory.

        Args:
            action (Action): The generated action object.
            response (str): The raw text response from the reasoning module.
            source (str): Identifier of the generation source (e.g., 'brain', 'memory_cache').
        """
        if not self.memory:
            return

        note = (action.metadata or {}).get("take_note")
        if note:
            self.memory.add(MemoryFragment(
                role="system",
                type=FragmentType.TEXT,
                content=f"Memory note: {note}",
                metadata={"source": "take_note"},
            ))
            
        self.memory.add(MemoryFragment(
            role="assistant",
            type=FragmentType.ACTION,
            content=action,
            metadata={"source": source}
        ))

        self.memory.add(MemoryFragment(
            role="assistant",
            type=FragmentType.TEXT,
            content=response,
            metadata={"source": source}
        ))
