from abc import ABC, abstractmethod
from typing import List, Optional, Any
from unimobile.core.protocol import Action, KnowledgeDoc

class BaseKnowledgeSource(ABC):
    """
    L4 Konwledge Base
    """

    @abstractmethod
    def add_document(self, app_name: str, content: str, metadata: dict = None):
        """
        Save a document
        """
        pass

    @abstractmethod
    def search_docs(self, query: str) -> List[KnowledgeDoc]:
        """
        Search document
        """
        pass

    @abstractmethod
    def add_trace(self, state_info: Any, task: str, action: Action):
        """Save a successful experience

        Args:
            state_info (Any): _description_
            task (str): _description_
            action (Action): _description_
        """
        
        
        pass

    @abstractmethod
    def match_trace(self, state_info: Any, task: str) -> Optional[Action]:
        """match document

        Args:
            state_info (Any): _description_
            task (str): _description_

        Returns:
            Optional[Action]: _description_
        """
        pass