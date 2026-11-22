"""Offline conversion fixtures; never uses real accounts, media or paid APIs."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SKILL = Path(__file__).resolve().parents[1]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


adapter = module('adapter', SKILL / 'assets/sync_agent_config.py')
importer = module('importer', SKILL / 'scripts/import_codex.py')


class ConversionTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'project with spaces'
        self.root.mkdir()

    def share(self, claude):
        source, link = ('CLAUDE.md', 'AGENTS.md') if claude else ('AGENTS.md', 'CLAUDE.md')
        (self.root / source).write_text('Existing project instructions')
        (self.root / link).symlink_to(source)
        source, link = ('.claude', '.agents') if claude else ('.agents', '.claude')
        (self.root / source / 'skills/existing').mkdir(parents=True)
        (self.root / source / 'skills/existing/SKILL.md').write_text('Existing skill')
        (self.root / link).mkdir(exist_ok=True)
        (self.root / link / 'skills').symlink_to('../%s/skills' % source)

    def sync(self, *args):
        return subprocess.run([sys.executable, str(SKILL / 'assets/sync_agent_config.py'),
                               '--root', str(self.root), *args], capture_output=True, text=True)

    def check_shared(self):
        self.assertEqual(adapter.check_links(self.root), [])
        for source, other in (('.claude', '.agents'), ('.agents', '.claude')):
            skill = self.root / source / ('skills/new-' + source[1:])
            skill.mkdir()
            (skill / 'SKILL.md').write_text('new skill')
            self.assertTrue((skill / 'SKILL.md').samefile(self.root / other / 'skills' / skill.name / 'SKILL.md'))

    @unittest.skipIf(importer.tomllib is None, 'Python 3.11+ or tomli required')
    def test_claude_only_conversion_and_future_settings(self):
        self.share(claude=True)
        (self.root / '.mcp.json').write_text(json.dumps({'mcpServers': {
            'local': {'command': 'python3', 'args': ['server.py']},
            'remote': {'type': 'http', 'url': 'https://example.test/mcp'}}}))
        (self.root / '.claude/settings.json').write_text(json.dumps({'permissions': {
            'deny': ['Bash(rclone sync:*)', 'mcp__local__write']}}))
        self.assertEqual(self.sync().returncode, 0)
        self.assertEqual(self.sync('--check').returncode, 0)
        self.check_shared()
        native = self.root / '.codex/config.toml'
        native.write_text('model = "retained"\n\n' + native.read_text())
        self.assertEqual(self.sync().returncode, 0)
        parsed = importer.tomllib.loads(native.read_text())
        self.assertEqual(parsed['model'], 'retained')
        self.assertEqual(parsed['mcp_servers']['local']['disabled_tools'], ['write'])

    @unittest.skipIf(importer.tomllib is None, 'Python 3.11+ or tomli required')
    def test_codex_only_import_preview_apply_and_refresh(self):
        self.share(claude=False)
        (self.root / '.codex').mkdir()
        native = self.root / '.codex/config.toml'
        original = ('model = "keep-this-model"\n[mcp_servers.local]\ncommand = "python3"\n'
                    'args = ["server.py"]\ndisabled_tools = ["write"]\n'
                    '[mcp_servers.remote]\nurl = "https://example.test/mcp"\n'
                    '[features]\nmulti_agent = false\n')
        native.write_text(original)
        env = dict(os.environ, XDG_DATA_HOME=str(self.root.parent / 'data'))
        command = [sys.executable, str(SKILL / 'scripts/import_codex.py'), str(self.root)]
        preview = subprocess.run(command, env=env, capture_output=True, text=True)
        self.assertEqual(preview.returncode, 0, preview.stderr)
        self.assertEqual(native.read_text(), original)
        self.assertFalse((self.root / '.mcp.json').exists())
        applied = subprocess.run(command + ['--apply'], env=env, capture_output=True, text=True)
        self.assertEqual(applied.returncode, 0, applied.stderr)
        self.assertEqual(self.sync().returncode, 0)
        self.assertEqual(self.sync('--check').returncode, 0)
        self.assertEqual(importer.tomllib.loads(native.read_text()), importer.tomllib.loads(original))
        self.check_shared()
        backups = list((self.root.parent / 'data').rglob('config.toml'))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(), original)

    @unittest.skipIf(importer.tomllib is None, 'Python 3.11+ or tomli required')
    def test_conflicting_native_and_shared_servers_are_preserved(self):
        (self.root / '.codex').mkdir()
        native = self.root / '.codex/config.toml'
        native.write_text('[mcp_servers.local]\ncommand = "first"\n')
        source = self.root / '.mcp.json'
        text = json.dumps({'mcpServers': {'local': {'command': 'second'}}})
        source.write_text(text)
        with self.assertRaisesRegex(ValueError, 'Conflicting'):
            importer.plan(self.root, adapter)
        self.assertEqual(source.read_text(), text)
        self.assertIn('first', native.read_text())

    def test_native_only_restrictions_and_credentials_need_explicit_mapping(self):
        for server in ({'command': 'server', 'enabled_tools': ['read']},
                       {'command': 'server', 'env': {'API_KEY': 'fixture-secret'}},
                       {'url': 'https://example.test/mcp', 'bearer_token_env_var': 'TOKEN'},
                       {'command': 'server', 'tool_timeout_sec': 500}):
            with self.assertRaises(ValueError):
                importer.convert_server('local', server)

    def test_unsupported_shared_policy_produces_no_native_outputs(self):
        self.share(claude=True)
        (self.root / '.mcp.json').write_text('{"mcpServers": {}}')
        (self.root / '.claude/settings.json').write_text('{"permissions": {"ask": ["Bash(*)"]}}')
        self.assertNotEqual(self.sync().returncode, 0)
        self.assertFalse((self.root / '.codex').exists())


if __name__ == '__main__':
    unittest.main()
