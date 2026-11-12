"""Staged application replacement. Only an external, trusted caller may drive it."""
import hashlib
from contextlib import closing
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sqlite3
import stat
import zipfile

OWNER = b'Gary.Windows.PerUser.v1\n'
SCHEMA = 'gary_v5_store_v1'
MAX_EXPANDED = 2 * 1024**3


def check_path(path):
    if path.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
        raise ValueError('MAINTENANCE_REPARSE_POINT')


def check_tree(path):
    check_path(path)
    for current, dirs, files in os.walk(path, followlinks=False):
        for name in dirs + files:
            check_path(Path(current) / name)


def check_owner(root):
    for parent in (root,*root.parents):
        check_path(parent)
    marker = root / 'Gary.installation'
    check_path(marker)
    if marker.read_bytes() != OWNER:
        raise ValueError('MAINTENANCE_NOT_OWNED')


def check_data(data):
    if not data.exists():
        return
    check_tree(data)
    db = data / 'prototype.v1.sqlite'
    if db.exists():
        with closing(sqlite3.connect(db.as_uri()+'?mode=ro',uri=True)) as conn:
            if (conn.execute('PRAGMA integrity_check').fetchone() != ('ok',)
                    or conn.execute("SELECT value FROM metadata WHERE key='version'").fetchone() != (SCHEMA,)):
                raise ValueError('MAINTENANCE_SCHEMA_OR_INTEGRITY')


def unpack(archive, target):
    with zipfile.ZipFile(archive) as package:
        entries = package.infolist()
        if sum(e.file_size for e in entries) > MAX_EXPANDED:
            raise ValueError('MAINTENANCE_ARCHIVE_LIMIT')
        for entry in entries:
            parts = entry.filename.split('/')
            if parts == ['Gary.pyw'] or parts[0] == 'MaintenanceRuntime':
                continue  # Stable launcher and maintenance runtime are not replaced.
            if (parts[0] != 'App' or len(parts) < 2 or
                    any(not p or p in ('.','..') or p[-1] in '. ' or any(c in p for c in '\\:') for p in parts)
                    or any(p.casefold() in {'data','private','source_accounts'} or
                           p.lower().endswith(('.dpapi','.sqlite','.sqlite-wal','.sqlite-shm')) for p in parts)
                    or stat.S_ISLNK(entry.external_attr >> 16)):
                raise ValueError('MAINTENANCE_ARCHIVE_PATH')
            path = target.joinpath(*PurePosixPath(entry.filename).parts)
            if any(os.path.isreserved(part) for part in parts):
                raise ValueError('MAINTENANCE_ARCHIVE_PATH')
            path.parent.mkdir(parents=True,exist_ok=True)
            with package.open(entry) as incoming, path.open('xb') as out:
                shutil.copyfileobj(incoming,out)


def recover(root, stopped):
    """Restore the old App after interruption. No automatic database restore."""
    check_owner(root)
    if not stopped():
        raise ValueError('MAINTENANCE_ACTIVE')
    work = root/'Maintenance'
    if not work.exists():
        return 'NO_REPLACEMENT'
    check_tree(work)
    previous, active = work/'previous-App', root/'App'
    if (work/'committed').exists():
        return 'COMMITTED'
    if previous.exists():
        if active.exists():
            active.rename(work/'failed-App')
        previous.rename(active)
        return 'RESTORED'
    return 'NO_REPLACEMENT'


def update(root, archive, authenticate, confirmed, stopped, probe):
    """Authenticate returns the signed version, digest and schema. No archive code before verification."""
    root = Path(root).absolute()
    if confirmed is not True:
        raise ValueError('MAINTENANCE_CONFIRMATION_REQUIRED')
    check_owner(root)
    version, expected_sha, schema = authenticate()
    if schema != SCHEMA:
        raise ValueError('MAINTENANCE_MIGRATION_UNSUPPORTED')
    if not stopped():
        raise ValueError('MAINTENANCE_ACTIVE')
    app, data = root/'App', root/'Data'
    check_tree(app)
    check_data(data)
    work = root/'Maintenance'
    if work.exists():
        raise ValueError('MAINTENANCE_RECOVERY_REQUIRED')
    needed = sum(f.stat().st_size for f in data.rglob('*') if f.is_file())
    if shutil.disk_usage(root).free < Path(archive).stat().st_size + needed + MAX_EXPANDED:
        raise ValueError('MAINTENANCE_DISK_SPACE')
    work.mkdir()
    sealed = work/'package.zip'
    with Path(archive).open('rb') as incoming,sealed.open('xb') as out:
        shutil.copyfileobj(incoming,out)
    with sealed.open('rb') as stream:
        if hashlib.file_digest(stream,'sha256').hexdigest() != expected_sha:
            raise ValueError('MAINTENANCE_HASH_INVALID')
        stream.seek(0)
        unpack(stream, work/'staged')
    staged = work/'staged/App'
    installed = json.loads((staged/'v5/release-version.json').read_text(encoding='utf8'))
    if installed.get('version') != version:
        raise ValueError('MAINTENANCE_VERSION_MISMATCH')
    if data.exists():
        shutil.copytree(data,work/'backup-Data')
        check_data(work/'backup-Data')
    if not stopped():
        raise ValueError('MAINTENANCE_ACTIVE')
    app.rename(work/'previous-App')
    try:
        staged.rename(app)
        if not probe(app):
            raise ValueError('MAINTENANCE_PROBE_FAILED')
        with (work/'committed').open('xb') as marker:
            marker.flush()
            os.fsync(marker.fileno())
    except Exception:
        recover(root,stopped)
        raise
    return work


def uninstall(root, confirmed, stopped, remove_integrations):
    """Retire only the owned application and its verified Windows integrations."""
    root = Path(root).absolute()
    if confirmed is not True:
        raise ValueError('MAINTENANCE_CONFIRMATION_REQUIRED')
    check_owner(root)
    app = root/'App'
    check_tree(app)
    if not stopped():
        raise ValueError('MAINTENANCE_ACTIVE')
    remove_integrations()
    retired = root/'Uninstalled-App'
    app.rename(retired)
    # Validate the fully resolved deletion target independently of caller input.
    if retired.resolve() != root.resolve()/'Uninstalled-App':
        raise ValueError('MAINTENANCE_PATH_REFUSED')
    check_tree(retired)
    shutil.rmtree(retired)
    (root/'Gary.installation').unlink()
