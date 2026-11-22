"""Storage targets and filesystem safety. No provider login or remote-upload claims."""
from __future__ import annotations
import contextlib
import ctypes
import errno
import fcntl
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import subprocess
import sys
import uuid

SKILL_VERSION = '3.1.2'
MARKER = '.archive-general-target.json'
KINDS = ('local', 'icloud', 'google-drive', 'google-drive-api')
ICLOUD = Path.home() / 'Library/Mobile Documents/com~apple~CloudDocs'


class TargetError(ValueError):
    pass


def apple_double(path):
    path = Path(path)
    if not path.name.startswith('._') or not path.with_name(path.name[2:]).exists() or path.is_symlink():
        return False
    try:
        with path.open('rb') as stream:
            return stream.read(4) == b'\x00\x05\x16\x07'
    except OSError:
        return False


def fsync_dir(path):
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name('.' + path.name + '.tmp-' + uuid.uuid4().hex)
    try:
        with temp.open('x') as stream:
            json.dump(value, stream, indent=2, sort_keys=True)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
        fsync_dir(path.parent)
    finally:
        temp.unlink(missing_ok=True)


def publish(source, destination):
    """Atomic no-replace publication on Darwin/Linux. Never fall back to overwrite."""
    source, destination = Path(source), Path(destination)
    libc = ctypes.CDLL(None, use_errno=True)
    if sys.platform == 'darwin':
        fn = libc.renamex_np
        fn.argtypes = (ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint)
        fn.restype = ctypes.c_int
        rc = fn(os.fsencode(source), os.fsencode(destination), 0x00000004)  # SDK sys/stdio.h RENAME_EXCL
    elif hasattr(libc, 'renameat2'):
        fn = libc.renameat2
        fn.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint)
        fn.restype = ctypes.c_int
        rc = fn(-100, os.fsencode(source), -100, os.fsencode(destination), 1)
    else:
        raise TargetError('this platform cannot publish without replacing a concurrent destination')
    if rc:
        number = ctypes.get_errno()
        raise OSError(number, os.strerror(number), str(destination))
    fsync_dir(destination.parent)
    if source.parent != destination.parent:
        fsync_dir(source.parent)


def safe_remove_tree(path):
    # ExFAT removes a file's ._ metadata companion with the file. A directory
    # listing taken before that unlink can otherwise make shutil.rmtree fail.
    def onerror(function, name, error):
        if not isinstance(error[1], FileNotFoundError):
            raise error[1]
    shutil.rmtree(path, onerror=onerror)


