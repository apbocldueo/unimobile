Actions History
{history_text}

Informations
{perception_prompt}

Your Task
{task}

Generate next actions to do this task.

The image is the current smartphone screenshot. Output exactly in this format:
actions:
tap, <point> x y</point>
swipe, from <point> x1 y1</point> to <point> x2 y2</point>
input, text
enter
answer, task complete

Use 0-1000 relative coordinates inside <point> tags. Generate one next action unless the answer is task complete.
