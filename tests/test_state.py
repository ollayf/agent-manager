"""agent-state export/import round trip between two fake home folders; never touches the real ~."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
TOOL = REPO / "bin/agent-state"
# Built at runtime so this file never contains a token shape the commit guard would flag.
GH_TOKEN = "gh" + "p_" + "Q7" * 15
OWN_VALUE = "own-secret-" + "z9" * 8
SESSION = "11111111-2222-3333-4444-555555555555"


def slug(path):
    return re.sub(r"[^A-Za-z0-9]", "-", str(path))


def jsonl(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in records))


class StateTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(os.path.realpath(tmp.name))
        self.old = self.tmp / "Users/alice"
        self.new = self.tmp / "Users/bob"
        self.out = self.tmp / "exports"
        self.secrets = self.tmp / "secrets.env"
        self.secrets.write_text(f"MY_TOKEN={OWN_VALUE}\nEMPTY=\n")

        app = self.old / "code/app"
        (app).mkdir(parents=True)
        (app / "CLAUDE.local.md").write_text("private project notes\n")
        project = self.old / ".claude/projects" / slug(app)
        jsonl(project / f"{SESSION}.jsonl", [
            {"type": "user", "cwd": str(app), "sessionId": SESSION, "timestamp": "2026-01-01T00:00:00Z",
             "message": {"content": f"token {GH_TOKEN} and {OWN_VALUE} in {app}/main.py"}},
            {"type": "assistant", "cwd": str(app), "sessionId": SESSION, "message": {"content": [
                {"type": "tool_use", "name": "Read", "input": {"file_path": f"{app}/main.py"}},
                {"type": "text", "text": f"cd {app} && ls"}]}},
        ])
        jsonl(project / SESSION / "subagents/agent-a.jsonl", [{"cwd": str(app), "type": "user"}])
        (project / "memory").mkdir()
        (project / "memory/MEMORY.md").write_text("- [Style](style.md) — prefers short answers\n")
        (project / "memory/style.md").write_text("Prefers short answers.\n")
        gone = self.old / ".claude/projects" / (slug(self.old) + "-old-thing")
        (gone / "memory").mkdir(parents=True)
        (gone / "memory/MEMORY.md").write_text("- old project memory\n")
        jsonl(self.old / ".claude/history.jsonl", [
            {"display": "hello", "timestamp": 200, "project": str(app), "sessionId": SESSION}])
        (self.old / ".claude/file-history" / SESSION).mkdir(parents=True)
        (self.old / ".claude/file-history" / SESSION / "abc@v1").write_text("old file body\n")
        (self.old / ".claude/settings.json").write_text('{"marker": "MUST-NOT-EXPORT"}')
        jsonl(self.old / ".codex/sessions/2026/01/02/rollout-2026-01-02T10-00-00-cdx1.jsonl", [
            {"type": "session_meta", "payload": {"id": "cdx1", "cwd": str(app)}},
            {"type": "turn_context", "payload": {"cwd": str(app), "workspace_roots": [str(app)],
                                                 "file_system_sandbox_policy": {"entries": [{"path": {"path": str(app)}}]}}},
            {"type": "event_msg", "payload": {"thread_settings": {"cwd": str(app), "runtime_workspace_roots": [str(app)]},
                                              "message": f"ran tests in {app}"}},
            {"type": "event_msg", "payload": {"note": str(self.old) + "xyz/notes"}}])
        jsonl(self.old / ".codex/history.jsonl", [{"session_id": "cdx1", "ts": 5, "text": "hi"}])
        (self.old / ".codex/auth.json").write_text('{"marker": "MUST-NOT-EXPORT"}')
        (self.new / "code/app").mkdir(parents=True)

    def run_tool(self, home, *args, ok=True, codex_stopped=False):
        env = dict(os.environ, HOME=str(home), AGENT_SECRETS_FILE=str(self.secrets))
        if codex_stopped:  # a real Codex may be running here; the tool must not see it
            fake = self.tmp / "fakebin"
            fake.mkdir(exist_ok=True)
            (fake / "pgrep").write_text("#!/bin/sh\nexit 1\n")
            (fake / "pgrep").chmod(0o755)
            env["PATH"] = f"{fake}:{env['PATH']}"
        env.pop("CODEX_HOME", None)
        r = subprocess.run([str(TOOL), *args], env=env, capture_output=True, text=True)
        if ok:
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r

    def export(self):
        self.run_tool(self.old, "export", "--out", str(self.out))
        (bundle,) = self.out.iterdir()
        return bundle

    def test_round_trip_to_another_username(self):
        bundle = self.export()
        names = {p.name for p in (bundle / "projects").iterdir()}
        self.assertIn("code__app", names)
        self.assertTrue(any(n.startswith("_unresolved__") for n in names))
        text = "".join(p.read_text(errors="ignore") for p in bundle.rglob("*") if p.is_file())
        self.assertNotIn(GH_TOKEN, text)
        self.assertNotIn(OWN_VALUE, text)
        self.assertNotIn("MUST-NOT-EXPORT", text)
        report = (bundle / "SECRETS-REPORT.txt").read_text()
        self.assertIn("GitHub token", report)
        self.assertIn("secrets.env MY_TOKEN", report)

        preview = self.run_tool(self.new, "import", str(bundle))
        self.assertIn("preview only", preview.stdout)
        self.assertIn(" 0 waiting", preview.stdout)  # ~/.claude need not exist yet
        self.assertNotIn("claude-account add main", preview.stdout)
        self.assertFalse((self.new / ".claude").exists())

        self.run_tool(self.new, "import", str(bundle), "--apply")
        app = self.new / "code/app"
        session = self.new / ".claude/projects" / slug(app) / f"{SESSION}.jsonl"
        records = [json.loads(l) for l in session.read_text().splitlines()]
        self.assertEqual(records[0]["cwd"], str(app))
        self.assertIn(str(self.old / "code/app") + "/main.py", records[0]["message"]["content"])
        self.assertIn("[REDACTED:GitHub token]", records[0]["message"]["content"])
        self.assertTrue((self.new / ".claude/projects" / slug(app) / SESSION / "subagents/agent-a.jsonl").exists())
        self.assertEqual((self.new / ".claude/projects" / slug(app) / "memory/style.md").read_text(),
                         "Prefers short answers.\n")
        self.assertTrue((self.new / ".claude/projects" / (slug(self.new) + "-old-thing") / "memory/MEMORY.md").exists())
        self.assertEqual((app / "CLAUDE.local.md").read_text(), "private project notes\n")
        tool, prose = records[1]["message"]["content"]
        self.assertEqual(tool["input"]["file_path"], f"{app}/main.py")
        self.assertEqual(prose["text"], f"cd {self.old / 'code/app'} && ls")  # prose keeps its words
        rollout = self.new / ".codex/sessions/2026/01/02/rollout-2026-01-02T10-00-00-cdx1.jsonl"
        meta, turn, settings, other = [json.loads(l) for l in rollout.read_text().splitlines()]
        self.assertEqual(meta["payload"]["cwd"], str(app))
        self.assertEqual(turn["payload"]["workspace_roots"], [str(app)])
        self.assertEqual(turn["payload"]["file_system_sandbox_policy"]["entries"][0]["path"]["path"], str(app))
        self.assertEqual(settings["payload"]["thread_settings"],
                         {"cwd": str(app), "runtime_workspace_roots": [str(app)]})
        self.assertEqual(settings["payload"]["message"], f"ran tests in {self.old / 'code/app'}")
        self.assertEqual(other["payload"]["note"], str(self.old) + "xyz/notes")  # lookalike prefix stays
        self.assertNotIn(str(self.old) + "/", "".join(
            json.dumps(r["payload"].get("thread_settings", {})) for r in (meta, turn, settings)))
        hist = json.loads((self.new / ".claude/history.jsonl").read_text())
        self.assertEqual(hist["project"], str(app))
        self.assertFalse((self.new / ".claude/settings.json").exists())
        self.assertFalse((self.new / ".codex/auth.json").exists())

        again = self.run_tool(self.new, "import", str(bundle), "--apply")
        self.assertIn(" 0 new", again.stdout)

    def test_existing_files_are_kept_and_history_is_merged(self):
        bundle = self.export()
        app = self.new / "code/app"
        mine = self.new / ".claude/projects" / slug(app) / "memory/style.md"
        mine.parent.mkdir(parents=True)
        mine.write_text("New machine wins.\n")
        jsonl(self.new / ".claude/history.jsonl", [
            {"display": "later", "timestamp": 300, "project": str(app)},
            {"display": "earlier", "timestamp": 100, "project": str(app)}])
        r = self.run_tool(self.new, "import", str(bundle), "--apply")
        self.assertIn("kept existing (differs)", r.stdout)
        self.assertEqual(mine.read_text(), "New machine wins.\n")
        order = [json.loads(l)["display"] for l in (self.new / ".claude/history.jsonl").read_text().splitlines()]
        self.assertEqual(order, ["earlier", "hello", "later"])
        backups = list((self.new / ".local/share/agent-manager/backups").rglob("history.jsonl"))
        self.assertEqual(len(backups), 1)

    def test_codex_index_warning_and_explicit_map(self):
        bundle = self.export()
        (self.new / ".codex").mkdir()
        (self.new / ".codex/state_5.sqlite").write_text("")
        target = self.new / "work/app"
        target.mkdir(parents=True)
        r = self.run_tool(self.new, "import", str(bundle), "--apply",
                          "--map", f"{self.old}/code={self.new}/work")
        self.assertIn("will not list the imported sessions", r.stdout)
        self.assertTrue((self.new / ".codex/state_5.sqlite").exists())
        self.assertTrue((self.new / ".claude/projects" / slug(target) / f"{SESSION}.jsonl").exists())
        self.assertTrue((target / "CLAUDE.local.md").exists())

    def test_verify_detects_changes_and_import_refuses(self):
        bundle = self.export()
        self.run_tool(self.old, "verify", str(bundle))
        mem = next(bundle.rglob("style.md"))
        mem.write_text("tampered\n")
        self.assertNotEqual(self.run_tool(self.old, "verify", str(bundle), ok=False).returncode, 0)
        self.assertNotEqual(self.run_tool(self.new, "import", str(bundle), "--apply", ok=False).returncode, 0)
        self.assertFalse((self.new / ".claude").exists())

    def test_scanner_ignores_base64_and_names_but_catches_escaped_lines(self):
        import importlib.machinery
        import importlib.util
        import sys
        sys.dont_write_bytecode = True  # no bin/__pycache__: doctor treats bin/* as commands
        loader = importlib.machinery.SourceFileLoader("agent_state", str(TOOL))
        spec = importlib.util.spec_from_loader("agent_state", loader)
        mod = importlib.util.module_from_spec(spec)
        loader.exec_module(mod)
        with mock.patch.dict(os.environ, {"AGENT_SECRETS_FILE": str(self.secrets)}):
            scanner = mod.Scanner()
        google = ("AI" + "za" + "B" * 35).encode()
        labels = lambda line: [label for _, _, label in scanner.spans(line)]
        self.assertEqual(labels(b'"data":"iVBOR/x' + google + b'+QQ"'), [])
        self.assertEqual(labels(b"task-" + b"a" * 40), [])
        self.assertEqual(labels(b'"text":"key:\\n' + google + b'\\n"'), ["Google API key"])
        self.assertEqual(labels(GH_TOKEN.encode()), ["GitHub token"])

    def tamper(self, bundle, edit):
        """Edit MANIFEST.json the way an attacker would: checksums recomputed to match."""
        path = bundle / "MANIFEST.json"
        manifest = json.loads(path.read_text())
        edit(manifest)
        if isinstance(manifest["files"], dict):
            for rel, meta in manifest["files"].items():
                f = bundle / rel
                if f.is_file():
                    meta["sha256"] = hashlib.sha256(f.read_bytes()).hexdigest()
        path.write_text(json.dumps(manifest))

    def test_tampered_manifest_is_refused_before_anything_is_written(self):
        def add(rel):
            def edit(m):
                m["files"][rel] = {"sha256": "", "size": 0}
            return edit

        def project(field, value):
            def edit(m):
                next(p for p in m["projects"] if p["name"] == "code__app")[field] = value
            return edit

        cases = {
            "dot-dot in a global path": add("global/claude/main/../planted.txt"),
            "dot-dot in a session path": add("projects/code__app/claude/sessions/../../../planted.txt"),
            "absolute path": add("/tmp/planted.txt"),
            "unexpected local file": add("projects/code__app/files/evil.sh"),
            "unexpected codex folder": add("projects/code__app/codex/config.toml"),
            "unexpected top-level folder": add("Library/LaunchAgents/x.plist"),
            "bad profile name": add("global/claude/../history.jsonl"),
            "slug that climbs": project("claude_slug", "../../planted"),
            "project name that climbs": project("name", ".."),
            "relative original path": project("original_path", "code/app"),
            "bare global entry": add("global"),
            "bare codex entry": add("global/codex"),
            "files table is a list": lambda m: m.update(files=list(m["files"])),
            "project entry is not an object": lambda m: m["projects"].append("x"),
        }
        for label, edit in cases.items():
            with self.subTest(label):
                bundle = self.export()
                for parent in ("global/claude/main", "global/claude"):
                    (bundle / parent).mkdir(parents=True, exist_ok=True)
                (bundle / "global/claude/planted.txt").write_text("planted\n")
                (bundle / "projects/code__app/files/evil.sh").write_text("planted\n")
                self.tamper(bundle, edit)
                r = self.run_tool(self.new, "import", str(bundle), "--apply", ok=False)
                self.assertNotEqual(r.returncode, 0, label)
                self.assertIn("refusing this bundle", r.stderr)
                self.assertFalse((self.new / ".claude").exists(), label)
                self.assertEqual(list(self.new.rglob("planted*")), [], label)
                self.assertNotIn("Traceback", r.stderr, label)
                self.assertNotEqual(self.run_tool(self.new, "verify", str(bundle), ok=False).returncode, 0)
                for child in sorted(self.out.iterdir()):
                    subprocess.run(["rm", "-rf", str(child)], check=True)

    def test_symlink_inside_bundle_fails_verification(self):
        bundle = self.export()
        mem = next(bundle.rglob("style.md"))
        outside = self.tmp / "outside.md"
        outside.write_bytes(mem.read_bytes())
        mem.unlink()
        mem.symlink_to(outside)
        r = self.run_tool(self.new, "verify", str(bundle), ok=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("link", r.stdout)

    def test_symlinked_destination_is_refused(self):
        bundle = self.export()
        elsewhere = self.tmp / "elsewhere"
        elsewhere.mkdir()
        target = self.new / ".claude/projects" / slug(self.new / "code/app")
        target.mkdir(parents=True)
        (target / "memory").symlink_to(elsewhere)
        r = self.run_tool(self.new, "import", str(bundle), "--apply")
        self.assertIn("refused (would land outside", r.stdout)
        self.assertEqual(list(elsewhere.iterdir()), [])
        self.assertTrue((target / f"{SESSION}.jsonl").exists())

    def test_reindex_works_on_a_follow_up_run(self):
        bundle = self.export()
        (self.new / ".codex").mkdir()
        (self.new / ".codex/state_5.sqlite").write_text("")
        first = self.run_tool(self.new, "import", str(bundle), "--apply")
        self.assertIn("--reindex-codex", first.stdout)
        self.assertTrue((self.new / ".codex/state_5.sqlite").exists())
        second = self.run_tool(self.new, "import", str(bundle), "--apply", "--reindex-codex",
                               codex_stopped=True)
        self.assertIn("index moved", second.stdout)
        self.assertFalse((self.new / ".codex/state_5.sqlite").exists())
        moved = list((self.new / ".local/share/agent-manager/backups").rglob("state_5.sqlite"))
        self.assertEqual(len(moved), 1)
        (self.new / ".codex/state_5.sqlite").write_text("")
        preview = self.run_tool(self.new, "import", str(bundle), "--reindex-codex", codex_stopped=True)
        self.assertNotIn("index moved", preview.stdout)
        self.assertTrue((self.new / ".codex/state_5.sqlite").exists())

    def test_reindex_refuses_while_codex_runs(self):
        bundle = self.export()
        (self.new / ".codex").mkdir()
        (self.new / ".codex/state_5.sqlite").write_text("")
        fake = self.tmp / "busybin"
        fake.mkdir()
        (fake / "pgrep").write_text("#!/bin/sh\nexit 0\n")
        (fake / "pgrep").chmod(0o755)
        env = dict(os.environ, HOME=str(self.new), AGENT_SECRETS_FILE=str(self.secrets),
                   PATH=f"{fake}:{os.environ['PATH']}")
        env.pop("CODEX_HOME", None)
        r = subprocess.run([str(TOOL), "import", str(bundle), "--apply", "--reindex-codex"],
                           env=env, capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("quit Codex", r.stderr)
        self.assertTrue((self.new / ".codex/state_5.sqlite").exists())
        self.assertFalse((self.new / ".claude").exists())  # refused before copying anything

    def test_export_refuses_to_write_inside_agent_folders(self):
        r = self.run_tool(self.old, "export", "--out", str(self.old / ".claude/x"), ok=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("refusing", r.stderr)


if __name__ == "__main__":
    unittest.main()
