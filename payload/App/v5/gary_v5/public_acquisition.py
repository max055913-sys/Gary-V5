"""Acquisition HTTPS bornée, sans proxy/cookie/auth et avec DNS épinglé."""
import http.client,ipaddress,queue,re,socket,ssl,threading,time
from urllib.parse import urlsplit,urlunsplit,parse_qsl,urljoin
from urllib.robotparser import RobotFileParser
from .commercial_supervisor import require

MAX_BYTES=1000000
_DNS_SLOTS=threading.BoundedSemaphore(4)
_FETCH_SLOTS=threading.BoundedSemaphore(4)

def public_url(value):
 require(type(value) is str and 0<len(value)<=4096 and not re.search(r'[\s\\\x00-\x1f\x7f]',value),'WEB_URL_INVALID')
 u=urlsplit(value)
 require(u.scheme=='https' and u.hostname and u.port in (None,443) and not u.username and not u.password and not u.fragment,'WEB_HTTPS_PUBLIC_REQUIRED')
 host=u.hostname.encode('idna').decode('ascii').lower()
 require('.' in host and not host.endswith(('.local','.localhost','.internal','.lan','.home.arpa','.onion')) and all(re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?',s) for s in host.split('.')),'WEB_HOST_INVALID')
 try:ipaddress.ip_address(host)
 except ValueError:pass
 else:raise ValueError('WEB_LITERAL_ADDRESS_FORBIDDEN')
 require(not any(k.casefold() in {'token','access_token','api_key','key','auth','authorization','session','signature','code','password','x-amz-signature','x-amz-credential'} for k,v in parse_qsl(u.query)),'WEB_SENSITIVE_URL')
 return urlunsplit(('https',host,u.path or '/',u.query,''))

def validate_addresses(values):
 require(bool(values),'WEB_DNS_EMPTY');result=[]
 for value in values:
  ip=ipaddress.ip_address(value)
  require(ip.is_global and not ip.is_multicast and not ip.is_unspecified and not ip.is_loopback and not ip.is_reserved,'WEB_PRIVATE_ADDRESS_REFUSED')
  require(not (isinstance(ip,ipaddress.IPv6Address) and (ip.ipv4_mapped or ip.sixtofour or ip.teredo)),'WEB_TRANSITION_ADDRESS_REFUSED')
  result.append(str(ip))
 return result

def resolve_public(host,timeout=3):
 require(_DNS_SLOTS.acquire(blocking=False),'WEB_DNS_BUSY');out=queue.Queue(maxsize=1)
 def run():
  try:out.put((True,[v[4][0] for v in socket.getaddrinfo(host,443,type=socket.SOCK_STREAM)]))
  except Exception:out.put((False,[]))
  finally:_DNS_SLOTS.release()
 threading.Thread(target=run,daemon=True).start()
 try:ok,values=out.get(timeout=timeout)
 except queue.Empty:raise ValueError('WEB_DNS_TIMEOUT') from None
 require(ok,'WEB_DNS_FAILED');return validate_addresses(values)

class PinnedHTTPS(http.client.HTTPSConnection):
 def __init__(self,host,address,timeout,deadline=None):
  super().__init__(host,timeout=timeout,context=ssl.create_default_context());self.address=address;self.deadline=deadline or time.monotonic()+timeout
 def connect(self):
  ip=ipaddress.ip_address(self.address);sock=socket.socket(socket.AF_INET6 if ip.version==6 else socket.AF_INET,socket.SOCK_STREAM)
  try:
   self.sock=sock;sock.settimeout(self.timeout);sock.connect((str(ip),443));sock.settimeout(max(.01,min(self.timeout,self.deadline-time.monotonic())))
   self.sock=self._context.wrap_socket(sock,server_hostname=self.host)
  except BaseException:sock.close();raise

class PublicFetcher:
 def _get(self,url,deadline,limit=MAX_BYTES):
  current=public_url(url);chain=[]
  for _ in range(4):
   require(time.monotonic()<deadline,'WEB_DEADLINE')
   u=urlsplit(current);addresses=resolve_public(u.hostname,min(3,max(.01,deadline-time.monotonic())))
   connection=PinnedHTTPS(u.hostname,addresses[0],min(5,max(.01,deadline-time.monotonic())),deadline)
   def abort():
    try:
     if connection.sock:connection.sock.shutdown(socket.SHUT_RDWR)
    except OSError:pass
    connection.close()
   timer=threading.Timer(max(.01,deadline-time.monotonic()),abort);timer.daemon=True;timer.start()
   try:
    connection.request('GET',u.path+('?' + u.query if u.query else ''),headers={'Host':u.hostname,'User-Agent':'GaryDocs/1.0','Accept':'text/html,text/plain','Accept-Encoding':'identity','Connection':'close'})
    response=connection.getresponse();status=response.status
    if status in (301,302,303,307,308):
     location=response.getheader('Location');require(type(location) is str,'WEB_REDIRECT_INVALID')
     target=public_url(urljoin(current,location));require(urlsplit(target).hostname==u.hostname,'WEB_CROSS_HOST_REQUIRES_REVIEW');chain.append({'from':current,'to':target,'status':status});current=target;continue
    kind=(response.getheader('Content-Type') or '').lower();encoding=response.getheader('Content-Encoding') or 'identity'
    if status!=200:return {'status':status,'url':current,'content_type':kind,'body':b'','redirects':chain,'last_modified':None}
    require(kind.split(';')[0].strip() in ('text/html','text/plain'),'WEB_CONTENT_TYPE_UNSUPPORTED')
    require(encoding.casefold()=='identity','WEB_ENCODING_UNSUPPORTED')
    length=response.getheader('Content-Length')
    if length is not None:require(length.isdigit() and int(length)<=limit,'WEB_RESPONSE_TOO_LARGE')
    chunks=[];size=0
    while True:
     left=deadline-time.monotonic();require(left>0,'WEB_DEADLINE')
     if connection.sock:connection.sock.settimeout(min(2,left))
     chunk=response.read1(min(16384,limit-size+1))
     if not chunk:break
     size+=len(chunk);require(size<=limit,'WEB_RESPONSE_TOO_LARGE');chunks.append(chunk)
    return {'status':status,'url':current,'content_type':kind,'body':b''.join(chunks),'redirects':chain,'last_modified':response.getheader('Last-Modified')}
   finally:timer.cancel();connection.close()
  raise ValueError('WEB_REDIRECT_LIMIT')
 def fetch(self,url):
  require(_FETCH_SLOTS.acquire(blocking=False),'WEB_FETCH_BUSY')
  try:return self._fetch(url)
  finally:_FETCH_SLOTS.release()
 def _fetch(self,url):
  url=public_url(url);u=urlsplit(url);deadline=time.monotonic()+15
  robots=self._get('https://'+u.netloc+'/robots.txt',deadline,64000)
  require(urlsplit(robots['url']).hostname==u.hostname,'WEB_ROBOTS_CROSS_HOST')
  if robots['status']!=404:
   require(robots['status']==200 and robots['content_type'].startswith('text/plain'),'WEB_ROBOTS_UNAVAILABLE')
   parser=RobotFileParser();parser.parse(robots['body'].decode('utf8',errors='strict').splitlines())
   require(parser.can_fetch('GaryDocs',url),'WEB_ROBOTS_DENIED')
   require(not parser.crawl_delay('GaryDocs'),'WEB_CRAWL_DELAY_REQUIRES_SCHEDULER')
  result=self._get(url,deadline)
  require(urlsplit(result['url']).hostname==u.hostname,'WEB_CROSS_HOST_REQUIRES_REVIEW')
  return result
