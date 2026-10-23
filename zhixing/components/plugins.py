"""Distribution-neutral declarations for external ZhiXing components."""

from __future__ import annotations

from dataclasses import dataclass

from .authoring import ComponentSpec, validate_component_spec
from .errors import ComponentDefinitionError


COMPONENT_BUNDLE_SCHEMA_VERSION = "1"


@dataclass(frozen=True)
class ComponentBundle:
    """Declare one provider's immutable collection of formal components.

    Args:
        components (tuple[ComponentSpec, ...]): Formal component specifications
            exported by one provider.
        schema_version (str): Bundle protocol version. Defaults to ``"1"``.

    Raises:
        ComponentDefinitionError: If the schema version, component collection,
            specification, or component identity is invalid.

    Returns:
        ComponentBundle: Validated immutable provider declaration.
    """

    components: tuple[ComponentSpec, ...]
    schema_version: str = COMPONENT_BUNDLE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        """Validate the bundle without importing or instantiating components.

        Raises:
            ComponentDefinitionError: If any declaration violates the public
                authoring contract.

        Returns:
            None: Validation succeeds without mutating the bundle.
        """
        if self.schema_version != COMPONENT_BUNDLE_SCHEMA_VERSION:
            raise ComponentDefinitionError(
                "component.bundle_schema_unsupported",
                "The component bundle schema version is not supported.",
                details={"schema_version": str(self.schema_version)},
            )
        if not isinstance(self.components, tuple) or not self.components:
            raise ComponentDefinitionError(
                "component.bundle_empty",
                "A component bundle must contain at least one ComponentSpec.",
            )

        identities: set[str] = set()
        for specification in self.components:
            if not isinstance(specification, ComponentSpec):
                raise ComponentDefinitionError(
                    "component.bundle_member_invalid",
                    "Every component bundle member must be a ComponentSpec.",
                    details={"member_type": type(specification).__name__},
                )
            validate_component_spec(specification)
            if specification.identifier in identities:
                raise ComponentDefinitionError(
                    "component.bundle_identity_duplicate",
                    "A component bundle contains a duplicate component identity.",
                    details={"component": specification.identifier},
                )
            identities.add(specification.identifier)

    def safe_metadata(self) -> dict[str, object]:
        """Return declaration metadata without factories or live objects.

        Returns:
            dict[str, object]: Safe, JSON-compatible bundle metadata.
        """
        return {
            "schema_version": self.schema_version,
            "components": [item.safe_metadata() for item in self.components],
        }


__all__ = ["COMPONENT_BUNDLE_SCHEMA_VERSION", "ComponentBundle"]
