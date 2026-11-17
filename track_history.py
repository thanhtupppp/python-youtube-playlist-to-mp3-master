import json
import os
import tempfile
from dataclasses import asdict, dataclass, fields
from pathlib import Path

DEFAULT_HISTORY_FILE_NAME = "__downloaded.yt.json"


@dataclass
class TrackHistory:
    title: str | None = None
    stream_id: int | None = None
    date: str | None = None
    target_file: str | None = None
    abr: int | None = None
    status: str = "pending"
    source_file: str | None = None
    output_file: str | None = None
    conversion_status: str = "pending"
    gain_status: str = "pending"
    gain_target: int | None = None
    last_error: str | None = None


def try_load_track_history(history_file_name):
    path = Path(history_file_name)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        names = {f.name for f in fields(TrackHistory)}
        result = {}
        for key, raw in data.items():
            track = TrackHistory(**{k: v for k, v in raw.items() if k in names})
            track.target_file = raw.get("target_file") or raw.get("file")
            track.abr = int(track.abr) if track.abr is not None else None
            if track.target_file:
                if Path(track.target_file).suffix.lower() == ".mp3":
                    track.output_file = track.output_file or track.target_file
                    track.conversion_status = "converted"
                else:
                    track.source_file = track.source_file or track.target_file
            result[key] = track
        return result
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError(f"Invalid history: {path}. Restore a backup; original file was not changed.") from exc


def save_track_history(tracks, history_file_name):
    path = Path(history_file_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as handle:
            temporary = handle.name
            json.dump({key: asdict(track) for key, track in tracks.items()}, handle, indent=2, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary:
            Path(temporary).unlink(missing_ok=True)
