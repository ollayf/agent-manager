"""End-to-end file inventory and warning-schema tests in fresh Git fixtures."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import check_worktree as checker
import file_types


class AddedFileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="added-files-test-")
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        self.git("init", "-q")

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.repo), *args],
                              check=True, capture_output=True).stdout

    def write(self, name, data):
        path = self.repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def scan(self, script="check_added_files.py"):
        result = subprocess.run([sys.executable, str(SCRIPTS / script), "--repo", str(self.repo), "--json"],
                                text=True, capture_output=True, timeout=60)
        return result.returncode, json.loads(result.stdout), result.stdout

    def test_every_added_path_is_reported_with_required_fields(self):
        paths = ["hello.py", "clip.mp4", "sound.wav", "unknown.strange", "nested/README.md"]
        for path in paths:
            self.write(path, b"content\n")
        self.git("add", "--", "hello.py", "clip.mp4")
        exit_code, report, _ = self.scan()
        self.assertEqual(exit_code, 2)
        self.assertEqual({r["path"] for r in report["files"]}, set(paths))
        self.assertEqual(report["summary"]["reported_paths"], len(paths))
        required = {"path", "source", "size_bytes", "category", "declared_category", "detected_format",
                    "inspection", "warnings", "added", "mode", "basis"}
        self.assertTrue(all(required <= set(r) for r in report["files"]))
        self.assertTrue(all({"severity", "code", "reason", "action", "path"} <= set(w)
                            for w in report["warnings"]))

    def test_staged_disguised_video_survives_working_copy_cleanup(self):
        self.write("innocent.txt", b"\0\0\0\x18ftypisom" + b"\0" * 32)
        self.git("add", "--", "innocent.txt")
        self.write("innocent.txt", b"cleaned text\n")
        _, report, _ = self.scan()
        staged = next(r for r in report["files"] if r["source"] == "index")
        self.assertEqual(staged["category"], "media_container")
        self.assertEqual(staged["detected_format"], "iso-media")
        self.assertIn("file-extension-mismatch", {w["code"] for w in staged["warnings"]})
        self.assertTrue(any(r["source"] == "worktree" and r["category"] == "text" for r in report["files"]))

    def test_media_extensions_warn_even_if_signature_is_not_recognized(self):
        for name in ["recording.mp4", "song.mp3", "camera.raw"]:
            self.write(name, b"arbitrary header")
        _, report, _ = self.scan()
        self.assertEqual({r["category"] for r in report["files"]}, {"video", "audio", "image"})
        self.assertTrue(all(r["warnings"] for r in report["files"]))

    def test_large_staged_video_is_classified_from_bounded_header(self):
        path = self.write("large.txt", b"\0\0\0\x18ftypisom")
        with path.open("ab") as stream:
            stream.truncate(file_types.LARGE_FILE_BYTES + 1)
        self.git("add", "--", "large.txt")
        _, report, _ = self.scan()
        record = report["files"][0]
        self.assertEqual(record["detected_format"], "iso-media")
        self.assertEqual(record["inspection"]["bytes_inspected"], file_types.HEADER_BYTES)
        self.assertEqual(record["inspection"]["coverage"], "header-only")
        self.assertIn("large-file-review", {w["code"] for w in report["warnings"]})

    def test_large_working_video_is_classified_from_bounded_header(self):
        path = self.write("large.mp4", b"\0\0\0\x18ftypisom")
        with path.open("ab") as stream:
            stream.truncate(checker.MAX_BYTES + 1)
        _, report, _ = self.scan()
        self.assertEqual(report["files"][0]["detected_format"], "iso-media")
        self.assertEqual(report["files"][0]["inspection"]["coverage"], "header-only")

    def test_full_checker_includes_file_type_warnings_and_inventory(self):
        self.write("recording.wav", b"RIFF\0\0\0\0WAVE" + b"\0" * 16)
        code, report, _ = self.scan("check_worktree.py")
        self.assertEqual(code, 2)
        self.assertTrue(report["file_checks"])
        self.assertTrue(any(f["code"] == "file-type-review" and f["category"] == "audio"
                            for f in report["findings"]))

    def test_unknown_binary_with_no_extension_is_not_omitted(self):
        self.write("mystery", b"\0\x88\x99")
        code, report, _ = self.scan()
        self.assertEqual(code, 2)
        self.assertEqual(report["files"][0]["category"], "unknown_binary")

    def test_ignored_media_is_excluded_until_force_added(self):
        self.write(".gitignore", b"private.mp4\n")
        self.write("private.mp4", b"\0\0\0\x18ftypisom")
        _, report, _ = self.scan()
        self.assertNotIn("private.mp4", {r["path"] for r in report["files"]})
        self.git("add", "-f", "--", "private.mp4")
        _, report, _ = self.scan()
        self.assertIn("private.mp4", {r["path"] for r in report["files"]})

    def test_symlink_is_reported_without_reading_target(self):
        self.write("ignored-target", b"confidential outside-data")
        self.write(".gitignore", b"ignored-target\n")
        (self.repo / "linked.mp4").symlink_to("ignored-target")
        _, report, output = self.scan()
        record = next(r for r in report["files"] if r["path"] == "linked.mp4")
        self.assertEqual(record["category"], "symlink")
        self.assertEqual(record["inspection"]["coverage"], "symlink-target-only")
        self.assertNotIn("confidential outside-data", output)

    def test_special_files_are_not_opened_or_hung(self):
        import os
        os.mkfifo(self.repo / "pipe.wav")
        _, report, _ = self.scan()
        records = [r for r in report["files"] if r["path"] == "pipe.wav"]
        # Some Git versions omit FIFOs from ls-files --others. Either way they
        # are never commit candidates; if listed, they must be reported skipped.
        if records:
            self.assertEqual(records[0]["category"], "special")
        self.assertFalse(any(r["inspection"]["coverage"] == "full-file-read" for r in records))

    def test_staged_executable_permission_requires_review(self):
        self.write("script.py", b"print('hello')\n")
        self.git("add", "--", "script.py")
        self.git("update-index", "--chmod=+x", "--", "script.py")
        _, report, _ = self.scan()
        self.assertIn("executable-mode-review", {w["code"] for w in report["warnings"]})

    def test_case_collisions_are_reported_even_on_case_insensitive_host(self):
        # Build both index entries without depending on the host filesystem.
        oid = self.git("hash-object", "-w", "--stdin").strip().decode()
        for path in ["Hello.py", "hello.py"]:
            self.git("update-index", "--add", "--cacheinfo", "100644," + oid + "," + path)
        _, report, _ = self.scan()
        self.assertEqual({w["path"] for w in report["warnings"] if w["code"] == "case-collision-review"},
                         {"Hello.py", "hello.py"})

    def test_aggregate_added_size_is_counted_once_per_path(self):
        for i in range(5):
            path = self.write(f"asset{i}.mp4", b"\0\0\0\x18ftypisom")
            with path.open("ab") as stream:
                stream.truncate(5 * 1024 * 1024)
            self.git("add", "--", path.name)
        # A worktree edit adds a second version, which must not double-count.
        with (self.repo / "asset0.mp4").open("r+b") as stream:
            stream.seek(12)
            stream.write(b"changed")
        _, report, _ = self.scan()
        self.assertEqual(report["summary"]["total_bytes"], 25 * 1024 * 1024)
        self.assertIn("added-files-total-size-review", {w["code"] for w in report["warnings"]})

    def test_reports_redact_content_and_do_not_modify_index_or_files(self):
        payload = b"private-file-content-must-not-appear"
        path = self.write("asset.mp4", b"\0\0\0\x18ftypisom" + payload)
        self.git("add", "--", "asset.mp4")
        before = ((self.repo / ".git/index").read_bytes(), path.read_bytes(),
                  self.git("status", "--porcelain=v1", "-z"))
        _, _, output = self.scan()
        self.assertNotIn(payload.decode(), output)
        self.assertEqual(before, ((self.repo / ".git/index").read_bytes(), path.read_bytes(),
                                 self.git("status", "--porcelain=v1", "-z")))

    def test_removing_signature_detection_breaks_disguised_media_detection(self):
        head = b"\0\0\0\x18ftypisom"
        working = file_types.classify("hidden.txt", "index", head, len(head), "100644", True, "full-file-read")
        original = file_types.signature
        try:
            file_types.signature = lambda head, declared: None
            broken = file_types.classify("hidden.txt", "index", head, len(head), "100644", True, "full-file-read")
        finally:
            file_types.signature = original
        self.assertEqual(working["category"], "media_container")
        self.assertNotEqual(working["category"], broken["category"])


if __name__ == "__main__":
    unittest.main()
