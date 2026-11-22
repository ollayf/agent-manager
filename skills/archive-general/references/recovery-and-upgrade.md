# Recovery, upgrade and import

Use the same `archive.py` engine. There is no separately installed upgrade skill.

## Recovery

Run `verify` and report its findings before `verify --fix`. An offline/wrong-target refusal precedes verification and must never be treated as missing archive bytes.

Supported repairs include torn manifest tails; stale summaries/mirrors; publication receipts whose copies can be verified; a matching duplicate working file; a stale record with a surviving local file; known partial outputs; and a legacy entry partly moved into format 2. Publication repair never erases unknown contents of a partial directory or an inode that replaced a partial file. A nonempty uncertain publication tree can therefore require a person to inspect it.

Changed or corrupt copies, unknown orphans, conflict copies, ghost roots and normal files inside the parked structure are reported and preserved. `verify --fix` does not perform normal folder parking; `tidy --plan`, then `tidy`, does that for a configured checkout.

## Upgrade

1. Inspect `status` and the selected target's `registry`. `registry --scan DIR...` finds older local indexes and registers their archives.
2. Show `upgrade --plan` for the requested paths, one project, or `--all`. Describe each conversion, refusal, space cost and provider upload wait. Ask only when the scope lacks explicit approval.
3. Run the same scope. Convert v1 entries resumably, save the park setting, and relocate an older flat archive root last. Local disks require no upload wait. Native iCloud root moves wait for upload; Google Drive remote upload cannot be verified automatically, so archive-data conversion and relocation steps are refused; checkout-only parking can still run.
4. Verify every affected local project and relay summaries. Report provider-specific upload and space state accurately.

Existing indexes keep their old filenames and storage records. New projects use generic filenames. A default-target change is not a migration of an existing project.

## Import

Show an import plan and honor existing explicit authorization. Mirror import maps files through optional CSV path/archive_path rows, checks size/MD5, uses a durable journal, records SHA-256 and imported_from, and adds imported_to without deleting CSV rows. Files with no supplied row or local/archive collisions are refused. Links and iCloud placeholders are not treated as original file data.

Split import verifies part hashes and the full decompressed stream before and after the move. Its manifest and scripts are retained under imported/. A post-move check failure must say that the parts moved but remain unrecorded. Cross-filesystem moves use checked exclusive copies and preserve recoverable publication state.

Do not fix mismatches by editing the foreign manifest. `--accept-mismatch PATH` accepts only a named mirror-file MD5 mismatch after user confirmation, preserving both values in provenance.

## Move

Version 3.5 moves archived files without passing them through the project: to a new folder layout, to another target, or both (for example a Google Drive archive onto the SSD). Plan first and get authorization for the whole move.

1. Write down every source record (path, size, sha256, mode, mtime_ns) by reading the source indexes; decide each file's new path. Check the destination drive has room for the staged copy.
2. `restore PATHS --into STAGING` from each source (project root or scope). STAGING must be a plain folder outside the project and outside every target; put it on the destination drive. Each file is verified against its record before the old archive copy and record are consumed (Drive objects go to Drive Trash). Empty parked folders of the moved paths are retired instead of moved back into the project. Interrupted Drive restores resume into the same folder with `verify --fix`.
3. Build MOVE.csv with columns `path` (new path inside the destination scope), `archive_path` (absolute staged file), `bytes`, `sha256`, `mode` (octal) and `mtime_ns` from step 1. `import STAGING --kind mirror --manifest MOVE.csv --plan` from the destination scope, then without `--plan`. Every staged file needs a row; a SHA-256 mismatch is refused and the file stays. The CSV's mode and mtime are recorded, because staging on ExFAT keeps neither.
   For a whole direct-Drive project retaining the same root and relative paths, run `retarget SSD_NAME --plan` and then `retarget SSD_NAME` before import (3.6+). It requires matching empty local/cloud indexes and an available registered SSD. It refuses occupied destinations, nested scopes and pending operations. With approval to retire a specifically identified unstarted upload, `--cancel-unstarted` cancels only a prepared intent with no allocated cloud objects and a surviving local original; that original is left alone. The empty cloud index remains historical. An interruption leaves a versioned transaction that the next non-plan command completes after checking both target identities and unchanged source maps.
4. `scope remove FOLDER` for each emptied source scope (refused while it has an index or parked files). Then `verify` and `status` (no `[unparked]`) on the source and destination, and spot-check `read` of moved paths.

Staged files are the only copy between steps 2 and 3, exactly as a restored file in the project would be. Keep the staging folder until the import reports `refused: 0` and verify is clean.

## Frozen readers

`read|restore --via-history` selects a recorded writer's authentic runtime, checks every SHA256SUMS entry and supplies an absolute project path. Released 2.3.1 bytes were retained unchanged. Earlier originals were unavailable during reconstruction, so their tests remain explicitly skipped. The new runtime is frozen with its storage adapter and Swift helper as well as its instructions; it must not import future mutable adapter code.
