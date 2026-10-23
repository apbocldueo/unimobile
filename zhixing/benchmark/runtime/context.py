"""Benchmark runtime context and device-preflight ownership boundary."""

from __future__ import annotations

from typing import Any, Mapping

from ..models import AppRequirement


def preflight_device(
    device: Any,
    *,
    platform: str,
    locale: str,
    orientation: str,
    apps: tuple[AppRequirement, ...],
) -> tuple[bool, dict[str, Any]]:
    """Check only observable device and App constraints.

    Args:
        device (Any): Explicit device session.
        platform (str): Required platform.
        locale (str): Required locale.
        orientation (str): Required orientation or any.
        apps (tuple[AppRequirement, ...]): Required logical Apps.

    Raises:
        None.

    Returns:
        tuple[bool, dict[str, Any]]: Validity and safe provenance.
    """
    actual_platform = str(getattr(device, "platform", "") or "")
    actual_locale = str(getattr(device, "locale", "") or "")
    actual_orientation = str(getattr(device, "orientation", "") or "")
    shell = getattr(device, "shell", None)
    if not actual_locale and callable(shell):
        for command in (
            "getprop persist.sys.locale",
            "getprop ro.product.locale",
        ):
            try:
                response = shell(command, error_raise=False)
                actual_locale = str(
                    getattr(response, "output", "") or ""
                ).strip()
            except Exception:
                actual_locale = ""
            if actual_locale:
                break
    if not actual_orientation:
        size = getattr(device, "display_size", None)
        if callable(size):
            try:
                width, height = size()
                actual_orientation = (
                    "portrait" if int(height) >= int(width) else "landscape"
                )
            except Exception:
                actual_orientation = ""
    app_names = getattr(device, "app_package_names", None)
    missing_apps = []
    app_verifiable = isinstance(app_names, Mapping)
    if app_verifiable:
        for item in apps:
            package_id = item.package_id or app_names.get(item.id.lower())
            if not package_id:
                missing_apps.append(item.id)
                continue
            if callable(shell):
                try:
                    response = shell(
                        f"pm path {package_id}",
                        error_raise=False,
                    )
                    output = str(getattr(response, "output", "") or "")
                    exit_code = int(getattr(response, "exit_code", 1))
                    if exit_code != 0 or not output.strip():
                        missing_apps.append(item.id)
                except Exception:
                    missing_apps.append(item.id)
    checks = {
        "platform": bool(actual_platform) and actual_platform == platform,
        "locale": bool(actual_locale) and actual_locale == locale,
        "orientation": (
            orientation == "any"
            or (bool(actual_orientation) and actual_orientation == orientation)
        ),
        "apps": app_verifiable and not missing_apps,
    }
    return all(checks.values()), {
        "platform": actual_platform or "unverified",
        "locale": actual_locale or "unverified",
        "orientation": actual_orientation or "unverified",
        "apps_verifiable": app_verifiable,
        "missing_apps": missing_apps,
        "checks": checks,
    }


__all__ = ["preflight_device"]
