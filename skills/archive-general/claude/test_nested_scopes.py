"""Nested archive scopes (3.3): one project, some folders archived to another target.

Each scope keeps its own index bound to exactly one target, so every archived entry
still has one unambiguous location. These tests use disposable local targets only."""
import json
from pathlib import Path

import pytest
from test_support import SKILL
from test_general_storage import GeneralEnv
from test_drive_api import Fixture


@pytest.fixture
def two(tmp_path):
    e = GeneralEnv(tmp_path)                                   # parent target "test" (default)
    e.second = tmp_path / 'ssd'
    e.ok('target', 'add', 'ssd', '--root', e.second, '--kind', 'local')
    return e


def manifest_rows(path):
    rows = {}
    if path.exists():
        for line in path.read_text().splitlines()[1:]:
            row = json.loads(line)
            if row.get('op') == 'add': rows[row['path']] = row
            elif row.get('op') == 'del': rows.pop(row['path'], None)
    return rows


def header(path):
    return json.loads(path.read_text().splitlines()[0])


def test_nested_scope_archives_to_its_own_target_from_the_parent(two):
    e = two
    e.write('notes/keep.txt', 'parent')
    e.ok('sync', 'notes/keep.txt')                              # parent binds to "test"
    e.write('trip/raw/a.mp4', b'A' * 1000); e.write('trip/plan.json', '{}')
    out = e.ok('scope', 'add', 'trip', '--to', 'ssd')
    assert 'nested archive scope on ssd' in out
    out = e.ok('sync', 'trip/raw', 'trip/plan.json')            # run from the parent's folder
    assert 'nested archive scope -> target ssd' in out
    child = e.repo / 'trip/ARCHIVE.manifest.jsonl'
    assert set(manifest_rows(child)) == {'raw/a.mp4', 'plan.json'}
    assert Path(header(child)['root']).is_relative_to(e.second)
    assert (Path(header(child)['root']) / 'files/raw/a.mp4').read_bytes() == b'A' * 1000
    assert set(e.records()) == {'notes/keep.txt'}               # parent index untouched
    assert Path(header(e.repo / 'ARCHIVE.manifest.jsonl')['root']).is_relative_to(e.base)
    # read + restore route the same way, from either folder
    assert str(Path(header(child)['root']) / 'files/raw/a.mp4') in e.ok('read', 'trip/raw/a.mp4')
    e.ok('restore', 'trip/raw/a.mp4')
    assert (e.repo / 'trip/raw/a.mp4').read_bytes() == b'A' * 1000
    e.ok('restore', 'plan.json', cwd=e.repo / 'trip')
    assert not manifest_rows(child)
    e.ok('verify'); e.ok('verify', cwd=e.repo / 'trip')


def test_parent_sync_and_tidy_never_enter_or_park_a_nested_scope(two):
    e = two
    e.write('media/other/x.bin', 'x'); e.write('media/trip/y.bin', 'y')
    e.ok('scope', 'add', 'media/trip', '--to', 'ssd')
    out = e.ok('sync', 'media')                                  # parent folder holding the scope
    assert 'media/trip/' in out and 'nested archive scope' in out
    assert set(e.records()) == {'media/other/x.bin'}
    assert (e.repo / 'media/trip/y.bin').exists()
    e.ok('tidy')
    assert (e.repo / 'media/trip/ARCHIVE.scope.json').is_file()  # media/ stays live: it holds the scope
    assert (e.repo / '_archive/media/other').is_dir() and not (e.repo / '_archive/media/trip').exists()
    e.ok('sync', 'media/trip/y.bin'); e.ok('tidy', 'media/trip')
    assert not (e.repo / 'media/trip/y.bin').exists()
    assert set(manifest_rows(e.repo / 'media/trip/ARCHIVE.manifest.jsonl')) == {'y.bin'}
    status = e.ok('status')
    assert '[nested-scope] media/trip/ -> target ssd' in status and '[unparked]' not in status


def test_paths_spanning_scopes_are_refused_without_changes(two):
    e = two
    e.write('a.txt', 'a'); e.write('trip/b.txt', 'b')
    e.ok('scope', 'add', 'trip', '--to', 'ssd')
    out = e.refused('sync', 'a.txt', 'trip/b.txt')
    assert 'more than one archive scope' in out
    assert (e.repo / 'a.txt').exists() and (e.repo / 'trip/b.txt').exists()
    assert not e.records() and not (e.repo / 'trip/ARCHIVE.manifest.jsonl').exists()


def test_scope_refuses_folders_already_archived_by_the_parent(two):
    e = two
    e.write('trip/a.txt', 'a'); e.ok('sync', 'trip/a.txt')
    out = e.refused('scope', 'add', 'trip', '--to', 'ssd')
    assert 'archived in this project' in out and not (e.repo / 'trip/ARCHIVE.scope.json').exists()


def test_scope_binding_cannot_be_redirected(two):
    e = two
    e.write('trip/a.txt', 'a'); e.ok('scope', 'add', 'trip', '--to', 'ssd')
    out = e.refused('--target', 'test', 'sync', 'trip/a.txt')
    assert 'bound to a different archive target' in out and (e.repo / 'trip/a.txt').exists()
    e.ok('sync', 'trip/a.txt')
    e.refused('--target', 'test', 'restore', 'trip/a.txt')
    assert not (e.repo / 'trip/a.txt').exists()


