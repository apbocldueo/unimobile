from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, Optional, List

class ActionType(Enum):
    TAP = "tap"
    SWIPE = "swipe"
    TEXT = "text"
    KEY = "key"     
    DONE = "done"   
    FAIL = "fail"   
    WAIT = "wait"   

@dataclass
class Action:
    """
    Agent Action
    """
    type: ActionType
    params: Dict[str, Any] = field(default_factory=dict)
    
    thought: Optional[str] = None

    metadata: Dict[str, Any] = field(default_factory=dict)

# ==========================================
# Infrastructure Interfaces
# ==========================================

@dataclass
class PerceptionResult:
    """
    The unified output format of the perception
    TODO
    """
    mode: str
    original_screenshot_path: str
    
    elements: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    data: Dict[str, Any] = field(default_factory=dict)
    marked_screenshot_path: Optional[str] = None
    
    prompt_representation: str = "" 
    
    visual_representations: List[str] = field(default_factory=list)

@dataclass
class PerceptionInput:
    screenshot_path: str
    width: int
    height: int
    ui_path: str = None

@dataclass
class PlanResult:
    """
    The output result of the planner
    """
    content: str 
    
    # {"target_app": "com.tencent.mm", "steps": [...]}
    data: Dict[str, Any] = field(default_factory=dict)

class FragmentType(Enum):
    TEXT = "text"
    IMAGE = "image"
    ACTION = "action"
    ERROR = "error"

    RAG_DOC = "rag_doc"     
    USER_PROFILE = "profile"
    FEW_SHOT = "few_shot"
    PLAN = "plan"

@dataclass
class MemoryFragment:
    """
    The smallest unit of memory
    """
    role: str   # "user", "assistant", "system"
    type: FragmentType   # "text", "image", "action", "knowledge"
    content: Any
    metadata: Dict = field(default_factory=dict)
    
@dataclass
class KnowledgeDoc:
    id: str
    content: str

    # e.g., "manual", "user_profile", "legal_warning", "custom_xyz"
    category: str = "general" 
    
    # e.g., {"source": "finance_policy_v2.pdf", "validity": "2025"}
    metadata: Dict[str, Any] = field(default_factory=dict)

    score: float = 0.0
    
@dataclass
class ExperienceTrace:
    id: str
    task_hash: str
    screenshot_hash: str
    action: Action
    success_rate: float = 1.0

@dataclass
class VerifierInput:
    task: str
    screenshot_before: str
    screenshot_after: str
    action: Action

    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class VerifierResult:
    is_success: bool
    feedback: str = ""
    
    score: float = 0.0
    should_retry: bool = False
    correction_suggestion: Optional[Action] = None
    
    metadata: Dict[str, Any] = field(default_factory=dict)
