def get_env(env):
    if env == 'android':
        from .android import Env
        return Env
    else:
        raise NotImplementedError(f"Environment {env} is not supported.")