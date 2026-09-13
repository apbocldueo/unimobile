from typing import Any, Dict

from zhixing.core.benchmark.interface import BaseParamInitializerGenerator
from zhixing.core.benchmark.protocol import ParamInitializerPluginType
from zhixing.core.factory import PluginRegistry


@PluginRegistry.register(namespace="benchmark.task", name="map_value")
class MapValueTaskGenerator(BaseParamInitializerGenerator):
    """Map an input value to an output using a fixed lookup table.

    Use after another initializer (e.g. ``random_choice``) so ``value`` can be
    ``"${on_or_off}"`` and is rendered before ``generate`` runs.

    Example::

        "on_or_off": {
            "name": "random_choice",
            "params": {"options": ["off", "on"]}
        },
        "bluetooth_on_expected": {
            "name": "map_value",
            "params": {
                "value": "${on_or_off}",
                "map": {"off": "0", "on": "1"}
            }
        }
    """

    gen_type = ParamInitializerPluginType.MAP_VALUE

    def generate(self, params: Dict[str, Any]) -> Any:
        value = str(params.get("value", "")).strip()
        mapping = params.get("map")
        if not isinstance(mapping, dict) or not mapping:
            raise ValueError("map_value requires a non-empty 'map' object.")
        if value not in mapping:
            raise ValueError(f"map_value: no entry for {value!r}; keys={list(mapping.keys())!r}")
        return mapping[value]
