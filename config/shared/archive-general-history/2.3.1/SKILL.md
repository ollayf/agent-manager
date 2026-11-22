---
name: archive-icloud
version: 2.3.1
description: Move files out of a project (git repo, or any folder with a CLAUDE.md) into iCloud Drive and back, one file at a time, keeping the same folder structure in iCloud. A folder whose files are all archived moves into the repo's `_archive/` folder under its own path, so the repo shows only folders that still hold files. All archives live under one iCloud folder, claude-archive/, nested by repo path, with a registry of where each came from. Tracked per repo by ICLOUD.md + ICLOUD.manifest.jsonl. Use when the user says "archive to iCloud", "move this to iCloud", "free up space in the repo", "archive last month", "sync to iCloud", "unarchive", "restore from iCloud", "bring back <file>", "which archives do we have", "too many empty folders after archiving", or asks to read a file that ICLOUD.md lists as archived (or one under `_archive/`). Files stay readable in place in iCloud; only files over the 50 GB iCloud limit are compressed. Skips files a running job is writing. Every file records the skill version that wrote it; archives made by older versions keep working, with the old code kept in history/ as a fallback. To move old archives to the current version, use the archive-icloud-upgrade skill.
argument-hint: "sync|archive|restore|read|status|list|verify|tidy|upload-status|evict|registry|version <paths>"
---

# archive-icloud

Run it only through the script, never by hand. The script holds the lock, checks every copy, and
keeps ICLOUD.md, the manifest and the registry correct.

```
S=~/.claude/skills/archive-icloud/icloud_archive.py
python3 $S sync <path>... [--exclude GLOB]... [--update]   # archive every file not archived yet
python3 $S archive <path>...      # the same as sync, without --update
python3 $S status [path...]       # what is archived, new, changed, or broken; read-only
python3 $S restore <path>...      # move back; a folder restores every file under it
python3 $S read <path>            # print where to read a file or folder; does NOT restore
python3 $S read --head N <path>   # compressed files: stream the first N lines, no temp copy
python3 $S read --full <path>     # compressed files over 10 GB: really decompress all of it to temp
python3 $S list [path...] | verify [--fix] | upload-status | evict
python3 $S tidy [path...] [--plan]  # move folders that hold only archived files into _archive/ (and back); see "Folders"
python3 $S registry [--scan DIR...]   # every archive in claude-archive/; --scan registers old ones
python3 $S version                # this skill's version, the formats it reads, the history it has
python3 $S read|restore --via-history <path>   # fallback: the frozen code of the release that wrote it
python3 $S import <folder> --kind mirror|split [--manifest CSV] --plan   # adopt a hand-made archive (see below)
```

Root = the highest folder above the cwd that has an `ICLOUD.md`; else the git toplevel; else the
highest folder with a `CLAUDE.md`. The script prints `repo: <root>` on stderr: check it.
`--repo DIR` overrides it. Paths are relative to the current directory or absolute. `--exclude`
takes repo-relative paths or globs (`2026-pull/SEP26-PULL/**`). `read` also takes an absolute
iCloud path, even one from before the archive moved.

## Where things are

```
~/Library/Mobile Documents/com~apple~CloudDocs/claude-archive/     the one base for every archive
  REGISTRY.md                generated: every archive, its repo, Mac, root, formats, writer versions
  registry/<repo-id>.json    one file per archive (only that archive's runs write it)
  repos/<repo path under ~>/ e.g. repos/develop/slide-tester/ — the archive root ("Root") of one repo
    files/<path>             format 2: each file as is, read-only — read it in place
    .big/<path>/             format 2, files over 49 GB: zst parts — use `read`
    .versions/<path>/        old copies replaced by `sync --update`, never deleted
    .manifest.jsonl          the iCloud copy of the repo's manifest
    <path>, <path>.packed    format 1 (v1) entries, until upgraded
  <name>-<hash>/             an older flat root (v1 / 2.0); `upgrade` moves it under repos/ (the registry keeps the old path)
```

