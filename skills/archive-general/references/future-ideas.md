# Future upgrade ideas

Ideas discussed but not built. Nothing here is current behaviour; do not act on it as an instruction. Each idea needs its own design, plan, tests and frozen release before use.

## 1. Zip mode for folders with many files

### Background (2026-10-26)

Archiving the iOS Simulator folders (about 36,000 small files) ran at under one file per second and kept slowing down. A manual test zipped `~/Library/Developer/Xcode/macOS DeviceSupport` (2,295 files, 2.9 GB → 1.07 GB), checked the zip by unpacking it and comparing every file, then archived the single zip: about 2¼ minutes in total instead of an estimated 48.

Profiling then showed the main cause was not the number of files on the SSD but the engine rereading both manifests for every file, which made runs quadratic. Release 3.2.0 fixed that with batched locking. Measured on the same real 2,295 files against a disposable SSD target:

| | 3.1.4 | 3.2.0 |
|---|---|---|
| sync | 276 s | 144 s |
| restore | 417 s | 39 s |

After that fix, each file still costs about 26 ms on the ExFAT SSD: a verified copy, about 14 fsyncs, an exclusive rename into place and a durable manifest record. Unpacking a zip on the SSD costs about 12 ms per file on its own (2,000 files in 24.6 s), because every file still has to be created there. So zip mode only pays off when the zip stays a single file on the target.

### Option A: zip as transport, unpacked on the target (decided against for now)

Flow: zip locally → copy the zip → unpack on the target → hash-check every file → publish each into `files/` → record → remove the originals. Restore reverses it.

- Pro: the archive layout and format-2 records stay unchanged, files stay readable in place, and older skill versions can still read and restore.
- Con: measured at best about 1.5× faster than 3.2.0 on an SSD, with extra moving parts (staging area, partial-unpack recovery). Not worth it for local targets. It may still be worth it for cloud targets where each object carries a large per-request cost (Google Drive API, iCloud).

### Option B: keep large folders as one zip on the target (the real speed-up)

- When: a named folder holds at least about 1,000 files. Count matters, not size: one 7 GB file archives quickly, while thousands of tiny files crawl. Keep the threshold configurable, and suggest the mode rather than use it silently.
- Where: `.big/<folder path>.zip` (`.big/` already holds packed data), with one record per member (path, size, SHA-256, mode, mtime) so that `status`, `list`, `read` and single-file `restore` still work per file.
- Safety: check for open files and recent changes first. Zip with `ditto -c -k --sequesterRsrc --keepParent` (or Python `zipfile` with explicit symlink entries). Verify every member's bytes and metadata against the local file before removing anything. Re-check that the source folder did not change while zipping. Remove the originals only after the zip and its records are durable, then park the emptied folders.
- Restore: unpack (the whole folder, or one member), verify each member against its record, reapply mode and mtime, then remove the zip only after every member has come back.
- Bonus: members can keep symlinks (today symlinks are skipped and stay local), and the target avoids per-file cluster waste on ExFAT.
- Cost: files are no longer readable in place on the target. It needs a new format number (format 4) with readers for formats 1–3 kept, an upgrade path if old archives should convert, full regression and mutation coverage, real-SSD round-trip tests and a frozen release.

### Interim manual method (works today)

1. Zip the folder next to itself.
2. Verify the zip by unpacking it to scratch and comparing every file, plus mode and mtime.
3. Wait out the minimum file age (10 minutes).
4. `sync` the zip.
5. Keep the original folder until the user explicitly approves deleting it.

Restore gives back the zip, which then has to be unpacked by hand.

## 2. Parent-folder `.DS_Store` files are lost on folder restore

Seen in both 3.1.4 and 3.2.0: when a parked folder tree comes back on restore, the tidy step deletes the `.DS_Store` files of intermediate parent folders instead of returning them. They hold only Finder view settings, and macOS recreates them, but restore should return them.
