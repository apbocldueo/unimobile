import re
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)

class ParamHandler:
    """
    Parameter Handler.
    Responsibility: Recursively replaces ${xxx} placeholders in configuration parameters 
    with actual values from the execution context.
    """

    PLACEHOLDER_PATTERN = re.compile(r"\$\{([^{}]+)\}")

    @staticmethod
    def render_placeholders(data: Any, context_params: Dict[str, Any]) -> Any:
        """Recursively renders parameters by replacing ${xxx} placeholders with actual values.

        Args:
            data (Any): The original data (string, dict, or list) containing placeholders.
            context_params (Dict[str, Any]): The context dictionary containing actual values used for replacement.

        Returns:
            Any: The newly rendered data with all matched placeholders replaced.
        """
        if isinstance(data, str):
            def normal_replace(match):
                key = match.group(1)
                if key not in context_params:
                    logger.warning(f"Attempted to render placeholder ${{{key}}}, but it does not exist in the context! Keeping original string.")
                    return f"${{{key}}}"
                return str(context_params.get(key))
            
            return ParamHandler.PLACEHOLDER_PATTERN.sub(normal_replace, data)
        
        elif isinstance(data, dict):
            return {k: ParamHandler.render_placeholders(v, context_params) for k, v in data.items()}
        
        elif isinstance(data, list):
            return [ParamHandler.render_placeholders(item, context_params) for item in data]
        
        return data

    @staticmethod
    def get_and_render(config: Dict[str, Any], key: str, context: Dict[str, Any], expected_type: type = str) -> Any:
        """Extracts a parameter from config, renders placeholders, and performs type conversion.

        Args:
            config (Dict[str, Any]): The configuration dictionary containing the target parameter.
            key (str): The specific parameter key to extract.
            context (Dict[str, Any]): The execution context containing task parameters.
            expected_type (type): The expected data type of the returned value (default is str).

        Returns:
            Any: The rendered and type-converted parameter value.
        """
        if key not in config:
            raise KeyError(f"Missing required parameter in evaluation strategy: '{key}'")
        
        raw_val = config[key]
        
        # Extract the variable pool from the task context
        task_params = context.get("task_params", {})
        
        # Render placeholders
        rendered_val = ParamHandler.render_placeholders(raw_val, task_params)

        # Dynamic type conversion
        if expected_type is not str and isinstance(rendered_val, str):
            try:
                rendered_val = expected_type(rendered_val)
            except ValueError:
                raise TypeError(f"Parameter '{key}' with rendered value '{rendered_val}' cannot be converted to {expected_type.__name__}")
        elif not isinstance(rendered_val, expected_type):
            raise TypeError(f"Parameter '{key}' expected type {expected_type.__name__}, got {type(rendered_val).__name__}")
            
        return rendered_val