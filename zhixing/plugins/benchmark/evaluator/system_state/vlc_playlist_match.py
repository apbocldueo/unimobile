import os
from typing import Any, Dict, List, Tuple

from zhixing.core.benchmark.protocol import EvalResult
from zhixing.core.benchmark.base_system import BaseSystemAction
from zhixing.core.benchmark.param_handler import ParamHandler
from zhixing.core.factory import PluginRegistry
from zhixing.plugins.benchmark.evaluator.system_state.sqlite_where_match import (
    _quote_posix_single,
)

_VLC_DB = "/data/data/org.videolan.vlc/app_db/vlc_media.db"
_SEP = "\x1f"


def _norm_name(s: str) -> str:
    return " ".join((s or "").split()).lower()


def _filename_matches(expected: str, got: str) -> bool:
    if expected == got:
        return True
    base = os.path.basename(got.replace("\\", "/"))
    return base == expected or got.endswith("/" + expected)


@PluginRegistry.register(namespace="evaluator.system_state", name="vlc_playlist_match")
class VlcPlaylistMatchAction(BaseSystemAction):
    """Verify a VLC playlist name and ordered media filenames in vlc_media.db.

    Mirrors AndroidWorld ``verify_playlist``: each expected file must appear at
    the matching ``position`` (0-based) under the named playlist.
    """

    def evaluate(self, context: Dict[str, Any]) -> EvalResult:
        playlist_name = self.get_param("playlist_name", context, expected_type=str)
        files_raw = self.params.get("files")
        if not isinstance(files_raw, list) or not files_raw:
            return EvalResult(is_pass=False, reason="Missing required param: files (non-empty array).")

        task_params = context.get("task_params") or {}
        expected_files: List[str] = [
            str(x) for x in ParamHandler.render_placeholders(files_raw, task_params)
        ]

        database = str(self.params.get("database") or _VLC_DB).strip()
        sep_sql = f"char({ord(_SEP)})"
        cols = [
            "Playlist.name",
            "Media.filename",
            "CAST(PlaylistMediaRelation.position AS TEXT)",
        ]
        concat = f" || {sep_sql} || ".join(f"IFNULL({c}, '')" for c in cols)
        inner = (
            "SELECT "
            + concat
            + " FROM PlaylistMediaRelation"
            " INNER JOIN Playlist ON Playlist.id_playlist = PlaylistMediaRelation.playlist_id"
            " INNER JOIN Media ON Media.id_media = PlaylistMediaRelation.media_id"
            " ORDER BY Playlist.name, PlaylistMediaRelation.position"
        )
        cmd = f"sqlite3 {_quote_posix_single(database)} {_quote_posix_single(inner)}"
        self.logger.info(
            "vlc_playlist_match playlist=%r files=%r",
            playlist_name,
            expected_files,
        )

        raw = self._run_device_shell(cmd)
        if raw.startswith("ERROR:"):
            return EvalResult(is_pass=False, reason=f"Shell/sqlite3 failed: {raw}")
        low = (raw or "").lower()
        if "unable to open database" in low or "no such table" in low:
            return EvalResult(is_pass=False, reason=f"sqlite3 error: {raw[:500]!r}")

        rows = self._parse_rows(raw)
        if not rows:
            return EvalResult(is_pass=False, reason="No playlist rows returned from VLC database.")

        target = _norm_name(playlist_name)
        playlist_rows = [
            (fname, pos)
            for pname, fname, pos in rows
            if _norm_name(pname) == target
        ]
        if not playlist_rows:
            names = sorted({_norm_name(p) for p, _, _ in rows})
            return EvalResult(
                is_pass=False,
                reason=f"Playlist {playlist_name!r} not found. Playlists seen: {names!r}",
            )

        matched = 0
        for index, expected_file in enumerate(expected_files):
            want_pos = str(index)
            if any(
                pos == want_pos and _filename_matches(expected_file, fname)
                for fname, pos in playlist_rows
            ):
                matched += 1
            else:
                got = [(fname, pos) for fname, pos in playlist_rows if pos == want_pos]
                return EvalResult(
                    is_pass=False,
                    reason=(
                        f"Position {index}: expected file {expected_file!r}, "
                        f"got {got!r} (all rows for playlist: {playlist_rows!r})"
                    ),
                )

        if matched != len(expected_files):
            return EvalResult(is_pass=False, reason="Playlist file count mismatch.")
        return EvalResult(
            is_pass=True,
            reason=f"Playlist {playlist_name!r} contains {len(expected_files)} file(s) in order.",
        )

    def _parse_rows(self, raw: str) -> List[Tuple[str, str, str]]:
        out: List[Tuple[str, str, str]] = []
        for line in (raw or "").splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split(_SEP)
            if len(parts) < 3:
                continue
            pname, fname, pos = parts[0], parts[1], parts[2]
            out.append((pname, fname, str(pos).strip()))
        return out
