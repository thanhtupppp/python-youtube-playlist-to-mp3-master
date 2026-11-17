import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import downloader
import main
import track_history
import webm2mp3
from output_lock import file_lock


class RegressionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "song.webm"
        self.source.write_bytes(b"audio")
        self.args = SimpleNamespace(to_mp3=True, keep_source=False, adjust_mp3_gain=False,
            ffmpeg_exe="ffmpeg", mp3gain_exe="mp3gain", target_mp3_gain=89, delay=0,
            output_path=str(self.root), history_filename="history.json", dont_load_history=False,
            dont_save_history=False, repeat_errors=False, url="playlist")

    def track(self):
        return track_history.TrackHistory(status="downloaded", source_file=str(self.source), target_file=str(self.source), abr=128)

    def encode(self, params, **kwargs):
        Path(params[-1]).write_bytes(b"encoded")

    def test_conversion_name_and_source_retained(self):
        with patch.object(webm2mp3.subprocess, "run", side_effect=self.encode):
            result = webm2mp3.convert_webm_file_to_mp3("ffmpeg", str(self.source))
        self.assertEqual(Path(result).name, "song.mp3")
        self.assertTrue(self.source.exists())

    def test_empty_output_is_failure(self):
        with patch.object(webm2mp3.subprocess, "run"):
            self.assertIsNone(webm2mp3.convert_webm_file_to_mp3("ffmpeg", str(self.source)))
        self.assertTrue(self.source.exists())
        self.assertFalse(list(self.root.glob(".convert-*")))

    def test_nonzero_preserves_source(self):
        with patch.object(webm2mp3.subprocess, "run", side_effect=subprocess.CalledProcessError(1, "ffmpeg")):
            self.assertIsNone(webm2mp3.convert_webm_file_to_mp3("ffmpeg", str(self.source)))
        self.assertTrue(self.source.exists())

    def test_existing_output_not_overwritten(self):
        self.source.with_suffix(".mp3").write_bytes(b"existing")
        with patch.object(webm2mp3.subprocess, "run") as run:
            self.assertIsNone(webm2mp3.convert_webm_file_to_mp3("ffmpeg", str(self.source)))
            run.assert_not_called()
        self.assertEqual(self.source.with_suffix(".mp3").read_bytes(), b"existing")

    def test_history_roundtrip(self):
        track = self.track()
        track.gain_status = "failed"
        path = self.root / "history.json"
        track_history.save_track_history({"url": track}, path)
        loaded = track_history.try_load_track_history(path)["url"]
        self.assertEqual(loaded.abr, 128)
        self.assertEqual(loaded.gain_status, "failed")
        self.assertIsInstance(track.abr, int)

    def test_legacy_history(self):
        path = self.root / "old.json"
        path.write_text(json.dumps({"url": {"file": str(self.source), "status": "downloaded", "abr": "128"}}))
        track = track_history.try_load_track_history(path)["url"]
        self.assertEqual(track.source_file, str(self.source))
        self.assertEqual(track.abr, 128)

    def test_corrupt_history_preserved(self):
        path = self.root / "bad.json"
        path.write_text("{")
        with self.assertRaises(ValueError):
            track_history.try_load_track_history(path)
        self.assertEqual(path.read_text(), "{")

    def test_checkpoint_before_source_cleanup(self):
        track = self.track()
        snapshots = []
        def save():
            snapshots.append((track.conversion_status, self.source.exists()))
        with patch.object(webm2mp3.subprocess, "run", side_effect=self.encode):
            self.assertTrue(main.process_track(track, self.args, save))
        self.assertIn(("converted", True), snapshots)
        self.assertFalse(self.source.exists())

    def test_resume_published_conversion(self):
        track = self.track()
        track.output_file = str(self.source.with_suffix(".mp3"))
        Path(track.output_file).write_bytes(b"published")
        track.conversion_status = "converting"
        with patch.object(webm2mp3, "convert_webm_file_to_mp3") as convert:
            self.assertTrue(main.process_track(track, self.args, lambda: None))
            convert.assert_not_called()
        self.assertEqual(track.conversion_status, "converted")

    def test_gain_retry_without_reencoding(self):
        track = self.track()
        track.output_file = str(self.source.with_suffix(".mp3"))
        Path(track.output_file).write_bytes(b"mp3")
        track.gain_status = "failed"
        self.args.adjust_mp3_gain = True
        with patch.object(main.mp3gain, "process_file", return_value=True) as gain:
            self.assertTrue(main.process_track(track, self.args, lambda: None))
            gain.assert_called_once()
        self.assertEqual(track.gain_status, "applied")

    def test_missing_file_redownload_and_playlist_scope(self):
        other = self.track()
        missing = track_history.TrackHistory(status="downloaded", source_file=str(self.root / "gone.webm"))
        track_history.save_track_history({"old-playlist": other, "current": missing}, self.root / "history.json")
        self.args.to_mp3 = False
        with patch.object(downloader, "playlist_urls", return_value=["current"]), patch.object(downloader, "download_track", return_value=self.track()) as download:
            self.assertEqual(main.run(self.args), 0)
            self.assertEqual(download.call_args.args[0], "current")
            self.assertEqual(download.call_count, 1)
        history = track_history.try_load_track_history(self.root / "history.json")
        self.assertIn("old-playlist", history)

    def test_checkpoint_survives_interrupt(self):
        self.args.to_mp3 = False
        with patch.object(downloader, "playlist_urls", return_value=["one", "two"]), patch.object(downloader, "download_track", side_effect=[self.track(), KeyboardInterrupt()]):
            with self.assertRaises(KeyboardInterrupt):
                main.run(self.args)
        self.assertIn("one", track_history.try_load_track_history(self.root / "history.json"))

    def test_lock_rejects_second_owner(self):
        with file_lock(self.root / "lock"):
            with self.assertRaises(RuntimeError):
                with file_lock(self.root / "lock"):
                    pass
        with file_lock(self.root / "lock"):
            pass

    def test_stream_validation(self):
        with self.assertRaises(ValueError):
            downloader._get_best_audio_stream(SimpleNamespace(streams=[]))
        bad = SimpleNamespace(mime_type="audio/webm", abr=None)
        with self.assertRaises(ValueError):
            downloader._get_best_audio_stream(SimpleNamespace(streams=[bad]))

    def test_download_plan_precedes_publication(self):
        import sys
        from types import ModuleType
        stream = SimpleNamespace(mime_type="audio/webm", abr="128kbps", itag=1)
        def fetch(output_path, filename):
            path = Path(output_path) / filename
            path.write_bytes(b"downloaded")
            return str(path)
        stream.download = fetch
        fake = ModuleType("pytubefix")
        fake.YouTube = lambda url: SimpleNamespace(title="Title", video_id="abcdefghijk", streams=[stream])
        states = []
        with patch.dict(sys.modules, {"pytubefix": fake}):
            track = downloader.download_track("url", str(self.root), on_plan=lambda t: states.append((t.status, Path(t.source_file).exists())))
        self.assertEqual(states, [("downloading", False)])
        self.assertTrue(Path(track.source_file).is_file())

    def test_gain_already_applied_is_skipped(self):
        track = self.track()
        track.output_file = str(self.source.with_suffix(".mp3"))
        Path(track.output_file).write_bytes(b"mp3")
        track.gain_status = "applied"
        track.gain_target = 89
        self.args.adjust_mp3_gain = True
        with patch.object(main.mp3gain, "process_file") as gain:
            self.assertTrue(main.process_track(track, self.args, lambda: None))
            gain.assert_not_called()

    def test_no_trailing_delay(self):
        self.args.to_mp3 = False
        with patch.object(downloader, "playlist_urls", return_value=["one"]), patch.object(downloader, "download_track", return_value=self.track()), patch.object(main.time, "sleep") as sleep:
            self.assertEqual(main.run(self.args), 0)
            sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main()
