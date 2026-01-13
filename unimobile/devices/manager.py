from typing import List
from unimobile.devices.base import DeviceInfo, BaseDevice
from unimobile.devices.android import AndroidDevice
from unimobile.devices.harmony import HarmonyDevice

class DeviceManager:
    """
    Equipment Management Center
    """
    
    @staticmethod
    def list_all_devices() -> List[DeviceInfo]:
        """
        Scan all supported platforms (Android + HarmonyOS)
        """
        all_devices = []
        
        # 1. Android
        try:
            android_devs = AndroidDevice.list_devices()
            all_devices.extend(android_devs)
        except Exception as e:
            print(f"DeviceManager Failed to scan Android (ADB may not be installed): {e}")

        # 2. HarmonyOS
        try:
            harmony_devs = HarmonyDevice.list_devices()
            all_devices.extend(harmony_devs)
        except Exception as e:
            print(f"DeviceManager Failed to scan Harmony (HDC may not be installed): {e}")
            
        return all_devices

    @staticmethod
    def get_device_instance(device_id: str = None, platform: str = None) -> BaseDevice:
        """
        Return the corresponding Device instance based on ID or platform
        """
        if not device_id:
            devices = DeviceManager.list_all_devices()
            if not devices:
                raise RuntimeError("No devices were found! Please connect the device or start the simulator.")
            target_info = devices[0]
        else:
            devices = DeviceManager.list_all_devices()
            target_info = next((d for d in devices if d.device_id == device_id), None)
            
            if not target_info and platform:
                from unimobile.devices.base import ConnectionType
                target_info = DeviceInfo(device_id, platform, "unknown", ConnectionType.USB)
            elif not target_info and not platform:
                raise ValueError(f"{device_id} cannot be found")

        if target_info.platform == "harmony":
            print(f"Initialize the Harmony device: {target_info.device_id}")
            return HarmonyDevice(device_id=target_info.device_id)
        elif target_info.platform == "android":
            print(f"Initialize the Android device: {target_info.device_id}")
            return AndroidDevice(device_id=target_info.device_id)
        else:
            raise ValueError(f"Unsupported platforms: {target_info.platform}")