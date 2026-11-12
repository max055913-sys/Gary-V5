"""Weekly update discovery state. No clinical dependency or install authority."""
import json
from pathlib import Path
import threading
import time


WEEK = 7 * 86400
RETRY = 3600


class UpdateSchedule:
    def __init__(self, path, version, discover=None, clock=time.time):
        self.path = Path(path)
        self.version = version
        self.discover = discover
        self.clock = clock
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.busy = False
        self.offer = None
        self.verified = None
        self.archive = None
        self.error = None
        self.state = {'automatic': True, 'last_success': None, 'retry_after': 0, 'ignored': None}
        if self.path.is_file():
            self.state.update(json.loads(self.path.read_text(encoding='utf8')))

    def _save(self):
        temporary = self.path.with_suffix('.tmp')
        temporary.write_text(json.dumps(self.state), encoding='utf8')
        temporary.replace(self.path)

    def status(self):
        with self.lock:
            return {**self.state, 'version': self.version, 'configured': self.discover is not None,
                    'busy': self.busy, 'offer': self.offer, 'error': self.error, 'verified': self.verified,
                    'period_days': 7}

    def preferences(self, data):
        with self.lock:
            if set(data) == {'automatic'} and type(data['automatic']) is bool:
                self.state['automatic'] = data['automatic']
            elif set(data) == {'ignore'} and self.offer and data['ignore'] == self.offer['version']:
                self.state['ignored'] = data['ignore']
            else:
                raise ValueError('UPDATE_PREFERENCE_INVALID')
            self._save()
        return self.status()

    def check(self, manual=False):
        with self.lock:
            now = self.clock()
            last = self.state['last_success']
            if not self.discover or self.busy or now < self.state['retry_after']:
                return False
            if not manual and (not self.state['automatic'] or last is not None and now < last + WEEK):
                return False
            self.busy = True
            self.verified = None
            threading.Thread(target=self._discover, daemon=True).start()
            return True

    def _discover(self):
        try:
            offer = self.discover()
            with self.lock:
                self.offer = offer
                self.error = None
                self.state.update(last_success=self.clock(), retry_after=0)
                self._save()
        except Exception:
            with self.lock:
                self.offer = None
                self.error = 'UPDATE_CHECK_FAILED'
                self.state['retry_after'] = self.clock() + RETRY
                self._save()
        finally:
            with self.lock:
                self.busy = False

    def run(self):
        while not self.stop.is_set():
            self.check()
            self.stop.wait(60)

    def download(self, version):
        with self.lock:
            if self.busy or not self.offer or version != self.offer['version']:
                raise ValueError('UPDATE_OFFER_STALE')
            self.busy = True
            self.verified = None
            self.error = None
            threading.Thread(target=self._download,args=(version,),daemon=True).start()

    def _download(self, version):
        try:
            archive = self.discover.download(version,self.path.parent.parent/'Updates')
            with self.lock:
                self.verified = version
                self.archive = archive
        except Exception:
            with self.lock:
                self.error = 'UPDATE_DOWNLOAD_FAILED'
        finally:
            with self.lock:
                self.busy = False

    def install(self, version, launch):
        with self.lock:
            if self.busy or not self.verified or version != self.verified or self.archive is None:
                raise ValueError('UPDATE_OFFER_STALE')
            process = launch(self.archive.name)
            self.busy = True
            threading.Thread(target=self._wait_install,args=(process,),daemon=True).start()

    def _wait_install(self, process):
        code = process.wait()
        with self.lock:
            self.busy = False
            if code:
                self.error = 'UPDATE_INSTALL_FAILED'
