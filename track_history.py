import json
import os
import tempfile
from pathlib import Path

DEFAULT_HISTORY_FILE_NAME = "__downloaded.yt.json"


class TrackHistory:
    def __init__(self):
        self.title = None
        self.stream_id = None
        self.date = None
        self.target_file = None
        self.abr = None
        self.status = None


def try_load_track_history(history_file_name):
    path = Path(history_file_name)
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        result = {}
        for key, value in data.items():
            track = TrackHistory()
            track.title = value["title"]
            track.date = value["date"]
            track.target_file = value["file"]
            track.stream_id = value["stream_id"]
            track.abr = int(value["abr"]) if value.get("abr") is not None else None
            track.status = value["status"]
            result[key] = track
        return result
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        raise ValueError(f"Invalid history file {path}; preserve or restore it before retrying") from exc


def save_track_history(tracks, history_file_name):
    path = Path(history_file_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {}
    for key, track in tracks.items():
        data[key] = {"title": track.title, "date": track.date, "file": track.target_file,
                     "stream_id": track.stream_id, "status": track.status, "abr": track.abr}
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=str(path.parent), delete=False) as handle:
            temporary = handle.name
            json.dump(data, handle, indent=2, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            Path(temporary).unlink(missing_ok=True)
