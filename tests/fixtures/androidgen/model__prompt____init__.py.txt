def prompt_provider(env, example=None):
    if env == 'android':
        from .android import system_prompt, default_example
        if example is not None:
            return system_prompt % example
        else:
            return system_prompt % default_example
    else:
        raise NotImplementedError(f"Environment {env} is not supported.")