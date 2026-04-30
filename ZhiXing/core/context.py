from dataclasses import dataclass

@dataclass
class EnvironmentInfo:
    """
    Environmental context information object
    Store the static environment data that all components may need
    """
    platform: str        # "android" or "harmony"
    width: int
    height: int
    language: str = "cn"
    device_serial: str = ""
    