def disk_info(path):
    if sys.platform != 'darwin':
        raise TargetError('removable target identity on this platform requires a supported volume identity adapter')
    try:
        result = subprocess.run(['diskutil', 'info', '-plist', str(path)], capture_output=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise TargetError('cannot confirm volume information: ' + str(error))
    if result.returncode:
        raise TargetError('cannot confirm mounted volume identity: ' + str(path))
    try:
        return plistlib.loads(result.stdout)
    except (ValueError, plistlib.InvalidFileException):
        raise TargetError('cannot parse mounted volume identity: ' + str(path))


def volume_uuid(path):
    # Darwin SDK sys/attr.h: ATTR_VOL_INFO | ATTR_VOL_UUID. Query the mounted
    # filesystem directly on every check, without a slow Disk Arbitration CLI.
    class Attributes(ctypes.Structure):
        _fields_ = [('count', ctypes.c_uint16), ('reserved', ctypes.c_uint16),
                    ('common', ctypes.c_uint32), ('volume', ctypes.c_uint32),
                    ('directory', ctypes.c_uint32), ('file', ctypes.c_uint32), ('fork', ctypes.c_uint32)]
    if sys.platform != 'darwin':
        raise TargetError('volume UUID adapter unavailable on this platform')
    attributes = Attributes(5, 0, 0, 0x80000000 | 0x00040000, 0, 0, 0)
    buffer = ctypes.create_string_buffer(1024)
    fn = ctypes.CDLL(None, use_errno=True).getattrlist
    fn.argtypes = (ctypes.c_char_p, ctypes.POINTER(Attributes), ctypes.c_void_p, ctypes.c_size_t, ctypes.c_ulong)
    fn.restype = ctypes.c_int
    if fn(os.fsencode(path), ctypes.byref(attributes), buffer, len(buffer), 0) or int.from_bytes(buffer.raw[:4], 'little') != 20:
        raise TargetError('cannot confirm mounted volume UUID: ' + str(path))
    return str(uuid.UUID(bytes=buffer.raw[4:20]))


def under(path, parent):
    try:
        Path(path).relative_to(parent)
        return True
    except ValueError:
        return False


def canonical(value):
    path = Path(value).expanduser().absolute()
    if any(ord(c) < 32 or c == '`' for c in str(path)):
        raise TargetError('unsafe target path')
    if path.is_symlink():
        raise TargetError('archive target must not be a symlink: ' + str(path))
    return path.resolve()


class Target:
    def __init__(self, value, managed=True):
        self.value = dict(value)
        self.root = Path(value['root']).expanduser().absolute()
        self.kind = value.get('kind', 'local')
        self.name = value.get('name', 'explicit-root')
        self.managed = managed
        if self.managed and self.kind != 'icloud' and under(self.root, ICLOUD.resolve()):
            raise TargetError('a native iCloud folder requires the icloud target kind')
        if self.kind == 'icloud' and self.managed and not under(self.root, ICLOUD.resolve()):
            raise TargetError('iCloud target is outside native iCloud Drive')
        if self.kind not in KINDS:
            raise TargetError('unknown target kind: ' + self.kind)

    def available(self):
        if self.kind == 'google-drive-api':
            from drive_api import validate_target
            validate_target(self.value)
            if self.root.is_symlink() or self.root.resolve() != self.root:
                raise TargetError('Drive metadata cache path is linked; refusing')
            self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
            return self
        if self.managed:
            if self.root.is_symlink() or not self.root.is_dir() or self.root.resolve() != self.root:
                raise TargetError(f'target {self.name} is offline or moved: {self.root}; nothing repaired or archived')
            marker = self.root / MARKER
            if marker.is_symlink():
                raise TargetError('target identity marker is a symlink; refusing')
            try:
                data = json.loads(marker.read_text())
            except (OSError, ValueError):
                raise TargetError(f'target {self.name} identity marker is missing/invalid; refusing any archive repair or write')
            if (data.get('id'), data.get('kind')) != (self.value.get('id'), self.kind):
                raise TargetError(f'wrong drive or target identity at {self.root}; refusing')
        mount = self.value.get('mount_point')
        if mount:
            if not os.path.ismount(mount):
                raise TargetError('external drive is not mounted: ' + mount)
            if volume_uuid(mount).upper() != self.value.get('volume_uuid', '').upper():
                raise TargetError('wrong volume UUID at ' + mount)
            if not os.access(self.root, os.W_OK):
                raise TargetError('archive volume is read-only: ' + mount)
        elif under(self.root, Path('/Volumes')):
            raise TargetError('an external root must be registered with its volume identity before use')
        return self

    def check_repo(self, repo):
        if under(self.root, repo) or under(repo, self.root):
            raise TargetError('archive target and project must not contain one another')

    def describe(self):
        available = 'available'
        try:
            self.available()
        except (OSError, TargetError) as error:
            available = 'OFFLINE / REFUSED: ' + str(error)
        return f'{self.name}\t{self.kind}\t{self.root}\t{available}'


def config_path():
    return Path(os.environ.get('ARCHIVE_GENERAL_CONFIG', str(Path.home() / '.config/archive-general/targets.json'))).expanduser().absolute()


def load_config():
    try:
        value = json.loads(config_path().read_text())
    except FileNotFoundError:
        return dict(format=1, by=SKILL_VERSION, targets={})
    if value.get('format') != 1 or not isinstance(value.get('targets'), dict):
        raise TargetError('unsupported/malformed target configuration')
    return value


@contextlib.contextmanager
def config_lock():
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path.with_suffix('.lock'), 'a') as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def recognized_archive_base(root):
    found = False
    for registry in (root / 'registry').glob('*.json'):
        try:
            value = json.loads(registry.read_text())
            relative = Path(value['root']).expanduser()
            archive = relative if relative.is_absolute() else root / relative
            if not under(archive, root) or archive.resolve() != archive or registry.is_symlink():
                return False
            with (archive / '.manifest.jsonl').open() as stream:
                header = json.loads(stream.readline(1024 * 1024))
            if header.get('icloud_archive_manifest') != 2 or header.get('id') != value.get('id'):
                return False
            found = True
        except (OSError, ValueError, KeyError):
            return False
    return found


