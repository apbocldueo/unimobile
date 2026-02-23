## Developing a Memory Plugin
### 1 Role & Responsibilities

A Memory Plugin manages contextual state and knowledge for the agent during execution.

In UniMobile, memory is responsible for:

+ Maintaining running execution history
+ Providing static or semi-static knowledge
+ Supplying a unified working context to planners, reasoners, or verifiers

### 2 Memory Design Pattern

Memory plugins in UniMobile follow a buffer-based composition pattern.

A typical memory implementation contains multiple buffers, each with a distinct semantic role:

System memory: static system-level context

Knowledge memory: external or long-term knowledge

History memory: dynamic execution traces

These buffers are merged on demand to form the agent’s working context.

### 3 Example: ExampleMemory
File location
```bash
docs/plugins/memory.md
```
Example Implementation
```python
@register_memory("example_memory")
class ExampleMemory(BaseMemory):
    def __init__(self, knowledge_source: BaseKnowledgeSource = None):
        super().__init__(knowledge_source)

        # running dynamic history
        self.history_buffer: List[MemoryFragment] = []

        # static knowledge
        self.knowledge_buffer: List[MemoryFragment] = []
        
        # static system context
        self.system_buffer: List[MemoryFragment] = []
    
    def add(self, fragment: MemoryFragment):
        """
        Add a memory fragment generated during execution.
        """
        self.history_buffer.append(fragment)

    def get_working_context(self) -> List[MemoryFragment]:
        """
        Assemble the current working context for downstream components.
        """
        context = []

        # system-level context (highest priority)
        context.extend(self.system_buffer)

        # long-term or external knowledge
        context.extend(self.knowledge_buffer)

        # recent execution history
        # (e.g., observations, actions, intermediate results)
        # context.extend(self.history_buffer)

        return context
```