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

logger = logging.getLogger(__name__)


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
    """Modular agent strategy executing a linear Perception -> Reasoning -> Action flow.
    
    This agent dynamically builds its components (Perception, Reasoning, Memory, etc.) 
    based on the provided configuration dictionary.
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
    
    def _build_components(self) -> None:
        """Dynamically instantiates all components defined in the configuration."""
        components_config = self.config.get("components", {})
        if not components_config:
            logger.warning("No 'components' found in agent config. Agent will be empty.")
            return

        # 1. Fetch the global default LLM configuration
        global_llm_config = self.config.get("global_config", {}).get("default_llm")
        
        # 2. Instance Cache: Prevents creating multiple duplicate LLM clients 
        # if multiple components fallback to the same global LLM.
        llm_instance_cache = {}

        for comp_role, comp_info in components_config.items():
            comp_name = comp_info.get("name")
            if not comp_name:
                continue
            
            namespace = f"agent.{comp_role}"
            kwargs = comp_info.get("params", {}).copy()
            
            # =========================================================
            # ✨ Core Logic: Local Override vs Global Fallback
            # =========================================================
            # Prefer local component LLM config; fallback to global if missing
            llm_config = comp_info.get("llm") or global_llm_config
            
            if llm_config:
                llm_name = llm_config.get("name")
                
                # Create a unique hash/string of the config to use as a cache key
                cache_key = str(llm_config)
                
                if cache_key not in llm_instance_cache:
                    # Not in cache? Instantiate it for the first time
                    LLMClass = PluginRegistry.get_plugin(namespace="llm", name=llm_name)
                    llm_params = llm_config.get("params", {}).copy()
                    
                    # Instantiate the LLM (e.g., OpenAILLM) using unpacked params
                    try:
                        llm_instance_cache[cache_key] = LLMClass(**llm_params, context=self.context)
                        logger.info(f"🔗 Initialize new LLM instance: {llm_name}")
                    except Exception as e:
                        logger.error(f"❌ Failed to initialize LLM [{llm_name}]: {e}")
                        raise
                
                # Dependency Injection: Inject the shared or specific LLM instance
                kwargs["llm_client"] = llm_instance_cache[cache_key]

            # 3. Inject framework global objects
            kwargs["device"] = self.device
            kwargs["context"] = self.context

            # 4. Instantiate the component using dynamic unpacking
            try:
                CompClass = PluginRegistry.get_plugin(namespace=namespace, name=comp_name)
                self.components[comp_role] = CompClass(**kwargs)
                logger.info(f"✅ Loaded Component [{comp_role.upper()}]: {comp_name}")
            except Exception as e:
                logger.error(f"❌ Failed to load component [{comp_role}::{(comp_name)}]: {e}")
                raise

    def reset(self, runner_input: Dict[str, Any]) -> None:
        """Resets the agent's memory and state for a new task.

        Args:
            runner_input (Dict[str, Any]): Contains task instructions and parameters.
        """
        task = runner_input.get("instruction", "Unknown Task")
        self.current_task = task
        logger.info(f"Agent reset task: {task}")
        
        self.state = AgentRuntimeState()
        
        if self.memory:
            self.memory.clear()
            self.memory.add(MemoryFragment(
                role="system",
                type=FragmentType.TEXT,
                content=f"New task started: {task}"
            ))
        
        if self.planner:
            logger.info("Agent generating plan...")
            plan_input = PlanInput(task=task)
            plan_result = self.planner.make_plan(plan_input)
            
            self.current_plan = getattr(plan_result, "content", str(plan_result))
            logger.info(f"    -> plan: {self.current_plan}")
            
            self.memory.add(MemoryFragment(
                role="system",
                type=FragmentType.PLAN,
                content=f"Plan: {self.current_plan}",
                metadata=getattr(plan_result, "data", {})
            ))
        else:
            self.current_plan = "No specific plan, execute step by step."
    
    def step(self, screenshot_path: str, width: int, height: int) -> Action:
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
            if self.state.last_action.type in [ActionType.TAP, ActionType.SWIPE, ActionType.TEXT]:
                
                verify_input = VerifierInput(
                    task=self.current_task,
                    screenshot_before=self.state.last_screenshot_path,
                    screenshot_after=screenshot_path,
                    action=self.state.last_action
                )
                
                verify_result = self.verifier.verify(verify_input)
                
                if not verify_result.is_success:
                    logger.warning(f"❌ [Verifier] Previous action verification failed: {verify_result.feedback}")
                    
                    # Attempt to downgrade perception strategy
                    if self.state.current_strategy_idx < len(self.perceptions) - 1:
                        self.state.current_strategy_idx += 1
                        new_strategy_name = self.perceptions[self.state.current_strategy_idx].__class__.__name__
                        logger.info(f"🔄 [Agent] Auto-switching perception strategy -> {new_strategy_name}")
                        
                        self.memory.add(MemoryFragment(
                            role="system",
                            type=FragmentType.ERROR,
                            content=f"Previous action failed verification. Reason: {verify_result.feedback}. Switching perception strategy."
                        ))
                    else:
                        logger.warning("⚠️ [Agent] No additional strategies available. Continuing with current strategy.")
                else:
                    if self.verbose: 
                        logger.info(f"✅ [Verifier] Verification passed: {verify_result.feedback}")
                    # Recover to primary strategy upon success
                    if self.state.current_strategy_idx != 0:
                        logger.info("🔄 [Agent] Action successful, reverting to primary perception strategy.")
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
                height=height
            )
            perception_result = current_perception_tool.perceive(perception_input)
            
            if perception_result is None:
                raise ValueError("Perception returned None")
                
        except Exception as e:
            logger.error(f"Perception {current_perception_tool.__class__.__name__} Error: {e}")
            if self.state.current_strategy_idx < len(self.perceptions) - 1:
                self.state.current_strategy_idx += 1
                logger.info("Agent Perception Error, trying next perception strategy...")
                return self.step(screenshot_path, width, height)
            else:
                return Action(type=ActionType.FAIL, thought=f"All perception strategies crashed: {e}")

        if self.verbose:
            logger.info(f"Agent perception done (Mode: {getattr(perception_result, 'mode', 'default')})")

        # =================================================
        # 2. Fast Path: Knowledge Traces
        # =================================================
        cached_action = None
        if self.memory:
            cached_action = self.memory.retrieve_experience(screenshot_path, self.current_task)
        
        if cached_action:
            logger.info(f"Agent Fast Path execute: {cached_action.type}")
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
            logger.info("Agent Slow Path execute...")
        
        try:
            action, response = self.reasoning.think(
                task=self.current_task,
                plan=self.current_plan,
                perception_result=perception_result,
                memory_context=context_fragments
            )
        except Exception as e:
            logger.error(f"Agent think Error: {e}")
            return Action(type=ActionType.FAIL, thought=f"Brain Error: {e}")

        # =================================================
        # 4. State Update
        # =================================================
        self._save_action_to_memory(action, response, source="brain")
        
        self.state.last_screenshot_path = screenshot_path
        self.state.last_action = action
        
        if self.verbose:
            logger.info(f"Agent decision generation: {action.type.value} {action.params}")

        return action

    def _save_action_to_memory(self, action: Action, response: str, source: str) -> None:
        """Persists the executed action and textual reasoning to memory.

        Args:
            action (Action): The generated action object.
            response (str): The raw text response from the reasoning module.
            source (str): Identifier of the generation source (e.g., 'brain', 'memory_cache').
        """
        if not self.memory:
            return
            
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