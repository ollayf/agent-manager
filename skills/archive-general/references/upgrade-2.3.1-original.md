---
name: archive-icloud-upgrade
version: 2.3.1
description: Upgrade iCloud archives made by older versions of the archive-icloud skill to the current format and folder layout — for one folder, one repo, or every archive in claude-archive/. Use when the user says "upgrade the archive", "upgrade old archives", "migrate archives to the new version", "update the archive version", "move the archive under repos/", or when archive-icloud's status shows `format 1` rows, a `flat` root, or folders that "hold only archived files" (the 2.3 `_archive/` layout). Always shows the plan first and asks before changing anything.
argument-hint: "[path...] | --repo DIR | --all"
---

# archive-icloud-upgrade

This is a sub-skill of **archive-icloud** (`~/.claude/skills/archive-icloud/SKILL.md`). It uses the
same script, and all of that skill's rules apply, including "on REFUSED, stop and tell the user".

```
S=~/.claude/skills/archive-icloud/icloud_archive.py
python3 $S registry                       # every archive: repo, root, scheme, formats, writer versions
python3 $S registry --scan [DIR...]       # register archives made before the registry existed (default ~/develop)
python3 $S --repo <repo> upgrade --plan [path...]   # one repo, or only the v1 entries under path
python3 $S upgrade --all --plan                     # every registered archive
python3 $S ... upgrade ...                          # the same, without --plan, after the user says yes
```

## What an upgrade does

Upgrades go between **formats**, **root schemes** and **repo layouts**, never between skill versions. A
release that changes none of them needs no upgrade. The steps chain, so a future format 3 is one more step.

| Step | From → to | How | Cost |
|---|---|---|---|
| `relocate` | flat root `claude-archive/<name>-<hash>/` → nested `claude-archive/repos/<repo path under ~>/` | runs **last**, as one rename inside iCloud, and only once iCloud has uploaded everything (it waits up to `--wait` min, default 10; otherwise it is deferred and the next run finishes it). Root line, manifest and registry are updated; nothing is written at the old path; the registry keeps the old path, so `read <old path>` still works | no download |
| `fmt1to2` `file`/`dir` | format 1 whole entry → format 2 files under `files/` | each file renamed inside iCloud, then hashed and recorded | no download, but hashing reads every file once (an evicted file is downloaded) |
| `park` | repo layout: folders in place (before 2.3) → folders whose files are all archived kept at `_archive/<path>` | records the name in ICLOUD.md and the manifest first, then moves the folders one at a time with archive-icloud's guards (see its "Folders" section). Runs after the format steps and before relocate. `--park-dir NAME` if the repo's own `_archive/` holds files | nothing in iCloud changes, no download, no upload wait |
| `fmt1to2` `zst×N` | format 1 pack → format 2 | unpacked raw into `files/` if it fits under 49 GB, checked against the pack's SHA-256; otherwise the parts are renamed into `.big/` as they are | the raw size on this Mac until uploaded and evicted |

Each record afterwards carries `format: 2`, `by: <this version>`, and `upgraded_from` (the old
format, writer and form).

Archives made **by hand or by another tool**, outside `claude-archive/`, are not upgraded here.
They are adopted with archive-icloud's `import`; see that skill's "Archives made by hand" section.
Find them with `registry`. Then look in the iCloud Drive root for `<repo>_archive` folders, and
search the repo docs for `com~apple~CloudDocs`.

## Scope

| Command | Upgrades |
|---|---|
| `upgrade <path>...` | only the v1 entries under those paths; no relocate, no park |
| `upgrade` (or `--repo DIR`) | the whole archive of one repo: relocate + every v1 entry + park |
| `upgrade --all` | every archive in `claude-archive/registry/`, including repos not on this Mac (park only for repos on this Mac) (done through the iCloud copy of the manifest; that repo's ICLOUD.md catches up on its next run, or with `verify --fix` there) |

An archive made before the registry existed is not in `--all` until registered: run
`registry --scan <folder that holds the repo>`. `registry` lists any unregistered folder.

## Procedure

1. Run `registry` (and `registry --scan` if it lists unregistered folders), then the same upgrade command with `--plan`.
2. Show the user the plan. It lists, per archive:
   - every step and anything it will REFUSE
   - what must be downloaded first
   - the free space each step needs on this Mac

   Ask before going on. `--plan` changes nothing.
3. Check free disk against the largest `needs … free` line. If space is short, say so. Run the upgrade
   in parts (by path), with `upload-status` and `evict` between parts.
4. Run the upgrade without `--plan`. Relay its output and SUMMARY.
5. Run `verify` in each upgraded repo that is on this Mac, and relay the result. Then follow
   archive-icloud's rule 7 (upload-status, then evict) for any unpacked files.
6. If it was interrupted: run `verify`, report, then `verify --fix`. Run the same upgrade again; it
   resumes. Never move or delete archive files by hand.