def add_target(name, root, kind, default=False, removable=False, adopt_existing=False, plan=False):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,63}', name):
        raise TargetError('target name must be a short plain name')
    root = canonical(root)
    if root in (Path('/'), Path.home()) or root.parent == Path('/Volumes'):
        raise TargetError('choose a dedicated archive subfolder, not a home, volume or filesystem root')
    if kind == 'icloud' and not under(root, ICLOUD):
        raise TargetError('an iCloud target must be inside the actual iCloud Drive folder')
    mount = None
    info = {}
    if under(root, Path('/Volumes')):
        if len(root.parts) < 4:
            raise TargetError('choose an archive subfolder on the external volume')
        mount = str(Path('/Volumes') / root.parts[2])
    elif removable:
        probe = root
        while not probe.exists():
            probe = probe.parent
        info = disk_info(probe)
        mount = info.get('MountPoint')
    if mount:
        if not os.path.ismount(mount):
            raise TargetError('drive is not mounted; refusing to create a fallback folder: ' + mount)
        info = disk_info(mount)
        if not info.get('VolumeUUID'):
            raise TargetError('volume has no stable UUID')
        if not info.get('WritableVolume', info.get('Writable', True)):
            raise TargetError('volume is read-only')
    if root.exists() and not (root / MARKER).exists():
        nonempty = any(p.name != '.DS_Store' for p in root.iterdir()) if root.is_dir() else True
        if nonempty and (not adopt_existing or not recognized_archive_base(root)):
            raise TargetError('unmarked root is not empty; choose a new folder or explicitly adopt a recognized old archive base')
    if plan:
        print(f'PLAN: register {name} ({kind}) at {root}; write target marker and machine-local configuration only; existing archives stay in place')
        return
    with config_lock():
        config = load_config()
        if name in config['targets'] and Path(config['targets'][name]['root']) != root:
            raise TargetError('target name is already bound to another root; use a new name')
        for other, value in config['targets'].items():
            if other != name and (under(root, Path(value['root'])) or under(Path(value['root']), root)):
                raise TargetError('target roots must not overlap: ' + other)
        marker = root / MARKER
        if marker.is_symlink():
            raise TargetError('target marker must be a plain file')
        if marker.exists():
            value = json.loads(marker.read_text())
            if value.get('format') != 1 or value.get('kind') != kind:
                raise TargetError('existing target marker is incompatible')
            target_id = value['id']
        else:
            if root.exists() and (not root.is_dir() or (any(p.name != '.DS_Store' for p in root.iterdir()) and not adopt_existing)):
                raise TargetError('unmarked root is not empty; choose a new folder to avoid taking over existing data')
            root.mkdir(parents=True, exist_ok=True)
            target_id = str(uuid.uuid4())
            atomic_json(marker, dict(format=1, by=SKILL_VERSION, id=target_id, kind=kind))
        value = dict(name=name, id=target_id, root=str(root), kind=kind, file_limit=49_000_000_000 if kind == 'icloud' else 0)
        if mount:
            value.update(mount_point=mount, volume_uuid=info['VolumeUUID'], filesystem=info.get('FilesystemType', 'unknown'))
            if str(info.get('FilesystemType', '')).lower() in ('msdos', 'fat32'):
                value['file_limit'] = 4 * 1024**3 - 1
        previous = config['targets'].get(name)
        if previous and previous.get('id') != target_id:
            raise TargetError('registered target identity differs; refusing to rebind it')
        target = Target(value).available()
        config['targets'][name] = value
        config['by'] = SKILL_VERSION
        if default or not config.get('default'):
            config['default'] = name
        atomic_json(config_path(), config)
        print(target.describe())
        print('default target: ' + config['default'])
        return target


