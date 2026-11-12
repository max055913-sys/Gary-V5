"""GitHub stable releases, authenticated metadata and explicit download."""
import base64
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time
from urllib.parse import urlsplit
from urllib.request import build_opener, HTTPRedirectHandler, Request
import uuid

from .storage import ROOT


APPROVED_REPOSITORY = None
TRUSTED_PUBLIC_KEY = None
LIMIT = 1024 ** 3
ASSET = 'Gary_V5_Portable.zip'
SEMVER = re.compile(r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-[0-9A-Za-z.-]+)?')


def version_tuple(version):
    match = SEMVER.fullmatch(version)
    if not match or len(version) > 50:
        raise ValueError('UPDATE_VERSION_INVALID')
    return (*map(int, match.groups()), '-' not in version)


def strict_json(raw):
    def object_pairs(items):
        value = dict(items)
        if len(value) != len(items):
            raise ValueError('UPDATE_DUPLICATE_FIELD')
        return value
    return json.loads(raw, object_pairs_hook=object_pairs)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def open_github(url, *, asset=False):
    from urllib.error import HTTPError
    opener = build_opener(NoRedirect())
    hosts = {'api.github.com'}
    if asset:
        hosts |= {'release-assets.githubusercontent.com', 'objects.githubusercontent.com'}
    for _ in range(4):
        dest = urlsplit(url)
        if (dest.scheme != 'https' or dest.hostname not in hosts or dest.port not in (None, 443)
                or dest.username is not None or dest.password is not None):
            raise ValueError('UPDATE_DESTINATION_REFUSED')
        headers = {'User-Agent': 'Gary-V5', 'Accept': 'application/octet-stream' if asset else 'application/vnd.github+json'}
        try:
            return opener.open(Request(url, headers=headers), timeout=10)
        except HTTPError as error:
            with error:
                if not asset or error.code not in (301, 302, 303, 307, 308):
                    raise
                url = error.headers['Location'] or ''
    raise ValueError('UPDATE_TOO_MANY_REDIRECTS')


class ReleaseDiscovery:
    def __init__(self, repository, key, version, windows_build, architecture, *, opener=open_github):
        if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository):
            raise ValueError('UPDATE_REPOSITORY_INVALID')
        self.api = 'https://api.github.com/repos/' + repository
        self.repository = repository
        self.key = key
        self.version = version
        self.windows_build = windows_build
        self.architecture = architecture
        self.open = opener
        self.selected = None

    def read(self, url, limit, *, asset=False):
        with self.open(url, asset=asset) as response:
            raw = response.read(limit + 1)
        if len(raw) > limit:
            raise ValueError('UPDATE_METADATA_TOO_LARGE')
        return raw

    def asset_url(self, asset_id):
        if type(asset_id) is not int or asset_id <= 0:
            raise ValueError('UPDATE_ASSET_ID_INVALID')
        return f'{self.api}/releases/assets/{asset_id}'

    def verify(self, raw, signature):
        encode = lambda data: base64.b64encode(data).decode('ascii')
        request = {'key': self.key, 'manifest': encode(raw), 'signature': encode(signature)}
        result = subprocess.run([str(ROOT/'runtime/node/node.exe'), str(Path(__file__).with_name('verify_release.mjs'))],
                                input=json.dumps(request).encode(), timeout=10, capture_output=True,
                                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        if result.returncode:
            raise ValueError('UPDATE_SIGNATURE_INVALID')

    def __call__(self):
        self.selected = None
        releases = []
        for page in range(1, 4):
            batch = strict_json(self.read(f'{self.api}/releases?per_page=20&page={page}', 512 * 1024))
            if type(batch) is not list:
                raise ValueError('UPDATE_RELEASE_LIST_INVALID')
            releases.extend(batch)
            if len(batch) < 20:
                break
        else:
            raise ValueError('UPDATE_RELEASE_LIST_TRUNCATED')
        stable = []
        for release in releases:
            tag = release.get('tag_name', '')
            if (release.get('draft') is False and release.get('prerelease') is False
                    and tag.startswith('v') and SEMVER.fullmatch(tag[1:]) and '-' not in tag):
                stable.append((version_tuple(tag[1:]), tag[1:], release))
        if not stable:
            return None
        order, version, release = max(stable, key=lambda item:item[0])
        if order <= version_tuple(self.version):
            return None
        assets = release['assets']
        def asset(name):
            matches = [x for x in assets if x['name'] == name]
            if len(matches) != 1:
                raise ValueError('UPDATE_RELEASE_INCOMPLETE')
            return matches[0]
        raw = self.read(self.asset_url(asset('gary-update.json')['id']), 65536, asset=True)
        signature = self.read(self.asset_url(asset('gary-update.sig')['id']), 64, asset=True)
        self.verify(raw, signature)
        manifest = strict_json(raw)
        if (manifest.get('schema') != 'gary-update-v1' or manifest.get('product') != 'Gary'
                or manifest.get('repository') != self.repository or manifest.get('channel') != 'stable'
                or manifest.get('version') != version):
            raise ValueError('UPDATE_SCOPE_INVALID')
        expires = datetime.fromisoformat(manifest['expires_at'])
        if expires <= datetime.now(timezone.utc):
            raise ValueError('UPDATE_MANIFEST_EXPIRED')
        if (manifest['architecture'] != self.architecture or type(manifest['min_windows_build']) is not int
                or manifest['min_windows_build'] > self.windows_build):
            raise ValueError('UPDATE_WINDOWS_INCOMPATIBLE')
        package = asset(ASSET)
        size, sha = manifest['bytes'], manifest['sha256']
        notes = manifest['notes_fr']
        if (manifest['asset'] != ASSET or type(size) is not int or not 0 < size <= LIMIT
                or package['size'] != size or not re.fullmatch(r'[a-f0-9]{64}',sha)
                or not isinstance(notes,str) or len(notes)>5000):
            raise ValueError('UPDATE_PACKAGE_METADATA_INVALID')
        self.selected = (version, raw, signature, expires, package['id'], size, sha)
        return {'version':version,'notes':notes,'bytes':size}

    def download(self, version, directory):
        if self.selected is None or self.selected[0] != version:
            raise ValueError('UPDATE_OFFER_STALE')
        _, raw, signature, expires, asset, size, sha = self.selected
        self.verify(raw, signature)
        if expires <= datetime.now(timezone.utc) or version_tuple(version) <= version_tuple(self.version):
            raise ValueError('UPDATE_OFFER_STALE')
        directory = Path(directory)
        directory.mkdir(parents=True,exist_ok=True)
        if directory.is_symlink() or directory.is_junction():
            raise ValueError('UPDATE_STAGING_REFUSED')
        temporary = directory / (uuid.uuid4().hex + '.part')
        try:
            digest = hashlib.sha256()
            received = 0
            deadline = time.monotonic() + 900
            with self.open(self.asset_url(asset),asset=True) as response, temporary.open('xb') as output:
                while chunk := response.read(65536):
                    received += len(chunk)
                    if received > size or time.monotonic() > deadline:
                        raise ValueError('UPDATE_DOWNLOAD_LIMIT')
                    digest.update(chunk)
                    output.write(chunk)
            if received != size or digest.hexdigest() != sha:
                raise ValueError('UPDATE_SHA256_MISMATCH')
            verified = temporary.with_suffix('.zip')
            with verified.with_suffix('.json').open('xb') as manifest:
                manifest.write(raw)
            with verified.with_suffix('.sig').open('xb') as detached:
                detached.write(signature)
            temporary.rename(verified)
            return verified
        finally:
            temporary.unlink(missing_ok=True)
