from fastapi.testclient import TestClient
from nse_ipo_analyzer.api.main import app
import json
c = TestClient(app)
r = c.post('/ipos/import', json={'symbol': 'MONEYVIEW', 'enrich': True})
d = r.json()
print('import status:', r.status_code)
print(json.dumps({k: d.get(k) for k in ('ipo_id', 'created', 'company', 'symbol', 'next')}, indent=1))
rec = d.get('record', {})
print('enriched:', {k: rec.get(k) for k in ('lot_size', 'issue_size_cr', 'fresh_issue_cr',
      'ofs_cr', 'min_investment', 'qib_pct', 'nii_pct', 'retail_pct',
      'listing_date', 'enrichment')})
a = c.post(f"/ipos/{d['ipo_id']}/analyze").json()
print('report keys ok:', all(k in a for k in ('valuation', 'demand', 'gmp', 'assessment', 'prediction')))
print('demand latest:', (a.get('demand') or {}).get('latest'))
print('structure:', {k: (a.get('structure') or {}).get(k) for k in ('fresh_pct', 'ofs_pct')})
print('for:', (a.get('assessment') or {}).get('evidence_for')[:3])
print('against:', (a.get('assessment') or {}).get('evidence_against')[:3])
