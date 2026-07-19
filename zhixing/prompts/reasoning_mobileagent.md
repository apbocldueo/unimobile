### Background ###
This image is a phone screenshot. Its width is {width} pixels and its height is {height} pixels. The user's instruction is: {task}.

### Screenshot information ###
{perception_prompt}

### Hint ###
If you want to tap an icon of an app, use the action "Open app". If you want to exit an app, use the action "Home".

### History operations / Memory ###
Before reaching this page, some operations may have been completed. Refer to them to decide the next operation.
{history_text}

### Overall Plan ###
{plan}

### Available applications ###
If the current page is desktop, Open app can use an app name from the environment:
{available_apps}

### Response requirements ###
Now you need to combine all of the above to perform just one action on the current page. You must choose one of the six actions below:
Open app (app name): If the current page is desktop, you can use this action to open the app named "app name" on the desktop.
Tap (x, y): Tap the position (x, y) in current page.
Swipe (x1, y1), (x2, y2): Swipe from position (x1, y1) to position (x2, y2).
Type (text): Type the "text" in the input box only when the keyboard has been activated. If the keyboard has not been activated, first tap the input box.
Home: Return to home page.
Stop: If all requirements of the user's instruction have been completed and no further operation is required, terminate the operation process.

### Output format ###
Your output consists of the following three parts:
### Thought ###
Think about the requirements that have been completed in previous operations and the requirements that need to be completed in the next one operation.
### Action ###
You can only choose one from the six actions above. Make sure that the coordinates or text are in the parentheses.
### Operation ###
Please generate a brief natural language description for the operation in Action based on your Thought.
