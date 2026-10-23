PLANNING_PROMPT = """
Based on this Android screenshot, please help me with: {instruction}

Please provide:
1. A description of what you see on the current screen
2. What needs to be done to achieve the goal
3. A step-by-step action plan and expectations in JSON format like this: 
```JSON
{{
"Step1": {{"thought": "I need to open the Clock app.", "step": "Tap the Clock app.", "expectation": "The clock app is opened."}},
"Step2": {{"thought": "I need to open the stopwatch in Clock app.", "step": "TAP the Stopwatch tab", "expectation": "The Stopwatch tab is opened."}},
"Step3": {{"thought": "I need to start the stopwatch.", "step": "TAP the Start button.", "expectation": "The stopwatch begins running."}}
}}
```
For each step, you can choose from the following actions:
1. TAP
2. SWIPE
3. INPUT [text]
4. ENTER
5. ANSWER
6. DELETE TEXT

Make sure the step is brief and clear, you should only include the most important information in the step description. For example, if you need to tap a button, you should only outline the button's name but not its location on the screen.
Everytime you need to type text in somewhere, please split it into two steps: tap the respective text box first and then input the text, the text should in [].
If you need to delete a text, you should tap the respective text box and then DELETE TEXT to delete all the words of the text. If you need to search, after input text, you should also ENTER to confirm the search.
You should note that if you need to tap a delete buttoon, you should TAP that delete button, rather than DELETE TEXT.
Your response MUST strictly adhere the following structure, and DO NOT add other contents:

Description: <You need to describe the current screen and what you see on it.>
Thought: <You need to think about what needs to be done to achieve the goal.>
Plan: <You need to provide a plan in JSON format as described above.>
"""

ACTION_PROMPT_UITARS = """
You are a GUI agent. You are given a task and your action history, with screenshots. You need to perform the next action to complete the task. 
## Output Format
```
Thought: ...
Action: ...
```
## Action Space

click(point='<point>x1 y1</point>')
long_press(point='<point>x1 y1</point>')
type(content='') #If you want to submit your input, use "\\n" at the end of `content`.
scroll(point='<point>x1 y1</point>', direction='down or up or right or left')
open_app(app_name=\'\')
drag(start_point='<point>x1 y1</point>', end_point='<point>x2 y2</point>')
press_home()
press_back()
finished(content='xxx') # Use escape characters \\', \\", and \\n in content part to ensure we can parse the content in normal python string format.


## Note
- Use English in `Thought` part.
- Write a small plan and finally summarize your next action (with its target element) in one sentence in `Thought` part.

## User Instruction
{goal}
"""

DESCRIPTION_PROMPT = """
You are an expert visual assistant trained to analyze smartphone screenshots.
- You are provided with a screenshot of a mobile phone.
- You are required to describe all the contents and functionality of the current screen.
- You should focus on the main elements and their purposes, avoiding unnecessary details.
- Focus on brief, you should in 3-5 sentences.
"""

SUMARRY_PROMPT = """
You are an intelligent and helpful visual assistant adept at analyzing mobile devices.
You are provided with two screenshots: one before execution and one after execution. Compare the two images and determine whether the post-execution result meets the user expectation: {expectation}
Your respond should be in English.
"""

