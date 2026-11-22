# Storage targets

Filesystem targets use a mounted/local path. Direct Google Drive API targets use a pinned account, folder ID and remote marker; see [google-drive-api.md](google-drive-api.md). The two Google modes have different guarantees and never migrate implicitly.

```sh
S=~/.claude/skills/archive-general/archive.py
python3 "$S" target add my-ssd --root "/Volumes/<SSD name>/Archives" --kind local --removable --default
python3 "$S" target add icloud --root "$HOME/Library/Mobile Documents/com~apple~CloudDocs/GeneralArchives" --kind icloud
python3 "$S" target add google --root "/actual/mounted/Google Drive/folder/GeneralArchives" --kind google-drive
python3 "$S" target list
python3 "$S" target doctor my-ssd
python3 "$S" target use my-ssd
python3 "$S" --target my-ssd --repo /path/to/project sync data/old/
```

Use an existing provider mount, and choose a new empty archive subfolder. The command refuses an unmarked nonempty directory, a symlink root, a home/volume/filesystem root, an existing name bound to another directory, or a different existing marker. A native iCloud target must be in the actual iCloud Drive directory.

Machine-local configuration is `~/.config/archive-general/targets.json`. The archive root contains `.archive-general-target.json`. The target descriptor is saved in each new project's manifest and mirrored with its records. A disconnected drive must not cause creation of a lookalike folder on the internal disk. The marker and, for external disks on macOS, mounted volume UUID are validated repeatedly. Losing/replacing the marker is a refusal; do not generate a replacement over existing archive data.

Changing the default affects new projects only. A bound project selects its recorded target even if another target is the new default. An explicit conflicting target is refused. Moving a drive to a differently named mount or relocating an archive to a different target requires deliberate reconciliation; the tool does not guess or migrate on a default change.

To send part of a project to another target, make that folder a nested scope: `scope add FOLDER --to TARGET` (3.3+). The folder gets its own index bound to TARGET; the project's index and its existing records stay where they are. A scope is never created over files the parent already archived, and the binding of either index never changes afterwards. Its emptied folders park in the project's `_archive/<scope path>/` (3.4+), so parked structure stays in one tree.

Local targets have no automatic raw-file size limit. Explicit `--pack` uses split zstd parts; FAT32 targets have a conservative filesystem file-size bound. iCloud targets retain the conservative 49,000,000,000-byte raw limit from the prior engine. `ARCHIVE_GENERAL_FILE_LIMIT` and `ARCHIVE_GENERAL_PART_SIZE` can configure limits; use small values only in isolated tests.

ExFAT may synthesize permissions, round timestamps, and store metadata in paired AppleDouble files. The manifest keeps original file metadata independently. The tool checks file bytes, not the fiction that an ExFAT archive copy enforces POSIX read-only permissions. For filesystems without exclusive atomic rename, publication uses O_EXCL/mkdir, streaming copy, hash checks, fsync and a recovery receipt. Interrupted nonempty directory publications with uncertain contents remain for inspection rather than being recursively erased.

For iCloud, macOS upload status and eviction use the included Swift helper. For Google Drive, upload state remains unknown and eviction is refused/unsupported. A Google Drive folder can hold a verified filesystem copy before the Drive app completes remote synchronization. Report this difference, and never promise off-device durability from local copy success.

`ARCHIVE_GENERAL_CONFIG`, `ARCHIVE_GENERAL_ROOT`, and the other `ARCHIVE_GENERAL_*` environment overrides are useful for isolated tests. Old `ICLOUD_ARCHIVE_*` overrides remain compatible. Do not use a test override to bypass a real target's identity checks.

Literal ._ path components and files with an ordinary ._ sibling stay local. This avoids macOS/ExFAT metadata aliasing; rename such user files deliberately before archiving rather than bypassing the guard.
