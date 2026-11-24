"""lib/tracked_links.py: which tracked symlinks survive a clone on another machine."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
HELPER = REPO / "lib/tracked_links.py"


class TrackedLinksTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.repo = Path(tmp.name) / "repo"
        self.repo.mkdir()
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        (self.repo / ".gitignore").write_text("secrets.env\n")
        (self.repo / "secrets.env").write_text("local only\n")
        (self.repo / "config/history/1.0").mkdir(parents=True)
        (self.repo / "config/history/1.0/SKILL.md").write_text("frozen\n")
        (self.repo / "skills/demo").mkdir(parents=True)
        (self.repo / "notes.txt").write_text("tracked\n")

    def link(self, name, target):
        path = self.repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        os.symlink(target, path)
        return name

    def broken(self, *pathspecs):
        subprocess.run(["git", "-C", str(self.repo), "add", "-A"], check=True)
        r = subprocess.run([sys.executable, str(HELPER), str(self.repo), *pathspecs],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        return sorted(r.stdout.split())

    def test_relative_links_to_tracked_content_pass(self):
        self.link("skills/demo/.history", "../../config/history")
        self.link("skills/demo/notes", "../../notes.txt")
        self.assertEqual(self.broken(), [])

    def test_links_that_break_in_a_clone_are_listed(self):
        good = self.link("skills/demo/.history", "../../config/history")
        bad = [
            self.link("skills/demo/absolute", str(self.repo / "notes.txt")),
            self.link("skills/demo/escapes", "../../../outside"),
            self.link("skills/demo/secret", "../../secrets.env"),
            self.link("skills/demo/dangling", "../../missing.txt"),
        ]
        found = self.broken()
        self.assertNotIn(good, found)
        self.assertEqual(found, sorted(bad))

    def test_pathspec_limits_the_check(self):
        self.link("elsewhere/absolute", "/etc/hosts")
        self.assertEqual(self.broken("skills/"), [])
        self.assertEqual(self.broken(), ["elsewhere/absolute"])

    @unittest.skipUnless((REPO / ".git").exists(), "not a git checkout (e.g. an exported snapshot)")
    def test_this_repository_has_no_breaking_links(self):
        r = subprocess.run([sys.executable, str(HELPER), str(REPO)], capture_output=True, text=True)
        self.assertEqual((r.returncode, r.stdout), (0, ""), r.stderr)


if __name__ == "__main__":
    unittest.main()