def target_command(args):
    action = args.target_action
    if action == 'add':
        if args.kind == 'google-drive-api':
            from drive_api import register
            register(args)
            return 0
        if not args.root:
            raise TargetError('filesystem targets require --root')
        add_target(args.name, args.root, args.kind, args.default, args.removable, args.adopt_existing, args.plan)
        return 0
    config = load_config()
    if action == 'use':
        with config_lock():
            config = load_config()
            if args.name not in config['targets']:
                raise TargetError('unknown target: ' + args.name)
            Target(config['targets'][args.name]).available()
            config['default'] = args.name
            config['by'] = SKILL_VERSION
            atomic_json(config_path(), config)
        print('default target for new projects: ' + args.name)
        return 0
    if action == 'list':
        for name, value in sorted(config['targets'].items()):
            print(('* ' if name == config.get('default') else '  ') + Target(value).describe())
        if not config['targets']:
            print('no targets configured: target add NAME --root DIR --kind local|icloud|google-drive')
        return 0
    name = getattr(args, 'name', None) or config.get('default')
    if name not in config['targets']:
        raise TargetError('no configured target selected')
    target = Target(config['targets'][name]).available()
    print(target.describe())
    print('identity marker: verified')
    if target.kind == 'google-drive-api':
        print('Google account and remote folder identity: verified')
        print('direct Drive: resumable uploads, remote SHA-256/size verification, format-3 records before local removal')
        print('remote folder: https://drive.google.com/drive/folders/' + target.value['drive_folder_id'])
        return 0
    if target.value.get('mount_point'):
        print('volume UUID: verified')
    print('filesystem: ' + target.value.get('filesystem', 'mounted folder'))
    print('free bytes: ' + str(shutil.disk_usage(target.root).free))
    if target.value.get('filesystem') == 'exfat':
        print('ExFAT: original mode/mtime are stored in records; archive POSIX permissions and nanosecond timestamps are not assumed. AppleDouble companions are filesystem metadata.')
    if target.kind == 'google-drive':
        print('Google Drive: filesystem copy/read/restore supported; remote upload confirmation and eviction are not implemented. No cloud durability is inferred.')
    return 0


def select_target(name=None, recorded=None, explicit_root=None):
    config = load_config() if not explicit_root or name else dict(targets={})
    if name:
        if name not in config['targets']:
            raise TargetError('unknown target: ' + name)
        chosen = Target(config['targets'][name])
        if recorded and chosen.value.get('id') != recorded.get('id'):
            raise TargetError('project is bound to a different archive target; changing a default does not migrate files')
    elif recorded:
        local = next((v for v in config.get('targets', {}).values() if v.get('id') == recorded.get('id')), None) if recorded.get('kind') == 'google-drive-api' else None
        if local:
            for field in ('kind', 'account_id', 'drive_folder_id', 'drive_marker_id'):
                if local.get(field) != recorded.get(field):
                    raise TargetError('machine-local Drive target identity differs from the project binding')
        chosen = Target(local or recorded)
    elif explicit_root:
        path = canonical(explicit_root)
        if (path / MARKER).is_file():
            value = json.loads((path / MARKER).read_text())
            value.update(root=str(path), name='explicit-root')
            # External roots need their registered UUID descriptor as well.
            config = load_config()
            match = next((x for x in config['targets'].values() if x.get('id') == value.get('id')), None)
            chosen = Target(match or value)
        else:
            chosen = Target(dict(root=str(path), kind='icloud' if under(path, ICLOUD) else 'local', name='explicit-root'), managed=False)
    else:
        default = config.get('default')
        if default not in config['targets']:
            raise TargetError('no archive target configured; use target add NAME --root DIR --kind local|icloud|google-drive')
        chosen = Target(config['targets'][default])
    return chosen.available()


