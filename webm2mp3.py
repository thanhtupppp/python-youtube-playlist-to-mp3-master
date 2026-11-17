import argparse
import os
import subprocess
import tempfile
from pathlib import Path


class ConversionError(RuntimeError):
    pass


def convert_webm_file_to_mp3(ffmpeg_exe, file_name, title=None, abr=None):
    """Publish MP3 without overwriting; caller owns source cleanup and checkpoints."""
    source = Path(file_name).resolve()
    target = source.with_suffix(".mp3")
    temporary = None
    try:
        if source.suffix.lower() != ".webm" or not source.is_file():
            raise ValueError("Input must be an existing WebM file")
        if target.exists():
            raise FileExistsError(str(target))
        fd, temporary = tempfile.mkstemp(prefix=".convert-", suffix=".mp3", dir=source.parent)
        os.close(fd)
        subprocess.run([ffmpeg_exe, "-nostdin", "-i", str(source), "-vn", "-c:a", "libmp3lame", "-q:a", "2", "-loglevel", "warning", "-y", temporary], check=True, timeout=3600)
        if Path(temporary).stat().st_size == 0:
            raise ConversionError("FFmpeg produced an empty file")
        os.link(temporary, target)
        return str(target)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"Failed to convert {title or file_name}: {exc}")
        return None
    finally:
        if temporary:
            Path(temporary).unlink(missing_ok=True)


def convert_webm_files_to_mp3(ffmpeg_exe, lst):
    outputs = []
    for item in lst:
        result = convert_webm_file_to_mp3(ffmpeg_exe, item["file"], item.get("title"))
        if result:
            outputs.append(result)
    return outputs


def convert_webm_folder_to_mp3(ffmpeg_exe, folder):
    return convert_webm_files_to_mp3(ffmpeg_exe, [{"file": str(p)} for p in sorted(Path(folder).iterdir()) if p.is_file() and p.suffix.lower() == ".webm"])


def main():
    parser = argparse.ArgumentParser(description="Convert WebM to MP3; source files are retained")
    parser.add_argument("path")
    parser.add_argument("--ffmpeg-exe", default="ffmpeg")
    args = parser.parse_args()
    from output_lock import file_lock
    path = Path(args.path).resolve()
    folder = path.parent if path.is_file() else path
    with file_lock(folder / ".audio-output.lock"):
        if path.is_file():
            return 0 if convert_webm_file_to_mp3(args.ffmpeg_exe, str(path)) else 1
        inputs = [p for p in path.iterdir() if p.is_file() and p.suffix.lower() == ".webm"]
        return int(len(convert_webm_folder_to_mp3(args.ffmpeg_exe, str(path))) != len(inputs))


if __name__ == "__main__":
    raise SystemExit(main())
