import random
import string
import datetime
from typing import Dict, Any
from unimobile.utils.app_resolver import AppResolver
from unimobile.devices.base import BaseDevice

GENERATOR_REGISTRY = {}

def register_generator(name):
    def decorator(func):
        GENERATOR_REGISTRY[name] = func
        return func
    return decorator

# --- generation function---
@register_generator("random_choice")
def gen_random_choice(config: Dict, **kwargs):
    """Random select from the list

    Returns:
        _type_: _description_
    """

    return random.choice(config["options"])

@register_generator("date_relative")
def gen_date_relative(config: Dict, **kwargs):
    """Generate relative datas

    Returns:
        _type_: _description_
    """

    today = datetime.date.today()
    offset = config.get("offset_days", 0)
    target_date = today + datetime.timedelta(days=offset)
    fmt = config.get("format", "%Y-%m-%d")
    return target_date.strftime(fmt)

@register_generator("random_number")
def gen_random_number(config: Dict, **kwargs):
    """Generate random numbers

    Returns:
        _type_: _description_
    """
    
    min_val = config.get("min", 0)
    max_val = config.get("max", 100)
    return random.randint(min_val, max_val)


@register_generator("random_string")
def gen_random_string(config: Dict, **kwargs):
    """Generate random strings

    Args:
        length (int): The length of the random part
        prefix (str): perfix
        suffix (str): suffix
        charset (str): 'digits' | 'letters' | 'alphanumeric'
        extensions (List[str] | str): The list or str of extension names

    Returns:
        str
    """
    length = config.get("length", 8)
    prefix = config.get("prefix", "")
    suffix_part = config.get("suffix", "")
    charset_type = config.get("charset", "alphanumeric")
    
    ext_config = config.get("extensions")
    final_ext = ""
    
    if ext_config:
        if isinstance(ext_config, list):
            final_ext = random.choice(ext_config)
        elif isinstance(ext_config, str):
            final_ext = ext_config
            
        if final_ext and not final_ext.startswith("."):
            final_ext = "." + final_ext

    if charset_type == "digits":
        chars = string.digits
    elif charset_type == "letters":
        chars = string.ascii_letters
    else:
        chars = string.ascii_letters + string.digits

    random_part = ''.join(random.choices(chars, k=length))

    # eg: "Rec_" + "aX9d" + "_backup" + ".mp3"
    return f"{prefix}{random_part}{suffix_part}{final_ext}"

@register_generator("random_int")
def gen_random_int(config: Dict, **kwargs):
    """Generate random integers

    Args:
        min (int): min
        max (int): max
        step (int): step
    
    Return:
        int
    """
    min_val = int(config.get("min", 0))
    max_val = int(config.get("max", 100))
    step = int(config.get("step", 1))

    
    try:
        return random.randrange(min_val, max_val + 1, step)
    except ValueError:
        return min_val


@register_generator("template_list")
def gen_template_list(config: Dict, **kwargs):
    """The string for generating and template lists
    eg: "Lunch $12, Taxi $30"

    Args:
      count (int), generate number
      template (str), template
      separator (str), connector
      variables (Dict), generate rule

    Returns:
        _type_: _description_
    """
    count = int(config.get("count", 1))
    template = config.get("template", "{item}")
    separator = config.get("separator", ", ")
    variables_config = config.get("variables", {})

    result_list = []

    for _ in range(count):
        item_params = {}
        for var_name, var_cfg in variables_config.items():
            gen_type = var_cfg.get("type")

            if gen_type in GENERATOR_REGISTRY:
                generator_func = GENERATOR_REGISTRY[gen_type]
                item_params[var_name] = generator_func(var_cfg)
            else:
                item_params[var_name] = f"UNKNOWN({gen_type})"
        
        try:
            item_str = template.format(**item_params)
            result_list.append(item_str)
        except KeyError as e:
            result_list.append(f"ERROR_MISSING_KEY_{e}")
    
    return separator.join(result_list)

@register_generator("app_lookup")
def gen_app_lookup(config: Dict, device: BaseDevice = None):
    alias = config.get("alias")
    if not device:
        return alias
    
    return AppResolver.resolve(alias, device.platform, device.language)

def generate_params(params_config: Dict[str, Any], device: BaseDevice = None) -> Dict[str, str]:
    concrete_params = {}
    
    for param_name, config in params_config.items():
        gen_type = config.get("type")
        if gen_type in GENERATOR_REGISTRY:
            func = GENERATOR_REGISTRY[gen_type]
    
            try:
                value = func(config, device=device)
            except TypeError:
                value = func(config)
                
            concrete_params[param_name] = str(value)
        else:
            concrete_params[param_name] = "UNKNOWN"
            
    return concrete_params



