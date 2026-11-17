import re
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from track_history import TrackHistory


def playlist_urls(url):
    from pytubefix import Playlist
    return list(dict.fromkeys(Playlist(url).video_urls))


def _get_best_audio_stream(yt):
    candidates = []
    for stream in yt.streams:
        if stream.mime_type != "audio/webm":
            continue
        match = re.fullmatch(r"([0-9]+)(?:\.[0-9]+)?kbps", str(stream.abr))
        if match:
            candidates.append((int(match.group(1)), stream))
    if not candidates:
        raise ValueError("No supported WebM audio stream with a valid bitrate")
    abr, stream = max(candidates, key=lambda pair: pair[0])
    return stream, abr


def download_track(url, output, on_plan=None):
    from pytubefix import YouTube
    yt = YouTube(url)
    title = yt.title
    video_id = yt.video_id
    if not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
        raise ValueError("Invalid YouTube video ID")
    stream, abr = _get_best_audio_stream(yt)
    target = Path(output).resolve() / f"{video_id}.webm"
    if target.exists():
        raise FileExistsError(f"Untracked source exists; inspect before retry: {target}")
    track = TrackHistory(title=title, stream_id=stream.itag, date=datetime.now(timezone.utc).isoformat(),
                         target_file=str(target), source_file=str(target), abr=abr, status="downloading")
    if on_plan:
        on_plan(track)
    with tempfile.TemporaryDirectory(prefix=".download-", dir=output) as temporary:
        downloaded = Path(stream.download(output_path=temporary, filename=target.name))
        if not downloaded.is_file() or downloaded.stat().st_size == 0:
            raise ValueError("Downloaded audio is empty")
        import os
        os.link(downloaded, target)
    track.status = "downloaded"
    return track


def download(url, output, history_old, *, delay_between_tracks=10, repeat_errors=False, verbose=True, on_result=None):
    """Compatibility entry point; callback checkpoints each result."""
    def has_file(value):
        return bool(value and Path(value).is_file() and Path(value).stat().st_size > 0)
    if delay_between_tracks < 0:
        raise ValueError("Delay must be non-negative")
    Path(output).mkdir(parents=True, exist_ok=True)
    result = {}
    attempted = False
    for item in playlist_urls(url):
        old = history_old.get(item)
        if old and (has_file(old.source_file) or has_file(old.output_file)):
            continue
        if old and (old.status or "").startswith("error:") and not repeat_errors:
            continue
        if attempted:
            time.sleep(delay_between_tracks)
        attempted = True
        try:
            track = download_track(item, output)
        except Exception as exc:
            track = TrackHistory(status="error: download", last_error=str(exc))
        result[item] = track
        if on_result:
            on_result(item, track)
    return result
