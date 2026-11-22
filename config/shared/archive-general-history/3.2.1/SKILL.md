---
name: archive-general
description: Archive named project files to a registered SSD, external disk, local folder, iCloud Drive folder or Google Drive folder/API; read, restore, verify, import and upgrade them through one checked engine. Use for archiving, freeing project space, restoring archived files, selecting a storage drive, investigating interrupted archives, importing old archives, or upgrading their format and parked-folder layout. Supports older ICLOUD indexes. Cloud upload and eviction capabilities depend on the selected provider.
metadata:
  version: 3.2.1
---

# Archive General

Use the one engine for all capabilities. Never move archive data, edit records, or clean up an archive by hand. Preserve the recorded target and agreed project-relative folder hierarchy; ask before acting if a destination or layout choice is unclear.

```sh
S=~/.claude/skills/archive-general/archive.py
python3 "$S" target list
python3 "$S" target doctor                 # validates the current target
python3 "$S" --target NAME sync PATH...
python3 "$S" status [PATH...] [--deep]
python3 "$S" read PATH [--head N | --full]
python3 "$S" restore PATH...
python3 "$S" list [PATH...]
python3 "$S" verify [--fix]
python3 "$S" tidy [PATH...] [--plan]
python3 "$S" registry [--scan DIR...]
python3 "$S" upgrade [PATH... | --all] [--plan]
python3 "$S" import FOLDER --kind mirror|split [--manifest CSV] [--plan]
python3 "$S" upload-status
python3 "$S" evict
python3 "$S" version
```

Global `--target NAME` and `--repo DIR` go **before** the command. Paths belong to the current directory or may be absolute. Check the printed `repo:` and target before acting. Root discovery uses the highest ancestor with `ARCHIVE.md`/its manifest or older `ICLOUD` maps, then Git's root, then the highest ancestor with `CLAUDE.md`.

## Select a drive

Read [references/targets.md](references/targets.md) when registering, choosing or diagnosing storage.

- A target has a name, kind, root and identity marker. External volumes also have a pinned volume UUID. Target validation happens before archive operations and repairs. An offline drive, wrong UUID or missing/mismatching marker is a refusal, never permission to create a fallback directory or drop records.
- `target use NAME` changes the default for **new** projects. Existing projects stay bound to the target in their manifest. A conflicting explicit target is refused; changing a default does not migrate data.
- A project's active archive lives on one target. Do not split its indexes across drives. Existing iCloud archives remain where recorded.
- **Local / SSD:** a verified destination and durable record precede local removal. No cloud upload or eviction applies. Report actual disk-free change; space reclaimed can differ from nominal file size.
- **iCloud:** check `upload-status` and request `evict` only after upload is reported complete. This Mac may hold the only bytes until upload finishes. Check at bounded intervals for about ten minutes; if still pending, report and stop.
- **Direct Google Drive API:** read [references/google-drive-api.md](references/google-drive-api.md) for setup, account identity and recovery. Use a separate `google-drive-api` target and format-3 receipts. Upload resumably, verify cloud size/SHA-256 (download-and-hash if absent), durably save local and verified cloud maps, then recheck and remove the original. Retain the agreed `repos/`, `files/`, `.big/`, `.versions/` and parked-folder hierarchy. Direct mode needs no mounted-folder eviction. Existing filesystem targets never migrate implicitly.
- **Google Drive folder (`google-drive`):** operates through a mounted/synced filesystem folder. File copy/read/restore and hashes work there. Remote upload confirmation and automatic eviction are **unsupported**; report upload as unknown and direct the user to Drive's sync status. Never claim cloud durability or reclaimed cache space from a successful filesystem copy.
- ExFAT does not enforce normal Unix permissions or retain nanosecond times in the archive. Original file mode and mtime are stored in records and reapplied on restore where the destination supports them. APFS-compressed files copy to such targets without macOS's compression flag, which only describes how the Mac stored the bytes. Genuine paired AppleDouble `._` files are filesystem metadata; ordinary similarly named user files and their conflicting siblings stay local with a reserved-name refusal/skip, because macOS/ExFAT can otherwise consume them.

## Archive and sync

1. Act on paths the user named. For “clean up this repo”, inspect and ask which paths; do not invent an archive scope.
2. Read project instructions. On a matching no-delete refusal, quote the rule. Use `--allow-protected` only after an explicit user override. Existing authorization for the same scope is sufficient; do not ask repeatedly.
3. Run `status` if the scope is already archived. Use `sync` for new files. Files changed since the archived version remain local unless the user approves `--update`; show the changed list first. Updated old copies are retained in `.versions/`.
4. Report skipped live files and kept folders. Never lower `--min-age` to bypass a running job. Recent mtime, known open handles, busy markers and database sidecars can skip a file.
5. Relay the SUMMARY and any refusals or post-check problems. Report the target/path, copy verification, provider-specific upload state and actual space result.
6. A `REFUSED` line does not mean nothing moved. Files verified before the refusal are already archived and their originals removed. Check `status` and `ARCHIVE.md` before reporting what happened. Keep each run's output in its own log file; never overwrite an earlier run's log with a retry.
7. A directory the engine cannot read (macOS privacy-protected folders such as `~/Movies/TV` or a Photos library) can stop the run after files were copied, and `--exclude` does not avoid that scan. Ask the user to grant Full Disk Access to their terminal app and restart it, then rerun `status` and finish with `tidy`.
8. Finish every `sync` and `restore` with the tidy step under **Folders**.

