from typing import List
from zhixing.devices.base import DeviceInfo, BaseDevice, ConnectionType
from zhixing.devices.android import AndroidDevice

class DeviceManager:
    """
    Equipment Management Center
    """
    
    @staticmethod
    def list_all_devices() -> List[DeviceInfo]:
        """Scan all supported device platforms.

        Args:
            None.

        Raises:
            None: Platform discovery failures are reported and skipped.

        Returns:
            List[DeviceInfo]: Android and HarmonyOS devices in discovery order.
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
            from zhixing.devices.harmony import HarmonyDevice

            harmony_devs = HarmonyDevice.list_devices()
            all_devices.extend(harmony_devs)
        except Exception as e:
            print(f"DeviceManager Failed to scan Harmony (HDC may not be installed): {e}")
            
        return all_devices

    @staticmethod
    def get_android_device(serial: str | None = None, language: str = "cn") -> AndroidDevice:
        """Create an Android-only device session without scanning HarmonyOS.

        Args:
            serial (str | None): Explicit target serial. When absent, exactly one
                ready Android device must exist.
            language (str): Device language passed to AndroidDevice.

        Raises:
            RuntimeError: No ready device or multiple ambiguous devices exist.
            ValueError: The explicit serial is missing, offline, or unauthorized.

        Returns:
            AndroidDevice: Serial-bound ready Android device.
        """
        states = AndroidDevice.list_device_states()
        if serial is not None:
            target = next((device for device in states if device.device_id == serial), None)
            if target is None:
                raise ValueError(f"Android device {serial!r} was not reported by adb")
            if target.status != "device":
                raise ValueError(
                    f"Android device {serial!r} is not ready (status={target.status!r})"
                )
            return AndroidDevice(serial=serial, language=language)

        ready = [device for device in states if device.status == "device"]
        if not ready:
            raise RuntimeError("No Android device in the 'device' state was found")
        if len(ready) > 1:
            candidates = ", ".join(device.device_id for device in ready)
            raise RuntimeError(
                f"Multiple Android devices are ready; pass an explicit serial ({candidates})"
            )
        return AndroidDevice(serial=ready[0].device_id, language=language)

    @staticmethod
    def get_device_instance(device_id: str = None, platform: str = None) -> BaseDevice:
        """Create a legacy device instance from an identifier or platform hint.

        Args:
            device_id (str): Optional concrete device identifier.
            platform (str): Optional fallback platform when discovery misses.

        Raises:
            RuntimeError: No devices are available for implicit selection.
            ValueError: The identifier or platform cannot be resolved.

        Returns:
            BaseDevice: Android or HarmonyOS device instance.
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
                target_info = DeviceInfo(device_id, platform, "unknown", ConnectionType.USB)
            elif not target_info and not platform:
                raise ValueError(f"{device_id} cannot be found")

        if target_info.platform == "harmony":
            from zhixing.devices.harmony import HarmonyDevice

            print(f"Initialize the Harmony device: {target_info.device_id}")
            return HarmonyDevice(device_id=target_info.device_id)
        elif target_info.platform == "android":
            print(f"Initialize the Android device: {target_info.device_id}")
            return AndroidDevice(serial=target_info.device_id)
        else:
            raise ValueError(f"Unsupported platforms: {target_info.platform}")
