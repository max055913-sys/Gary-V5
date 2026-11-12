import copy, hashlib, ipaddress, re, time

from datetime import datetime

from urllib.parse import urlsplit

from .storage import canonical, digest

VERSION = 'gary_v5_web_selection_p2_v1'

DEPTHS = {'rapide': (2, 4), 'standard': (4, 8), 'approfondie': (8, 16)}

def url_valid(value):
    try:
        u = urlsplit(value)
        if u.scheme not in ('http', 'https') or not u.hostname or u.username or u.password or u.fragment or re.search(r'[\s\\]', value): return False
        if u.port not in (None, 80, 443): return False
        host = u.hostname.encode('idna').decode()
        try: ipaddress.ip_address(host); return False
        except ValueError: pass
        return '.' in host and all(re.fullmatch(r'[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?', x) for x in host.split('.')) and not host.endswith(('.local', '.localhost'))
    except (ValueError, TypeError, UnicodeError): return False

def initial_settings(sources):
    return {'schema': VERSION, 'revision': 0, 'modules': {m: {'depth': 'standard', 'preferred_domains': [], 'sources': copy.deepcopy(g['sources']), 'secondary_automatic': True} for m, g in sources['modules'].items()}}

def validate_settings(value, modules):
    if not isinstance(value, dict) or set(value) != {'schema','revision','modules'} or value['schema'] != VERSION or type(value['revision']) is not int or set(value['modules']) != set(modules): raise ValueError('P2_SETTINGS_INVALID')
    for g in value['modules'].values():
        if set(g) != {'depth','preferred_domains','sources','secondary_automatic'} or g['depth'] not in DEPTHS or g['secondary_automatic'] is not True: raise ValueError('P2_SETTINGS_INVALID')
        if not isinstance(g['preferred_domains'], list) or len(g['preferred_domains'])>100 or len(set(g['preferred_domains']))!=len(g['preferred_domains']): raise ValueError('P2_DOMAINS_INVALID')
        for domain in g['preferred_domains']:
            if not isinstance(domain,str) or '/' in domain or ':' in domain or not url_valid('https://'+domain): raise ValueError('P2_DOMAINS_INVALID')
        seen=set()
        if not isinstance(g['sources'],list) or len(g['sources'])>100: raise ValueError('P2_SOURCES_INVALID')
        for s in g['sources']:
            if set(s)!={'id','title','url','provenance'} or not isinstance(s['id'],str) or not re.fullmatch(r'[\w-]{1,100}',s['id']) or s['id'] in seen: raise ValueError('P2_SOURCE_INVALID')
            seen.add(s['id'])
            if not isinstance(s['title'],str) or not s['title'].strip() or len(s['title'])>200 or not isinstance(s['provenance'],str) or not s['provenance']: raise ValueError('P2_SOURCE_INVALID')
            if s['url'] is not None and not url_valid(s['url']): raise ValueError('P2_URL_INVALID')
            if s['provenance']=='USER_V5_P2' and s['url'] is None: raise ValueError('P2_URL_REQUIRED')
"""Extension SQLite autonome ; ne migre et ne remplace aucune préférence P1."""
import copy,json
from .storage import digest,canonical

class SettingsP2:
    def __init__(self,store): self.store=store
    def read_write(self,value=None,revision=None):
        initial=initial_settings(self.store.sources())
        with self.store.tx() as db:
            row=db.execute("SELECT value FROM metadata WHERE key='web_selection_p2'").fetchone()
            if row:
                e=json.loads(row[0]);old=e['payload']
                if e['sha']!=digest(old):raise ValueError('P2_SETTINGS_CORRUPT')
            else:old=initial
            validate_settings(old,initial['modules'])
            if value is None:return old
            if type(revision)is not int or old['revision']!=revision:raise ValueError('REVISION_CONFLICT')
            validate_settings(value,initial['modules']);new=copy.deepcopy(value);new['revision']=old['revision']+1
            references={s['id']:s for g in initial['modules'].values() for s in g['sources']}
            for g in new['modules'].values():
                for s in g['sources']:
                    if s['provenance']!='USER_V5_P2' and references.get(s['id'])!=s:raise ValueError('P2_REFERENCE_PROVENANCE_INVALID')
            db.execute("INSERT OR REPLACE INTO metadata VALUES('web_selection_p2',?)",(canonical({'payload':new,'sha':digest(new)}),))
            return new