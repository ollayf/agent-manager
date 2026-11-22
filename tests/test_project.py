"""Offline regressions for installed commands and shared project files."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]


class ProjectTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.project = self.base / 'project with spaces'
        self.project.mkdir()
        self.env = dict(os.environ, XDG_CONFIG_HOME=str(self.base / 'config'),
                        XDG_DATA_HOME=str(self.base / 'data'))

    def run_cli(self, name, *args, installed=False):
        executable = REPO / 'bin' / name
        if installed:
            bindir = self.base / 'bin'
            bindir.mkdir(exist_ok=True)
            executable = bindir / name
            if not executable.exists():
                executable.symlink_to(REPO / 'bin' / name)
        return subprocess.run([str(executable), *map(str, args)], env=self.env,
                              capture_output=True, text=True)

    def init(self, *args):
        return self.run_cli('agent-manager', 'project', 'init', self.project, *args)

    def test_installed_entrypoints_resolve_their_checkout(self):
        for name in ('agent-manager', 'agent-skills', 'agent-mcp', 'claude-manager',
                     'claude-skills', 'claude-account', 'claude-plugins'):
            result = self.run_cli(name, '--help', installed=True)
            self.assertEqual(result.returncode, 0, (name, result.stderr))

    def test_claude_only_keeps_skills_and_instructions(self):
        source = self.project / '.claude/skills/existing'
        source.mkdir(parents=True)
        (source / 'SKILL.md').write_text('existing')
        (self.project / 'CLAUDE.md').write_text('Important project rules')
        result = self.init()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse((self.project / '.claude/skills').is_symlink())
        self.assertTrue((self.project / '.agents/skills').samefile(source.parent))
        (self.project / 'AGENTS.md').write_text('Edited in Codex')
        self.assertEqual((self.project / 'CLAUDE.md').read_text(), 'Edited in Codex')
        self.assertEqual(self.init().returncode, 0)
        result = self.run_cli('agent-skills', 'create', 'project-regression-fixture',
                              '--scope', 'project', '--project', self.project)
        self.assertEqual(result.returncode, 0, result.stderr)
        skill = self.project / '.claude/skills/project-regression-fixture/SKILL.md'
        self.assertTrue(skill.samefile(self.project / '.agents/skills/project-regression-fixture/SKILL.md'))

    def test_codex_only_and_new_project_share_future_edits(self):
        (self.project / 'AGENTS.md').write_text('Codex project rules')
        self.assertEqual(self.init().returncode, 0)
        self.assertTrue((self.project / 'CLAUDE.md').samefile(self.project / 'AGENTS.md'))
        skill = self.project / '.claude/skills/from-claude'
        skill.mkdir()
        (skill / 'SKILL.md').write_text('New Claude skill')
        self.assertEqual((self.project / '.agents/skills/from-claude/SKILL.md').read_text(), 'New Claude skill')

    def test_conflicting_instructions_do_not_change_project(self):
        (self.project / 'AGENTS.md').write_text('First rule')
        (self.project / 'CLAUDE.md').write_text('Different rule')
        self.assertNotEqual(self.init().returncode, 0)
        self.assertFalse((self.project / '.agents').exists())
        self.assertEqual((self.project / 'CLAUDE.md').read_text(), 'Different rule')

    def test_dry_run_leaves_no_files(self):
        self.assertEqual(self.init('--dry-run').returncode, 0)
        self.assertEqual(list(self.project.iterdir()), [])

    def test_invalid_skill_root_is_preserved(self):
        (self.project / '.agents').mkdir()
        source = self.project / '.agents/skills'
        source.write_text('This is a file, not a directory')
        result = self.run_cli('agent-skills', 'create', 'project-regression-fixture',
                              '--scope', 'project', '--project', self.project)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(source.read_text(), 'This is a file, not a directory')
        self.assertNotEqual(self.init().returncode, 0)

    def test_init_does_not_migrate_an_external_skill_tree(self):
        external = self.base / 'external'
        external.mkdir()
        (external / 'precious.txt').write_text('preserve')
        (self.project / '.claude').mkdir()
        (self.project / '.claude/skills').symlink_to(external)
        self.assertNotEqual(self.init().returncode, 0)
        self.assertEqual((external / 'precious.txt').read_text(), 'preserve')
        self.assertFalse((self.project / '.agents').exists())

    def test_conflicting_skills_are_preserved(self):
        for source, value in (('.claude', 'Claude version'), ('.agents', 'Codex version')):
            path = self.project / source / 'skills/collision'
            path.mkdir(parents=True)
            (path / 'SKILL.md').write_text(value)
        self.assertNotEqual(self.init().returncode, 0)
        self.assertEqual((self.project / '.claude/skills/collision/SKILL.md').read_text(), 'Claude version')
        self.assertEqual((self.project / '.agents/skills/collision/SKILL.md').read_text(), 'Codex version')

    def test_identical_instructions_share_one_source_with_backup(self):
        for name in ('AGENTS.md', 'CLAUDE.md'):
            (self.project / name).write_text('Same instructions')
        self.assertEqual(self.init().returncode, 0)
        self.assertTrue((self.project / 'CLAUDE.md').is_symlink())
        backups = list((self.base / 'data').rglob('CLAUDE.md'))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(), 'Same instructions')


if __name__ == '__main__':
    unittest.main()
