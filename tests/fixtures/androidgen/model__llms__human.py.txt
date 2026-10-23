import matplotlib.pyplot as plt
from PIL import Image

class Human:
    def __init__(
            self,
            **kwargs,
    ) -> None:
        pass

    def generate(self, prompt, system_prompt=None, history=[], **kwargs):
        if type(prompt) == str:
            operation = input(f'Current State: {prompt}\n\nPlease input your operation: ')
        else:
            if "image_url" in prompt:
                image = Image.open(prompt["image_url"])
                plt.imshow(image)
                plt.show()
            operation = input(f'Current State: {prompt["text"]}\n\nPlease input your operation: ')
        return f'```\n{operation}\n```'
    