# TODO
from typing import Dict

KNOWLEDGE_TEMPLATES: Dict[str, str] = {
    "general": "--- Reference Info ---\n{content}",
    
    # 1. AppManual
    "manual": "--- App Operation Manual ---\nTip: {content}",
    
    # 2. Profile
    "user_profile": "--- User Preference ---\nIMPORTANT: The user prefers: {content}",
    
    # 3. Rule
    "constraint": "--- SAFETY CONSTRAINT ---\nWARNING: You MUST follow this rule: {content}",
    
    # 4. Few-Shot
    "example": "--- Success Example ---\nHere is how to do it: {content}"
}

def register_knowledge_template(category: str, template: str):
    """
    Users can register their own unique Prompt formats for knowledge types through this function
    """
    KNOWLEDGE_TEMPLATES[category] = template

def format_knowledge(doc) -> str:
    """
    Automatically select templates for packaging
    """
    template = KNOWLEDGE_TEMPLATES.get(doc.category, KNOWLEDGE_TEMPLATES["general"])
    try:
        # 使用 format 填充 content
        return template.format(content=doc.content, **doc.metadata)
    except Exception as e:
        return f"--- Knowledge ({doc.category}) ---\n{doc.content}"