- In the repo: `_archive/<path>/` holds the folders whose files are all in iCloud, and nothing else (see "Folders").
- In the repo: `ICLOUD.md` is the summary. Its first table, `| Path | Form | Archived |`, lists the
  format-1 rows exactly as v1 wrote them. After it come a per-folder table (with the writer
  version) and the compressed files. `ICLOUD.manifest.jsonl` lists every file with its format,
  writer version, size, SHA-256, mtime and mode.
- No `ICLOUD.md` = nothing archived from this repo. Still, a fresh clone finds its archive through
  the registry: run `status`, then `verify --fix`.
- Format 2 file: `Root:` line + `files/` + path. Read it in place with the Read tool; iCloud
  downloads it on open. `.big` files: `read --head N` for a look, or `read`, then Read the temp path.
- Format 1 rows: location = `Root:` + `Path`. `file`/`dir`: read in place. `zst×N`: use `read`.
- macOS denies listing `com~apple~CloudDocs` itself, so always use full paths below it.

## Folders: `_archive/` (2.3)

- **What moves.** A folder whose files are all archived moves to `_archive/<its path>`, with the empty folders in it.
  A folder that still holds any file (even one that is not archived) stays. An empty folder that never held an
  archived file never moves.
- **When.**
  - `sync` moves the folders under the paths it archived.
  - `restore` brings back the folder of what it restores; empty subfolders without archived files follow it.
  - `tidy [path...]` moves anything left over (`--plan` first). `status` lists such folders as `[unparked]`.
- **How.** One folder at a time: mkdir on the other side, then rmdir. rmdir refuses a folder that is not empty, so a
  file that appears meanwhile keeps its folder, and no file is ever moved or deleted with a folder. Only `.DS_Store`
  is carried along. Folders keep their mode, times and flags; Finder tags on folders are not kept.
