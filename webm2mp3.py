import argparse
import os
import subprocess
import tempfile
from pathlib import Path


def _read_arguments():
    parser = argparse.ArgumentParser(description="Convert WebM audio to MP3")
    parser.add_argument("path")
    parser.add_argument("--ffmpeg-exe", default="ffmpeg")
    return parser.parse_args()


def convert_webm_folder_to_mp3(ffmpeg_exe, folder):
    files = sorted(p for p in Path(folder).iterdir() if p.is_file() and p.suffix.lower() == ".webm")
    return convert_webm_files_to_mp3(ffmpeg_exe, [{"file": str(p)} for p in files])


def convert_webm_files_to_mp3(ffmpeg_exe, lst):
    outputs = []
    for item in lst:
        result = convert_webm_file_to_mp3(ffmpeg_exe, item["file"], item.get("title"), item.get("abr"))
        if result is not None:
            outputs.append(result)
    return outputs


def convert_webm_file_to_mp3(ffmpeg_exe, file_name, title=None, abr=None):
    source = Path(file_name)
    target = source.with_suffix(".mp3")
    temporary = None
    try:
        if source.suffix.lower() != ".webm" or not source.is_file():
            raise ValueError("Input must be an existing WebM file")
        if target.exists():
            raise FileExistsError(str(target))
        fd, temporary = tempfile.mkstemp(prefix=".convert-", suffix=".mp3", dir=str(source.parent))
        os.close(fd)
        params = [ffmpeg_exe, "-nostdin", "-i", str(source), "-vn", "-c:a", "libmp3lame", "-q:a", "2", "-loglevel", "warning", "-y", temporary]
        subprocess.run(params, check=True, timeout=3600)
        if Path(temporary).stat().st_size == 0:
            raise RuntimeError("FFmpeg produced an empty file")
        if target.exists():
            raise FileExistsError(str(target))
        os.replace(temporary, target)
        temporary = None
        try:
            source.unlink()
        except OSError as exc:
            print(f"MP3 created, but source cleanup failed: {exc}")
        return str(target)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f"Failed to convert {title or file_name}: {exc}")
        return None
    finally:
        if temporary is not None:
            Path(temporary).unlink(missing_ok=True)


def main():
    args = _read_arguments()
    if Path(args.path).is_file():
        return 0 if convert_webm_file_to_mp3(args.ffmpeg_exe, args.path) else 1
    files = [p for p in Path(args.path).iterdir() if p.is_file() and p.suffix.lower() == ".webm"]
    return 0 if len(convert_webm_folder_to_mp3(args.ffmpeg_exe, args.path)) == len(files) else 1


if __name__ == "__main__":
    raise SystemExit(main())