REPLANNING_PROMPT = """
Original Plan:
{original_plan}

The screen has changed as follows:
{descriptions}

Please create a new plan for goal: {goal} based on current screenshot and previous descriptions.

Please provide:
1. Why the previous action was not successful? [For example, Click the wrong button or text or which step need to be splited into two steps or earlier step is false]
2. What needs to be done to achieve the goal? [For example, declear the specific location of button you need to click]
3. What can you learn from this failure? [For example, I need to click the correct button or text or I need to split the step into two steps]
4. A new step-by-step action plan for REMAINING steps and expectations in JSON format like this: 
```JSON
{{
  "Step1": {{"thought": "I need to return to the Contacts tab.", "step": "PRESS_BACK", "expectation": "The Contacts section is showed."}},
  "Step2": {{"thought": "I notice that there is "Create new contact" text inc Contacts tab, but the step in orignal plan is "Tap Add Contact button", I need to tap the correct field.", "step": "Tap "Create new contact" text", "expectation": "The Add Contact screen is displayed."}},
  "Step3": {{"thought": "I need to enter the contact's name.", "step": "Tap Name field", "expectation": "The keyboard appears."}},
  "Step4": {{"thought": "I need to type the contact's name.", "step": "Input [Hugo Pereira]", "expectation": "The name 'Hugo Pereira' is showed in the screen."}},
  "Step5": {{"thought": "I need to enter the contact's phone number.", "step": "Tap Phone field", "expectation": "The keyboard appears."}},
  "Step6": {{"thought": "I need to type the contact's phone number.", "step": "Input [+13920741751]", "expectation": "The phone number '+13920741751' is showed in the screen."}},
  "Step7": {{"thought": "I need to save the new contact.", "step": "Tap Save button", "expectation": "The screen shows a new contact named 'Hugo Pereira' and number is '+13920741751'."}}
}}
```
For each step, you can choose from the following actions:
1. TAP
2. SWIPE
3. INPUT [text]
4. ENTER
5. ANSWER
6. DELETE TEXT
7. PRESS_HOME
8. PRESS_BACK

Make sure the step is brief and clear, you should only include the most important information in the step description. For example, if you need to click a button, you should only outline the button's name but not its location on the screen.
Everytime you need to type text in somewhere, please split it into two steps: tap the respective text box first and then input the text.  If you need to search, after input text, you should also ENTER to confirm the search.
If you need to delete a text, you should tap the respective text box and then DELETE TEXT to delete all the words of the text.
Your response MUST strictly adhere the following structure, and DO NOT add other contents:

Relection: <You need to reflect on the last action and what you can learn from this failure.>
Plan: <You need to provide a new plan for the remaining steps in JSON format as described above.>


If you have reviewed the screen history CAREFULLY and confirmed that the original plan is correct, please JUST respond with:
'No need to replan.'
"""

ACTION_PROMPT_SHOWUI = """
You are an assistant trained to navigate the phone screen. 
Given a task instruction, a screen observation, and an action history sequence, 
output the next action and wait for the next observation. 
Here is the action space:
1. `INPUT`: Type a string, value is a string to type. 
2. `SWIPE`: Swipe the screen, value is not applicable and the position [[x1,y1], [x2,y2]] is the start and end position of the swipe operation.
3. `TAP`: Tap on an element, value is not applicable and the position [x,y] is required.
4. `ANSWER`: Answer the question, value is the status (e.g., 'task complete') and the position is not applicable.
5. `ENTER`: Enter operation, value and position are not applicable.
Format the action as a dictionary with the following keys:
{'action': 'ACTION_TYPE', 'value': 'element', 'position': [x,y]}

If value or position is not applicable, set it as `None`.
Position might be [[x1,y1], [x2,y2]] if the action requires a start and end position.
Position represents the relative coordinates on the screenshot and should be scaled to a range of 0-1.
Task: {goal}"""

ACTION_PROMPT_OS_ATLAS = """
You are now operating in Executable Language Grounding mode. Your goal is to help users accomplish tasks by suggesting executable actions that best fit their needs. Your skill set includes both basic and custom actions:

1. Basic Actions
Basic actions are standardized and available across all platforms. They provide essential functionality and are defined with a specific format, ensuring consistency and reliability. 
Basic Action 1: CLICK 
    - purpose: Click at the specified position.
    - format: CLICK <point>[[x-axis, y-axis]]</point>
    - example usage: CLICK <point>[[101, 872]]</point>
       
Basic Action 2: TYPE
    - purpose: Enter specified text at the designated location.
    - format: TYPE [input text]
    - example usage: TYPE [Shanghai shopping mall]

Basic Action 3: SCROLL
    - purpose: SCROLL in the specified direction.
    - format: SCROLL [direction (UP/DOWN/LEFT/RIGHT)]
    - example usage: SCROLL [UP]
    
2.Custom Actions
Custom actions are unique to each user's platform and environment. They allow for flexibility and adaptability, enabling the model to support new and unseen actions defined by users. These actions extend the functionality of the basic set, making the model more versatile and capable of handling specific tasks.
Custom Action 1: LONG_PRESS 
    - purpose: Long press at the specified position.
    - format: LONG_PRESS <point>[[x-axis, y-axis]]</point>
    - example usage: LONG_PRESS <point>[[101, 872]]</point>
       
Custom Action 2: OPEN_APP
    - purpose: Open the specified application.
    - format: OPEN_APP [app_name]
    - example usage: OPEN_APP [Google Chrome]

Custom Action 3: PRESS_BACK
    - purpose: Press a back button to navigate to the previous screen.
    - format: PRESS_BACK
    - example usage: PRESS_BACK

Custom Action 4: PRESS_HOME
    - purpose: Press a home button to navigate to the home page.
    - format: PRESS_HOME
    - example usage: PRESS_HOME

Custom Action 5: PRESS_RECENT
    - purpose: Press the recent button to view or switch between recently used applications.
    - format: PRESS_RECENT
    - example usage: PRESS_RECENT

Custom Action 6: ENTER
    - purpose: Press the enter button.
    - format: ENTER
    - example usage: ENTER

Custom Action 7: WAIT
    - purpose: Wait for the screen to load.
    - format: WAIT
    - example usage: WAIT

Custom Action 8: COMPLETE
    - purpose: Indicate the task is finished.
    - format: COMPLETE
    - example usage: COMPLETE

    
In most cases, task instructions are high-level and abstract. Carefully read the instruction and action history, then perform reasoning to determine the most appropriate next action. Ensure you strictly generate two sections: Thoughts and Actions.
Thoughts: Clearly outline your reasoning process for current step.
Actions: Specify the actual actions you will take based on your reasoning. You should follow action format above when generating. 

Your current task instruction, action history, and associated screenshot are as follows:
Screenshot: 
<image>
Task instruction: {goal}
History: null
"""

