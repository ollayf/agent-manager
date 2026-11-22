#!/usr/bin/env python3
"""Break one documented guard in an isolated copy and run its paired regression."""
import argparse
import ast
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent


def replacements():
    return {86: [('                    guard_archive_path(store.root)\n                    repair()', '                    repair()')], 1: [('indexed[-1] if indexed else expand(git) if git else claude[-1]',
          'indexed[0] if indexed else expand(git) if git else claude[0]')],
     2: [('if time.time() - path.stat().st_mtime < min_age * 60:', 'if False:'),
         ('if time.time() - path.stat().st_mtime < args.min_age * 60:', 'if False:')],
     3: [('if any(BUSY.search(name) for name in names):', 'if False:')],
     4: [('if path.resolve() in opened:', 'if False:')],
     5: [('if any(path.with_name(path.name + suffix).exists() for suffix in ("-wal", "-shm", "-journal")) or '
          'any(path.name.endswith(suffix) for suffix in ("-wal", "-shm", "-journal")):',
          'if False:')],
     6: [('if any(rel == r["path"].rstrip("/") or rel.startswith(r["path"].rstrip("/") + "/") for r in store.v1):',
          'if False:'),
         ('if any(rel_file == r["path"].rstrip("/") or rel_file.startswith(r["path"].rstrip("/") + "/") for r in '
          'store.v1):',
          'if False:')],
     7: [('if any(Path(x["path"]).parts[0] in ("files", ".big", ".versions", ".manifest.jsonl", ".import-journal.jsonl") '
          'for x in self.v1):',
          'if False:')],
     8: [('if clash:\n        raise Refused', 'if False:\n        raise Refused'),
         ('if different:\n                    raise Refused', 'if False:\n                    raise Refused')],
     9: [('publish(store.location(old), kept)', 'remove_output(store.location(old))')],
     10: [('if not args.update:', 'if False:')],
     11: [('lines += self.suffix',
           'lines += self.suffix\n'
           '        if self.v1:\n'
           '            lines = [BEGIN, "## Archived files (v2)", END] + lines')],
     12: [('store.v1 = [x for x in store.v1 if x["path"] != rel]', 'store.v1 = store.v1')],
     13: [('form = (record or row)["form"]', 'form = record["form"] if record else "file"')],
     14: [('reserved = {"files", ".big", ".versions", ".manifest.jsonl", ".import-journal.jsonl"}', 'reserved = set()')],
     15: [('if mirror.get("id") and mirror["id"] != self.id:', 'if False:')],
     16: [('def supported(record):\n    if record.get("format", 2) != 2:', 'def supported(record):\n    if False:')],
     17: [('if path.is_symlink() or not path.is_file() or hash_file(path) != sha:', 'if False:')],
     18: [('prefix[i] = f"Root: `{compact_path(self.root)}/`"', 'prefix[i] = line')],
     19: [('if self.root in old and current and current.exists():', 'if False:')],
     20: [('rc = upgrade_archive(local if on_mac else None, None if on_mac else entry, args)',
           'rc = upgrade_archive(local, None, args) if on_mac else 0')],
     21: [('if moved.exists() or big.exists():', 'if False:')],
     22: [('if exists(path):\n        raise Refused(f"{rel} exists {\'in the --into folder\' if into else \'locally\'}; not overwriting")',
           'if exists(path):\n'
           '        store.save()\n'
           '        raise Refused(f"{rel} exists {\'in the --into folder\' if into else \'locally\'}; not overwriting")')],
     23: [('(fallback if fallback.exists() else self.nested_root())', 'self.nested_root()')],
     24: [('form="file", date=today(), format=2, by=SKILL_VERSION)', 'form="file", date=today(), format=2)')],
     25: [('if pending and not wait_uploaded(store.root, args.wait):', 'if False:')],
     26: [('if not scopes and store.scheme == "flat":', 'if False:')],
     27: [('for old in store.registry.get("old_roots", []):', 'for old in []:')],
     28: [('if row and row.get("md5") and row["md5"].lower() != md5:', 'if False:')],
     29: [('refused.append((str(path), "in the folder but in no manifest row"))\n                continue',
           'matching = (0, {"path": path.relative_to(folder).as_posix()}, "")')],
     30: [('if exists(store.repo / rel):\n                raise Refused("exists locally; not overwriting")',
           'if False:\n                raise Refused("exists locally; not overwriting")'),
          ('if exists(destination) or exists(store.repo / rel):', 'if exists(destination):')],
     31: [('if source.is_symlink() or not source.is_file() or source.stat().st_size != part["size"] or hash_file(source) '
           '!= part["sha256"]:',
           'if False:')],
     32: [('decompress_parts(paths, expected=(meta["original_bytes"], meta["original_sha256"]))',
           'pass  # omitted whole-stream preflight')],
     33: [('imported = [] if args.plan else resume_import(store, journal, ledger)', 'imported = []')],
     34: [('for child in list(path.iterdir()):\n        if child.is_dir()',
           'shutil.rmtree(path)\n    return True\n    for child in list(path.iterdir()):\n        if child.is_dir()')],
     35: [('if inside(folder.resolve(), BASE.resolve()):', 'if False:')],
     36: [('if rel not in accepted:', 'if not accepted:')],
     37: [('if path.is_symlink():\n                raise Refused("symlink; never followed")',
           'if False:\n                raise Refused("symlink; never followed")'),
          ('if source.is_symlink() or not source.is_file():', 'if not source.is_file():')],
     38: [('if meta["original_size"] > READ_FULL_LIMIT and not args.full:', 'if False:')],
     39: [('return entry, None, result', 'return entry, origin["maps_to"], None')],
     40: [('if content or any(live_children):', 'if False:')],
     41: [('elif rel in self.archived:', 'elif True:')],
     42: [('self.places[rel] = self.places.get(parent_rel, "live")', 'self.places[rel] = "live"')],
     43: [('while path != self.repo and not path.is_dir():',
           'if not path.is_dir():\n'
           '                    continue\n'
           '                while path != self.repo and not path.is_dir():')],
     44: [('return self.ledger.young(path, self.min_age) if age and path.exists() else None', 'return None')],
     45: [('before = entry["before"]',
           'before = entry["after"]\n            if not entry["external"]:\n                return None')],
     46: [('entry["external"] = True', 'entry["external"] = False'),
          ('if entry["external"] or current != entry["after"]:', 'if False:')],
     47: [('for parent, info in saved_times.items():', 'for parent, info in []:')],
     48: [('if rel in self.in_use:', 'if False:')],
     49: [('plan.blocked = error', 'plan.blocked = None')],
     50: [('if rel in self.linked:', 'if False:')],
     51: [('if match_path(rel, self.excludes) or match_path(rel + "/", self.excludes):', 'if False:')],
     52: [('source.rmdir()', 'shutil.rmtree(source)')],
     53: [('if reason:\n                    self.park_note', 'if False:\n                    self.park_note')],
     54: [('elif ix_park or header_park:\n                self.parked = ix_park or header_park',
           'elif header_park:\n                self.parked = header_park')],
     55: [('header_park = self.header.get("parked")',
           'header_park = self.header.get("parked") or self.mirror_header.get("parked")')],
     56: [('elif not self.index_exists and not self.manifest_exists:', 'elif True:')],
     57: [('if self.parked and not store_shared_park(self) and (rel == self.parked or rel.startswith(self.parked + "/")):', 'if False:')],
     58: [('"Folders stay in the repo. Every file is listed, with the skill version that wrote it, in '
           '`ICLOUD.manifest.jsonl`."',
           'f"Folders are parked in {self.parked}. Every file is in the manifest."')],
     59: [('pending = any(s["kind"] != "park" for s in steps) and pending_upload(store.root)',
           'pending = bool(steps) and pending_upload(store.root)')],
     60: [('if report.items:\n            store.save()\n        store.parked = remembered_park',
           'if False:\n            store.save()\n        store.parked = remembered_park'),
          ('if folder:\n            folder.apply()\n    return report.summary',
           'if folder:\n'
           '            folder.apply()\n'
           '        if report.items:\n'
           '            store.save()\n'
           '    return report.summary')],
     61: [('store.parked = remembered_park\n        if into:',
           'remembered_park = store.parked\n        if into:')],
     62: [('name not in (".git", ".keep")', 'name not in (".git",)')],
     63: [('name not in (".git", ".keep")', 'name not in (".keep",)')],
     64: [('for name in files if name != ".DS_Store"', 'for name in files if not litter(name)')],
     65: [('elif (child.name == ".DS_Store" or storage.apple_double(child)) and child.is_file() and not '
           'child.is_symlink():',
           'elif litter(child.name) and child.is_file() and not child.is_symlink():')],
     66: [('command, str(store.repo / rel)]', 'command, rel]')],
     67: [('def settle(self):\n        if self.dirty:', 'def settle(self):\n        if False:')],
     68: [('self.write_registry()\n        self.dirty', 'pass  # no registry\n        self.dirty')],
     69: [('if path.is_file() and (path.name == ".keep" or litter(path.name)):', 'if False:')],
     70: [('or p.as_posix() in (INDEX, MANIFEST, "ICLOUD.md", "ICLOUD.manifest.jsonl", "ARCHIVE.md", '
           '"ARCHIVE.manifest.jsonl", SCOPE_FILE) ',
           '')],
     71: [('if moved.exists() or big.exists():', 'if not cloud.exists() and (moved.exists() or big.exists()):')],
     72: [('if store.dirty or any(not x["refuse"] for x in steps):', 'if any(not x["refuse"] for x in steps):')],
     73: [('if changed_store or before_manifest != after_manifest:', 'if changed_store:')],
     74: [("if (data.get('id'), data.get('kind')) != (self.value.get('id'), self.kind):", 'if False:')],
     75: [('    def available(self):\n        if self.kind == \'google-drive-api\':',
           '    def available(self):\n        return self\n        if self.kind == \'google-drive-api\':')],
     76: [("if volume_uuid(mount).upper() != self.value.get('volume_uuid', '').upper():", 'if False:')],
     77: [('elif recorded:', 'elif False:')],
     78: [('if under(self.root, repo) or under(repo, self.root):', 'if False:')],
     79: [('if open_error and TARGET and TARGET.managed:', 'if False:')],
     80: [('if storage.reserved_collision(path):', 'if False:'), ('elif storage.reserved_collision(p):', 'elif False:')],
     81: [('def guard_archive_path(path):\n    path = Path(path)',
           'def guard_archive_path(path):\n    return\n    path = Path(path)')],
     82: [('0x00000004)  # SDK sys/stdio.h RENAME_EXCL', '0)  # deliberately allow replacement')],
     83: [("if not value.get('identity') or identity != value['identity'] or info.st_dev != value.get('device'):",
           'if False:')],
     84: [('        if dest.is_dir():\n            dest.rmdir()',
           '        if dest.is_dir():\n            safe_remove_tree(dest)')],
     85: [('or fingerprint(source) != fingerprint(destination):', ':'),
          ('if fingerprint(destination) != expected or fingerprint(source) != expected:', 'if False:')],
     87: [('        if time.monotonic() - self.started >= BATCH_SECONDS:\n            self.close()',
           '        if False:\n            self.close()')],
     88: [('            time.sleep(LOCK_YIELD)\n', '')],
     89: [('            time.sleep(LOCK_YIELD)\n', '')],
     90: [('        if error.errno != errno.EINVAL or not flags & stat.UF_COMPRESSED:\n            raise', '        raise')],
     91: [('        if error.errno != errno.EINVAL or not flags & stat.UF_COMPRESSED:\n            raise', '        if False:\n            raise')],
     92: [('        if flags & ~stat.UF_COMPRESSED:\n            try:', '        if False:\n            try:')],
     93: [('    copy2(source, destination)\n    with open(destination, "rb") as handle:', '    shutil.copy2(source, destination)\n    with open(destination, "rb") as handle:')],
     94: [('        if len(found) > 1:\n            names =', '        if False:\n            names =')],
     95: [('dirs[:] = [d for d in dirs if d != ".git" and not (Path(parent) / d).is_symlink() and not scope_root(Path(parent) / d)]\n            result += [Path(parent) / f for f in files', 'dirs[:] = [d for d in dirs if d != ".git" and not (Path(parent) / d).is_symlink()]\n            result += [Path(parent) / f for f in files')],
     97: [('                        elif scope_root(p):\n                            report.skipped.append((r + "/", "nested archive scope with its own index; archive it from there"))\n', '')],
     98: [('        if clash:\n            raise Refused(f"{len(clash)} entries under', '        if False:\n            raise Refused(f"{len(clash)} entries under')],
     99: [("and not core.scope_root(Path(parent)/d) and not core.match_path", "and not core.match_path")],
     100: [('"list", "status", "tidy", "upgrade")\n', '"list", "status", "tidy")\n')],
     101: [('parked_folders = [p for p in all_folders(self.park) if not any(p == f or inside(p, f) for f in foreign)]', 'parked_folders = all_folders(self.park)')],
     102: [('    return store_shared_park(store) or (store.repo / store.parked', '    return (store.repo / store.parked')],
     103: [('            twin = scope_parked_path(repo, absolute)\n', '            twin = None\n')],
     104: [('    if inside(real, repo.resolve()) or inside(repo.resolve(), real):', '    if False:')],
     105: [('        if root.exists() and (inside(real, root.resolve()) or inside(root.resolve(), real)):', '        if False:')],
     106: [('    path = (into or repo) / rel.rstrip("/")', '    path = repo / rel.rstrip("/")')],
     107: [('        if any(r == rel or r.startswith(rel + "/") for r in remaining):\n            continue', '        if False:\n            continue')],
     108: [("        if into:op['into']=str(into)\n", '')],
     109: [('            carry_identity(source, destination)\n', '            pass\n')],
     110: [('    if index:\n        raise Refused(f"{rel}/ still holds', '    if False:\n        raise Refused(f"{rel}/ still holds')],
     111: [('    if leftovers:\n', '    if False:\n')],
     112: [('    if args.via_history and into:', '    if False:')],
     113: [('    path=base/rel\n', '    path=store.repo/rel\n')],
     114: [('            local = (self.into or self.repo) / rel', '            local = self.repo / rel')],
     115: [('                if row.get("sha256") and row["sha256"].strip().lower() != sha:', '                if False:')],
     116: [('                    record["mode"] = int(row["mode"].strip(), 8) & 0o7777', '                    pass')]}

