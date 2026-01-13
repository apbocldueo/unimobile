### User Instruction ###
{task}

### Overall Plan ###
{plan}

### History ###
{history_text}
Note that the operations recorded in the historical log are NOT guaranteed to be fully accurate and may contain incorrect actions. In particular, if you detect duplicate operations in the historical record, this is a strong indicator that the relevant operation is erroneous and needs to be adjusted and corrected accordingly.

The attached image is a screenshot showing the current state of the phone. Its width and height are {width} and {height} pixels, respectively.

CRITICAL OBSERVATION: If your last Tap action or clear action was meant to clear the input box, yet the text in the box still exists — this text is a **VIRTUAL PLACEHOLDER** that cannot be deleted. Do NOT try to clear it again. Switch immediately to the 'Type' action and input your text directly. Once text input is complete, you can perform the 'Enter' action.

### Screen Information ###
{perception_prompt}

#### Atomic Actions ####
Available actions in JSON format `{"name": "...", "arguments": {...}}`:
{actions_def}

### Output Format (Strict JSON) ###
You must output a single JSON object. Do not wrap it in markdown codes if possible.
The JSON object MUST contain the following keys:
1. "thought": Explain your reasoning process step by step.
2. "name": The name of the atomic action ("Tap", "Swipe", "Type", "Enter", "Back", "Home", "Clear").
3. "arguments": A dictionary of parameters for the action.