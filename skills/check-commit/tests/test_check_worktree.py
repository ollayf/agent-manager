"""Integration coverage using fresh repositories, synthetic secrets, and no commits."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SKILL = Path(__file__).resolve().parents[1]
SCRIPT = SKILL / "scripts/check_worktree.py"
sys.path.insert(0, str(SKILL / "scripts"))
spec = importlib.util.spec_from_file_location("checker", SCRIPT)
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


class WorktreeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="check-commit-test-")
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        self.git("init", "-q")

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.repo), *args],
                              check=True, capture_output=True).stdout

    def write(self, name, content):
        path = self.repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content)
        return path

    def scan(self):
        result = subprocess.run([sys.executable, str(SCRIPT), "--repo", str(self.repo), "--json"],
                                capture_output=True, text=True)
        return result.returncode, json.loads(result.stdout), result.stdout + result.stderr

    def assert_code(self, code, report):
        self.assertIn(code, {f["code"] for f in report["findings"]})

    def test_safe_untracked_change_passes_only_automated_checks(self):
        self.write("hello.py", "print('hello')\n")
        exit_code, report, _ = self.scan()
        self.assertEqual(exit_code, 0)
        self.assertEqual(report["status"], "AUTOMATED_PASS")
        self.assertIn("Tests and human", " ".join(report["limitations"]))

    def test_empty_repository_has_nothing_to_commit(self):
        exit_code, report, _ = self.scan()
        self.assertEqual(exit_code, 2)
        self.assert_code("nothing-to-commit", report)

    def test_staged_secret_is_found_even_when_working_copy_is_cleaned(self):
        secret = "sk-proj-" + "A9b8C7d6" * 6
        self.write("config.py", f'api_key = "{secret}"\n')
        self.git("add", "--", "config.py")
        self.write("config.py", 'api_key = "placeholder"\n')
        exit_code, report, output = self.scan()
        self.assertEqual(exit_code, 1)
        self.assert_code("api-token", report)
        self.assert_code("staged-worktree-versions-differ", report)
        self.assertNotIn(secret, output)
        self.assertTrue(any(f.get("source") == "index" for f in report["findings"]))

    def test_unstaged_secret_is_scanned(self):
        self.write("settings.py", "value = 1\n")
        self.git("add", "--", "settings.py")
        self.write("settings.py", 'password = "live-production-credential"\n')
        _, report, _ = self.scan()
        self.assert_code("credential-assignment", report)
        self.assertTrue(any(f.get("source") == "worktree" for f in report["findings"]))

    def test_deleting_working_file_does_not_hide_staged_secret(self):
        path = self.write("key.py", 'token = "production-credential-123"\n')
        self.git("add", "--", "key.py")
        path.unlink()
        exit_code, report, _ = self.scan()
        self.assertEqual(exit_code, 1)
        self.assert_code("credential-assignment", report)

    def test_ignored_environment_file_is_outside_pending_commit(self):
        self.write(".gitignore", ".env\n")
        self.write(".env", 'api_key = "not-for-the-repository"\n')
        exit_code, report, _ = self.scan()
        self.assertEqual(exit_code, 0)
        self.assertNotIn(".env", report["scope"]["untracked"])

    def test_force_added_ignored_environment_file_blocks(self):
        self.write(".gitignore", ".env\n")
        self.write(".env", "SAFE_LOOKING=value\n")
        self.git("add", "-f", "--", ".env")
        _, report, _ = self.scan()
        self.assert_code("sensitive-file", report)

    def test_template_name_is_not_an_exemption_for_real_secrets(self):
        self.write(".env.example", 'api_key = "sk-' + "Ab12" * 10 + '"\n')
        _, report, _ = self.scan()
        self.assert_code("api-token", report)

    def test_explicit_template_placeholder_passes(self):
        self.write(".env.example", 'API_KEY="your_api_key_here"\n')
        self.assertEqual(self.scan()[0], 0)

    def test_private_key_header_blocks(self):
        self.write("fixture.txt", "-----BEGIN RSA PRIVATE KEY-----\n")
        _, report, _ = self.scan()
        self.assert_code("private-key", report)

    def test_vendor_tokens_are_redacted(self):
        tokens = ["AKIA" + "Z" * 16, "ghp_" + "z" * 36,
                  "github_pat_" + "z" * 40, "xoxb-" + "1234567890-" * 4,
                  "sk-ant-" + "Ab12" * 12]
        for token in tokens:
            with self.subTest(prefix=token[:4]):
                self.write("tokens.txt", token + "\n")
                exit_code, _, output = self.scan()
                self.assertEqual(exit_code, 1)
                self.assertNotIn(token, output)

    def test_authenticated_url_is_redacted(self):
        url = "https://operator:real-secret-value@example.invalid/resource"
        self.write("config.txt", url + "\n")
        _, report, output = self.scan()
        self.assert_code("authenticated-url", report)
        self.assertNotIn(url, output)

    def test_unquoted_yaml_credential_is_redacted(self):
        secret = "productionCredential123456"
        self.write("settings.yaml", "api_key: " + secret + "\n")
        _, report, output = self.scan()
        self.assert_code("unquoted-credential-assignment", report)
        self.assertNotIn(secret, output)

    def test_oversized_sensitive_file_still_blocks(self):
        self.write(".env", b"a" * (checker.MAX_BYTES + 1))
        exit_code, report, _ = self.scan()
        self.assertEqual(exit_code, 1)
        self.assert_code("sensitive-file", report)
        self.assert_code("oversized-not-scanned", report)

    def test_inventory_change_during_scan_requires_review(self):
        self.write("code.py", "value = 1\n")
        original = checker.inventory
        calls = []

        def changing_inventory(repo):
            result = original(repo)
            calls.append(1)
            if len(calls) == 2:
                result["untracked"].append("new-file.py")
            return result

        try:
            checker.inventory = changing_inventory
            report = checker.check(self.repo)
        finally:
            checker.inventory = original
        self.assertEqual(report["status"], "NEEDS_REVIEW")
        self.assert_code("worktree-changed-during-check", report)

    def test_conflict_marker_blocks_with_line_number(self):
        self.write("code.py", "line\n<<<<<<< branch\nvalue\n=======\nother\n>>>>>>> main\n")
        _, report, _ = self.scan()
        self.assert_code("conflict-marker", report)
        self.assertTrue(any(f.get("line") == 2 for f in report["findings"]))

    def test_unmerged_index_is_a_blocker(self):
        oid = self.git("hash-object", "-w", "--stdin")  # empty synthetic blob
        payload = b"100644 " + oid.strip() + b" 1\tconflict.txt\n"
        subprocess.run(["git", "-C", str(self.repo), "update-index", "--index-info"],
                       input=payload, check=True, capture_output=True)
        _, report, _ = self.scan()
        self.assert_code("unmerged-index", report)

    def test_unfinished_operation_blocks_even_without_conflict_markers(self):
        self.write("hello.py", "value = 1\n")
        self.write(".git/MERGE_HEAD", "0" * 40 + "\n")
        _, report, _ = self.scan()
        self.assert_code("unfinished-git-operation", report)

    def test_new_file_whitespace_is_checked(self):
        self.write("hello.py", "value = 1 \n")
        _, report, _ = self.scan()
        self.assert_code("trailing-whitespace", report)

    def test_staged_whitespace_check_does_not_print_source(self):
        self.write("hello.py", "private_content_do_not_print \n")
        self.git("add", "--", "hello.py")
        _, report, output = self.scan()
        self.assert_code("diff-check-failed", report)
        self.assertNotIn("private_content_do_not_print", output)

    def test_binary_is_incomplete_instead_of_clean(self):
        self.write("asset.bin", b"\x00\x01\x02")
        exit_code, report, _ = self.scan()
        self.assertEqual(exit_code, 2)
        self.assert_code("binary-not-scanned", report)

    def test_oversized_file_is_incomplete(self):
        self.write("large.txt", b"a" * (checker.MAX_BYTES + 1))
        exit_code, report, _ = self.scan()
        self.assertEqual(exit_code, 2)
        self.assert_code("oversized-not-scanned", report)

    def test_oversized_index_blob_is_incomplete(self):
        self.write("large.txt", b"a" * (checker.MAX_BYTES + 1))
        self.git("add", "--", "large.txt")
        _, report, _ = self.scan()
        self.assert_code("oversized-not-scanned", report)

    def test_non_utf8_is_incomplete(self):
        self.write("text.txt", b"\xff\xfeABC")
        _, report, _ = self.scan()
        self.assert_code("encoding-not-scanned", report)

    def test_generated_artifact_requires_review(self):
        self.write("dist/app.js", "console.log('hello');\n")
        _, report, _ = self.scan()
        self.assert_code("generated-or-private-artifact", report)

    def test_symlink_target_is_not_read(self):
        outside = self.repo.parent / (self.repo.name + "-outside")
        outside.write_text('password = "sensitive-outside-repo"\n')
        self.addCleanup(outside.unlink)
        (self.repo / "linked.txt").symlink_to(outside)
        exit_code, report, output = self.scan()
        self.assertEqual(exit_code, 2)
        self.assert_code("symlink-review", report)
        self.assertNotIn("credential-assignment", output)

    def test_index_symlink_requires_review(self):
        (self.repo / "alias").symlink_to("README.md")
        self.git("add", "--", "alias")
        _, report, _ = self.scan()
        self.assert_code("symlink-review", report)

    def test_deleted_paths_under_replaced_directory_are_not_read_through_symlink(self):
        path = self.write("old/code.py", "value = 1\n")
        self.git("add", "--", "old/code.py")
        path.unlink()
        path.parent.rmdir()
        target = self.repo / "replacement"
        target.mkdir()
        self.write("replacement/code.py", "value = 2\n")
        (self.repo / "old").symlink_to("replacement", target_is_directory=True)
        _, report, _ = self.scan()
        self.assertNotIn("symlink-parent-not-scanned", {f["code"] for f in report["findings"]})
        self.assertIn("old/code.py", report["scope"]["unstaged"])

    def test_submodule_content_is_not_claimed_scanned(self):
        # An arbitrary object id is sufficient to represent a synthetic gitlink.
        self.git("update-index", "--add", "--cacheinfo", "160000," + "1" * 40 + ",sub")
        _, report, _ = self.scan()
        self.assert_code("submodule-not-scanned", report)

    def test_spaces_newlines_and_leading_dash_paths_are_safe(self):
        for name in ["file with spaces.py", "-odd.py", "line\nbreak.py"]:
            self.write(name, "value = 1\n")
            self.git("add", "--", name)
        exit_code, report, output = self.scan()
        self.assertEqual(exit_code, 2)
        self.assertEqual(len(report["scope"]["staged"]), 3)
        self.assertIn("line\\nbreak.py", output)
        self.assert_code("unusual-filename-review", report)

    def test_scan_does_not_change_files_or_index(self):
        self.write("code.py", "value = 1\n")
        self.git("add", "--", "code.py")
        before = (self.git("status", "--porcelain=v1", "-z"),
                  (self.repo / ".git/index").read_bytes(), (self.repo / "code.py").read_bytes())
        self.scan()
        after = (self.git("status", "--porcelain=v1", "-z"),
                 (self.repo / ".git/index").read_bytes(), (self.repo / "code.py").read_bytes())
        self.assertEqual(before, after)

    def test_nonrepository_returns_incomplete_without_traceback(self):
        with tempfile.TemporaryDirectory() as outside:
            result = subprocess.run([sys.executable, str(SCRIPT), "--repo", outside, "--json"],
                                    capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout)["status"], "NEEDS_REVIEW")
        self.assertNotIn("Traceback", result.stderr)

    def test_tests_detect_disabled_secret_scanner(self):
        # Mutation guard: removing the feature changes the result to a false pass.
        self.write("fixture.txt", "ghp_" + "Z" * 36 + "\n")
        original = checker.PATTERNS
        try:
            checker.PATTERNS = {}
            broken = checker.check(self.repo)
        finally:
            checker.PATTERNS = original
        working = checker.check(self.repo)
        self.assertEqual(broken["status"], "AUTOMATED_PASS")
        self.assertEqual(working["status"], "BLOCKED")


if __name__ == "__main__":
    unittest.main()
