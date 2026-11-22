# Direct Google Drive — version 3.2.1 / format 3

This mode uploads file bytes directly to the Google Drive API. It does not rely on the Drive desktop app, a mounted folder, or cache eviction. Keep the user's agreed folder hierarchy and ask before choosing a permanent remote archive folder. Register a dedicated empty folder. To reconnect an existing Archive General API root after local configuration loss, show `target add ... --adopt-existing --plan` first; verify its account, marker and registry identities, then adopt the same folder with explicit authorization. Adoption rebuilds machine-local configuration without moving cloud bytes. Never take over My Drive itself or an unknown folder.

```sh
S=~/.claude/skills/archive-general/archive.py
python3 "$S" target add google-api --kind google-drive-api \
  --drive-folder-id EXISTING_EMPTY_FOLDER_ID --credential-remote gdrive-rw --plan
# After scope/destination authorization:
python3 "$S" target add google-api --kind google-drive-api \
  --drive-folder-id EXISTING_EMPTY_FOLDER_ID --credential-remote gdrive-rw
python3 "$S" target doctor google-api
python3 "$S" --target google-api --repo /path/to/project sync data/finished/
```

Authorization may come from an existing rclone Drive profile with a custom OAuth client, or a private Google authorized-user credential file via `--oauth-file`. Refresh happens directly with Google. Tokens and client secrets are read in memory and never written into manifests, printed, passed on the command line, or committed. Target descriptors reference the credential profile and pin Google's account permission ID, archive folder ID and marker ID. Connecting the wrong account, moving/replacing the remote marker or losing access causes refusal before local removal or recovery.

Changing a default affects new projects only. A filesystem archive retains its recorded target. Filesystem-to-API migration/import is not implemented by this release and is refused rather than guessed. Direct archives are already format 3; checkout folder tidying remains supported. Native iCloud and Google mounted-folder capabilities are unchanged.

## Shared local access: Claude Code and Codex

### Saved permanent destination

On 2026-11-06 the user approved: "call it ElijahArchives. also save it in the skill itself so we know where to make this consistent". The permanent Google Drive archive root is **My Drive / ElijahArchives**, folder ID `1aLr5rpv2kSRqaZO_nVI_HcR9EQRbpHcF`, registered as **`elijah-drive`** on **`iefuy1523@gmail.com`** through `gdrive-rw`. Both agents reuse this registered target for Google Drive archive requests. Validate its live account and marker as usual; preserve the existing default and project bindings. If local configuration is lost, use the planned adoption procedure above for this same folder, never create a replacement with the same name.

On this machine, the existing rclone profiles are `gdrive-ro` (`drive.readonly`) and `gdrive-rw` (`drive`). The intended account is **iefuy1523@gmail.com**. Both agents can read the same private `~/.config/rclone/rclone.conf` through `drive_api.Client`; a missing Google Drive MCP/connector does not mean Drive is unavailable. This is local OAuth access, independent of either agent's cloud connectors. Do not print the config, tokens, client secret, or resumable session URLs.

Start with `rclone listremotes`, then verify Google's live account identity using the engine's client. Configured scope alone does not prove effective permissions or the account:

```sh
python3 - <<'PY'
from pathlib import Path
import sys
skill = (Path.home() / '.claude/skills/archive-general').resolve()
sys.path.insert(0, str(skill))
from drive_api import Client
client = Client({'kind': 'rclone', 'remote': 'gdrive-rw'})
email = client.about()['user']['emailAddress']
print('Google Drive account:', email)
if email != 'iefuy1523@gmail.com':
    raise SystemExit('REFUSED: unexpected Google Drive account; no writes performed')
PY
```

Pass `--credential-remote gdrive-rw` when registering an authorized empty archive folder, as shown above. Inspect `target list` separately: available OAuth credentials do not imply that a permanent API archive target is already registered. Preserve the existing default and any project binding. If the profile is absent or refresh fails, report the precise failure and reconnect that account; do not silently use another profile/account or infer access from Claude's connector alone.

When asked to test capabilities, use one uniquely named disposable folder after verifying the account. Through `Client`, create a folder and file (`create_folder`, `write_bytes`), read back exact bytes (`body`), edit content (`write_bytes` with `existing`), rename with a metadata PATCH, and test Trash/untrash. If deletion testing is authorized, permanently delete only a test-created file with `DELETE /drive/v3/files/<id>`; archive restore itself uses Trash. Check returned file `capabilities` as supporting evidence. Report tested operations separately from untested features such as sharing or Google Docs editing; full OAuth scope does not override individual file permissions.

