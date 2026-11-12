import hashlib
import base64
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import unittest
import zipfile

from maintenance_transaction import OWNER, SCHEMA, recover, uninstall, update


class MaintenanceTests(unittest.TestCase):
    def setUp(self):
        base = Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()
        self.root = base/'gary'
        self.app = self.root/'App'
        self.app.mkdir(parents=True)
        (self.root/'Gary.installation').write_bytes(OWNER)
        (self.app/'old.txt').write_bytes(b'old')
        self.data = self.root/'Data'
        self.data.mkdir()
        self.db = self.data/'prototype.v1.sqlite'
        with closing(sqlite3.connect(self.db)) as db, db:
            db.execute('CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT)')
            db.executemany('INSERT INTO metadata VALUES(?,?)',[('version',SCHEMA),('fixture','retained')])
        for relative in ('private/fixture.dpapi','cache/extrait.txt','documents/fiche.txt','preferences.json'):
            file = self.data/relative
            file.parent.mkdir(parents=True,exist_ok=True)
            file.write_bytes(b'fictitious '+relative.encode())
        self.before = self.snapshot(self.data)
        self.archive = base/'package.zip'
        self.write_archive()

    def write_archive(self, extra=None):
        with zipfile.ZipFile(self.archive,'w') as archive:
            archive.writestr('Gary.pyw','stable launcher remains installed')
            archive.writestr('App/v5/release-version.json',json.dumps({'version':'5.0.1'}))
            if extra:
                archive.writestr(extra,b'invalid')
        self.sha = hashlib.sha256(self.archive.read_bytes()).hexdigest()

    def snapshot(self,directory):
        return {p.relative_to(directory):p.read_bytes() for p in directory.rglob('*') if p.is_file()}

    def auth(self):
        return '5.0.1',self.sha,SCHEMA

    def apply(self, confirmed=True, stopped=lambda:True, probe=lambda app:True, authenticate=None):
        return update(self.root,self.archive,authenticate or self.auth,confirmed,stopped,probe)

    def test_success_with_prior_backup(self):
        def probe(app):
            self.assertEqual(self.snapshot(self.root/'Maintenance/backup-Data'),self.before)
            return (app/'v5/release-version.json').is_file()
        work=self.apply(probe=probe)
        self.assertTrue((work/'committed').is_file())
        self.assertEqual((work/'previous-App/old.txt').read_bytes(),b'old')
        self.assertEqual(self.snapshot(self.data),self.before)
        self.assertEqual(recover(self.root,lambda:True),'COMMITTED')

    def test_real_signature_before_replacement(self):
        app=Path(__file__).resolve().parents[1]/'payload/App/v5'
        node=Path(os.environ.get('GARY_BUILD_NODE', app/'runtime/node/node.exe'))
        verifier=app/'gary_v5/verify_release.mjs'
        manifest=json.dumps({'version':'5.0.1','sha256':self.sha,'data_schema':SCHEMA}).encode()
        key,signature=json.loads(subprocess.check_output([str(node),'-e',"""
const {generateKeyPairSync,sign}=require('node:crypto');
const {publicKey,privateKey}=generateKeyPairSync('ed25519');
const raw=require('node:fs').readFileSync(0);
console.log(JSON.stringify([publicKey.export({type:'spki',format:'pem'}),sign(null,raw,privateKey).toString('base64')]));
"""],input=manifest))
        def authenticate(raw):
            args={'key':key,'manifest':base64.b64encode(raw).decode(),'signature':signature}
            if subprocess.run([str(node),str(verifier)],input=json.dumps(args).encode()).returncode:
                raise ValueError('SIGNATURE_INVALID')
            parsed=json.loads(raw)
            return parsed['version'],parsed['sha256'],parsed['data_schema']
        with self.assertRaisesRegex(ValueError,'SIGNATURE_INVALID'):
            self.apply(authenticate=lambda:authenticate(manifest+b' '))
        self.assertFalse((self.root/'Maintenance').exists())
        self.apply(authenticate=lambda:authenticate(manifest))
        self.assertEqual(self.snapshot(self.data),self.before)

    def test_failed_probe_restores_application(self):
        with self.assertRaisesRegex(ValueError,'MAINTENANCE_PROBE_FAILED'):
            self.apply(probe=lambda app:False)
        self.assertEqual((self.app/'old.txt').read_bytes(),b'old')
        self.assertEqual(self.snapshot(self.data),self.before)

    def test_interruption_after_first_rename(self):
        work=self.root/'Maintenance'
        work.mkdir()
        self.app.rename(work/'previous-App')
        self.assertEqual(recover(self.root,lambda:True),'RESTORED')
        self.assertEqual((self.app/'old.txt').read_bytes(),b'old')

    def test_interruption_before_transaction(self):
        self.assertEqual(recover(self.root,lambda:True),'NO_REPLACEMENT')
        self.assertEqual((self.app/'old.txt').read_bytes(),b'old')
        self.assertEqual(self.snapshot(self.data),self.before)

    def test_interruption_after_new_application_rename(self):
        work=self.root/'Maintenance'
        work.mkdir()
        self.app.rename(work/'previous-App')
        self.app.mkdir()
        (self.app/'new.txt').write_bytes(b'not committed')
        self.assertEqual(recover(self.root,lambda:True),'RESTORED')
        self.assertEqual((self.app/'old.txt').read_bytes(),b'old')
        self.assertEqual((work/'failed-App/new.txt').read_bytes(),b'not committed')
        self.assertEqual(self.snapshot(self.data),self.before)

    def test_no_consent_or_running(self):
        with self.assertRaisesRegex(ValueError,'CONFIRMATION_REQUIRED'):
            self.apply(confirmed=False)
        with self.assertRaisesRegex(ValueError,'MAINTENANCE_ACTIVE'):
            self.apply(stopped=lambda:False)
        self.assertFalse((self.root/'Maintenance').exists())

    def test_incompatible_schema_blocks_replacement(self):
        with self.assertRaisesRegex(ValueError,'MIGRATION_UNSUPPORTED'):
            self.apply(authenticate=lambda:('5.0.1',self.sha,'future-schema'))
        self.assertTrue((self.app/'old.txt').exists())

    def test_tampered_archive_does_not_reach_probe(self):
        with self.archive.open('ab') as out:
            out.write(b'alteration')
        with self.assertRaisesRegex(ValueError,'HASH_INVALID'):
            self.apply(probe=lambda app:self.fail('unverified code reached probe'))
        self.assertTrue((self.app/'old.txt').exists())

    def test_archive_cannot_replace_data(self):
        self.write_archive('App/Data/fixture.txt')
        with self.assertRaisesRegex(ValueError,'ARCHIVE_PATH'):
            self.apply()
        self.assertEqual(self.snapshot(self.data),self.before)

    def test_uninstall_preserves_data_and_refuses_unknown_root(self):
        calls=[]
        marker=self.root/'Gary.installation'
        marker.write_bytes(b'foreign')
        with self.assertRaisesRegex(ValueError,'NOT_OWNED'):
            uninstall(self.root,True,lambda:True,lambda:calls.append(True))
        marker.write_bytes(OWNER)
        uninstall(self.root,True,lambda:True,lambda:calls.append(True))
        self.assertEqual(calls,[True])
        self.assertFalse(self.app.exists())
        self.assertEqual(self.snapshot(self.data),self.before)


if __name__ == '__main__':
    unittest.main()

