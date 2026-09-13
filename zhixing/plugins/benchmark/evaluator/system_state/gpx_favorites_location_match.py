"""GPX-based OsmAnd checks (favorites and tracks).

**Mode A — ``match_kind`` = ``favorite_location`` (default)**

Read a single GPX file (default ``favorites.gpx``) via ``adb shell cat``, inspect ``<wpt>`` elements.

Pass iff at least one waypoint matches **either**:

1. **Name substring** — task ``location`` appears as a substring of ``<name>`` (case-insensitive),
   or of ``<name>``/``<desc>``/``<cmt>`` when ``<name>`` is empty.
2. **(Optional) Coordinate proximity** — only if ``coordinates`` and/or a parseable ``lat, lon``
   in ``location`` is provided.

**Mode B — ``match_kind`` = ``track_directory_ordered_coords``**

List files under OsmAnd ``tracks/`` (see default paths below), ``cat`` each file, parse as GPX,
extract every ``<trkpt>`` in document order (all ``<trk>`` → ``<trkseg>`` → ``<trkpt>``).
Pass iff **some file** yields a point sequence that **subsequence-matches** ``ordered_waypoints``
as lat/lon targets (see ``coordinates``): scan points in order; each target must be hit within
``lat_lon_tolerance_deg`` before advancing to the next; extra points in between are allowed.

OsmAnd data roots (try tracks under each when resolving directory):

- ``/storage/emulated/0/Android/data/net.osmand/files``
- ``/data/media/0/Android/data/net.osmand/files``
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional, Tuple

from zhixing.core.benchmark.protocol import EvalResult
from zhixing.core.benchmark.base_system import BaseSystemAction
from zhixing.core.factory import PluginRegistry

_DEFAULT_GPX = "/storage/emulated/0/Android/data/net.osmand/files/favorites/favorites.gpx"
_OSMAND_FILES_CANDIDATES = (
    "/storage/emulated/0/Android/data/net.osmand/files",
    "/data/media/0/Android/data/net.osmand/files",
)
_DEFAULT_TRACKS_SUBDIR = "tracks"

_FLOAT_PAIR = re.compile(
    r"^\s*(-?\d+(?:\.\d+)?)\s*[,;\s]\s*(-?\d+(?:\.\d+)?)\s*$",
)


def _local_tag(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[-1]
    return tag


def _wpt_text(wpt: ET.Element, child: str) -> str:
    for el in wpt:
        if _local_tag(el.tag) == child and el.text:
            return el.text.strip()
    return ""


def _iter_waypoints(root: ET.Element) -> List[ET.Element]:
    out: List[ET.Element] = []
    for el in root.iter():
        if _local_tag(el.tag) == "wpt":
            out.append(el)
    return out


def _parse_lat_lon_attrs(el: ET.Element) -> Optional[Tuple[float, float]]:
    lat_s, lon_s = el.get("lat"), el.get("lon")
    if lat_s is None or lon_s is None:
        return None
    try:
        return float(lat_s), float(lon_s)
    except ValueError:
        return None


def _lookup_coordinates(
    coordinates: Any, location: str
) -> Optional[Tuple[float, float]]:
    if not isinstance(coordinates, dict) or not location:
        return None
    if location in coordinates:
        return _coerce_pair(coordinates[location])
    loc_l = location.strip().lower()
    for k, v in coordinates.items():
        if isinstance(k, str) and k.strip().lower() == loc_l:
            return _coerce_pair(v)
    return None


def _coerce_pair(v: Any) -> Optional[Tuple[float, float]]:
    if isinstance(v, (list, tuple)) and len(v) >= 2:
        try:
            return float(v[0]), float(v[1])
        except (TypeError, ValueError):
            return None
    if isinstance(v, dict):
        lat, lon = v.get("lat"), v.get("lon")
        if lat is not None and lon is not None:
            try:
                return float(lat), float(lon)
            except (TypeError, ValueError):
                return None
    return None


def _parse_lat_lon_from_location_string(location: str) -> Optional[Tuple[float, float]]:
    m = _FLOAT_PAIR.match(location.strip())
    if not m:
        return None
    try:
        return float(m.group(1)), float(m.group(2))
    except ValueError:
        return None


def _coord_close(
    a: Tuple[float, float], b: Tuple[float, float], tol: float
) -> bool:
    return abs(a[0] - b[0]) <= tol and abs(a[1] - b[1]) <= tol


def _extract_trkpt_sequence(root: ET.Element) -> List[Tuple[float, float]]:
    """GPX 1.1: ordered list of (lat, lon) from every ``<trkpt>`` under ``<trk>``, document order.

    Uses tree preorder (``Element.iter()``) so all ``trkpt`` under ``trk`` appear before any
    later top-level elements; OsmAnd track exports are typically ``<trk>``-only.
    """
    seq: List[Tuple[float, float]] = []
    for el in root.iter():
        if _local_tag(el.tag) != "trkpt":
            continue
        ll = _parse_lat_lon_attrs(el)
        if ll is not None:
            seq.append(ll)
    return seq


def _ordered_targets_from_params(
    ordered_waypoints: Any, coordinates: Any
) -> Tuple[Optional[List[Tuple[float, float]]], Optional[str]]:
    if not isinstance(ordered_waypoints, list) or not ordered_waypoints:
        return None, "Param 'ordered_waypoints' must be a non-empty JSON array of strings."
    if not isinstance(coordinates, dict):
        return None, "Param 'coordinates' must be a JSON object (waypoint label → {lat, lon})."
    targets: List[Tuple[float, float]] = []
    for label in ordered_waypoints:
        if not isinstance(label, str):
            return None, f"ordered_waypoints entries must be strings, got {type(label).__name__}."
        pair = _lookup_coordinates(coordinates, label.strip())
        if pair is None:
            return None, f"No coordinates entry for waypoint label {label!r}."
        targets.append(pair)
    return targets, None


def _track_points_match_sequence(
    seq: List[Tuple[float, float]], targets: List[Tuple[float, float]], tol: float
) -> bool:
    if not targets:
        return False
    ti = 0
    for p in seq:
        if ti < len(targets) and _coord_close(p, targets[ti], tol):
            ti += 1
            if ti == len(targets):
                return True
    return False


@PluginRegistry.register(namespace="evaluator.system_state", name="gpx_favorites_location_match")
class GpxFavoritesLocationMatchAction(BaseSystemAction):
    """See module docstring."""

    def evaluate(self, context: Dict[str, Any]) -> EvalResult:
        kind_raw = self.get_param("match_kind", context, default="favorite_location", expected_type=str)
        kind = (kind_raw or "favorite_location").strip().lower()
        aliases = {
            "favorite": "favorite_location",
            "favorites": "favorite_location",
            "tracks": "track_directory_ordered_coords",
            "track": "track_directory_ordered_coords",
            "track_ordered": "track_directory_ordered_coords",
        }
        kind = aliases.get(kind, kind)
        if kind == "track_directory_ordered_coords":
            return self._evaluate_track_directory_ordered(context)
        return self._evaluate_favorite_location(context)

    def _evaluate_favorite_location(self, context: Dict[str, Any]) -> EvalResult:
        file_path = self.get_param("file_path", context, default=_DEFAULT_GPX, expected_type=str).strip()
        location = self.get_param("location", context, expected_type=str).strip()
        tol = self.get_param("lat_lon_tolerance_deg", context, default=0.001, expected_type=float)

        coordinates = self.params.get("coordinates")
        if coordinates is not None and not isinstance(coordinates, dict):
            return EvalResult(
                is_pass=False,
                reason="Optional param 'coordinates' must be a JSON object mapping location → {lat, lon} or [lat, lon].",
            )

        self.logger.info("gpx_favorites_location_match favorite_location path=%r location=%r", file_path, location)

        raw = self._run_device_shell(f"cat {file_path}")
        if "No such file" in raw or "No such file or directory" in raw or raw.startswith("ERROR:"):
            return EvalResult(
                is_pass=False,
                reason=f"favorites.gpx missing or unreadable at {file_path!r}: {(raw or '')[:200]!r}",
            )

        try:
            root = ET.fromstring(raw)
        except ET.ParseError as e:
            return EvalResult(is_pass=False, reason=f"Invalid GPX/XML: {e}")

        wpts = _iter_waypoints(root)
        if not wpts:
            return EvalResult(is_pass=False, reason="GPX parsed but contains no <wpt> waypoints.")

        target_ll: Optional[Tuple[float, float]] = None
        if isinstance(coordinates, dict):
            target_ll = _lookup_coordinates(coordinates, location)
        if target_ll is None:
            target_ll = _parse_lat_lon_from_location_string(location)

        loc_l = location.lower()
        reasons: List[str] = []

        for i, wpt in enumerate(wpts):
            name = _wpt_text(wpt, "name")
            desc = _wpt_text(wpt, "desc")
            cmt = _wpt_text(wpt, "cmt")
            hay = " ".join(x for x in (name, desc, cmt) if x).lower()

            if name:
                if loc_l in name.lower():
                    return EvalResult(
                        is_pass=True,
                        reason=f"Waypoint #{i + 1} <name> contains location substring ({name[:80]!r}).",
                    )
            else:
                if loc_l in hay:
                    return EvalResult(
                        is_pass=True,
                        reason=f"Waypoint #{i + 1} (no <name>) text contains location substring.",
                    )

            w_ll = _parse_lat_lon_attrs(wpt)
            if w_ll is not None and target_ll is not None and _coord_close(w_ll, target_ll, tol):
                return EvalResult(
                    is_pass=True,
                    reason=(
                        f"Waypoint #{i + 1} lat/lon {w_ll[0]:.6f},{w_ll[1]:.6f} within "
                        f"±{tol} of target {target_ll[0]:.6f},{target_ll[1]:.6f}."
                    ),
                )

            reasons.append(
                f"wpt#{i + 1} name={name[:40]!r} ll={w_ll} "
                f"{'(no target lat/lon)' if target_ll is None else ''}".strip()
            )

        tail = "; ".join(reasons[:5])
        if len(reasons) > 5:
            tail += f"; … ({len(reasons)} waypoints total)"
        return EvalResult(
            is_pass=False,
            reason=(
                f"No waypoint matched location {location!r} by name substring or coordinate proximity. "
                f"Samples: {tail}"
            ),
        )

    def _resolve_tracks_directory(self, context: Dict[str, Any]) -> str:
        override = self.params.get("tracks_directory")
        if isinstance(override, str) and override.strip():
            return self.get_param("tracks_directory", context, expected_type=str).strip()
        for base in _OSMAND_FILES_CANDIDATES:
            d = f"{base.rstrip('/')}/{_DEFAULT_TRACKS_SUBDIR}"
            names = self._list_track_filenames(d)
            if names:
                self.logger.info("gpx track mode using tracks_directory=%r (%d files)", d, len(names))
                return d
        return f"{_OSMAND_FILES_CANDIDATES[0]}/{_DEFAULT_TRACKS_SUBDIR}"

    def _list_track_filenames(self, directory: str) -> List[str]:
        raw = self._run_device_shell(f"ls -1 {directory} 2>/dev/null || ls {directory} 2>/dev/null")
        if "No such file" in raw or not raw.strip():
            return []
        names: List[str] = []
        for line in raw.splitlines():
            n = line.strip()
            if n and n not in (".", ".."):
                names.append(n)
        return names

    def _evaluate_track_directory_ordered(self, context: Dict[str, Any]) -> EvalResult:
        tol = self.get_param("lat_lon_tolerance_deg", context, default=0.001, expected_type=float)
        ordered = self.params.get("ordered_waypoints")
        coordinates = self.params.get("coordinates")
        targets, err = _ordered_targets_from_params(ordered, coordinates)
        if err:
            return EvalResult(is_pass=False, reason=err)
        assert targets is not None

        tracks_dir = self._resolve_tracks_directory(context)
        self.logger.info(
            "gpx track_directory_ordered_coords dir=%r n_targets=%d tol=%s",
            tracks_dir,
            len(targets),
            tol,
        )

        filenames = self._list_track_filenames(tracks_dir)
        if not filenames:
            return EvalResult(
                is_pass=False,
                reason=f"No files listed under tracks directory {tracks_dir!r} (empty or missing).",
            )

        parse_errors = 0
        for fn in filenames:
            path = f"{tracks_dir.rstrip('/')}/{fn}"
            raw = self._run_device_shell(f"cat {path}")
            if "No such file" in raw or not raw.strip():
                continue
            try:
                root = ET.fromstring(raw)
            except ET.ParseError:
                parse_errors += 1
                continue
            seq = _extract_trkpt_sequence(root)
            if not seq:
                continue
            if _track_points_match_sequence(seq, targets, tol):
                return EvalResult(
                    is_pass=True,
                    reason=(
                        f"Track GPX {fn!r} contains an ordered <trkpt> subsequence matching "
                        f"{len(targets)} target waypoint(s) within ±{tol}°."
                    ),
                )

        return EvalResult(
            is_pass=False,
            reason=(
                f"No GPX under {tracks_dir!r} matched ordered waypoints in coordinate tolerance "
                f"(files tried: {len(filenames)}, xml parse skips: {parse_errors})."
            ),
        )