For an engine smoke test, create an empty subfolder inside that disposable folder and isolate `ARCHIVE_GENERAL_CONFIG` and `ARCHIVE_GENERAL_LOCK_DIR` in a temporary local directory. Resolve the directory first with `Path(tempfile.mkdtemp(...)).resolve()`: macOS `/var` aliases `/private/var`, and an unresolved path triggers the engine's linked-cache-root refusal. Use a disposable repo and aged sample file. Run target registration `--plan`, registration, `target doctor`, `sync`, `read --head`, `verify`, and `restore`; confirm the restored bytes match. Finish each sync/restore with `status`, `tidy --plan`, authorized `tidy`, and another `status`. Keep each command's output in a separate evidence log. Trash the test folder after completion; never touch existing Drive files or change the real default for a test. Stamp retained test reports with the skill version and report format.

Live validation on 2026-11-06 confirmed this account and profile support create/upload/read, content edits, rename, Trash/untrash, permanent deletion of a disposable file, and an isolated engine archive/read/verify/restore round trip. This is historical evidence; recheck identity and current access on future runs.

## Layout and transaction order

The cloud root contains the identity marker, `registry/<project-id>.json` and `repos/<same project path>/`. Raw data lives in `files/<same relative path>`, packed data in `.big/<same path>/`, and retained updates in `.versions/<same path>/`. Local `_archive/` holds only eligible emptied structure. Format-3 manifests record Google object IDs and SHA-256 plus original mode/mtime. The local Drive state directory contains maps, resumable journals and explicit read/staging caches, not a full mirror of archived raw data.

1. Check project scope, instructions, live/open files, source identity, account and remote target marker.
2. Persist a preallocated Google file ID and resumable session privately before uploading chunks. Resume by querying Google's acknowledged byte range. Existing unknown destinations or name/case collisions are refused.
3. Verify the remote object size, SHA-256 and expected location. If Google does not expose SHA-256, stream the remote bytes and hash them. A completed HTTP upload alone does not permit source removal.
4. Save/fsync the local manifest, upload and verify its cloud mirror, write the readable index and registry, then revalidate the target and unchanged source before unlinking the local file.
5. Retain old updates under `.versions/`. An interruption leaves a resumable operation journal and preserves uncertain copies. Use `verify`, inspect, then `verify --fix` or rerun the same authorized operation. Never delete operation journals by hand; their session URLs are private capability data.

A restore exclusively publishes verified returned bytes, restores file metadata, saves the maps, then moves owned consumed cloud objects to Drive Trash. Existing local destinations are refused. Interrupted restores use an object-bound tag to avoid mistaking someone else's file for the restored file. Cloud Trash is recovery space and can still consume Google storage.

`read --head N` streams a sample and leaves the archive record intact. Raw samples use bounded memory and a default 16 MiB byte cap, with an explicit truncation notice for very long lines. A full raw read downloads a checked local read cache; reads over the configured full-read limit require `--full` and sufficient space. Packed sampling downloads/checks its compressed parts before streaming the sample; a sample is not a full original-stream audit.

Locks serialize participating writers on one Mac. Remote manifest content checks detect observed competing writers; metadata-only version changes are allowed, but this release is not a distributed-lock system for concurrent Macs. Unexpected edits, permissions/quota errors and unknown cloud objects stop the operation; no local original is removed to work around them.

From 3.6, one record verification can obtain its file and known ancestor metadata in a GET-only HTTP batch. Each verification gets a fresh snapshot and discards it immediately; folder IDs are still checked against current parent, name, type and Trash state. This reduces network round trips without using stale folder metadata. Optional `restore --into --batch-size 16 --jobs 4` prepares independent verified staging copies with per-file journals, rechecks them, commits their local/cloud maps together, then retires only the committed cloud objects. Map writes are serialized under the project lock; independent post-commit retirements retain every source identity/hash check. An interruption resumes through the same per-file journal protocol. Default restores remain sequential.

## Validation

Use the wire-protocol fault tests plus the full filesystem regression suite. A live test must use its own disposable remote folder and isolated target configuration; never change the SSD default or migrate real project archives as a test. Verify raw/empty/Unicode and packed round trips, interruption/resume, changed source, quota/offline refusal, checksum corruption, cloud-map failure, scoped restore and existing-local-file refusal. Report live cloud tests separately from simulated protocol faults.

Sources: [uploads and safe preallocated-ID retries](https://developers.google.com/workspace/drive/api/guides/manage-uploads), [file metadata and SHA-256](https://developers.google.com/workspace/drive/api/reference/rest/v3/files), [downloads](https://developers.google.com/workspace/drive/api/guides/manage-downloads).
