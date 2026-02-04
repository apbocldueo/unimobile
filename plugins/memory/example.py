import logging
from typing import List
from unimobile.core.interfaces import BaseMemory
from unimobile.knowledge.base import BaseKnowledgeSource
from unimobile.core.protocol import Action, MemoryFragment, FragmentType
from unimobile.utils.registry import register_memory

logger = logging.getLogger(__name__)

@register_memory("example_memory")
class ExampleMemory(BaseMemory):
    def __init__(self, knowledge_source: BaseKnowledgeSource = None):
        super().__init__(knowledge_source)

        # running dynamic history
        self.history_buffer: List[MemoryFragment] = []

        # static konwledge
        self.knowledge_buffer: List[MemoryFragment] = []
        
        # running static system
        self.system_buffer: List[MemoryFragment] = []
    
    def add(self, fragment: MemoryFragment):
        self.history_buffer.append(fragment)

    def get_working_context(self) -> List[MemoryFragment]:
        context = []

        # add system
        context.extend(self.system_buffer)

        # add knowledge (slow)
        context.extend(self.knowledge_buffer)

        # add history (fast)
        ##

        return context
    