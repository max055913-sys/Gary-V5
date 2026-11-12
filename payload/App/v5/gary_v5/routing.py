"""Résolution locale des intentions et des neuf modules, sans moteur documentaire."""
import re,unicodedata
MODULES=("AUTO","DIAG","PATH","TTT","SUIVI","PED","PREG","ADM","FICH")
def normalize(value):
 s=unicodedata.normalize('NFKC',value).casefold().replace('≤','<=').replace('≥','>=').replace('≠','!=').replace('−','-').replace('⁄','/').replace('∕','/').replace('’',"'")
 s=''.join(c for c in unicodedata.normalize('NFKD',s) if not unicodedata.combining(c))
 s=re.sub(r'(?<=\d),(?=\d)','.',s)
 # Normaliser uniquement la ponctuation décorative connue. Les séparateurs
 # internes, unités/symboles et opérateurs peuvent changer la portée clinique.
 s=re.sub(r'^(definition documentaire de|definir dans le document)\s*:\s*',r'\1 ',s.strip())
 s=re.sub(r'(?<=[^\W\d_])[-‐‑](?=[^\W\d_])',' ',s)
 s=s.strip(" \t\r\n.!?«»\"'")
 return ' '.join(re.findall(r'<=|>=|!=|-?\d+(?:\.\d+)?|[^\W\d_]+|[^\s]',s))






def _quantity(value,field):
 """Comparer des unités explicites ; jamais convertir jours en mois ou SG en SA."""
 from decimal import Decimal
 text=normalize(value)
 pattern=r'(\d+(?:\.\d+)?)\s*(jours?|mois|ans?|annees?)' if field=='age' else r'(\d+(?:\.\d+)?)\s*(?:sa|semaines? d \' amenorrhee)?'
 match=re.fullmatch(pattern,text)
 if not match:return None
 number=Decimal(match[1])
 if field=='term':return ('SA',number)
 unit=match[2]
 return ('jours',number) if unit.startswith('jour') else ('mois',number*12 if unit.startswith(('an','annee')) else number)

def analyze(question,module='AUTO',profile=None,timings=None):
 result=explicit_route(question,module,profile)
 effective=dict(profile or {});conflicts=[];extracted={}
 # Une valeur n'est extraite que d'une commande PED/PREG explicite.
 command=re.match(r'^\s*(PED|PREG)(?:\s*:\s*|\s+)(.+)$',question,re.I|re.S)
 if command:
  field='age' if command[1].upper()=='PED' else 'term'
  text=normalize(command[2])
  pattern=r'\b\d+(?:\.\d+)?\s*(?:jours?|mois|ans?|annees?)\b' if field=='age' else r'\b\d+(?:\.\d+)?\s*sa\b'
  values=re.findall(pattern,text)
  quantities=[_quantity(v,field) for v in values]
  invalid_signed=bool(re.search(r'(?:^|\s)[+-]\s*\d',text))
  uncertain_quantity=bool(re.search(r'\b(?:environ|entre)\b|\d\s*(?:a|-)\s*\d',text))
  compound_term=field=='term' and bool(values) and bool(re.search(r'\b\d+\s*jours?\b',text))
  if invalid_signed or uncertain_quantity or compound_term or len(set(quantities))>1:conflicts.append(field)
  elif values:
   existing=effective.get(field,'').strip()
   if existing and _quantity(existing,field)!=quantities[0]:conflicts.append(field)
   elif not existing:
    effective[field]=values[0];extracted[field]=values[0]
 result.update(version='gary_routing_explicit_r01_v1',effective_profile=effective,extracted_profile=extracted,profile_conflicts=conflicts)
 return result

def command_parts(question,module='AUTO'):
 """Commandes explicites seulement ; aucune interprétation de question libre."""
 if type(question) is not str or not question.strip() or len(question)>1000 or module not in MODULES:raise ValueError('REQUETE_INVALIDE')
 q=question.strip();prefix=re.match(r'^(AUTO|DIAG|PATH|TTT|SUIVI|PED|PREG|ADM|FICH)(?:\s*:\s*|\s+)(.+)$',q,re.I|re.S)
 if prefix and prefix[1].upper()=='SUIVI' and prefix[1]!='SUIVI' and not re.match(r'^suivi\s*:',q,re.I):prefix=None
 if prefix:
  forced=prefix[1].upper()
  if module!='AUTO' and module!=forced:raise ValueError('MODULE_CONTRADICTOIRE')
  module=forced;q=prefix[2]
 return (None if module=='AUTO' else module),q

def explicit_route(question,module='AUTO',profile=None):
 profile={} if profile is None else profile
 if type(profile) is not dict or set(profile)-{'age','sex','weight','term','context'} or any(type(v) is not str or len(v)>500 for v in profile.values()):raise ValueError('PROFIL_INVALIDE')
 resolved,q=command_parts(question,module)
 return {'version':'gary_routing_explicit_r01_v1','original_question':question,'topic_exact':q,'module':resolved,'requested_auto':resolved is None,
         'ambiguous_intent':resolved is None,'missing_profile_fields':[],'profile':dict(profile),'method':'EXPLICIT_COMMAND_OR_LUNA_REQUIRED'}
