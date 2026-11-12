"""Préparation locale d'une campagne DRAFT ; ne peut autoriser ni émettre.

Usage futur côté serveur : python -m v5.gary_v5.service_setup --request-file ...
Le fichier contient les mêmes données que la préparation HTTP, sans secret.
Aucune commande d'approbation, de levée de verrou ou d'émission n'est fournie.
"""
import argparse
import json
from pathlib import Path
import uuid
from .commercial_supervisor import require
from .live_supervisor import LiveSupervisor,LIVE_PATH,TEST_ROOT,prepare_live_request


def prepare_campaign(runtime,data,*,test_directory=None):
    require(type(data) is dict and set(data)<={'query','module','profile','privacy_confirmed','depth','context_policy','model'},'REQUEST_FIELDS_REFUSED')
    prepared,request=runtime.prepare_request(data)
    require(request is not None,'CLARIFICATION_REQUIRED')
    request=prepare_live_request(request)
    name=uuid.uuid4().hex+'.sqlite'
    root=Path(test_directory) if test_directory is not None else LIVE_PATH.parent/'campaigns'
    if test_directory is not None:require(root.resolve().is_relative_to(TEST_ROOT.resolve()),'TEST_PATH_REQUIRED')
    supervisor=LiveSupervisor.create(request,root/name,test=test_directory is not None)
    state=supervisor.snapshot()
    return {'schema':'gary_service_draft_v1','registry':name,'campaign':state['campaign'],
            'request_sha256':state['request_sha256'],'state':'DRAFT','network_authorized':False,
            'qualified_commercial_policy':False,'approval_consumed':False,
            'requirements':['Borne financière tout compris reconnue','Décision humaine reconnue liée au SHA et à la campagne',
                            'Paquet approuvé côté serveur','Release réseau reconnue','Confirmation propriétaire fraîche']}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description='Créer un brouillon local sans autorisation ni émission.')
    parser.add_argument('--request-file',required=True)
    args=parser.parse_args()
    from .application import Runtime
    from .storage import Store
    try:
        data=json.loads(Path(args.request_file).read_text('utf8'))
        print(json.dumps(prepare_campaign(Runtime(Store()),data),ensure_ascii=False))
    except Exception:
        raise SystemExit('SERVICE_DRAFT_REFUSED_NO_EMISSION')
