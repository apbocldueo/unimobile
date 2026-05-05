
ATOMIC_ACTION_SIGNITURES = {
    "Tap": {
        "arguments": ["x", "y"],
        "description": lambda info: "Tap the absolute position (x, y) on the screen. Example: {\"name\":\"Tap\", \"arguments\":{\"x\":\"100\", \"y\": \"200\"}}"
    },
    "Swipe": {
        "arguments": ["direction", "dist"],
        "description": lambda info: "Swipe the screen. 'direction' must be one of: 'up', 'down', 'left', 'right'. CRITICAL: Swipe 'up' (finger moves up) to view content BELOW. Swipe 'down' (finger moves down) to view content ABOVE. 'dist' must be 'short', 'medium', or 'long'. Example: {\"name\":\"Swipe\", \"arguments\":{\"direction\":\"up\", \"dist\": \"medium\"}}"
    },
    "Type": {
        "arguments": ["text"],
        "description": lambda info: "Type 'text' into the currently focused input box. PRECONDITION: You MUST ensure the input box is already activated (usually by using 'Tap' first) and the virtual keyboard is visible. Example: {\"name\":\"Type\", \"arguments\":{\"text\":\"hello\"}}"
    },
    "Enter": {
        "arguments": [],
        "description": lambda info: "Press the 'Enter' or 'Search' key on the virtual keyboard to submit the typed text. Example: {\"name\":\"Enter\", \"arguments\":{}}"
    },
    "Back": {
        "arguments": [],
        "description": lambda info: "Press the system Back button to return to the previous page or close the keyboard. Example: {\"name\":\"Back\", \"arguments\":{}}"
    },
    "Home": {
        "arguments": [],
        "description": lambda info: "Press the system Home button to return to the desktop. Example: {\"name\":\"Home\", \"arguments\":{}}"
    },
    "Clear":{
        "arguments": [],
        "description": lambda info: "Clear all existing text in the currently focused input box. Use this before 'Type' if you need to replace existing text. Example: {\"name\":\"Clear\", \"arguments\":{}}"
    },
    "Done": {
        "arguments": [],
        "description": lambda info: "CRITICAL TERMINATION SIGNAL. Output this action IMMEDIATELY when you observe that the user's task goal has been successfully achieved. Do not perform any further redundant checks or actions. Example: {\"name\":\"Done\", \"arguments\":{}}"
    }
}


ATOMIC_ACTION_SIGNITURES_GRIDDING = {
    "Tap": {
        "arguments": ["area", "subarea"],
        "description": lambda info: "Tap a specific grid area. 'area' is the integer label (e.g., 5). 'subarea' defines the exact relative location within that grid: 'center', 'top-left', 'top', 'top-right', 'left', 'right', 'bottom-left', 'bottom', or 'bottom-right'. Example: {\"name\":\"Tap\", \"arguments\":{\"area\":5, \"subarea\": \"center\"}}"
    },
    "Swipe": {
        "arguments": ["direction", "dist"],
        "description": lambda info: "Swipe the screen. CRITICAL: Swipe 'up' means finger moves UP, which scrolls the page DOWN to reveal content below. Swipe 'down' scrolls the page UP. 'dist' is 'short', 'medium', or 'long'. Example: {\"name\":\"Swipe\", \"arguments\":{\"direction\":\"up\", \"dist\": \"short\"}}"
    },
    "Type": {
        "arguments": ["text"],
        "description": lambda info: "Type 'text' into the currently focused input box. You MUST first use 'Tap' on the grid area containing the input box to activate it. Example: {\"name\":\"Type\", \"arguments\":{\"text\":\"AI Agent\"}}"
    },
    "Enter": {
        "arguments": [],
        "description": lambda info: "Press Enter to submit input. Use immediately after typing to trigger search or send. Example: {\"name\":\"Enter\", \"arguments\":{}}"
    },
    "Done": {
        "arguments": [],
        "description": lambda info: "CRITICAL TERMINATION SIGNAL. Output this action IMMEDIATELY when the task goal is achieved. Stop reasoning. Example: {\"name\":\"Done\", \"arguments\":{}}"
    },
    "Clear":{
        "arguments": [],
        "description": lambda info: "Clear all text in the currently focused input box. Example: {\"name\":\"Clear\", \"arguments\":{}}"
    }
}


ATOMIC_ACTION_SIGNITURES_SOM = {
    "Tap": {
        "arguments": ["element_id"],
        "description": lambda info: "Tap the UI element identified by its numeric red box tag ID. Example: {\"name\":\"Tap\", \"arguments\":{\"element_id\": 5}}"
    },
    "Type": {
        "arguments": ["text", "element_id"], 
        "description": lambda info: "Type text into an input box. If 'element_id' is provided, it will automatically focus that element and type. If 'element_id' is null/empty, it types into the currently focused field. Example: {\"name\":\"Type\", \"arguments\":{\"text\":\"coffee\", \"element_id\": 3}}"
    },
    "Swipe": {
        "arguments": ["direction", "dist"],
        "description": lambda info: "Swipe the screen. Direction ('up', 'down', 'left', 'right'). CRITICAL: Swipe 'up' scrolls the page DOWN. Swipe 'down' scrolls the page UP. Distance ('short', 'medium', 'long'). Example: {\"name\":\"Swipe\", \"arguments\":{\"direction\":\"up\", \"dist\": \"medium\"}}"
    },
    "Enter": {
        "arguments": [],
        "description": lambda info: "Press Enter to submit the text just typed. Example: {\"name\":\"Enter\", \"arguments\":{}}"
    },
    "Back": {
        "arguments": [],
        "description": lambda info: "Return to the previous state or close popups/keyboards. Example: {\"name\":\"Back\", \"arguments\":{}}"
    },
    "Home": {
        "arguments": [],
        "description": lambda info: "Return to home page. Example: {\"name\":\"Home\", \"arguments\":{}}"
    },
    "Done": {
        "arguments": [],
        "description": lambda info: "CRITICAL TERMINATION SIGNAL. Output this action IMMEDIATELY when the task goal is achieved. Stop reasoning. Example: {\"name\":\"Done\", \"arguments\":{}}"
    },
    "Clear":{
        "arguments": [],
        "description": lambda info: "Clear the text in the currently focused input box. Example: {\"name\":\"Clear\", \"arguments\":{}}"
    }
}

def get_action_space_by_mode(mode: str) -> dict:
    """根据感知模式，动态路由并返回对应的动作空间说明书"""
    if mode == "grid":
        return ATOMIC_ACTION_SIGNITURES_GRIDDING
    elif mode == "set_of_marks":
        return ATOMIC_ACTION_SIGNITURES_SOM
    
    # 默认返回原始坐标空间
    return ATOMIC_ACTION_SIGNITURES