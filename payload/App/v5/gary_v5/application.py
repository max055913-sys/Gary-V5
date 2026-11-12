"""Orchestration locale autonome. La préparation n'émet jamais de requête réseau."""
import json
from .storage import ROOT,digest
from .routing import MODULES,analyze
from .module_rules import RULES
from .settings import Settings
from .generation_contract import build_request

class Runtime:
 def __init__(self,store):self.store=store
 def prepare_request(self,data):
  """Retour interne (préparation, corps fournisseur). Jamais une émission."""
  if data.get('privacy_confirmed')is not True:raise ValueError('PRIVACY_CONFIRMATION_REQUIRED')
  q=data.get('query');module=data.get('module','AUTO');profile=data.get('profile',{})
  route=analyze(q,module,profile)
  conflicts=route.get('profile_conflicts',[]);missing=route.get('missing_profile_fields',[])
  if route.get('ambiguous_intent') or missing or conflicts:
   message=('Valeur ambiguë dans la commande ou incompatible avec le profil : '+', '.join(conflicts)+'. Corrigez les valeurs sans en choisir une implicitement.') if conflicts else ('Données nécessaires à la demande individualisée : '+', '.join(missing)) if missing else 'Le routage AUTO nécessite une décision Luna reconnue. Luna est indisponible dans ce parcours ; sélectionnez un module ou réessayez après qualification. Aucun routage lexical de secours.'
   return {'schema':'gary_v5_prepared_v1','status':'clarification','question':q,'module':route.get('module') or module,'message':message,'missing_profile_fields':missing,'profile_conflicts':conflicts,'request_sha256':None,'transport_enabled':False},None
  profile=route['effective_profile']
  m=route['module'];settings=Settings(self.store).read_write()
  depth=data.get('depth',settings['value']['modules'][m]['depth']);context=data.get('context_policy','intermediaire')
  request=build_request(q,m,profile,settings,depth,context)
  return {'schema':'gary_v5_prepared_v1','status':'prepared','question':q,'module':m,'message':'Requête OpenAI préparée localement. Aucun appel autorisé ou effectué.','request_sha256':digest(request),'transport_enabled':False,'response_contract':'gary_v5_result_v1','depth':depth,'context_policy':context},request
 def prepare(self,data):
  return self.prepare_request(data)[0]
