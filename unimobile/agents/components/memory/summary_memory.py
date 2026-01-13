import logging
from typing import List, Any
from unimobile.core.interfaces import BaseMemory, BaseBrain
from unimobile.core.protocol import MemoryFragment, FragmentType
from unimobile.utils.registry import register_memory

logger = logging.getLogger(__name__)

@register_memory("summary_memory")
class SummaryMemory(BaseMemory):
    def __init__(self, 
                 llm_client: BaseBrain,
                 knowledge_source: Any = None,
                 max_history_len: int = 10,
                 compress_ratio: float = 0.5
                 ):
        super().__init__(knowledge_source)
        self.llm = llm_client
        self.max_history_len = max_history_len
        self.compress_ratio = compress_ratio
        
        self.summary_content: str = ""
        
        self.active_history: List[MemoryFragment] = []
        
        self.system_fragment: MemoryFragment = None

    def add(self, fragment: MemoryFragment):
        if fragment.role == "system" and fragment.type == FragmentType.TEXT:
            self.system_fragment = fragment
            return

        self.active_history.append(fragment)
        
        if len(self.active_history) > self.max_history_len:
            self._compress_history()

    def get_working_context(self) -> List[MemoryFragment]:
        context = []

        # System
        if self.system_fragment:
            context.append(self.system_fragment)

        # Knowledge
        context.extend(self.knowledge_buffer)

        # Summary
        if self.summary_content:
            context.append(MemoryFragment(
                role="system",
                type=FragmentType.TEXT,
                content=f"--- Previous Conversation Summary ---\n{self.summary_content}\n-----------------------------------"
            ))

        # Active History
        context.extend(self.active_history)

        return context

    def clear(self):
        super().clear()
        self.active_history = []
        self.summary_content = ""

    def _compress_history(self):
        """
        compress
        """
        cut_index = int(self.max_history_len * self.compress_ratio)
        if cut_index == 0: return

        to_compress = self.active_history[:cut_index]
        remaining = self.active_history[cut_index:]

        history_text = ""
        for frag in to_compress:
            content = str(frag.content)
            if hasattr(frag.content, 'type') and hasattr(frag.content, 'params'):
                content = f"{frag.content.type.value} {frag.content.params}"
            history_text += f"[{frag.role}]: {content}\n"

        prompt = f"""
        You are a helpful assistant summarizing a conversation history for a mobile agent.
        
        Previous Summary:
        {self.summary_content or "None"}
        
        New Conversation to Compress:
        {history_text}
        
        Task:
        Summarize the new conversation and merge it with the previous summary. 
        Keep key information about what the user wanted and what actions the agent performed.
        Be concise.
        """

        try:
            new_summary = self.llm.generate(prompt)
            if new_summary:
                self.summary_content = new_summary
                self.active_history = remaining
                logger.info(f"compress successful: {len(new_summary)}")
        except Exception as e:
            logger.error(f"compress failed: {e}")