import argparse
import subprocess
from pathlib import Path


def process_file(mp3gain_exe, mp3file, target_gain=89):
    try:
        if not Path(mp3file).is_file():
            raise FileNotFoundError(mp3file)
        params = [mp3gain_exe, "-r"]
        if target_gain != 89:
            params.extend(["-d", str(float(target_gain - 89))])
        subprocess.run(params + [str(mp3file)], check=True, timeout=600)
        return True
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"Failed to apply mp3gain on {mp3file}: {exc}")
        return False


def process_files(mp3gain_exe, mp3files, target_gain=89):
    return all([process_file(mp3gain_exe, path, target_gain) for path in mp3files])


def process_folder(mp3gain_exe, folder, target_gain=89):
    files = sorted(str(p) for p in Path(folder).iterdir() if p.is_file() and p.suffix.lower() == ".mp3")
    return process_files(mp3gain_exe, files, target_gain)


def main():
    parser = argparse.ArgumentParser(description="Adjust MP3 gain")
    parser.add_argument("path")
    parser.add_argument("--mp3gain-exe", default="mp3gain")
    parser.add_argument("--target-gain", type=int, default=89)
    args = parser.parse_args()
    from output_lock import file_lock
    path = Path(args.path).resolve()
    folder = path.parent if path.is_file() else path
    with file_lock(folder / ".audio-output.lock"):
        process = process_file if path.is_file() else process_folder
        return 0 if process(args.mp3gain_exe, str(path), args.target_gain) else 1


if __name__ == "__main__":
    raise SystemExit(main())