def test_scope_marker_and_root_are_protected(two):
    e = two
    e.write('trip/a.txt', 'a'); e.ok('scope', 'add', 'trip', '--to', 'ssd')
    e.refused('sync', 'trip/ARCHIVE.scope.json')
    e.refused('sync', 'trip')
    e.refused('scope', 'add', 'trip', '--to', 'ssd')            # already a scope
    assert (e.repo / 'trip/ARCHIVE.scope.json').is_file() and (e.repo / 'trip/a.txt').exists()


def test_scope_plan_writes_nothing(two):
    e = two
    e.write('trip/a.txt', 'a')
    assert 'PLAN' in e.ok('scope', 'add', 'trip', '--to', 'ssd', '--plan')
    assert not (e.repo / 'trip/ARCHIVE.scope.json').exists()


def test_offline_scope_target_refuses_without_touching_files(two):
    e = two
    e.write('trip/a.txt', 'a'); e.ok('scope', 'add', 'trip', '--to', 'ssd')
    (e.second / '.archive-general-target.json').rename(e.second / 'moved-away')   # wrong/missing identity
    e.refused('sync', 'trip/a.txt')
    assert (e.repo / 'trip/a.txt').exists() and not (e.repo / 'trip/ARCHIVE.manifest.jsonl').exists()


def test_drive_api_parent_skips_a_nested_local_scope(tmp_path, monkeypatch):
    d = Fixture(tmp_path, monkeypatch)
    ssd = tmp_path / 'ssd'
    assert d.run('target', 'add', 'ssd', '--root', str(ssd), '--kind', 'local') == 0
    d.write('cloud/a.txt', 'a'); d.write('cloud/trip/b.txt', 'b')
    assert d.run('scope', 'add', str(d.repo / 'cloud/trip'), '--to', 'ssd') == 0
    assert d.run('sync', 'cloud') == 0
    assert set(d.store().records) == {'cloud/a.txt'}
    assert (d.repo / 'cloud/trip/b.txt').exists()
    assert d.run('sync', str(d.repo / 'cloud/trip/b.txt')) == 0
    child = d.repo / 'cloud/trip/ARCHIVE.manifest.jsonl'
    assert set(manifest_rows(child)) == {'b.txt'}
    assert Path(header(child)['root']).is_relative_to(ssd)
    assert set(d.store().records) == {'cloud/a.txt'}


def test_parent_status_and_verify_leave_nested_files_alone(two):
    e = two
    e.write('a.txt', 'a'); e.ok('sync', 'a.txt')
    e.write('trip/b.txt', 'b'); e.write('trip/b.txt.restoring-123', 'partial restore owned by the scope')
    e.ok('scope', 'add', 'trip', '--to', 'ssd')
    status = e.ok('status')
    assert '[new] trip/' not in status and '[new] ./' not in status
    e.run('verify', '--fix')                                    # parent repair must not reach into the scope
    assert (e.repo / 'trip/b.txt.restoring-123').read_text() == 'partial restore owned by the scope'
    assert '[new] ./' in e.ok('status', cwd=e.repo / 'trip')     # the scope itself still sees its files


def test_upgrade_named_in_a_scope_runs_on_that_scope(two):
    e = two
    e.write('a.txt', 'a'); e.ok('sync', 'a.txt')
    e.write('trip/b.txt', 'b'); e.ok('scope', 'add', 'trip', '--to', 'ssd'); e.ok('sync', 'trip/b.txt')
    out = e.ok('upgrade', 'trip', '--plan')
    assert 'nested archive scope -> target ssd' in out
    assert str(e.second) in out and str(e.base) not in out


def test_scope_parks_in_the_projects_shared_park_and_parent_leaves_it_alone(two):
    e = two
    e.write('tokyo/a.mp4', 'a'); e.ok('sync', 'tokyo/a.mp4')           # parent parks _archive/tokyo
    e.write('p3/storage/day1/v.mp4', 'v'); e.write('p3/exports/final.mp4', 'keep')
    out = e.ok('scope', 'add', 'p3', '--to', 'ssd')
    assert 'park at _archive/p3/' in out
    assert json.loads((e.repo / 'p3/ARCHIVE.scope.json').read_text())['park_root'] == '_archive/p3'
    e.ok('sync', 'p3/storage')
    assert (e.repo / '_archive/p3/storage/day1').is_dir()               # shared park, same path
    assert not (e.repo / 'p3/storage').exists() and not (e.repo / 'p3/_archive').exists()
    assert (e.repo / '_archive/tokyo').is_dir() and (e.repo / 'p3/exports/final.mp4').exists()
    assert '_archive/p3/' in (e.repo / 'p3/ARCHIVE.md').read_text()
    e.ok('tidy')                                                         # parent must not pull them back
    assert (e.repo / '_archive/p3/storage/day1').is_dir() and not (e.repo / 'p3/storage').exists()
    for where in (e.repo, e.repo / 'p3'):
        assert '[unparked]' not in e.ok('status', cwd=where)
    e.ok('verify'); e.ok('verify', cwd=e.repo / 'p3')
    # the parked path works from the project and from inside the scope
    assert 'files/storage/day1/v.mp4' in e.ok('read', '_archive/p3/storage/day1/v.mp4')
    assert 'files/storage/day1/v.mp4' in e.ok('read', '../_archive/p3/storage/day1/v.mp4', cwd=e.repo / 'p3')
    e.ok('restore', '_archive/p3/storage/day1/v.mp4')
    assert (e.repo / 'p3/storage/day1/v.mp4').read_text() == 'v'
    assert not (e.repo / '_archive/p3').exists() and (e.repo / '_archive/tokyo').is_dir()