def mutants():
    text = (HERE / 'archive-icloud-guide.md').read_text()
    rows = re.findall(r'^\| (\d+) \| ([\d.]+) \| (.*?) \| `([^`]+)` \|$', text, re.M)
    result = [dict(id=int(i), release=r, guard=g, test=t) for i, r, g, t in rows]
    assert len(result) == 68
    result.append(dict(id=69, release='2.3.1', guard='named junk archived directly', test='test_rebuild_regressions.py::test_named_junk_is_refused_without_side_effects'))
    extras = [
        (70, 'import accepts protected index paths', 'test_import_cannot_create_records_for_the_indexes'),
        (71, 'verify misses a partly moved v1 directory', 'test_verify_finishes_a_partly_moved_v1_directory'),
        (72, 'upgrade leaves interrupted relocation unsettled', 'test_upgrade_alone_settles_an_interrupted_relocation'),
        (73, 'failed sync leaves durable changes uncompacted', 'test_failed_sync_with_durable_changes_compacts_both_indexes'),
    ]
    for number, guard, test in extras:
        result.append(dict(id=number, release='2.3.1', guard=guard, test='test_rebuild_regressions.py::' + test))
    for number, guard, test, source in [(74, 'target marker identity unchecked', 'test_wrong_marker_refuses_verification_and_preserves_data', 'storage.py'), (75, 'offline target allowed to fall back', 'test_offline_target_refuses_without_record_changes', 'storage.py'), (76, 'external volume UUID unchecked', 'test_wrong_external_uuid_is_refused_without_any_write', 'storage.py'), (77, 'bound target ignored after default switch', 'test_default_target_change_does_not_redirect_bound_project', 'storage.py'), (78, 'archive/project containment accepted', 'test_nested_target_and_project_refuse', 'storage.py'), (79, 'file lsof failure accepted', 'test_registered_file_operation_fails_closed_when_lsof_is_missing', 'archive.py'), (80, 'ordinary ._ collision archived', 'test_fake_appledouble_user_file_is_preserved', 'archive.py'), (81, 'archive storage symlink followed', 'test_archive_storage_symlink_is_refused', 'archive.py'), (82, 'publication overwrites an existing path', 'test_atomic_publication_never_overwrites', 'storage.py'), (83, 'publication object identity not checked', 'test_publication_nonce_rejects_reused_inode', 'storage.py'), (84, 'nonempty partial publication recursively deleted', 'test_nonempty_partial_directory_is_never_recursively_deleted', 'storage.py'), (85, 'exclusive copy accepts damaged bytes', 'test_fallback_copy_refuses_bad_bytes_and_keeps_source', 'storage.py')]:
        result.append(dict(id=number, release="3.0.0", guard=guard, test="test_general_storage.py::" + test, file=source))
    result.append(dict(id=86, release='3.0.0', guard='verification repair skips target recheck', test='test_general_storage.py::test_verify_rechecks_target_before_repair_if_it_disappears_during_hash', file='archive.py'))
    result.append(dict(id=87, release='3.2.0', guard='batched run never releases the repo lock', test='test_batching.py::test_lock_is_released_between_batches_and_other_writers_get_in', file='archive.py'))
    result.append(dict(id=88, release='3.2.0', guard='batched run retakes the lock before a waiting writer can', test='test_batching.py::test_lock_is_released_between_batches_and_other_writers_get_in', file='archive.py'))
    result.append(dict(id=89, release='3.2.0', guard='a real second archive run starves behind a batched run', test='test_batching.py::test_a_second_real_archive_run_gets_in_while_a_big_run_is_busy', file='archive.py'))
    result.append(dict(id=90, release='3.2.1', guard='compressed source refused by a target without the flag', test='test_compressed.py::test_copy_stat_drops_only_the_compression_flag_and_keeps_other_metadata', file='storage.py'))
    result.append(dict(id=91, release='3.2.1', guard='unrelated metadata errors silently ignored', test='test_compressed.py::test_copy_stat_still_raises_einval_for_an_uncompressed_source', file='storage.py'))
    result.append(dict(id=92, release='3.2.1', guard='other file flags dropped with the compression flag', test='test_compressed.py::test_copy_stat_drops_only_the_compression_flag_and_keeps_other_metadata', file='storage.py'))
    result.append(dict(id=93, release='3.2.1', guard='archive copy bypasses the compression-tolerant metadata step', test='test_compressed.py::test_compressed_files_archive_and_restore_on_a_target_that_refuses_the_flag', file='archive.py'))
    for number, guard, test, source in [(94, 'one command spans two archive scopes', 'test_paths_spanning_scopes_are_refused_without_changes', 'archive.py'),
                                        (95, 'parent status/verify walk into a nested scope', 'test_parent_status_and_verify_leave_nested_files_alone', 'archive.py'),
                                        (97, 'parent sync archives a nested scope', 'test_parent_sync_and_tidy_never_enter_or_park_a_nested_scope', 'archive.py'),
                                        (98, 'scope created over parent-archived files', 'test_scope_refuses_folders_already_archived_by_the_parent', 'archive.py'),
                                        (99, 'Drive parent sync archives a nested scope', 'test_drive_api_parent_skips_a_nested_local_scope', 'drive_archive.py'),
                                        (100, 'upgrade of a scope runs on the parent', 'test_upgrade_named_in_a_scope_runs_on_that_scope', 'archive.py')]:
        result.append(dict(id=number, release='3.3.0' if number < 100 else '3.3.1', guard=guard, test='test_nested_scopes.py::' + test, file=source))
    for number, guard, test in [(101, "parent tidy pulls a scope's parked folders back", 'test_scope_parks_in_the_projects_shared_park_and_parent_leaves_it_alone'),
                                (102, "scope parks inside itself instead of the project's park", 'test_scope_parks_in_the_projects_shared_park_and_parent_leaves_it_alone'),
                                (103, 'a shared-park path is not routed to its scope', 'test_scope_parks_in_the_projects_shared_park_and_parent_leaves_it_alone')]:
        result.append(dict(id=number, release='3.4.0', guard=guard, test='test_nested_scopes.py::' + test, file='archive.py'))
    for number, guard, test, source in [(104, 'restore --into accepted inside the project', 'test_restore_into_refuses_unsafe_destinations_without_changes', 'archive.py'),
                                        (105, 'restore --into accepted inside an archive target', 'test_restore_into_refuses_unsafe_destinations_without_changes', 'archive.py'),
                                        (106, 'restore --into writes into the project anyway', 'test_restore_into_writes_outside_the_project_and_consumes_the_archive_copy', 'archive.py'),
                                        (107, 'restore --into retires parked structure still in use', 'test_restore_into_keeps_parked_structure_that_still_has_archived_files', 'archive.py'),
                                        (108, 'resumed Drive restore forgets its --into folder', 'test_drive_restore_into_resumes_into_the_same_folder', 'drive_archive.py'),
                                        (109, 'copy-fallback publication drops the owner mark', 'test_copy_fallback_publication_keeps_the_source_identity', 'storage.py'),
                                        (110, 'scope remove retires a scope that still has an index', 'test_scope_remove_refuses_while_anything_is_archived_or_parked', 'archive.py'),
                                        (111, 'scope remove deletes a park that still holds files', 'test_scope_remove_refuses_while_anything_is_archived_or_parked', 'archive.py'),
                                        (112, 'via-history restore accepts --into', 'test_via_history_does_not_take_into', 'archive.py'),
                                        (113, 'Drive restore ignores --into', 'test_drive_restore_into_a_staging_folder', 'drive_archive.py'),
                                        (114, 'restore --into post-check looks in the project', 'test_restore_into_writes_outside_the_project_and_consumes_the_archive_copy', 'archive.py'),
                                        (115, 'import accepts a file whose SHA-256 disagrees with its CSV row', 'test_import_csv_restores_original_identity_and_metadata', 'archive.py'),
                                        (116, 'import ignores the original mode carried by a CSV row', 'test_import_csv_restores_original_identity_and_metadata', 'archive.py')]:
        result.append(dict(id=number, release='3.5.0', guard=guard, test='test_restore_into.py::' + test, file=source))
    for value in result:
        value['replacements'] = replacements()[value['id']]
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('ids', nargs='*', type=int)
    parser.add_argument('--report', type=Path)
    parser.add_argument('--validate', action='store_true')
    args = parser.parse_args()
    results = []
    for value in mutants():
        if args.ids and value['id'] not in args.ids:
            continue
        source = (SKILL / value.get('file', 'archive.py')).read_text()
        for before, after in value['replacements']:
            if source.count(before) != 1:
                raise SystemExit('BAD MUTANT ' + str(value['id']) + ': matches=' + str(source.count(before)) + ' ' + repr(before))
            source = source.replace(before, after)
        ast.parse(source)
        if args.validate:
            print(value['id'], 'valid')
            continue
        # Keep evidence on disk; no original repository/history is ever mutated.
        temp = Path(tempfile.mkdtemp(prefix='archive-mutant-' + str(value['id']) + '-'))
        copy = temp / 'archive-general'
        shutil.copytree(SKILL, copy, ignore=shutil.ignore_patterns('__pycache__', '.pytest_cache'))
        (copy / value.get('file', 'archive.py')).write_text(source)
        command = [sys.executable, '-m', 'pytest', '-q', '-x', str(copy / 'claude' / value['test']), '--tb=short', '-rs']
        process = subprocess.run(command, capture_output=True, text=True, timeout=180)
        output = process.stdout + process.stderr
        (temp / 'pytest.log').write_text(output)
        if re.search(r'\b\d+ skipped\b', output) and process.returncode == 0 and not re.search(r'\b\d+ passed\b', output):
            status = 'SKIPPED' if 'original frozen history/' in output or 'original history/' in output else 'SURVIVED'  # A6 is the only skip exception
        elif process.returncode == 0:
            status = 'SURVIVED'
        elif process.returncode != 1 or 'ERROR collecting' in output or 'ImportError' in output or 'SyntaxError' in output:
            status = 'INVALID'
        else:
            status = 'KILLED'
        reasons = [line for line in output.splitlines() if line.startswith('E ') or line.startswith('E\t')]
        result = dict(id=value['id'], guard=value['guard'], test=value['test'], status=status, reason=reasons[0] if reasons else '', evidence=str(temp))
        results.append(result)
        print(value['id'], status, result['reason'], flush=True)
    if args.report:
        args.report.write_text(json.dumps(results, indent=2) + '\n')
    return any(r['status'] in ('SURVIVED', 'INVALID') for r in results)


if __name__ == '__main__':
    raise SystemExit(main())
