"""Small dependency-free API smoke test. Start backend first: python backend/main.py"""
import json, urllib.request
BASE='http://127.0.0.1:8765'
def call(path, data=None):
 req=urllib.request.Request(BASE+path, data=json.dumps(data).encode() if data is not None else None, headers={'Content-Type':'application/json'}, method='POST' if data is not None else 'GET')
 with urllib.request.urlopen(req, timeout=3) as r: return json.loads(r.read())
assert call('/api/health')['ok'] is True
call('/api/proxies/clear', {})
result=call('/api/proxies/import', {'text':'127.0.0.1:8080\nnot-a-proxy'})
assert result['added'] == 1 and result['errors']
task=call('/api/tasks/create', {'name':'Smoke test','url':'https://example.com'})
assert task['id']
state=call('/api/state'); assert state['tasks']
print('API smoke test passed')