ACTION_PROMPT_QWEN3 = """# Tools

You may call one or more functions to assist with the user query.

You are provided with function signatures within <tools></tools> XML tags:
<tools>
{"type": "function", "function": {"name": "mobile_use", "description": "Use a touchscreen to interact with a mobile device, and take screenshots.\\n* This is an interface to a mobile device with touchscreen. You can perform actions like clicking, typing, swiping, etc.\\n* Some applications may take time to start or process actions, so you may need to wait and take successive screenshots to see the results of your actions.\\n* The screen's resolution is 999x999.\\n* Make sure to click any buttons, links, icons, etc with the cursor tip in the center of the element. Don't click boxes on their edges unless asked.", "parameters": {"properties": {"action": {"description": "The action to perform. The available actions are:\\n* `click`: Click the point on the screen with coordinate (x, y).\\n* `long_press`: Press the point on the screen with coordinate (x, y) for specified seconds.\\n* `swipe`: Swipe from the starting point with coordinate (x, y) to the end point with coordinates2 (x2, y2).\\n* `type`: Input the specified text into the activated input box.\\n* `answer`: Output the answer.\\n* `system_button`: Press the system button.\\n* `wait`: Wait specified seconds for the change to happen.\\n* `terminate`: Terminate the current task and report its completion status.", "enum": ["click", "long_press", "swipe", "type", "answer", "system_button", "wait", "terminate"], "type": "string"}, "coordinate": {"description": "(x, y): The x (pixels from the left edge) and y (pixels from the top edge) coordinates to move the mouse to. Required only by `action=click`, `action=long_press`, and `action=swipe`.", "type": "array"}, "coordinate2": {"description": "(x, y): The x (pixels from the left edge) and y (pixels from the top edge) coordinates to move the mouse to. Required only by `action=swipe`.", "type": "array"}, "text": {"description": "Required only by `action=type` and `action=answer`.", "type": "string"}, "time": {"description": "The seconds to wait. Required only by `action=long_press` and `action=wait`.", "type": "number"}, "button": {"description": "Back means returning to the previous interface, Home means returning to the desktop, Menu means opening the application background menu, and Enter means pressing the enter. Required only by `action=system_button`", "enum": ["Back", "Home", "Menu", "Enter"], "type": "string"}, "status": {"description": "The status of the task. Required only by `action=terminate`.", "type": "string", "enum": ["success", "failure"]}}, "required": ["action"], "type": "object"}}}
</tools>

For each function call, return a json object with function name and arguments within <tool_call></tool_call> XML tags:
<tool_call>
{"name": <function-name>, "arguments": <args-json-object>}
</tool_call>

# Response format

Response format for every step:
1) Thought: one concise sentence explaining the next move (no multi-step reasoning).
2) Action: a short imperative describing what to do in the UI.
3) A single <tool_call>...</tool_call> block containing only the JSON: {"name": <function-name>, "arguments": <args-json-object>}.

Rules:
- Output exactly in the order: Thought, Action, <tool_call>.
- Be brief: one sentence for Thought, one for Action.
- Do not output anything else outside those three parts.
- If finishing, use action=terminate in the tool call.
Quest: {goal}"""

