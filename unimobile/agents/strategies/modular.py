from typing import Union, List, Optional
import logging
from dataclasses import dataclass

from unimobile.core.interfaces import BaseAgent, BasePerception, BaseReason, BaseMemory, BasePlanner, BaseVerifier
from unimobile.core.protocol import (
    Action, ActionType, 
    MemoryFragment, FragmentType, 
    PerceptionResult, PerceptionInput,
    VerifierInput, VerifierResult,
    PlanInput
)
from unimobile.utils.registry import register_strategy

logger = logging.getLogger(__name__)

@dataclass
class AgentRuntimeState:
    """
    It is used to maintain the state between steps for verification and rollback
    """
    last_screenshot_path: Optional[str] = None
    last_action: Optional[Action] = None
    current_strategy_idx: int = 0

@register_strategy("modular_agent")
class ModularAgent(BaseAgent):
    """
    Modular agent strategy (L3)
    """
    def __init__(
        self, 
        perception: Union[BasePerception, List[BasePerception]], 
        reasoning: BaseReason,           
        memory: BaseMemory,         
        planner: BasePlanner = None, 
        verifier: BaseVerifier = None,
        verbose: bool = True
    ):
        if isinstance(perception, list):
            self.strategies = perception
        else:
            self.strategies = [perception]
            
        self.reasoning = reasoning
        self.memory = memory
        self.planner = planner
        self.verifier = verifier
        self.verbose = verbose
        
        self.state = AgentRuntimeState()
        self.current_task = ""
        self.current_plan = ""

    def reset(self, task: str):
        self.current_task = task
        logger.info(f"Agent reset task: {task}")
        
        self.state = AgentRuntimeState()
        
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
            
            self.current_plan = plan_result.content
            logger.info(f"    -> plan: {self.current_plan}")
            
            self.memory.add(MemoryFragment(
                role="system",
                type=FragmentType.PLAN,
                content=f"Plan: {self.current_plan}",
                metadata=plan_result.data
            ))
        else:
            self.current_plan = "No specific plan, execute step by step."

    def step(self, screenshot_path: str, width: int, height: int) -> Action:
        
        # =================================================
        # 0. Verification Phase
        # =================================================
        if self.verifier and self.state.last_screenshot_path and self.state.last_action:
            
            if self.state.last_action.type in [ActionType.TAP, ActionType.SWIPE, ActionType.TEXT]:
                
                verify_input = VerifierInput(
                    task=self.current_task,
                    screenshot_before=self.state.last_screenshot_path,
                    screenshot_after=screenshot_path,
                    action=self.state.last_action
                )
                
                verify_result = self.verifier.verify(verify_input)
            
                if not verify_result.is_success:
                    logger.warning(f"The previous operation of the Verifier was judged as a failure: {verify_result.feedback}")

                    if self.state.current_strategy_idx < len(self.strategies) - 1:
                        self.state.current_strategy_idx += 1
                        new_strategy_name = self.strategies[self.state.current_strategy_idx].__class__.__name__
                        logger.info(f"The Agent automatically switches the perception strategy -> {new_strategy_name}")
                        
                        self.memory.add(MemoryFragment(
                            role="system",
                            type=FragmentType.ERROR,
                            content=f"Previous action failed verification. Reason: {verify_result.feedback}. Switching perception strategy."
                        ))
                    else:
                        logger.warning("The Agent has no more strategies to switch to. Keep trying the current strategy.")
                else:
                    # success
                    if self.verbose: logger.info(f"Verifier passed: {verify_result.feedback}")
                    if self.state.current_strategy_idx != 0:
                        logger.info("Agent operate successfully")
                        self.state.current_strategy_idx = 0

        # =================================================
        # 1. Perception Phase
        # =================================================
        current_perception_tool = self.strategies[self.state.current_strategy_idx]
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
            if self.state.current_strategy_idx < len(self.strategies) - 1:
                self.state.current_strategy_idx += 1
                logger.info("Agent Perception Error, try next perception...")
                return self.step(screenshot_path, width, height)
            else:
                return Action(type=ActionType.FAIL, thought=f"All perception strategies crashed: {e}")

        if self.verbose:
            logger.info(f"Agent perception done (Mode: {perception_result.mode})")

        # =================================================
        # 2. Fast Path: Konwledge Traces
        # =================================================
        cached_action = self.memory.retrieve_experience(screenshot_path, self.current_task)
        
        if cached_action:
            logger.info(f"Agent Fast Path execute: {cached_action.type}")
            
            self._save_action_to_memory(cached_action, source="memory_cache")
            
            self.state.last_screenshot_path = screenshot_path
            self.state.last_action = cached_action
            return cached_action

        # =================================================
        # 3. Slow Path
        # =================================================
        # A. Memory retriever
        self.memory.load_knowledge(query=self.current_task)

        # B. Get Fragment
        context_fragments = self.memory.get_working_context()

        # C. Think
        if self.verbose: logger.info("Agent Slow Path execute...")
        
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

    def _save_action_to_memory(self, action: Action, response: str, source: str):
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
