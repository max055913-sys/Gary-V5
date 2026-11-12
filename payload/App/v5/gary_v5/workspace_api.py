"""Actions locales de consultation et d'édition, séparées des autorisations API."""
from pathlib import Path
import json
import uuid
import hashlib
from urllib.parse import urlsplit,parse_qs
from .functional_store import FunctionalStore,patient_document_title
from .commercial_supervisor import require
from .live_supervisor import TEST_ROOT
from .live_evidence import manifest_write

class WorkspaceAPI:
    @staticmethod
    def present_draft(draft):
        return {**draft,'versions':[
            {**version,'document_title':patient_document_title(version['text'],draft['title'])}
            for version in draft['versions']]}
    def __init__(self,store,*,sources=None):
        self.store=store;self.data=FunctionalStore(store)
        from .source_service import SourceService
        self.sources=sources or SourceService(store)
        from .source_connectors import SourceConnectors, DocumentaryTools
        self.connectors = SourceConnectors(store)
        self.documentary_tools = DocumentaryTools(self.sources, self.connectors)
    def get(self,path):
        url=urlsplit(path);parts=url.path.split('/');query=parse_qs(url.query)
        require(url.path not in ('/api/local/source-account', '/api/local/professional-browser'), 'PROFESSIONAL_ACCESS_ARCHIVED')
        if url.path=='/api/local/options':return self.data.options()
        if url.path=='/api/local/web-sources':
            from .source_catalog import url_groups
            result = self.sources.read()
            sources = result['value']['sources']
            with self.store.tx() as db:
                result['connectors'] = {source['id']: self.connectors.present(source, self.connectors._read(db, source)) for source in sources}
            result['duplicate_urls'] = [sorted(ids) for ids in url_groups(sources).values() if len(ids)>1]
            return result
        if url.path=='/api/local/source-connector':
            require(set(query)=={'id'} and len(query['id'])==1,'CONNECTOR_FIELDS_REFUSED');return self.connectors.read(query['id'][0])
        if url.path=='/api/local/web-source-text':return self.sources.read_text(query.get('id',[''])[0])
        if url.path=='/api/local/modes':
            from .modes_inspection import inspection
            return inspection(self.store,query.get('module',['AUTO'])[0])
        if url.path=='/api/local/history':return {'items':self.data.histories(query.get('q',[''])[0],query.get('module',[''])[0])}
        if url.path=='/api/local/drafts':return {'items':self.data.drafts()}
        if url.path=='/api/local/drafts/deleted':return {'items':self.data.drafts(deleted=True)}
        if url.path=='/api/local/draft/last-validator':return {'validator':self.data.last_validator()}
        if len(parts)==5 and parts[3]=='history':return self.data.history(parts[4])
        if len(parts)==5 and parts[3]=='draft':return self.present_draft(self.data.draft(parts[4]))
        raise ValueError('LOCAL_ROUTE_ABSENT')
    def post(self,path,data):
        require(urlsplit(path).path not in ('/api/local/source-account', '/api/local/professional-browser'), 'PROFESSIONAL_ACCESS_ARCHIVED')
        require(type(data) is dict,'REQUEST_INVALID')
        if path=='/api/local/web-sources/save':
            return self.connectors.save_public(data)
        if path=='/api/local/source-connector':
            require(set(data)=={'id','value','revision'},'CONNECTOR_FIELDS_REFUSED');return self.connectors.save(data['id'],data['value'],data['revision'])
        if path in ('/api/local/web-sources','/api/local/web-sources/probe'):
            try:
                if path.endswith('/probe'):
                    require(set(data)=={'id','nonce'},'WEB_REQUEST_FIELDS')
                    env=self.connectors.read(data['id'])
                    return self.documentary_tools.execute({'schema':'gary_documentary_tool_v1','source_id':data['id'],'operation':'open_page','configuration_sha256':env['configuration_sha256'],'nonce':data['nonce']})['result']
                require(set(data)=={'value','revision'},'WEB_REQUEST_FIELDS')
                proposed = {source['id']: source for source in data['value']['sources']}
                old_sources = {source['id']: source for source in self.sources.catalog.read()['value']['sources']}
                for identity, previous in old_sources.items():
                    if previous['access_kind'] != 'PUBLIC':
                        require(proposed.get(identity) == previous, 'WEB_HISTORICAL_SOURCE_READ_ONLY')
                    elif identity not in proposed:
                        from .storage import digest
                        account = self.sources.store.root / 'source_accounts' / (digest(identity) + '.dpapi.json')
                        require(not account.exists(), 'WEB_HISTORICAL_SOURCE_READ_ONLY')
                require(all(source['access_kind'] == 'PUBLIC' or old_sources.get(identity) == source
                            for identity, source in proposed.items()), 'WEB_PUBLIC_SOURCE_REQUIRED')
                self.sources.catalog.save(data['value'],data['revision'],remove_module_references=True)
                return self.get('/api/local/web-sources')
            except ValueError as error:
                code=str(error);raise ValueError(code if code=='REVISION_CONFLICT' or (code.startswith(('WEB_','SOURCE_ACCOUNT_')) and __import__('re').fullmatch('[A-Z_]+',code)) else 'WEB_OPERATION_REFUSED') from None
        if path=='/api/local/options':return self.data.options(data['value'],data['revision'])
        if path=='/api/local/history/delete':return self.data.delete_history(data['id'],data['revision'],data.get('confirmed'))
        if path=='/api/local/history/purge':return self.data.purge_history(data['count'],data.get('confirmed'))
        if path=='/api/local/draft/create':return self.data.create_draft(data.get('title','Nouvelle fiche patient'),data.get('text',''),test=self.store.root.is_relative_to(TEST_ROOT))
        if path=='/api/local/draft/save':return self.present_draft(self.data.save_draft(data['id'],data['revision'],data['text']))
        if path=='/api/local/draft/approve':return self.present_draft(self.data.approve_draft(data['id'],data['revision'],data.get('validator',''),data.get('confirmed')))
        if path in ('/api/local/draft/delete','/api/local/draft/restore'):
            require(set(data)=={'id','revision','visibility_revision','confirmed'},'DRAFT_VISIBILITY_FIELDS')
            return self.data.set_draft_deleted(data['id'],data['revision'],data['visibility_revision'],
                                               data['confirmed'],deleted=path.endswith('/delete'))
        if path=='/api/local/draft/pdf':return self.export_patient(data)
        if path=='/api/local/draft/library-pdf':return self.export_patient(data,library=True)
        raise ValueError('LOCAL_ROUTE_ABSENT')
    def export_patient(self,data,*,library=False):
        import os,shutil,subprocess
        from .storage import ROOT
        require(set(data)=={'id','revision'},'PATIENT_EXPORT_INVALID')
        def approved():
            if library:return self.data.approved_version(self.data.draft(data['id']),data['revision'])
            return self.data.require_approved(data['id'],data['revision'])
        draft=approved()
        configured=os.environ.get('GARY_PDF_NODE')
        node=Path(configured or ROOT/'runtime/node/node.exe')
        require(node.is_file(),'PATIENT_PDF_NODE_MISSING')
        folder=self.store.root/'patient_exports'/draft['id']/uuid.uuid4().hex
        folder.mkdir(parents=True,exist_ok=False)
        manifest={'schema':'gary_patient_pdf_v1','state':'PREPARE','draft_id':draft['id'],'revision':draft['revision'],
                  'doctor_action':draft['validation'],'test':draft['test'],'sources':draft['sources'],
                  'qualification_by_codex':False,'files':{}}
        if library:manifest['library_export']=True
        manifest_write(folder,manifest)
        try:
            output=subprocess.run([str(node),str(ROOT/'gary_v5/render_patient.mjs')],input=json.dumps({'directory':str(folder),'draft':draft}),text=True,encoding='utf8',capture_output=True,timeout=30,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            prerequisites={21:'PATIENT_PDF_DEPENDENCIES_MISSING',22:'PATIENT_PDF_PLAYWRIGHT_MISSING',23:'PATIENT_PDF_BROWSER_UNAVAILABLE'}
            if output.returncode in prerequisites:raise ValueError(prerequisites[output.returncode])
            require(output.returncode==0,'PATIENT_RENDER_FAILED')
            require(approved()['validation']==draft['validation'],'DRAFT_APPROVAL_CHANGED')
            (folder/'texte_version.md').write_bytes(draft['versions'][-1]['text'].encode('utf8'))
            manifest['files']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.iterdir() if p.is_file() and p.name!='manifest.json'}
            manifest['state']='EXPORTED_APPROVED_DOCUMENT_VERSION';manifest_write(folder,manifest)
            return {'state':manifest['state'],'export_id':folder.name,'draft_id':draft['id'],'revision':draft['revision']}
        except Exception as error:
            manifest['state']='EXPORT_FAILED_OR_STALE';manifest_write(folder,manifest)
            if isinstance(error,ValueError) and str(error) in ('PATIENT_PDF_DEPENDENCIES_MISSING','PATIENT_PDF_PLAYWRIGHT_MISSING','PATIENT_PDF_BROWSER_UNAVAILABLE'):
                raise ValueError(str(error)) from None
            raise ValueError('PATIENT_EXPORT_FAILED_OR_APPROVAL_INVALIDATED') from None
    def patient_file(self,identity,export_id,name):
        require(name in ('Fiche_patient.pdf','manifest.json') and __import__('re').fullmatch('[0-9a-f]{32}',export_id),'PATIENT_EXPORT_PATH_INVALID')
        folder=self.store.root/'patient_exports'/identity/export_id
        require(folder.resolve().is_relative_to((self.store.root/'patient_exports').resolve()),'PATIENT_EXPORT_PATH_INVALID')
        for p in (folder,*folder.parents):require(not p.is_symlink() and not p.is_junction(),'PATIENT_EXPORT_PATH_INVALID')
        m=json.loads((folder/'manifest.json').read_text('utf8'));require(m['draft_id']==identity and m['state']=='EXPORTED_APPROVED_DOCUMENT_VERSION','PATIENT_EXPORT_UNAVAILABLE')
        if m.get('library_export') is True:
            approved=self.data.approved_version(self.data.draft(identity),m['revision'])
            require(approved['validation']==m['doctor_action'],'DRAFT_APPROVAL_CHANGED')
        else:self.data.require_approved(identity,m['revision'])
        require(all(hashlib.sha256((folder/n).read_bytes()).hexdigest()==v for n,v in m['files'].items()),'PATIENT_EXPORT_CORRUPT')
        return (folder/name).read_bytes()

    def history_file(self,identity,version_id,name):
        require(name in ('reponse_gary_brute.txt','reponse_fournisseur.json','manifest.json','Gary_TEST_reponse_originale.pdf','Gary_reponse_originale.pdf','capture_reference.png'),'ARTIFACT_REFUSED')
        value=self.data.history(identity);version=next((v for v in value['versions'] if v['id']==version_id),None)
        require(version is not None and version.get('evidence'),'ARTIFACT_ABSENT')
        from .live_evidence import directory
        folder=directory(version['evidence'],version['test'])
        manifest=json.loads((folder/'manifest.json').read_text('utf8'))
        require(all(hashlib.sha256((folder/n).read_bytes()).hexdigest()==h for n,h in manifest['files'].items()),'EVIDENCE_CORRUPT')
        path=folder/name;require(path.is_file() and not path.is_symlink(),'ARTIFACT_ABSENT')
        return path.read_bytes()
