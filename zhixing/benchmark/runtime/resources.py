"""Runtime-only logical resource providers for Benchmark Packages."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from zhixing.benchmark.models import BenchmarkPlan, ResourceRef
from zhixing.benchmark.resources import file_sha256, resolve_package_path


class BenchmarkResourceProvider(Protocol):
    """Resolve declared logical resources without changing Plan identity."""

    def resolve(self, uri: str) -> Path:
        """Resolve one logical URI to a verified local file."""
        ...

    def bind(self, value: Any) -> Any:
        """Recursively replace logical URIs in runtime-only plugin values."""
        ...


class EmptyBenchmarkResourceProvider:
    """Provider for standalone tasks that declare no Package resources."""

    def resolve(self, uri: str) -> Path:
        """Reject logical resources because no Package is bound.

        Args:
            uri (str): Logical URI.

        Raises:
            ValueError: Always.

        Returns:
            Path: Never returned.
        """
        raise ValueError(f"no Benchmark Package resource provider for {uri!r}")

    def bind(self, value: Any) -> Any:
        """Reject encountered logical URIs while preserving ordinary values.

        Args:
            value (Any): JSON-compatible runtime value.

        Raises:
            ValueError: Value contains an asset or ground-truth URI.

        Returns:
            Any: Recursively copied ordinary value.
        """
        if isinstance(value, str) and value.startswith(("asset://", "groundtruth://")):
            return str(self.resolve(value))
        if isinstance(value, dict):
            return {key: self.bind(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self.bind(item) for item in value]
        if isinstance(value, tuple):
            return tuple(self.bind(item) for item in value)
        return value


class PackageBenchmarkResourceProvider:
    """Verified resolver bound explicitly to one Package root and Plan."""

    def __init__(self, root: str | Path, plan: BenchmarkPlan) -> None:
        """Create a provider and index the Plan resource closure.

        Args:
            root (str | Path): Explicit Benchmark Package root.
            plan (BenchmarkPlan): Compiled Plan declaring usable resources.

        Raises:
            ValueError: A resource path, digest, or kind is invalid.

        Returns:
            None.
        """
        self._root = Path(root).resolve()
        self._resources = {item.id: item for item in plan.resources}

    def resolve(self, uri: str) -> Path:
        """Resolve and verify one logical resource.

        Args:
            uri (str): ``asset://`` or ``groundtruth://`` URI.

        Raises:
            ValueError: URI is undeclared, mismatched, missing, or modified.

        Returns:
            Path: Verified path confined to the Package root.
        """
        if "://" not in uri:
            raise ValueError("Benchmark resource must be a logical URI")
        scheme, logical_id = uri.split("://", 1)
        resource = self._resources.get(logical_id)
        if resource is None:
            raise ValueError(f"undeclared Benchmark resource {logical_id!r}")
        expected = "asset" if resource.kind.value == "asset" else "groundtruth"
        if scheme != expected:
            raise ValueError("Benchmark resource URI kind mismatch")
        path = resolve_package_path(self._root, resource.path)
        self._verify(path, resource)
        return path

    @staticmethod
    def _verify(path: Path, resource: ResourceRef) -> None:
        """Verify one resource before it crosses the side-effect boundary.

        Args:
            path (Path): Confined resource path.
            resource (ResourceRef): Declared metadata.

        Raises:
            ValueError: File is missing or content does not match.

        Returns:
            None.
        """
        if not path.is_file():
            raise ValueError("Benchmark resource does not exist")
        if path.stat().st_size != resource.size:
            raise ValueError("Benchmark resource size changed")
        if file_sha256(path) != resource.sha256:
            raise ValueError("Benchmark resource digest changed")

    def bind(self, value: Any) -> Any:
        """Resolve logical URIs recursively for a runtime plugin call.

        Args:
            value (Any): JSON-compatible semantic value.

        Raises:
            ValueError: A logical resource cannot be verified.

        Returns:
            Any: Runtime-only value containing confined local paths.
        """
        if isinstance(value, str) and value.startswith(("asset://", "groundtruth://")):
            return str(self.resolve(value))
        if isinstance(value, dict):
            return {key: self.bind(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self.bind(item) for item in value]
        if isinstance(value, tuple):
            return tuple(self.bind(item) for item in value)
        return value

