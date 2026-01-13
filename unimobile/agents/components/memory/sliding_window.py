from typing import List
from unimobile.core.interfaces import BaseMemory
from unimobile.knowledge.base import BaseKnowledgeSource
from unimobile.core.protocol import Action, MemoryFragment, FragmentType
from unimobile.utils.registry import register_memory

@register_memory("sliding_window")
class SlidingWindowMemory(BaseMemory):
    """
    Sliding Window Memory
    Features
    1. Only retain the History Buffer of the most recent N rounds.
    2. Permanently retain the System Prompt (System Buffer).
    3. Dynamically load Knowledge Buffer.
    """
    def __init__(self, 
                 window_size: int = 10,
                 knowledge_source: BaseKnowledgeSource = None,
                 include_thought: bool = True,
                 include_raw: bool = False):
        """

        Args:
            window_size (int, optional): window size. Defaults to 10.
            knowledge_source (BaseKnowledgeSource, optional): konwledge. Defaults to None.
            include_thought (bool, optional): thought. Defaults to True.
            include_raw (bool, optional): raw. Defaults to False.
        """
        
        super().__init__(knowledge_source)
        self.window_size = window_size
        self.include_thought = include_thought
        self.include_raw = include_raw

        self.history_buffer: List[MemoryFragment] = []
        self.knowledge_buffer: List[MemoryFragment] = []
        
        self.system_buffer: List[MemoryFragment] = []

    def add(self, fragment: MemoryFragment):
        if fragment.role == "system":
            self.system_buffer.append(fragment)
        else:
            # user/assistant
            self.history_buffer.append(fragment)
    

    def get_working_context(self) -> List[MemoryFragment]:
        context = []

        # System
        context.extend(self.system_buffer)

        # konwledge
        context.extend(self.knowledge_buffer)

        # history
        recent_history = self.history_buffer[-self.window_size:]

        for frag in recent_history:
            
            if frag.type == FragmentType.ACTION:
                action: Action = frag.content
                
                action_str = f"Action: {action.type.value}"
                if action.params:
                    action_str += f" {action.params}"
                
                content_str = action_str
                if self.include_thought and action.thought:
                    content_str = f"Thought: {action.thought}\n{action_str}"
                
                if self.include_raw and "raw_response" in action.metadata:
                    content_str += f"\n(Raw Output: {action.metadata['raw_response']})"

                new_frag = MemoryFragment(
                    role=frag.role,
                    type=FragmentType.TEXT,
                    content=content_str,
                    metadata=frag.metadata
                )
                context.append(new_frag)

            else:
                context.append(frag)

        return context
    
    def clear(self):
        self.history_buffer = []
        self.system_buffer = []