def fingerprint(path):
    import hashlib
    path = Path(path)
    if path.is_symlink():
        raise TargetError('symlink in publication: ' + str(path))
    if path.is_file():
        sha = hashlib.sha256()
        with path.open('rb') as stream:
            for chunk in iter(lambda: stream.read(8 * 1024**2), b''):
                sha.update(chunk)
        return dict(form='file', size=path.stat().st_size, sha256=sha.hexdigest())
    if not path.is_dir():
        raise TargetError('publication source is missing: ' + str(path))
    entries = {}
    for parent, dirs, files in os.walk(path, followlinks=False):
        for name in dirs + files:
            p = Path(parent) / name
            if apple_double(p):
                continue
            rel = p.relative_to(path).as_posix()
            if p.is_symlink():
                raise TargetError('symlink in publication: ' + str(p))
            entries[rel] = dict(form='dir') if p.is_dir() else fingerprint(p)
    return dict(form='dir', entries=entries)


IDENTITY_ATTRIBUTE = b"com.archive-general.publication"


def publication_identity(fd, token=None):
    """An object-bound nonce prevents partial cleanup from trusting a reused inode."""
    if sys.platform != "darwin":
        try:
            if token is not None:
                os.setxattr(fd, IDENTITY_ATTRIBUTE, token.encode())
            return os.getxattr(fd, IDENTITY_ATTRIBUTE).decode()
        except (OSError, AttributeError):
            return None
    libc = ctypes.CDLL(None, use_errno=True)
    if token is not None:
        value = token.encode()
        fn = libc.fsetxattr
        fn.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint32, ctypes.c_int)
        if fn(fd, IDENTITY_ATTRIBUTE, value, len(value), 0, 0):
            return None
    buffer = ctypes.create_string_buffer(128)
    fn = libc.fgetxattr
    fn.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint32, ctypes.c_int)
    fn.restype = ctypes.c_ssize_t
    length = fn(fd, IDENTITY_ATTRIBUTE, buffer, len(buffer), 0, 0)
    return buffer.raw[:length].decode() if length >= 0 else None


def exclusive_copy(source, destination, created=None):
    """Exclusive creation, streaming copy and content verification; source is retained."""
    before = source.stat()
    flags = os.O_RDWR | os.O_CREAT | os.O_EXCL
    fd = os.open(destination, flags, 0o600)
    if created:
        created(os.fstat(fd), fd)
    with os.fdopen(fd, 'wb') as out, source.open('rb') as incoming:
        shutil.copyfileobj(incoming, out, 8 * 1024**2)
        out.flush()
        os.fsync(out.fileno())
    shutil.copystat(source, destination, follow_symlinks=False)
    with destination.open('rb') as stream:
        os.fsync(stream.fileno())
    if (source.stat().st_size, source.stat().st_mtime_ns) != (before.st_size, before.st_mtime_ns) or fingerprint(source) != fingerprint(destination):
        raise TargetError('publication changed or failed content verification; source retained')
    fsync_dir(destination.parent)


def remove_known_source(source, expected):
    """Remove only expected, still-identical source files; unknown additions survive."""
    if not source.exists():
        return
    if expected['form'] == 'file':
        if fingerprint(source) != expected:
            raise TargetError('source changed after publication; retained')
        source.unlink()
        fsync_dir(source.parent)
        return
    for rel, value in sorted(expected['entries'].items(), key=lambda x: len(Path(x[0]).parts), reverse=True):
        p = source / rel
        if not p.exists():
            continue
        if value['form'] == 'file':
            remove_known_source(p, value)
        elif p.is_symlink():
            raise TargetError('source folder became a link; retained')
        else:
            p.rmdir()
    source.rmdir()
    fsync_dir(source.parent)


_native_publish = publish


