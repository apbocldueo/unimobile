"""Build a deterministic public-source tree from an explicit allowlist."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable, Mapping, Sequence


DEFAULT_MANIFEST = Path("release/public-manifest.json")
OUTPUT_MANIFEST = "RELEASE-MANIFEST.json"
FORBIDDEN_PARTS = {
    ".git",
    ".ua",
    ".codex-build",
    ".venv",
    "node_modules",
    "temp",
    "tmp",
}
FORBIDDEN_NAMES = {
    ".env",
    "secrets.yaml",
    "secrets.local.yaml",
    "device-profiles.json",
}
SECRET_PATTERNS = (
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(rb"\bghp_[A-Za-z0-9]{30,}\b"),
    re.compile(rb"\bgithub_pat_[A-Za-z0-9_]{30,}\b"),
    re.compile(rb"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(rb"\bAKIA[0-9A-Z]{16}\b"),
)
# Exact synthetic value used by reporting redaction tests, never a real key.
SYNTHETIC_SECRET = b"sk-live-acceptance-canary"


class PublicReleaseError(RuntimeError):
    """Raised when a public release cannot be constructed safely."""


@dataclass(frozen=True)
class ReleaseManifest:
    """Validated public-release selection contract."""

    include_paths: tuple[str, ...]
    exclude_paths: tuple[str, ...]
    exclude_names: frozenset[str]
    exclude_suffixes: tuple[str, ...]
    renames: Mapping[str, str]
    max_file_bytes: int
    retain_renamed_sources: bool = False


def _run_git(root: Path, arguments: Sequence[str]) -> bytes:
    """Run a bounded Git query in the selected repository.

    Args:
        root: Repository root.
        arguments: Git arguments excluding the executable name.

    Raises:
        PublicReleaseError: Git cannot complete the query.

    Returns:
        Raw command output.
    """
    try:
        return subprocess.check_output(
            ["git", *arguments], cwd=root, stderr=subprocess.STDOUT
        )
    except subprocess.CalledProcessError as error:
        detail = error.output.decode("utf-8", errors="replace").strip()
        raise PublicReleaseError(f"Git query failed: {detail}") from error


def _normalize_relative(value: str) -> str:
    """Validate and normalize one repository-relative POSIX path.

    Args:
        value: Manifest or Git path.

    Raises:
        PublicReleaseError: The path is empty, absolute, or escapes the root.

    Returns:
        Normalized POSIX path.
    """
    path = PurePosixPath(value)
    if (not value or value in {".", "./"} or path.is_absolute()
            or ".." in path.parts or "\\" in value or ":" in value
            or any(ord(char) < 32 for char in value)):
        raise PublicReleaseError(f"Unsafe repository path: {value!r}")
    return path.as_posix().removeprefix("./")


def load_manifest(path: Path) -> ReleaseManifest:
    """Load the strict public-release manifest.

    Args:
        path: Existing JSON manifest path.

    Raises:
        OSError: The manifest cannot be read.
        PublicReleaseError: The manifest schema is unsupported or malformed.

    Returns:
        Validated release manifest.
    """
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or type(raw.get("schemaVersion")) is not int or raw.get("schemaVersion") != 1:
        raise PublicReleaseError("public manifest schemaVersion must be 1")
    allowed = {
        "schemaVersion",
        "includePaths",
        "excludePaths",
        "excludeNames",
        "excludeSuffixes",
        "renames",
        "maxFileBytes",
        "retainRenamedSources",
    }
    unknown = sorted(set(raw) - allowed)
    if unknown:
        raise PublicReleaseError(f"Unknown manifest fields: {unknown}")

    def path_list(field: str) -> tuple[str, ...]:
        """Validate a required array of relative paths.

        Args:
            field: Manifest field containing the path array.
        Raises:
            PublicReleaseError: The field or a path is malformed.
        Returns:
            Normalized relative paths.
        """
        value = raw.get(field)
        if not isinstance(value, list) or not all(
            isinstance(item, str) for item in value
        ):
            raise PublicReleaseError(f"{field} must be an array of paths")
        return tuple(_normalize_relative(item) for item in value)

    renames = raw.get("renames", {})
    if not isinstance(renames, dict) or not all(
        isinstance(source, str) and isinstance(target, str)
        for source, target in renames.items()
    ):
        raise PublicReleaseError("renames must map source paths to target paths")
    max_file_bytes = raw.get("maxFileBytes")
    if type(max_file_bytes) is not int or max_file_bytes <= 0:
        raise PublicReleaseError("maxFileBytes must be a positive integer")
    for field in ("excludeNames", "excludeSuffixes"):
        value = raw.get(field)
        if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
            raise PublicReleaseError(f"{field} must be an array of nonempty strings")
    if type(raw.get("retainRenamedSources", False)) is not bool:
        raise PublicReleaseError("retainRenamedSources must be boolean")
    return ReleaseManifest(
        include_paths=path_list("includePaths"),
        exclude_paths=path_list("excludePaths"),
        exclude_names=frozenset(raw.get("excludeNames", ())),
        exclude_suffixes=tuple(raw.get("excludeSuffixes", ())),
        renames={
            _normalize_relative(source): _normalize_relative(target)
            for source, target in renames.items()
        },
        max_file_bytes=max_file_bytes,
        retain_renamed_sources=raw.get("retainRenamedSources", False),
    )


def _is_at_or_below(path: str, root: str) -> bool:
    """Return whether a path equals or is nested below a manifest root.

    Args:
        path: Candidate repository path.
        root: Exact file or directory-style include/exclude root.

    Raises:
        None.

    Returns:
        True when the candidate is inside the root.
    """
    return path == root or path.startswith(f"{root}/")


def select_paths(
    tracked_paths: Iterable[str], manifest: ReleaseManifest
) -> tuple[str, ...]:
    """Select tracked paths through the explicit include and deny lists.

    Args:
        tracked_paths: Git-tracked repository paths.
        manifest: Validated release selection contract.

    Raises:
        PublicReleaseError: An output rename collides with another file.

    Returns:
        Deterministically sorted selected source paths.
    """
    selected: list[str] = []
    targets: dict[str, str] = {}
    for raw_path in tracked_paths:
        path = _normalize_relative(raw_path)
        parts = PurePosixPath(path).parts
        if not any(_is_at_or_below(path, item) for item in manifest.include_paths):
            continue
        if any(_is_at_or_below(path, item) for item in manifest.exclude_paths):
            continue
        if any(part in manifest.exclude_names for part in parts):
            continue
        if path.endswith(manifest.exclude_suffixes):
            continue
        target = manifest.renames.get(path, path)
        previous = targets.get(target)
        if previous is not None and previous != path:
            raise PublicReleaseError(
                f"Release target collision: {previous!r} and {path!r} -> {target!r}"
            )
        targets[target] = path
        selected.append(path)
    return tuple(sorted(selected))


def _sha256(path: Path) -> str:
    """Compute one file's SHA-256 digest.

    Args:
        path: Existing regular file.

    Raises:
        OSError: The file cannot be read.

    Returns:
        Lowercase hexadecimal digest.
    """
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_source(
    root: Path, source_path: str, target_path: str, manifest: ReleaseManifest
) -> dict[str, object]:
    """Validate one selected source and return its release inventory row.

    Args:
        root: Repository root.
        source_path: Selected repository-relative source path.
        target_path: Release-relative output path after optional rename.
        manifest: Validated release selection contract.

    Raises:
        PublicReleaseError: The file is missing, unsafe, oversized, or secret-like.
        OSError: File metadata or content cannot be read.

    Returns:
        JSON-compatible inventory row.
    """
    source = root / source_path
    target = PurePosixPath(target_path)
    if any(parent.is_symlink() for parent in (source, *source.parents) if parent != root and root in parent.parents):
        raise PublicReleaseError(f"Symlinks are not allowed: {source_path}")
    if not source.is_file():
        raise PublicReleaseError(f"Tracked release file is missing: {source_path}")
    lowered_parts = {part.lower() for part in target.parts}
    if (lowered_parts & FORBIDDEN_PARTS or target.name.lower() in FORBIDDEN_NAMES
            or (target.name.lower().startswith(".env.") and target.name != ".env.example")
            or target.name.lower().endswith(".secrets.yaml")
            or target_path == OUTPUT_MANIFEST):
        raise PublicReleaseError(f"Forbidden release path: {target_path}")
    if target.name.lower().endswith((".pem", ".key", ".p12", ".pfx")):
        raise PublicReleaseError(f"Credential-shaped release file: {target_path}")
    size = source.stat().st_size
    if size > manifest.max_file_bytes:
        raise PublicReleaseError(
            f"Release file exceeds {manifest.max_file_bytes} bytes: {source_path}"
        )
    content = source.read_bytes()
    for pattern in SECRET_PATTERNS:
        if any(match.group() != SYNTHETIC_SECRET for match in pattern.finditer(content)):
            raise PublicReleaseError(f"Possible credential in {source_path}")
    return {
        "path": target_path,
        "source": source_path,
        "sizeBytes": size,
        "sha256": hashlib.sha256(content).hexdigest(),
    }


def build_release(
    root: Path,
    manifest_path: Path,
    destination: Path | None,
    *,
    allow_dirty: bool,
    include_untracked: bool = False,
) -> dict[str, object]:
    """Validate and optionally materialize the public release tree.

    Args:
        root: Git repository root.
        manifest_path: Public selection manifest.
        destination: Empty output directory, or None for validation only.
        allow_dirty: Permit a preview from a dirty worktree.
        include_untracked: Include allowlisted new files only in an explicit preview.

    Raises:
        PublicReleaseError: Repository, selection, safety, or destination checks fail.
        OSError: Selected files cannot be copied.

    Returns:
        JSON-compatible release inventory.
    """
    root = root.resolve()
    if include_untracked and not allow_dirty:
        raise PublicReleaseError("--include-untracked requires --allow-dirty (preview only)")
    manifest = load_manifest(manifest_path)
    dirty = bool(_run_git(root, ["status", "--porcelain=v1", "-z"]))
    if dirty and not allow_dirty:
        raise PublicReleaseError(
            "Working tree is dirty; commit the reviewed release state first"
        )
    tracked = tuple(
        item.decode("utf-8")
        for item in _run_git(root, ["ls-files", "-z"]).split(b"\0")
        if item
    )
    if include_untracked:
        tracked += tuple(item.decode("utf-8") for item in _run_git(
            root, ["ls-files", "--others", "--exclude-standard", "-z"]
        ).split(b"\0") if item)
    selected = select_paths(tracked, manifest)
    tracked_set = set(tracked)
    missing_required = sorted(
        item
        for item in manifest.include_paths
        if not any(_is_at_or_below(path, item) for path in tracked_set)
    )
    if missing_required:
        raise PublicReleaseError(
            f"Required release paths are not tracked: {missing_required}"
        )
    rows = [
        validate_source(root, path, manifest.renames.get(path, path), manifest)
        for path in selected
    ]
    if manifest.retain_renamed_sources:
        rows.extend(validate_source(root, path, path, manifest) for path in selected
                    if path in manifest.renames and manifest.renames[path] != path)
    targets = [str(row["path"]).casefold() for row in rows]
    if len(targets) != len(set(targets)):
        raise PublicReleaseError("Release output paths collide (including case-insensitive names)")
    if any(parent.as_posix().casefold() in targets for row in rows
           for parent in PurePosixPath(str(row["path"])).parents if parent.as_posix() != "."):
        raise PublicReleaseError("Release output file/directory collision")
    rows.sort(key=lambda row: str(row["path"]))
    commit = _run_git(root, ["rev-parse", "HEAD"]).decode("ascii").strip()
    inventory: dict[str, object] = {
        "schemaVersion": 1,
        "sourceCommit": commit,
        "dirtyPreview": dirty or include_untracked,
        "includesUntracked": include_untracked,
        "fileCount": len(rows),
        "files": rows,
    }
    if destination is None:
        return inventory
    destination = destination.resolve()
    if destination == root or root in destination.parents or destination in root.parents:
        raise PublicReleaseError("Destination must be outside the source repository")
    if destination.exists() and any(destination.iterdir()):
        raise PublicReleaseError("Destination must not exist or must be empty")
    destination.mkdir(parents=True, exist_ok=True)
    for row in rows:
        source = root / str(row["source"])
        target = destination / str(row["path"])
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        if _sha256(target) != row["sha256"]:
            raise PublicReleaseError(f"Source changed during export: {row['source']}")
    (destination / OUTPUT_MANIFEST).write_text(
        json.dumps(inventory, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return inventory


def _parser() -> argparse.ArgumentParser:
    """Build the command-line parser.

    Args:
        None.

    Raises:
        None.

    Returns:
        Configured argument parser.
    """
    parser = argparse.ArgumentParser(
        description="Validate or build the allowlisted ZhiXing public source tree."
    )
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--destination", type=Path)
    parser.add_argument("--include-untracked", action="store_true",
                        help="Preview only: also inspect allowlisted new files; requires --allow-dirty.")
    parser.add_argument(
        "--allow-dirty",
        action="store_true",
        help="Preview only: permit uncommitted tracked changes.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the public-release builder.

    Args:
        argv: Optional command arguments excluding the executable name.

    Raises:
        None. User-facing errors are converted to exit code 2.

    Returns:
        Process exit code.
    """
    args = _parser().parse_args(argv)
    root = args.root.resolve()
    manifest_path = (
        args.manifest
        if args.manifest.is_absolute()
        else root / args.manifest
    )
    try:
        inventory = build_release(
            root,
            manifest_path,
            args.destination,
            allow_dirty=args.allow_dirty,
            include_untracked=args.include_untracked,
        )
    except (OSError, ValueError, PublicReleaseError) as error:
        print(f"public release blocked: {error}")
        return 2
    mode = "built" if args.destination is not None else "validated"
    print(
        f"public release {mode}: {inventory['fileCount']} files from "
        f"{inventory['sourceCommit']}"
    )
    if inventory["dirtyPreview"]:
        print("warning: this was a dirty-worktree preview, not a release candidate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
