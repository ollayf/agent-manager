# Safety boundaries

The engine retains the prior file checks: project/path boundaries, protected Git/index files, symlinks, case collisions, recent writes, known open handles, busy markers, database sidecars, v1 overlap, changed-file approval, unknown destinations, disk space, copied SHA-256, packed part/stream hashes, source size/mtime recheck, and restore destination/content checks.

General storage adds a target marker, pinned external volume UUID, offline refusal before repair, archive/project non-overlap, archive-storage symlink refusal, per-index target binding (nested scopes keep their own index; the parent never enters or parks them, and one command never spans two scopes), generic index discovery, provider-aware reporting, cross-filesystem verified publication, and genuine AppleDouble identification.

Local no-replace rename is used when supported. The fallback exclusively creates the destination, checks its contents, flushes data and a receipt, then removes only expected source files. A crash can leave duplicate or partial output. The receipt allows verified repair; uncertain contents are retained. Never describe the fallback as an atomic directory rename.

An archived raw file is made read-only where the filesystem supports it. ExFAT does not supply that POSIX security boundary. The script adds no encryption. Local advisory locks coordinate cooperating processes on this Mac, not arbitrary programs or multiple Macs. Registered targets refuse a file operation when lsof cannot answer. Folder movement also blocks. The explicit legacy-environment compatibility path retains the older permissive file check; use a registered target for the stronger guard.

Original mode and nanosecond mtime are saved before archiving and restored where supported by the destination. ACLs, Finder tags, every filesystem-specific flag and permission enforcement on an external filesystem are not universally guaranteed. Hashes detect changes against trusted records; they do not authenticate metadata that an attacker can also rewrite.

Ordinary checks can avoid fetching evicted raw bytes. `status --deep` hashes them, potentially causing download. A compressed head read checks compressed parts, which can fetch/cache them, but does not validate the entire original stream. An existing full-read temp cache is reused by size; use a fresh deep verification for an integrity audit.

The ExFAT/SSD suite must use disposable repositories and archive roots. Test bytes, metadata round trips to the original filesystem, uncompressed/packed data, update retention, one-file/folder restore, both import modes across filesystems, legacy upgrade, interruptions/publication receipts, corruption, collision refusal, parallel operations, target switching, wrong UUID/marker and offline behavior. Do not unmount or reformat a user's volume to inject a fault; simulate unavailable identities/paths with isolated fixtures.
