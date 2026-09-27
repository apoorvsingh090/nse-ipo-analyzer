from fastapi.testclient import TestClient
from nse_ipo_analyzer.api.main import app
import json
c = TestClient(app)
ipos = c.get('/ipos').json()
ex = [x for x in ipos if x['company_name'] == 'Narmada AgroTech Ltd'][0]
print('example:', ex['id'], ex['company_name'])
r = c.post(f"/ipos/{ex['id']}/analyze").json()
print('keys:', list(r.keys()))
print('valuation:', json.dumps(r['valuation'], indent=1)[:600])
print('prediction:', json.dumps(r['prediction'], indent=1)[:1200])
print('pillars:', list(r['assessment']['pillars'].keys()))
print('for:', r['assessment']['evidence_for'][:4])
print('against:', r['assessment']['evidence_against'][:4])
print('narrative:', r.get('narrative'))
