"""Lecture SSE bornée, sans réseau ni interprétation médicale."""
from copy import deepcopy
import codecs,hashlib,json,time,re
from .storage import canonical
from .commercial_supervisor import require
from .functional_store import privacy_check

LIMIT=8_388_608

class StreamFailure(ValueError):pass

class StreamCapture:
 def __init__(self,model,on_progress=None):
  self.model=model;self.callback=on_progress;self.raw=bytearray();self.decoder=codecs.getincrementaldecoder('utf8')('strict');self.buffer='';self.lines=[]
  self.parts={};self.items={};self.annotations={};self.final=None;self.terminal=False;self.failed=False;self.model_verified=False;self.started=time.perf_counter();self.first_event_ms=None;self.first_text_ms=None;self.sequence=-1;self.events=0
 def feed(self,raw):
  require(type(raw) is bytes and len(self.raw)+len(raw)<=LIMIT,'SSE_SIZE_LIMIT');self.raw.extend(raw);self.buffer+=self.decoder.decode(raw)
  require(len(self.buffer)<=1_048_576,'SSE_EVENT_LIMIT')
  while '\n' in self.buffer:
   line,self.buffer=self.buffer.split('\n',1);self.line(line.rstrip('\r'))
 def line(self,line):
  if line=='':
   if self.lines:
    value='\n'.join(self.lines);self.lines=[]
    if value=='[DONE]':
     require(self.terminal,'SSE_UNTYPED_TERMINAL');return
    from .live_transport import strict_json
    self.event(strict_json(value))
  elif line.startswith('data:'):
   self.lines.append(line[5:].lstrip(' '));require(sum(map(len,self.lines))<=1_048_576,'SSE_EVENT_LIMIT')
  # Commentaires et métadonnées SSE ne deviennent pas des instructions.
 def event(self,event):
  require(type(event) is dict and type(event.get('type')) is str,'SSE_EVENT_SCHEMA')
  require(not self.terminal,'SSE_AFTER_TERMINAL')
  n=event.get('sequence_number')
  if n is not None:require(type(n) is int and n>self.sequence,'SSE_SEQUENCE');self.sequence=n
  now=(time.perf_counter()-self.started)*1000
  if self.first_event_ms is None:self.first_event_ms=now
  self.events+=1;t=event['type']
  if t in ('response.created','response.in_progress'):
   response=event.get('response',{});model=response.get('model')
   if model is not None:require(model==self.model,'SSE_MODEL');self.model_verified=True
  elif t=='response.output_item.added':
   i=self.index(event,'output_index');item=event['item'];require(type(item) is dict,'SSE_ITEM');self.items[i]=deepcopy(item)
  elif t=='response.output_text.delta':
   key=(self.index(event,'output_index'),self.index(event,'content_index'));value=event['delta'];require(type(value) is str,'SSE_TEXT')
   self.parts[key]=self.parts.get(key,'')+value
   if value and self.first_text_ms is None:self.first_text_ms=now
   # Contrôle cumulé : une donnée sensible découpée ne passe pas par morceaux.
   privacy_check('\n'.join(self.parts[k] for k in sorted(self.parts)))
  elif t=='response.output_text.done':
   key=(self.index(event,'output_index'),self.index(event,'content_index'));require(self.parts.get(key,'')==event['text'],'SSE_TEXT_DIVERGENCE')
  elif t=='response.output_text.annotation.added':
   key=(self.index(event,'output_index'),self.index(event,'content_index'),self.index(event,'annotation_index'));value=event.get('annotation')
   require(value is None or type(value) is dict,'SSE_ANNOTATION_SCHEMA')
   if value is not None:
    require(key not in self.annotations or self.annotations[key]==value,'SSE_ANNOTATION_DIVERGENCE');self.annotations[key]=deepcopy(value)
  elif t in ('response.completed','response.incomplete','response.failed'):
   response=event.get('response');require(type(response) is dict and response.get('model')==self.model and type(response.get('output')) is list,'SSE_FINAL_SCHEMA')
   expected={'response.completed':'completed','response.incomplete':'incomplete','response.failed':'failed'}[t]
   require(response.get('status')==expected,'SSE_FINAL_STATUS');privacy_check(response)
   for (i,c),value in self.parts.items():
    require(i<len(response['output']) and c<len(response['output'][i].get('content',[])) and response['output'][i]['content'][c].get('text')==value,'SSE_FINAL_TEXT_DIVERGENCE')
   for (i,c,a),value in self.annotations.items():
    require(i<len(response['output']) and c<len(response['output'][i].get('content',[])),'SSE_FINAL_ANNOTATION_MISSING')
    annotations=response['output'][i]['content'][c].get('annotations',[])
    require(a<len(annotations) and annotations[a]==value,'SSE_FINAL_ANNOTATION_DIVERGENCE')
   self.model_verified=True;self.final=deepcopy(response);self.terminal=True
  elif t=='error':raise StreamFailure('SSE_PROVIDER_ERROR')
  # Les annotations provisoires et raisonnements ne sont pas exposés au client.
  if self.callback:self.callback(self)
 @staticmethod
 def index(event,name):
  value=event[name];require(type(value) is int and 0<=value<512,'SSE_INDEX');return value
 def preview(self):
  if not self.model_verified:return ''
  result=[]
  for k in sorted(self.parts):
   text=self.parts[k]
   # Ne plus attendre le paragraphe complet. Une amorce de secret découpée
   # reste toutefois privée jusqu'au contrôle cumulé de la suite.
   tails=[m.start() for pattern in (r'\b(?:sk-[A-Za-z0-9_-]*|sk|s)$',r'\S+@\S*$',r'(?<!\w)\+?\d[\d .-]*$') if (m:=re.search(pattern,text))]
   if tails:text=text[:min(tails)]
   result.append(text)
  text='\n'.join(result);privacy_check(text);return text
 def finish(self):
  self.buffer+=self.decoder.decode(b'',final=True)
  # Une trame non terminée n'est jamais adoptée implicitement.
  require(not self.buffer.strip() and not self.lines and self.terminal,'SSE_INTERRUPTED')
  privacy_check(bytes(self.raw).decode('utf8'));return canonical(self.final).encode('utf8')
 def partial(self):
  if not self.model_verified:return None
  text='\n'.join(self.parts[k] for k in sorted(self.parts));privacy_check(text)
  if not text:return None
  return {'model':self.model,'status':'incomplete','usage':None,'output':[{'type':'message','content':[{'type':'output_text','text':text,'annotations':[]}]}],
          'incomplete_details':{'reason':'stream_interrupted','origin':'LOCAL_TRANSPORT_NOT_PROVIDER'}}
 def telemetry(self):
  return {'first_event_ms':self.first_event_ms,'first_text_ms':self.first_text_ms,'stream_events':self.events,'stream_terminal_received':self.terminal}
 def consume(self,response,deadline=None):
  try:
   while True:
    if deadline is not None:
     remaining=deadline-time.monotonic();require(remaining>0,'SSE_DEADLINE')
     sock=getattr(getattr(getattr(response,'fp',None),'raw',None),'_sock',None)
     if sock is not None:sock.settimeout(remaining)
    block=(response.read1 if hasattr(response,'read1') else response.read)(4096)
    if not block:break
    self.feed(block)
   return self.finish()
  except Exception:
   self.failed=True;raise StreamFailure('SSE_STOPPED_NO_RETRY') from None

def simulated_chunks(provider):
 """Adaptation du transport simulé existant, uniquement dans TEST_ROOT."""
 yield ('data: '+canonical({'type':'response.created','response':{'model':provider.get('model'),'status':'in_progress'}})+'\n\n').encode()
 for i,item in enumerate(provider.get('output',[])):
  yield ('data: '+canonical({'type':'response.output_item.added','output_index':i,'item':item})+'\n\n').encode()
  for c,part in enumerate(item.get('content',[])):
   if part.get('type')=='output_text':
    yield ('data: '+canonical({'type':'response.output_text.delta','output_index':i,'content_index':c,'delta':part['text']})+'\n\n').encode()
 status=provider.get('status');event='response.completed' if status=='completed' else 'response.incomplete' if status=='incomplete' else 'response.failed'
 yield ('data: '+canonical({'type':event,'response':provider})+'\n\n').encode()
