"""CPA Control Center local service. Persistent, privacy-first and proxy-aware."""
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import json, time, threading, sqlite3, os, random, ssl, urllib.request
from urllib.parse import urlparse
DB=os.environ.get('CPA_DB_PATH',os.path.join(os.path.dirname(__file__),'cpa.sqlite3'))
os.makedirs(os.path.dirname(os.path.abspath(DB)),exist_ok=True)
LOCK=threading.RLock(); TASK_LOCK=threading.Lock(); CHECK_LOCK=threading.Lock(); MAX_BODY=1024*1024
DEFAULT={"running":False,"started_at":None,"requests":0,"success":0,"failed":0,"logs":[],"proxies":[],"tasks":[],"settings":{"rotation":"smart","timeout":8,"retries":2,"verify":True},"stats":{"avg_latency":None,"active_tasks":0}}
rotation_cursor=0
state=json.loads(json.dumps(DEFAULT))

def db():
 c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; return c
def init_db():
 with db() as c:
  c.execute('CREATE TABLE IF NOT EXISTS proxies (id INTEGER PRIMARY KEY, raw TEXT UNIQUE, url TEXT, host TEXT, port INTEGER, scheme TEXT, username TEXT, status TEXT, latency INTEGER, score REAL DEFAULT 0, failures INTEGER DEFAULT 0, successes INTEGER DEFAULT 0, cooldown REAL DEFAULT 0, last_check REAL)')
  try: c.execute('ALTER TABLE proxies ADD COLUMN score REAL DEFAULT 0')
  except sqlite3.OperationalError: pass
  c.execute('CREATE TABLE IF NOT EXISTS tasks (id INTEGER PRIMARY KEY, name TEXT, url TEXT, enabled INTEGER DEFAULT 1, status TEXT DEFAULT "idle", runs INTEGER DEFAULT 0, successes INTEGER DEFAULT 0, created REAL)')
  c.execute('CREATE TABLE IF NOT EXISTS logs (id INTEGER PRIMARY KEY, time TEXT, level TEXT, message TEXT)')
  c.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)')
  c.execute('UPDATE tasks SET status="idle" WHERE status="running"')
  c.commit()
def load():
 with db() as c:
  state['proxies']=[dict(x) for x in c.execute('SELECT * FROM proxies ORDER BY score DESC, status="healthy" DESC, latency IS NULL, latency ASC')]
  state['tasks']=[dict(x) for x in c.execute('SELECT * FROM tasks ORDER BY id DESC')]
  state['logs']=[dict(x) for x in c.execute('SELECT time,level,message FROM logs ORDER BY id DESC LIMIT 100')]
  for k,v in c.execute('SELECT key,value FROM settings'): state['settings'][k]=json.loads(v)
 state['requests']=sum(int(t.get('runs') or 0) for t in state['tasks'])
 state['success']=sum(int(t.get('successes') or 0) for t in state['tasks'])
 state['failed']=max(0,state['requests']-state['success'])
 latencies=[p['latency'] for p in state['proxies'] if p.get('latency') is not None]
 state['stats']={'avg_latency':round(sum(latencies)/len(latencies)) if latencies else None,'active_tasks':sum(t.get('status')=='running' for t in state['tasks'])}
