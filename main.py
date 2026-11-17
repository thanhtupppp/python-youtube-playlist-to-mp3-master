import argparse
import os

import mp3gain
import track_history
import webm2mp3
from downloader import download


def _read_arguments():
    parser = argparse.ArgumentParser(description="Download audio from a YouTube playlist")
    parser.add_argument("url")
    parser.add_argument("output_path", metavar="output-path")
    parser.add_argument("--dont-load-history", action="store_true")
    parser.add_argument("--dont-save-history", action="store_true")
    parser.add_argument("--delay", type=int, default=10)
    parser.add_argument("--history-filename", default=track_history.DEFAULT_HISTORY_FILE_NAME)
    parser.add_argument("--to-mp3", action="store_true")
    parser.add_argument("--ffmpeg-exe", default="ffmpeg")
    parser.add_argument("--adjust-mp3-gain", action="store_true")
    parser.add_argument("--target-mp3-gain", type=int, default=89)
    parser.add_argument("--mp3gain-exe", default="mp3gain")
    parser.add_argument("--repeat-errors", action="store_true")
    args = parser.parse_args()
    if args.delay < 0:
        parser.error("--delay must be non-negative")
    if args.adjust_mp3_gain and not args.to_mp3:
        parser.error("--adjust-mp3-gain requires --to-mp3")
    return args


def _load_history(args):
    return track_history.try_load_track_history(os.path.join(args.output_path, args.history_filename))


def _save_history(args, history):
    if not args.dont_save_history:
        track_history.save_track_history(history, os.path.join(args.output_path, args.history_filename))


def _merge_history(old, new):
    return {**old, **new}


def main():
    args = _read_arguments()
    os.makedirs(args.output_path, exist_ok=True)
    history_old = {} if args.dont_load_history else _load_history(args)
    history_new = download(args.url, args.output_path, history_old,
                           delay_between_tracks=args.delay,
                           repeat_errors=args.repeat_errors, verbose=True)
    history = _merge_history(history_old, history_new)
    _save_history(args, history)
    failed = any((h.status or "").startswith("error:") for h in history_new.values())
    if args.to_mp3:
        for track in history.values():
            if track.status != "downloaded" or not track.target_file:
                continue
            if not os.path.isfile(track.target_file):
                continue
            converted = webm2mp3.convert_webm_file_to_mp3(
                args.ffmpeg_exe, track.target_file, track.title, track.abr)
            if converted is None:
                failed = True
                continue
            track.target_file = converted
            track.status = "converted"
            _save_history(args, history)
            if args.adjust_mp3_gain:
                if not mp3gain.process_file(args.mp3gain_exe, converted, args.target_mp3_gain):
                    failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
