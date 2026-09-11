"""CPA Control Center local service. Persistent, privacy-first and proxy-aware."""
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import json, time, threading, sqlite3, os, urllib.request
from urllib.parse import urlparse
DB=os.path.join(os.path.dirname(__file__),'cpa.sqlite3'); LOCK=threading.RLock()
DEFAULT={"running":False,"started_at":None,"requests":0,"success":0,"failed":0,"logs":[],"proxies":[],"tasks":[],"settings":{"rotation":"smart","timeout":8,"retries":2,"verify":True}}
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
  c.commit()
def load():
 with db() as c:
  state['proxies']=[dict(x) for x in c.execute('SELECT * FROM proxies ORDER BY score DESC, status="healthy" DESC, latency IS NULL, latency ASC')]
  state['tasks']=[dict(x) for x in c.execute('SELECT * FROM tasks ORDER BY id DESC')]
  state['logs']=[dict(x) for x in c.execute('SELECT time,level,message FROM logs ORDER BY id DESC LIMIT 100')]
  for k,v in c.execute('SELECT key,value FROM settings'): state['settings'][k]=json.loads(v)
def persist_proxy(p):
 with db() as c: c.execute('INSERT OR REPLACE INTO proxies(id,raw,url,host,port,scheme,username,status,latency,score,failures,successes,cooldown,last_check) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(p.get('id'),p['raw'],p['url'],p['host'],p['port'],p['scheme'],p.get('username'),p['status'],p.get('latency'),p.get('score',0),p.get('failures',0),p.get('successes',0),p.get('cooldown',0),p.get('last_check')))
def log(level,message):
 item={"time":time.strftime('%H:%M:%S'),"level":level,"message":message}
 with LOCK:
  state['logs'].insert(0,item); state['logs']=state['logs'][:100]
  with db() as c: c.execute('INSERT INTO logs(time,level,message) VALUES(?,?,?)',(item['time'],level,message)); c.execute('DELETE FROM logs WHERE id NOT IN (SELECT id FROM logs ORDER BY id DESC LIMIT 100)')
def parse_proxy(raw):
 raw=raw.strip(); candidate=raw if '://' in raw else 'http://'+raw; u=urlparse(candidate)
 if u.scheme not in ('http','https','socks5') or not u.hostname or not u.port: raise ValueError('يجب استخدام scheme://host:port صحيح')
 return {'raw':raw,'url':candidate,'host':u.hostname,'port':u.port,'scheme':u.scheme,'username':u.username,'status':'untested','latency':None,'failures':0,'successes':0,'cooldown':0,'last_check':None}
def check_proxy(p):
 started=time.perf_counter(); now=time.time()
 try:
  if p['scheme']=='socks5': raise RuntimeError('SOCKS5 adapter غير مثبت')
  req=urllib.request.Request('https://www.gstatic.com/generate_204',headers={'User-Agent':'CPA-Control-Center/1.0'})
  opener=urllib.request.build_opener(urllib.request.ProxyHandler({'http':p['url'],'https':p['url']}))
  with opener.open(req,timeout=float(state['settings']['timeout'])): pass
  p.update(status='healthy',latency=round((time.perf_counter()-started)*1000),failures=0,last_check=now); p['successes']+=1
  # score rewards reliability and low latency; it is intentionally bounded 0..100
  reliability=p['successes']/max(1,p['successes']+p['failures']); speed=max(0,100-min(100,p['latency']/10))
  p['score']=round(reliability*70+speed*0.30,1)
 except Exception:
  p.update(status='offline',latency=None,failures=p.get('failures',0)+1,last_check=now); p['cooldown']=now+min(300,2**p['failures']); p['score']=round(max(0,p.get('score',0)-15),1)
 with LOCK: persist_proxy(p)
 return p['status']=='healthy'
def health_all():
 with LOCK: items=list(state['proxies'])
 ts=[threading.Thread(target=check_proxy,args=(p,),daemon=True) for p in items]
 for t in ts:t.start()
 for t in ts:t.join()
 good=sum(p['status']=='healthy' for p in items); log('success',f'اكتمل الفحص: {good}/{len(items)} بروكسي متاح')
def send(h,code,payload):
 body=json.dumps(payload,ensure_ascii=False).encode(); h.send_response(code); h.send_header('Content-Type','application/json; charset=utf-8'); h.send_header('Content-Length',str(len(body))); h.send_header('Access-Control-Allow-Origin','*'); h.end_headers(); h.wfile.write(body)
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
  try:data=json.loads(self.rfile.read(int(self.headers.get('Content-Length',0))) or b'{}')
  except:return send(self,400,{'error':'invalid json'})
  if path=='/api/proxies/import':
   added=0; errors=[]
   with LOCK:
    existing={p['raw'] for p in state['proxies']}
    for raw in data.get('text','').replace(',','\n').splitlines():
     try:
      p=parse_proxy(raw)
      if p['raw'] not in existing: persist_proxy(p); state['proxies'].append(p); existing.add(p['raw']); added+=1
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
   task={'name':data.get('name','مهمة جديدة'),'url':data.get('url',''),'enabled':1,'status':'idle','runs':0,'successes':0,'created':time.time()}
   with db() as c: cur=c.execute('INSERT INTO tasks(name,url,enabled,status,runs,successes,created) VALUES(?,?,?,?,?,?,?)',(task['name'],task['url'],1,'idle',0,0,task['created'])); task['id']=cur.lastrowid
   state['tasks'].insert(0,task); log('info',f"تم إنشاء المهمة: {task['name']}"); return send(self,200,task)
  if path=='/api/tasks/toggle':
   with db() as c:c.execute('UPDATE tasks SET enabled=1-enabled WHERE id=?',(data.get('id'),))
   load(); return send(self,200,state['tasks'])
  if path=='/api/settings':
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