def publish(source, destination, journal_root=None):
    source, destination = Path(source), Path(destination)
    try:
        return _native_publish(source, destination)
    except OSError as error:
        if error.errno not in (errno.EXDEV, errno.ENOTSUP, errno.EOPNOTSUPP, errno.ENOSYS, errno.EINVAL):
            raise
    expected = fingerprint(source)
    home = Path(journal_root) if journal_root else destination.parent / '.publications'
    home.mkdir(parents=True, exist_ok=True)
    receipt = home / (uuid.uuid4().hex + '.json')
    value = dict(format=1, by=SKILL_VERSION, source=str(source), destination=str(destination), expected=expected, phase='planned')
    atomic_json(receipt, value)
    def created(info, fd):
        token = uuid.uuid4().hex
        identity = publication_identity(fd, token)
        os.fsync(fd)
        value.update(inode=info.st_ino, device=info.st_dev, identity=identity, phase='created')
        atomic_json(receipt, value)
        if os.environ.get('ARCHIVE_GENERAL_FAULT') == 'publish-after-create':
            os._exit(99)
    try:
        if expected['form'] == 'file':
            exclusive_copy(source, destination, created)
        else:
            destination.mkdir()  # exclusive; never reuse a pre-existing destination
            fd = os.open(destination, os.O_RDONLY)
            try:
                created(os.fstat(fd), fd)
            finally:
                os.close(fd)
            for rel, data in sorted(expected['entries'].items(), key=lambda x: (len(Path(x[0]).parts), x[0])):
                p = destination / rel
                if data['form'] == 'dir':
                    p.mkdir()
                else:
                    exclusive_copy(source / rel, p)
            fsync_dir(destination)
        if fingerprint(destination) != expected or fingerprint(source) != expected:
            raise TargetError('publication hash mismatch; source retained')
        value['phase'] = 'copied'
        atomic_json(receipt, value)
        if os.environ.get('ARCHIVE_GENERAL_FAULT') == 'publish-after-copy':
            os._exit(99)
        remove_known_source(source, expected)
        receipt.unlink()
        fsync_dir(home)
    except BaseException:
        # Keep a durable receipt for verified repair. Never recursively erase an
        # unknown partial tree, and never remove a replacement inode.
        raise


def publication_problems(home, scope):
    """Return only this archive's receipts, never another project's or arbitrary paths."""
    result = []
    home, scope = Path(home), Path(scope)
    for receipt in sorted(home.glob('*.json')):
        try:
            value = json.loads(receipt.read_text())
            dest, source = Path(value['destination']), Path(value['source'])
            if value.get('format') != 1 or not under(dest, scope) or not dest.is_absolute() or not source.is_absolute():
                continue
            result.append((receipt, value))
        except (OSError, ValueError, KeyError):
            continue
    return result


def publication_complete(home, source, destination):
    for receipt, value in publication_problems(home, destination):
        if Path(value['destination']) == destination and Path(value['source']) == source and value.get('phase') == 'copied':
            try:
                return fingerprint(destination) == value['expected']
            except (OSError, TargetError):
                return False
    return False


def repair_publication(receipt, value):
    source, dest, expected = Path(value['source']), Path(value['destination']), value['expected']
    dest_ok = dest.exists() and fingerprint(dest) == expected
    source_ok = source.exists() and fingerprint(source) == expected
    if dest_ok:
        if source.exists() and value.get('phase') == 'copied' and under(source, receipt.parent.parent):
            remove_known_source(source, expected)
        receipt.unlink()
        fsync_dir(receipt.parent)
        return
    if not source_ok:
        raise TargetError('publication has no complete verified source; copies left for inspection')
    if dest.exists():
        info = dest.lstat()
        fd = os.open(dest, os.O_RDONLY)
        try:
            identity = publication_identity(fd)
        finally:
            os.close(fd)
        if not value.get('identity') or identity != value['identity'] or info.st_dev != value.get('device'):
            raise TargetError('publication object identity cannot be confirmed; copies retained')
        if dest.is_dir():
            dest.rmdir()  # a nonempty partial tree is preserved for inspection
        else:
            dest.unlink()
        fsync_dir(dest.parent)
    receipt.unlink()
    fsync_dir(receipt.parent)


def reserved_collision(path):
    """Darwin/ExFAT can consume a ._ sibling even when it is ordinary user data."""
    path = Path(path)
    if any(part.startswith('._') for part in path.parts):
        return True
    companion = path.with_name('._' + path.name)
    return companion.exists() and not apple_double(companion)
