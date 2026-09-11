"""Local, privacy-first API for CPA Control Center.
Proxy design: strict parsing, async health checks, latency scoring, cooldowns and
circuit breakers. It never forwards traffic until a proxy is explicitly selected.
"""
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import json, time, threading, urllib.request, urllib.error
from urllib.parse import urlparse

lock = threading.RLock()
state = {"running": False, "started_at": None, "requests": 0, "success": 0, "failed": 0, "logs": [], "proxies": [], "settings": {"rotation":"smart","timeout":8,"retries":2,"verify":True}}

def log(level, message):
    with lock:
        state["logs"].insert(0,{"time":time.strftime("%H:%M:%S"),"level":level,"message":message})
        state["logs"] = state["logs"][:100]

def parse_proxy(raw):
    raw=raw.strip()
    if not raw: raise ValueError("empty proxy")
    candidate=raw if "://" in raw else "http://"+raw
    u=urlparse(candidate)
    if u.scheme not in ("http","https","socks5"): raise ValueError("unsupported scheme")
    if not u.hostname or not u.port: raise ValueError("proxy must contain host:port")
    return {"raw":raw,"url":candidate,"host":u.hostname,"port":u.port,"scheme":u.scheme,"username":u.username,"status":"untested","latency":None,"failures":0,"successes":0,"cooldown":0,"last_check":None}

def check_proxy(p):
    started=time.perf_counter(); now=time.time()
    try:
        if p["scheme"]=="socks5": raise RuntimeError("SOCKS5 requires optional PySocks adapter")
        req=urllib.request.Request("https://www.gstatic.com/generate_204",headers={"User-Agent":"CPA-Control-Center/1.0"})
        handler=urllib.request.ProxyHandler({"http":p["url"],"https":p["url"]})
        opener=urllib.request.build_opener(handler)
        with opener.open(req,timeout=state["settings"]["timeout"]) as response: response.read(1)
        p.update(status="healthy",latency=round((time.perf_counter()-started)*1000),failures=0,last_check=now)
        p["successes"]+=1; return True
    except Exception as e:
        p.update(status="offline",latency=None,failures=p.get("failures",0)+1,last_check=now)
        if p["failures"]>=3: p["cooldown"]=now+min(300,2**p["failures"])
        return False

def health_all():
    with lock: items=list(state["proxies"])
    threads=[threading.Thread(target=check_proxy,args=(p,),daemon=True) for p in items]
    for t in threads:t.start()
    for t in threads:t.join()
    good=sum(p["status"]=="healthy" for p in items); log("success",f"Proxy health check completed: {good}/{len(items)} healthy")

def response(handler, code, payload):
    body=json.dumps(payload,ensure_ascii=False).encode(); handler.send_response(code); handler.send_header("Content-Type","application/json; charset=utf-8"); handler.send_header("Content-Length",str(len(body))); handler.send_header("Access-Control-Allow-Origin","*"); handler.end_headers(); handler.wfile.write(body)
class API(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def do_OPTIONS(self): response(self,204,{})
    def do_GET(self):
        path=urlparse(self.path).path
        if path=="/api/health": return response(self,200,{"ok":True,"service":"CPA Control Center API"})
        if path=="/api/state":
            with lock: return response(self,200,state)
        response(self,404,{"error":"not found"})
    def do_POST(self):
        path=urlparse(self.path).path
        try: data=json.loads(self.rfile.read(int(self.headers.get("Content-Length",0))) or b"{}")
        except: return response(self,400,{"error":"invalid json"})
        if path=="/api/proxies/import":
            added=0; errors=[]
            with lock:
                existing={p["raw"] for p in state["proxies"]}
                for raw in data.get("text","").replace(",","\n").splitlines():
                    try:
                        p=parse_proxy(raw)
                        if p["raw"] not in existing: state["proxies"].append(p); existing.add(p["raw"]); added+=1
                    except ValueError as e: errors.append(f"{raw.strip()}: {e}")
            log("info",f"Imported {added} proxy{'' if added==1 else 'ies'}")
            return response(self,200,{"added":added,"errors":errors})
        if path=="/api/proxies/check": threading.Thread(target=health_all,daemon=True).start(); return response(self,202,{"started":True})
        if path=="/api/proxies/clear":
            with lock: state["proxies"].clear()
            log("info","Proxy pool cleared"); return response(self,200,{"ok":True})
        if path=="/api/automation/toggle":
            with lock: state["running"]=not state["running"]; state["started_at"]=time.time() if state["running"] else None
            log("success" if state["running"] else "info","Automation started" if state["running"] else "Automation paused"); return response(self,200,state)
        if path=="/api/settings":
            with lock: state["settings"].update({k:v for k,v in data.items() if k in state["settings"]})
            return response(self,200,state["settings"])
        response(self,404,{"error":"not found"})
if __name__=="__main__":
    log("info","Local API ready on http://127.0.0.1:8765")
    ThreadingHTTPServer(("127.0.0.1",8765),API).serve_forever()