Large runs hold the project lock in batches of about 10 seconds, reusing the loaded maps inside a batch and pausing briefly between batches so other agents can get in. Any error rereads the maps from disk. The engine copies through temporary outputs, checks hashes, writes and fsyncs each record, then removes the working file. On filesystems without atomic no-replace rename, an exclusive verified copy and publication journal preserve recoverable state. A failed or interrupted copy can leave known partials for `verify`; do not delete them manually.

## Read and restore

- A missing project file may be archived. Check the owning project's `ARCHIVE.md`/manifest, older `ICLOUD` maps, registry and any older cleanup manifest before saying it is gone.
- `read` normally prints the archived raw file's location; open that path to read it. This does **not** restore it.
- For compressed files use `read --head N` for a sample. Part-hash checks can download/cache compressed parts. A full decompression above 10,000,000,000 original bytes requires `--full` and enough local space. A cached full-read temp copy is reused by size; it is not a fresh audit.
- Restore only when requested. A folder restores the archived entries below it; one file leaves its archived siblings alone. A v1 directory must be restored as the whole entry. Existing local destinations are refused.
- A successful restore verifies bytes, restores recorded file metadata, removes the active archive copy/record, saves the maps, then repairs parked folder structure. Direct Drive moves consumed cloud objects to Trash only after the returned file and maps are verified. It is not a copy-only operation.

## Folders

Eligible emptied folders are parked at `_archive/<same path>` inside the project. This holds structure and Finder metadata, not the archived file bytes. Read/restore/list/status accept the equivalent path under the park prefix.

**Tidy step.** After any `sync` or `restore`, and always after a refused or interrupted run, run `status`. Each `[unparked]` line is a folder the run did not park or bring back. Run `tidy --plan`, show the plan, then run `tidy` within the scope the user already authorized, and recheck `status` until no `[unparked]` line remains. Tidy moves only folder structure, never file bytes. Report folders it kept in place and why.

- A `.keep` file pins a folder and is never archived. Files still in use, recent/external folder changes, inbound symlinks and exclusions can keep folders in place.
- The mover uses mkdir/rmdir and never sweeps normal files into the parked tree. A file arriving during a move prevents rmdir.
- If the project already uses `_archive/` for real files, report the reason; do not take it over. A planned upgrade can choose another plain `--park-dir` name.
- Old checkouts keep folders in place until the upgrade's park step. Use `tidy --plan` for a checkout that is already configured for parking. Never create, move or delete parked folders by hand.

## Verify, recover, upgrade and import

Read [references/recovery-and-upgrade.md](references/recovery-and-upgrade.md) for these less frequent operations.

- After interruption, run `verify`, explain the findings, then use supported `verify --fix` repairs. It can remove verified duplicate/temporary output, repair publication receipts, drop stale records when the local file survives, rewrite maps and finish a half-upgrade. It does not choose between differing/unknown copies.
- A target-identity or offline refusal must be resolved by reconnecting the correct drive. Do not “repair” a disconnected archive as missing data.
- For upgrade/import show `--plan` before changes and honor any explicit approval already given for that scope. With no such authorization, show the plan and ask.
- Never alter a foreign CSV's MD5 to make import pass. A named `--accept-mismatch PATH` requires approval of that particular current file and records both MD5s.
- `read|restore --via-history PATH` checks the authentic frozen runtime's checksums before execution. Missing old releases cannot be fabricated. Format-2 and format-3 records carry the version that actually wrote them.

## Maps, versions and tests

New projects use `ARCHIVE.md` and `ARCHIVE.manifest.jsonl`; legacy projects retain their `ICLOUD` filenames. The archive mirrors the manifest; `registry/` lists archives on the selected target. Do not hand-edit these files. Human prose above the first index table is preserved; leave the Root and park-setting lines intact.

Locks coordinate participating writers on one Mac, not independent Macs or arbitrary file editors. Hashes detect changes against a trusted record; they do not encrypt files or authenticate an attacker-rewritten manifest. See [references/safety.md](references/safety.md) for boundaries and checks.

Ideas discussed but not built (such as zip mode for folders with many files) are in [references/future-ideas.md](references/future-ideas.md); they are not current behaviour.

Run the automated suites, mutation checks, independent sandbox workflows and real-SSD disposable-file tests after engine changes. Freeze the actual runtime and this skill with SHA256SUMS only after validation. Keep authentic released bytes unchanged in `.history/`; never rewrite a released snapshot.
