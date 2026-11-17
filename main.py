import argparse
import logging
import shutil
import time
from contextlib import ExitStack
from pathlib import Path

import downloader
import mp3gain
import track_history
import webm2mp3
from output_lock import file_lock

log = logging.getLogger(__name__)


def has_file(value):
    return bool(value and Path(value).is_file() and Path(value).stat().st_size > 0)


def _read_arguments():
    parser = argparse.ArgumentParser(description="Download playlist audio with per-track resume")
    parser.add_argument("url")
    parser.add_argument("output_path", metavar="output-path")
    for name in ("dont-load-history", "dont-save-history", "to-mp3", "adjust-mp3-gain", "repeat-errors", "keep-source"):
        parser.add_argument("--" + name, action="store_true")
    parser.add_argument("--delay", type=int, default=10)
    parser.add_argument("--history-filename", default=track_history.DEFAULT_HISTORY_FILE_NAME)
    parser.add_argument("--ffmpeg-exe", default="ffmpeg")
    parser.add_argument("--mp3gain-exe", default="mp3gain")
    parser.add_argument("--target-mp3-gain", type=int, default=89)
    args = parser.parse_args()
    if args.delay < 0:
        parser.error("--delay must be non-negative")
    if args.adjust_mp3_gain and not args.to_mp3:
        parser.error("--adjust-mp3-gain requires --to-mp3")
    return args


def process_track(track, args, save):
    if not args.to_mp3:
        return True
    if not has_file(track.output_file):
        if not has_file(track.source_file):
            raise ValueError("Source and output are missing")
        target = str(Path(track.source_file).with_suffix(".mp3"))
        track.output_file = target
        track.conversion_status = "converting"
        track.last_error = None
        save()
        result = webm2mp3.convert_webm_file_to_mp3(args.ffmpeg_exe, track.source_file, track.title)
        if result is None:
            track.conversion_status = "failed"
            track.last_error = "Conversion failed; source retained"
            save()
            return False
        track.output_file = result
    track.target_file = track.output_file
    track.conversion_status = "converted"
    track.status = "converted"
    track.last_error = None
    save()
    if not args.keep_source and track.source_file and has_file(track.source_file):
        Path(track.source_file).unlink()
    if args.adjust_mp3_gain and (track.gain_status != "applied" or track.gain_target != args.target_mp3_gain):
        track.gain_status = "applying"
        save()
        success = mp3gain.process_file(args.mp3gain_exe, track.output_file, args.target_mp3_gain)
        track.gain_status = "applied" if success else "failed"
        track.gain_target = args.target_mp3_gain if success else None
        track.last_error = None if success else "MP3Gain failed"
        save()
        return success
    return True


def run(args):
    output = Path(args.output_path).resolve()
    output.mkdir(parents=True, exist_ok=True)
    history_path = (output / args.history_filename).resolve()
    if args.to_mp3 and not shutil.which(args.ffmpeg_exe):
        raise ValueError(f"FFmpeg not found: {args.ffmpeg_exe}")
    if args.adjust_mp3_gain and not shutil.which(args.mp3gain_exe):
        raise ValueError(f"MP3Gain not found: {args.mp3gain_exe}")
    locks = sorted({output / ".audio-output.lock", history_path.with_name(history_path.name + ".lock")}, key=str)
    with ExitStack() as stack:
        for lock in locks:
            stack.enter_context(file_lock(lock))
        history = {} if args.dont_load_history else track_history.try_load_track_history(history_path)
        def save():
            if not args.dont_save_history:
                track_history.save_track_history(history, history_path)
        urls = downloader.playlist_urls(args.url)
        failed = 0
        attempted = False
        for url in urls:
            track = history.get(url)
            try:
                if track and track.conversion_status not in ("converted", "converting"):
                    track.output_file = None
                if not track or not (has_file(track.source_file) or has_file(track.output_file)):
                    if track and (track.status or "").startswith("error:") and not args.repeat_errors:
                        failed += 1
                        log.error("Previous download failed; use --repeat-errors: %s", url)
                        continue
                    if attempted:
                        time.sleep(args.delay)
                    attempted = True
                    try:
                        def on_plan(planned):
                            history[url] = planned
                            save()
                        track = downloader.download_track(url, str(output), on_plan=on_plan)
                    except Exception as exc:
                        history[url] = track_history.TrackHistory(status="error: download", last_error=str(exc))
                        save()
                        raise
                    history[url] = track
                    save()
                if not process_track(track, args, save):
                    failed += 1
            except (OSError, ValueError, RuntimeError) as exc:
                failed += 1
                log.error("Track failed %s: %s", url, exc)
        log.info("Playlist complete: %d tracks, %d failed", len(urls), failed)
        return int(failed > 0)


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    try:
        return run(_read_arguments())
    except KeyboardInterrupt:
        log.warning("Interrupted; completed checkpoints retained")
        return 130
    except (OSError, ValueError, RuntimeError) as exc:
        log.error("%s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
