"""Small dependency-free API smoke test. Start backend first: python backend/main.py"""
import json, urllib.request, urllib.error
BASE='http://127.0.0.1:8765'
def call(path, data=None):
 req=urllib.request.Request(BASE+path, data=json.dumps(data).encode() if data is not None else None, headers={'Content-Type':'application/json'}, method='POST' if data is not None else 'GET')
 with urllib.request.urlopen(req, timeout=3) as r: return json.loads(r.read())
assert call('/api/health')['ok'] is True
call('/api/proxies/clear', {})
result=call('/api/proxies/import', {'text':'127.0.0.1:8080\nnot-a-proxy'})
assert result['added'] == 1 and result['errors']
state=call('/api/state')
assert state['proxies'][0]['id']
settings=call('/api/settings', {'retries': 3, 'verify': False, 'rotation': 'round_robin'})
assert settings['retries'] == 3 and settings['verify'] is False
task=call('/api/tasks/create', {'name':'Smoke test','url':'https://example.com'})
assert task['id']
call('/api/tasks/toggle', {'id':task['id']})
try:
	call('/api/tasks/run', {'id':task['id']})
	raise AssertionError('disabled task was allowed to run')
except urllib.error.HTTPError as error:
	assert error.code == 409
state=call('/api/state'); assert state['tasks'] and 'stats' in state
try:
	call('/api/tasks/delete', {'id': 999999})
	raise AssertionError('missing task was deleted')
except urllib.error.HTTPError as error:
	assert error.code == 409
print('API smoke test passed')