def persist_proxy(p):
 with db() as c: c.execute('INSERT OR REPLACE INTO proxies(id,raw,url,host,port,scheme,username,status,latency,score,failures,successes,cooldown,last_check) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(p.get('id'),p['raw'],p['url'],p['host'],p['port'],p['scheme'],p.get('username'),p['status'],p.get('latency'),p.get('score',0),p.get('failures',0),p.get('successes',0),p.get('cooldown',0),p.get('last_check')))
def log(level,message):
 item={"time":time.strftime('%H:%M:%S'),"level":level,"message":message}
 with LOCK:
  state['logs'].insert(0,item); state['logs']=state['logs'][:100]
  with db() as c: c.execute('INSERT INTO logs(time,level,message) VALUES(?,?,?)',(item['time'],level,message)); c.execute('DELETE FROM logs WHERE id NOT IN (SELECT id FROM logs ORDER BY id DESC LIMIT 100)')
def parse_proxy(raw):
 if not isinstance(raw,str): raise ValueError('صيغة البروكسي غير صالحة')
 raw=raw.strip()
 if len(raw)>512: raise ValueError('عنوان البروكسي طويل جداً')
 candidate=raw if '://' in raw else 'http://'+raw
 try: u=urlparse(candidate); port=u.port
 except ValueError: raise ValueError('المنفذ يجب أن يكون رقماً بين 1 و65535')
 if u.scheme not in ('http','https','socks5') or not u.hostname or not port or not (1<=port<=65535): raise ValueError('يجب استخدام scheme://host:port صحيح')
 return {'raw':raw,'url':candidate,'host':u.hostname,'port':port,'scheme':u.scheme,'username':u.username,'status':'untested','latency':None,'failures':0,'successes':0,'cooldown':0,'last_check':None}
def request_context():
 return ssl.create_default_context() if state['settings'].get('verify',True) else ssl._create_unverified_context()
def opener_for(proxy=None):
 handlers=[urllib.request.HTTPSHandler(context=request_context())]
 if proxy: handlers.insert(0,urllib.request.ProxyHandler({'http':proxy['url'],'https':proxy['url']}))
 return urllib.request.build_opener(*handlers)
def check_proxy(p):
 started=time.perf_counter(); now=time.time()
 try:
  if p['scheme']=='socks5': raise RuntimeError('SOCKS5 adapter غير مثبت')
  req=urllib.request.Request('https://www.gstatic.com/generate_204',headers={'User-Agent':'CPA-Control-Center/1.0'})
  with opener_for(p).open(req,timeout=float(state['settings']['timeout'])): pass
  p.update(status='healthy',latency=round((time.perf_counter()-started)*1000),failures=0,last_check=now); p['successes']+=1
  # score rewards reliability and low latency; it is intentionally bounded 0..100
  reliability=p['successes']/max(1,p['successes']+p['failures']); speed=max(0,100-min(100,p['latency']/10))
  p['score']=round(reliability*70+speed*0.30,1)
 except Exception:
  p.update(status='offline',latency=None,failures=p.get('failures',0)+1,last_check=now); p['cooldown']=now+min(300,2**p['failures']); p['score']=round(max(0,p.get('score',0)-15),1)
 with LOCK: persist_proxy(p)
 return p['status']=='healthy'
def health_all():
 if not CHECK_LOCK.acquire(blocking=False): return
 try:
  with LOCK: items=list(state['proxies'])
  ts=[threading.Thread(target=check_proxy,args=(p,),daemon=True) for p in items]
  for t in ts:t.start()
  for t in ts:t.join()
  good=sum(p['status']=='healthy' for p in items); log('success',f'اكتمل الفحص: {good}/{len(items)} بروكسي متاح')
 finally: CHECK_LOCK.release()
def choose_proxy():
 global rotation_cursor
 with LOCK: items=list(state['proxies'])
 eligible=[p for p in items if p.get('status')=='healthy' and p.get('cooldown',0)<=time.time()]
 if not eligible: return None
 mode=state['settings'].get('rotation','smart')
 if mode=='random': return random.choice(eligible)
 if mode=='round_robin':
  selected=eligible[rotation_cursor%len(eligible)]; rotation_cursor+=1; return selected
 return max(eligible,key=lambda p:(p.get('score',0),-p.get('latency',10**9)))
def run_task(task):
 started=time.perf_counter(); ok=False; selected=choose_proxy()
 with LOCK:
  with db() as c:
   updated=c.execute('UPDATE tasks SET status="running",runs=runs+1 WHERE id=? AND enabled=1 AND status!="running"',(task['id'],)).rowcount
  if not updated: return False
 load(); log('info',f"بدأ تنفيذ المهمة: {task['name']}" + (f" عبر {selected['host']}:{selected['port']}" if selected else ' بدون بروكسي'))
 retries=int(state['settings'].get('retries',0)); attempts=retries+1
 for attempt in range(attempts):
  try:
   req=urllib.request.Request(task['url'],headers={'User-Agent':'CPA-Control-Center/1.0'})
   with opener_for(selected).open(req,timeout=float(state['settings']['timeout'])) as response: ok=200 <= response.status < 400
   if ok: break
  except Exception as e:
   if attempt==attempts-1: log('error',f"فشلت المهمة {task['name']}: {type(e).__name__}")
  if not ok: time.sleep(min(0.25*(attempt+1),1))
 with db() as c:c.execute('UPDATE tasks SET status=?,successes=successes+? WHERE id=?',('success' if ok else 'failed',1 if ok else 0,task['id']))
 load(); log('success' if ok else 'error',f"انتهت المهمة: {task['name']} ({round((time.perf_counter()-started)*1000)} ms)")
 return ok
def send(h,code,payload):
 body=json.dumps(payload,ensure_ascii=False).encode(); h.send_response(code); h.send_header('Content-Type','application/json; charset=utf-8'); h.send_header('Content-Length',str(len(body))); h.send_header('Cache-Control','no-store'); h.send_header('X-Content-Type-Options','nosniff'); origin=h.headers.get('Origin');
 if origin in ('http://localhost:5173','http://127.0.0.1:5173'): h.send_header('Access-Control-Allow-Origin',origin)
 h.send_header('Access-Control-Allow-Methods','GET,POST,OPTIONS'); h.send_header('Access-Control-Allow-Headers','Content-Type'); h.end_headers();
 if code!=204: h.wfile.write(body)
def read_json(h):
 try: length=int(h.headers.get('Content-Length','0'))
 except ValueError: raise ValueError('invalid content length')
 if length<0 or length>MAX_BODY: raise ValueError('request body too large')
 raw=h.rfile.read(length) if length else b'{}'
 try: data=json.loads(raw or b'{}')
 except json.JSONDecodeError: raise ValueError('invalid json')
 if not isinstance(data,dict): raise ValueError('json object required')
 return data
class API(BaseHTTPRequestHandler):
 def log_message(self,*a): pass
 def do_OPTIONS(self): send(self,204,{})
 def do_GET(self):
  path=urlparse(self.path).path
  if path=='/api/health': return send(self,200,{'ok':True,'service':'CPA Control Center API'})
  if path=='/api/state':
   with LOCK:return send(self,200,state)
  if path=='/api/export':
   with LOCK:return send(self,200,{'proxies':state['proxies'],'tasks':state['tasks'],'settings':state['settings']})
  send(self,404,{'error':'not found'})
 def do_POST(self):
  path=urlparse(self.path).path
  try:data=read_json(self)
  except ValueError as e:return send(self,400,{'error':str(e)})
  if path=='/api/proxies/import':
   added=0; errors=[]
   text=data.get('text','')
   if not isinstance(text,str): return send(self,400,{'error':'text must be a string'})
   if len(text)>MAX_BODY: return send(self,413,{'error':'proxy list is too large'})
   with LOCK:
    existing={p['raw'] for p in state['proxies']}
    for raw in text.replace(',','\n').splitlines():
     try:
      p=parse_proxy(raw)
      if p['raw'] not in existing:
       with db() as c: p['id']=c.execute('INSERT INTO proxies(raw,url,host,port,scheme,username,status,latency,score,failures,successes,cooldown,last_check) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',(p['raw'],p['url'],p['host'],p['port'],p['scheme'],p.get('username'),p['status'],p.get('latency'),p.get('score',0),p.get('failures',0),p.get('successes',0),p.get('cooldown',0),p.get('last_check'))).lastrowid
       state['proxies'].append(p); existing.add(p['raw']); added+=1
     except ValueError as e: errors.append(f'{raw.strip()}: {e}')
   log('info',f'تمت إضافة {added} بروكسي'); return send(self,200,{'added':added,'errors':errors})
  if path=='/api/proxies/check': threading.Thread(target=health_all,daemon=True).start(); return send(self,202,{'started':True})
  if path=='/api/proxies/clear':
   with LOCK:
    state['proxies'].clear()
    with db() as c:c.execute('DELETE FROM proxies')
   log('info','تم مسح قائمة البروكسي'); return send(self,200,{'ok':True})
  if path=='/api/proxies/delete':
   with LOCK:
    state['proxies'][:]=[p for p in state['proxies'] if p.get('id')!=data.get('id')]
    with db() as c:c.execute('DELETE FROM proxies WHERE id=?',(data.get('id'),))
   return send(self,200,{'ok':True})
  if path=='/api/tasks/create':
   name=data.get('name','مهمة جديدة'); url=data.get('url','')
   if not isinstance(name,str) or not name.strip() or len(name)>120: return send(self,400,{'error':'اسم المهمة مطلوب (حتى 120 حرفاً)'})
   if not isinstance(url,str) or not url.startswith(('http://','https://')) or len(url)>2048: return send(self,400,{'error':'يجب إدخال رابط HTTP أو HTTPS صالح'})
   task={'name':name.strip(),'url':url.strip(),'enabled':1,'status':'idle','runs':0,'successes':0,'created':time.time()}
   with db() as c: cur=c.execute('INSERT INTO tasks(name,url,enabled,status,runs,successes,created) VALUES(?,?,?,?,?,?,?)',(task['name'],task['url'],1,'idle',0,0,task['created'])); task['id']=cur.lastrowid
   state['tasks'].insert(0,task); log('info',f"تم إنشاء المهمة: {task['name']}"); return send(self,200,task)
  if path=='/api/tasks/toggle':
   with db() as c: updated=c.execute('UPDATE tasks SET enabled=1-enabled WHERE id=? AND status!="running"',(data.get('id'),)).rowcount
   if not updated: return send(self,409,{'error':'لا يمكن تعديل مهمة قيد التنفيذ أو غير موجودة'})
   load(); return send(self,200,state['tasks'])
  if path=='/api/tasks/delete':
   with db() as c: deleted=c.execute('DELETE FROM tasks WHERE id=? AND status!="running"',(data.get('id'),)).rowcount
   if not deleted: return send(self,409,{'error':'لا يمكن حذف مهمة قيد التنفيذ أو غير موجودة'})
   load(); log('info','تم حذف المهمة'); return send(self,200,state['tasks'])
  if path=='/api/tasks/run':
   task=next((t for t in state['tasks'] if t.get('id')==data.get('id')),None)
   if not task or not task.get('url','').startswith(('http://','https://')): return send(self,400,{'error':'رابط المهمة غير صالح'})
   if not task.get('enabled'): return send(self,409,{'error':'المهمة متوقفة، فعّلها قبل التشغيل'})
   if task.get('status')=='running': return send(self,409,{'error':'المهمة قيد التنفيذ بالفعل'})
   threading.Thread(target=run_task,args=(task,),daemon=True).start(); return send(self,202,{'started':True})
  if path=='/api/settings':
   allowed={'rotation':('smart','round_robin','random')}
   if 'rotation' in data and data['rotation'] not in allowed['rotation']: return send(self,400,{'error':'استراتيجية تدوير غير صالحة'})
   if 'timeout' in data and (not isinstance(data['timeout'],(int,float)) or not 1<=data['timeout']<=120): return send(self,400,{'error':'المهلة يجب أن تكون بين 1 و120 ثانية'})
   if 'retries' in data and (not isinstance(data['retries'],int) or not 0<=data['retries']<=10): return send(self,400,{'error':'عدد المحاولات يجب أن يكون رقماً صحيحاً بين 0 و10'})
   if 'verify' in data and not isinstance(data['verify'],bool): return send(self,400,{'error':'قيمة التحقق يجب أن تكون منطقية'})
   with LOCK:
    for k,v in data.items():
     if k in state['settings']: state['settings'][k]=v
     with db() as c:c.execute('INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)',(k,json.dumps(v)))
   return send(self,200,state['settings'])
  if path=='/api/automation/toggle':
   state['running']=not state['running']; state['started_at']=time.time() if state['running'] else None; log('success' if state['running'] else 'info','بدأت الأتمتة' if state['running'] else 'تم إيقاف الأتمتة'); return send(self,200,state)
  send(self,404,{'error':'not found'})
init_db(); load(); log('info','Local API جاهز — البيانات محفوظة محلياً')
if __name__=='__main__': ThreadingHTTPServer(('127.0.0.1',8765),API).serve_forever()
