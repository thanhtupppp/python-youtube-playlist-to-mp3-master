# YouTube playlist audio downloader

Python >=3.11. Download only content you own or are permitted to download.

## Install and run

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py "PLAYLIST_URL" "D:/Music" --to-mp3
```

Install FFmpeg separately and make `ffmpeg` available on PATH, or pass
`--ffmpeg-exe PATH`. Gain adjustment additionally needs MP3Gain (`--mp3gain-exe`).
Use `python main.py --help` to list arguments.

- Without `--to-mp3`, retain original WebM audio without re-encoding.
- `--adjust-mp3-gain --target-mp3-gain 89` applies gain; requires `--to-mp3`.
- `--keep-source` retains WebM after conversion. Standalone `webm2mp3.py` always retains sources.
- `--delay 10` waits between download attempts, never after the last attempt.
- `--repeat-errors` retries failed downloads. Conversion and gain failures retry automatically.
- `--dont-load-history` ignores previous records; existing files are never silently overwritten.
- `--dont-save-history` disables durable resume and crash recovery.
- `--history-filename` selects the history file (relative to output or absolute).

## Resume and migration

Only videos in the current playlist are processed; unrelated history is preserved.
New downloads use video IDs as filenames to prevent title collisions. Download and
conversion outputs are published only after success. A checkpoint is written before
source cleanup, and after each completed download/conversion/gain stage.
Old flat JSON history is read automatically; back it up before the first run because
new records include separate source, output, conversion and gain fields.
Legacy relative file paths retain their original working-directory interpretation.
A corrupt history file causes an explicit error and is not overwritten.
If an untracked file already exists, inspect/move it rather than forcing overwrite.
Recovered outputs are checked for existence and nonzero size, not fully decoded.

The main CLI locks both output and history on local Windows/POSIX filesystems.
Do not use lock guarantees on network filesystems or run other tools modifying the
same files concurrently. Atomic no-overwrite publication requires hard-link support
(e.g. local NTFS/ext4); unsupported filesystems fail safely and retain source audio.
A hard-killed download may leave a `.download-*` directory; inspect and remove it
only after confirming no process is using it. Do not delete active lock files.

## Tests and dependencies

```powershell
python -m unittest discover -s tests -v
python -m pip check
```

The unittest suite uses mocks and requires neither YouTube access nor FFmpeg.
Root `test_pytube.py` and `test_pytubefix.py` are guarded manual CLI aliases.
`requirements.txt` pins direct runtime dependencies only; it is not a complete lock.
CI installs on Windows/Linux with Python 3.11-3.13 and uploads the resolved package
list per environment. These artifacts are environment snapshots, not hash-locked
cross-platform dependency files. Live YouTube/FFmpeg/MP3Gain smoke tests remain manual.
