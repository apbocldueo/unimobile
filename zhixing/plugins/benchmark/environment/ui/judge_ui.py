import time
import logging
from typing import Dict, Any, List

from zhixing.core.benchmark.interface import BaseEnvironmentInitializerOperation
from zhixing.core.benchmark.protocol import EnvironmentInitializerPluginType
from zhixing.core.factory import PluginRegistry

logger = logging.getLogger(__name__)

@PluginRegistry.register(namespace="benchmark.environment.ui", name="ui_judge_ui")
class UIJudgeUIGenerator(BaseEnvironmentInitializerOperation):
    """_summary_

    Args:
        BaseEnvOp (_type_): _description_

    Returns:
        _type_: _description_
    """

    op_type = EnvironmentInitializerPluginType.UI_JUDEG_UI

    def execute(self
                , meta: Dict[str, Any]
                , params: Dict[str, Any]
                ) -> bool:
        """_summary_

        Args:
            meta (Dict[str, Any]): _description_
            params (Dict[str, Any]): 
            {
                "steps": [
                    {
                        "action": "judge",
                        "params": [
                            {
                                "content": ['content_1', 'content_2', 'content_3', ...], 
                                "fields": ['content_desc', 'text', 'label', ...]
                            },
                            {
                                "model": "model_name",
                                "prompt": "model_prompt"
                            }
                            要求 content_desc == content_1 and text == content_2 and label == content_3 都满足
                            为啥是 list, 因为可以要有多个
                        ]
                    },
                    {
                        "action": "start_app",
                        "params": {
                            "app_name": "app_name"
                        }
                    },
                    {
                        "action": "tap",
                        "params": {
                            "x": x,
                            "y": y
                        }
                    },
                    {
                        "action": "type",
                        "params": {
                            "text": "text"
                        }
                    },
                    {
                        "action": "swipe",
                        "params": {
                            "direction": "'up', 'down', 'left', 'right'",
                            "scale": float
                        }
                    },
                    {
                        "action": "enter",
                        "params": {}
                    },
                    {
                        "action": "back",
                        "params": {}
                    },
                    {
                        "action": "home",
                        "params": {}
                    },
                    {
                        "action": "done",
                        "params": {}
                    },
                    {
                        "action": "clear",
                        "params": {
                            "num": int
                        }
                    }
                ]
            }

        Returns:
            bool: _description_
        """
        device = meta.get("device")
        if not device:
            logger.error("[JudgeUI] meta 中缺少 device 实例！")
            return False
        steps = params.get("steps")
        if not steps or not isinstance(steps, list):
            logger.error("[JudgeUI] steps 中缺少 steps 实例！")
            return False
        
        # try:
        for step in steps:
            params = step.get("params")
            if step.get("action").lower() == "judge":
                time.sleep(5)
                ui_elements = device.extract_android_ui_elements()
                screenshot = "benchmarks\\temp\\judge.png"
                device.device.screenshot(screenshot)
                temp = True # 默认是做到了（这个函数的逻辑是：判断是否已经做到这件事，做到了就取消）
                for param in params: # param 也是 list 类型
                    # 1. xml + 规则的方式
                    if all(k in param for k in ["content", "fields"]):
                        # print("content", "fields")
                        if not self._judge_content_in_elements_xml(param, ui_elements):
                            temp = False
                            break
                    elif all(k in param for k in ["model", "prompt"]):
                        prompt = param.get("prompt")
                        if not self._judge_content_in_elements_llm(device, prompt):
                            temp = False
                            break
                    else:
                        temp = False
                        break
                print(temp)
                if temp: # 说明后续不需要操作
                    break # judge 后续的操作都不需要了
            elif step.get("action").lower() == "start_app":
                device.device.start_app(f"{params.get('app_name')}")
            elif step.get("action").lower() == "tap":
                device.device.tap(f"{params.get('x')}", f"{params.get('y')}")
            elif step.get("action").lower() == "type":
                device.device.input_text(f"{params.get('text')}")
            elif step.get("action").lower() == "swipe":
                device.device.swipe(f"{params.get('direction')}", f"{params.get('scale')}")
            elif step.get("action").lower() == "enter":
                time.sleep(3)
                device.device.enter()
            elif step.get("action").lower() == "back":
                device.device.go_back()
            elif step.get("action").lower() == "home":
                device.device.go_home()
            elif step.get("action").lower() == "clear":
                device.device.clear_text(f"{params.get('num', 15)}")
            else:
                logger.error(f"[JudgeUI] 没有操作: {step.get('action')}")
                return False
            time.sleep(2)
        # except Exception as e:
        #     logger.error(f"[JudgeUI] 执行异常：{str(e)}", exc_info=True)
        #     return False
        return True
    

    def _judge_content_in_elements_xml(self, variable:dict, elements: List[dict]) -> bool:
        for element in elements:
            if self._check_match(variable, element): # 如果有一个 element 元素满足
                return True
        return False

    def _judge_content_in_elements_llm(self, device, prompt: str) -> bool:
        
        pass

    @staticmethod
    def _check_match(d: dict, element: dict) -> bool:
        """
        验证：fields[i] == content[i] 一一对应且全部满足（忽略大小写+首尾空格）
        :param d: 包含content和fields的字典，如 {"content":[c1,c2], "fields":[f1,f2]}
        :param element: 元素字典，如 {"content_desc":"c1", "text":"c2"}
        :return: 所有字段一一匹配返回True，否则False
        """
        return all(element.get(f, "").lower().strip() == c.lower().strip() for f, c in zip(d["fields"], d["content"]))
    