"""Unmodified selected EcoAgent prompt constants; see source-origin.json and LICENSE."""

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