- **Kept in place** (a `kept <folder>/: …` line, not an error; report it). A later `sync` or `tidy` moves it once
  the reason is gone:
  - the folder changed in the last `--min-age` minutes, other than by this run (by another program, or by an
    earlier run of this skill, e.g. a `sync --update` right after a `sync`);
  - a process has something in it open, or works in it (also the script's own current folder);
  - a symlink in the repo points into it;
  - it is, or holds, an `--exclude`d path.
  If `lsof` cannot answer, no folder moves at all. Never lower `--min-age` to get past a kept folder.
- **`_archive/` holds only folders.** Never put files there. A file found there is reported as `[parked-file]` and
  is never moved or deleted. Never create, move or delete folders in it by hand: use `tidy`.
- **A path under `_archive/` means the same path without it.** `read`, `restore`, `list` and `status` accept either,
  e.g. `read _archive/m/AUG/a.csv` = `read m/AUG/a.csv`.
- **`.keep`.** A folder that holds a `.keep` file always stays, and `.keep` is never archived. Use it for a folder
  that a job writes into without creating it first (such a job fails once its folder has moved).
- **Repos archived before 2.3** keep their folders in place, exactly as before, until a whole-repo `upgrade` runs its
  `park` step (archive-icloud-upgrade: plan first, then ask). `status` notes how many folders would move.
- **The name.** It is `_archive/` in every repo. If a repo's own `_archive/` holds files, or archived files sit under
  `_archive/`, folders stay in place and `status` says why; `upgrade --park-dir NAME` picks another name. The name is
  recorded twice, in ICLOUD.md (the `Parked folders:` line above the table) and in the manifest header; each restores
  the other.

## Versions and old archives

- Two numbers. The **skill version** (`version:` above, also `SKILL_VERSION`) is stamped on every
  record as `by`. The **format** is how a record is stored: 1 = whole file or folder, or zst×N
  pack (skill 1.x); 2 = per-file mirror (skill 2.x). v1 never recorded a version, so its rows
  read as `by 1.x`.
- This skill reads every format by default, old packs included. A record in a format it does not
  know is refused, with "update the skill". It never guesses.
- If the built-in code fails on an old entry, the error names the release that wrote it and gives
  the exact `--via-history` command. That runs `history/<version>/icloud_archive.py`, the frozen
  code of that release, after checking its SHA-256. It is for read and restore only. To see how
  that version worked, read `history/<version>/SKILL.md`. `history/INDEX.json` lists every release
  and the formats it writes.
- Repo layout: folders in place (before 2.3), or parked in `_archive/` (2.3+). Records and iCloud are the same in
  both. Older versions read, list, check (`status`, `verify`) and restore a parked repo. Their restore puts the
  folder back in place, and 2.3's next run moves the rest of that tree back from `_archive/`.
- To move old archives to the current format, the nested root and the parked layout, use the
  **archive-icloud-upgrade** skill.

## Archives made by hand or by other tools: `import`

Some archives were made before this skill, by hand or by another tool, and sit outside
`claude-archive/` (e.g. `iCloud Drive/<repo>_archive/`). `import` adopts one into the repo's archive
as format 2. It records `imported_from`, removes the empty foreign folder, and lets the old path
still resolve through `read`.
- `--kind mirror`: a folder whose files sit at their repo paths. `--manifest CSV` (columns `path`,
  `archive_path`, optional `bytes`, `md5`, `status`) maps rows, including folder rows.
  - **Each file is hashed in place (this downloads it), checked against the CSV's size and md5,
    renamed into `files/`, and recorded.** It works in ~10 GB batches, evicting after each.
  - It refuses any file in no row, any collision, and any local file with that path. Rows marked
    `deleted` are skipped.
  - An `imported_to` column is added to the CSV; no row is removed.
- `--kind split`: `MANIFEST.txt` (original path, size, sha256, `part_prefix`) + `SHA256SUMS` + zstd parts.
  - Every part is checked, and the whole stream is decompressed against the original sha256 —
    before the move and again after it.
  - The parts go to `.big/<path>/`; `MANIFEST.txt` and the other files go to `.big/<path>/imported/`.
- **Always run `--plan` first, show it, and ask.** It is resumable: after a crash, run the same
  command again. An `md5`, `SHA-256` or stream mismatch is a REFUSED (rule 3): that file stays where
  it is. **Never edit the foreign manifest, or its md5, to make a check pass.** It is the only record of what
  the file was. Report the mismatch and let the user decide.
  If the user confirms the file as it is now, rerun with `--accept-mismatch <path>`. It imports that one file and
  records both md5s in its `imported_from`. There is no other way to bring it in; never move it by hand.

## Rules

1. **Ask before archiving** unless the user named the exact paths. "Clean up the repo" is not a list.
2. **Read ≠ restore.** If the user wants to look at an archived file, use `read`. Restore only when asked.
3. **On REFUSED, stop and tell the user.** Do not work around it. In particular:
   - `no-delete rule`: show the user the quoted lines. Rerun with `--allow-protected` only after they say yes.
     The skill has no copy-only mode: archiving always removes the local copy. Never offer, or make, a copy by hand instead.
   - `not overwriting` / `with no record of it`: something is already there. Run `verify` and report. Never delete it yourself.
   - `holds the archive of another repo`: a repo moved, or two repos share a path. Report it; do not pass `--repo` to get around it unless the user confirms which repo it is.
   - `does not know that format`: tell the user the skill needs updating.
   - `built-in reader … failed`: tell the user, then run the `--via-history` command it prints.
4. **`skipped (live …)` is not an error.** The file changed in the last 10 minutes (`--min-age`),
   a process has it open, its folder holds a `*.cursor` / `*.partial-*` / `*.tmp-*` /
   `*.restoring-*` file, or a database has a `-wal`/`-shm`/`-journal` file. Report the skipped files.
   Never lower `--min-age` to get past a running job. `kept <folder>/: …` is the same for folders (see "Folders").
5. **`changed` files are never replaced without `--update`.** Show the user the list, and ask before
   running `--update`.
6. **Always relay the SUMMARY block.** It checks the result from disk, not from memory. If it says
   `PROBLEMS FOUND`, or the exit code is non-zero, say so plainly.
7. **Space is not returned on archive.** iCloud Drive is on the same disk. The space comes back
   only after upload finishes and `evict` runs. Until upload finishes, this Mac holds the only copy. Tell the user, then:
   - run `upload-status` until everything is uploaded (the user can also check in Finder). Check every
     1–2 minutes for at most ~10 minutes; if still pending, report the state and stop — do not block;
   - run `evict`. Its SUMMARY reports the disk-free change.
   - The job is done only after you report: where every file is, the upload state, and the space returned.
8. **After a crash or interruption**, run `verify`. Report its findings, then run `verify --fix`.
   `--fix` only finishes an operation when both copies are byte-identical. It never touches differing copies or unknown files.
   A `note:` line in `status` means the repo index is behind iCloud (an upgrade ran elsewhere): `verify --fix` updates it.
9. Never hand-edit ICLOUD.md, the manifest, the registry, the archive folder or `_archive/`. Text above the first table in ICLOUD.md may be edited; the script keeps it (leave the `Root:` and `Parked folders:` lines as they are).

## Recurring archive (for example, every month)

```
python3 $S --repo <repo> status 2026-pull                                    # what is new
python3 $S --repo <repo> sync 2026-pull --exclude '2026-pull/<newest month>/**'
python3 $S --repo <repo> upload-status    # then evict once everything is uploaded
```
A month whose files are all archived moves to `_archive/<its path>`; the newest month stays where it is.

## What the script guarantees

| Situation | Behaviour |
|---|---|
| Any copy | Verified by SHA-256 before the local file is deleted. Compressed: full decompress first. |
| File over 49 GB | zstd `-19 --long=30` (`--fast`: `-10`); split into parts ≤ 49 GB if still too big; `MANIFEST.json` + `SHA256SUMS` |
| Low disk | Checks free space first. ENOSPC mid-copy: partial deleted, original untouched |
| Two agents at once | Per-repo `flock` (`~/.claude/locks/`), taken per file; state re-read under the lock; the registry has its own lock |
| iCloud already has the path | Identical → recorded, no copy. Different → refused, never overwritten |
| Crash at any step | The original is never lost; `verify --fix` completes or rolls back; a rerun of `sync` resumes |
| File changes during archive | Local copy is not deleted |
| Two names that differ only in case | Refused (iCloud is case-insensitive) |
| Two repos at one nested path | Refused (each root's manifest names its repo id) |
| iCloud conflict copy (`ICLOUD 2.md`, `x 2.json`) | Reported by `verify`, never deleted |
| Outside repo, `..`, `.git`, `ICLOUD.md`, the manifest, backtick/newline in name | Refused |
| Symlink inside a folder | Skipped and reported |
| Folder whose files are all archived | Moves to `_archive/<path>`, one folder at a time (mkdir, then rmdir); a file that appears meanwhile keeps its folder; no file ever moves |
| Folder in use, changed recently, linked into, or excluded | Kept in place and reported; no folder moves if `lsof` cannot answer |
| A file inside `_archive/` | Reported as `[parked-file]`; never moved or deleted |
| Repo archived before 2.3 | Folders stay in place until `upgrade` parks them |
| v1 entry, or a file inside a v1 folder | handled as v1 did; `sync` skips it |

Git is ignored on purpose: an archived tracked file shows as deleted in `git status`.

## Tests and releases

Run after any change to the script:
`cd ~/.claude/skills/archive-icloud && uvx --index-url https://pypi.apple.com/simple --with pytest-timeout pytest -q --timeout 90 claude/`
- `claude/test_icloud_archive.py`: the current version.
- `claude/test_parked_folders.py`: the 2.3 folder layout, its guards, old releases on a parked repo, and random
  operation sequences checked after every step.
- `claude/test_legacy_compat.py`: the full v1 suite. Every archive is made by
  `history/1.0.0/icloud_archive.py`, and every other command by the current script.
- `claude/_mutate.py`: breaks each guard and checks that its test fails.
- `claude/_setup_evals.py` + `claude/_score_evals.py`: the subagent evals (sandboxes, then scoring from disk). `claude/evals.md`: all results.

**To release a version:**
1. Bump `version:` here and `SKILL_VERSION` in the script.
2. Add a `history/INDEX.json` entry.
3. Run `python3 claude/_release.py`. It freezes the script and this file into `history/<version>/` with `SHA256SUMS`.

Never edit a released `history/` folder. If a release changes how files are stored, add a new
format number and an upgrade step.
