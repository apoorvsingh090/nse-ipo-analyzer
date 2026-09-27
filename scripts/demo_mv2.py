"""Re-import Moneyview (fills financials/anchor/GMP) and print the report."""
from fastapi.testclient import TestClient
from nse_ipo_analyzer.api.main import app
import json
c = TestClient(app)
imp = c.post('/ipos/import', json={'symbol': 'MONEYVIEW', 'enrich': True, 'gmp': True}).json()
print('import:', json.dumps({k: imp.get(k) for k in ('ipo_id', 'created', 'financials_added', 'gmp')}, indent=1, default=str))
a = c.post(f"/ipos/{imp['ipo_id']}/analyze").json()
print('valuation:', json.dumps(a['valuation'], indent=1)[:500])
print('vsPeers:', json.dumps(a['valuation_vs_peers'], indent=1)[:300])
print('growth:', json.dumps({k: {'cagr': v.get('cagr_3y_pct'), 'yoy': v.get('latest_yoy_pct')} for k, v in a['growth'].items()}, indent=1))
print('fq:', json.dumps(a['financial_quality'], indent=1))
print('demand:', json.dumps((a.get('demand') or {}).get('latest'), indent=1, default=str)[:400])
print('gmp:', json.dumps({k: a['gmp'].get(k) for k in ('latest_gmp', 'implied_listing_price', 'gmp_pct', 'momentum', 'source_kind')}, indent=1))
print('anchor:', json.dumps(a['anchor'], indent=1, default=str)[:500])
print('pred:', json.dumps({k: (a.get('prediction') or {}).get(k) for k in ('expected_gain_pct', 'expected_listing_price', 'ci_low_pct', 'ci_high_pct', 'confidence')}, indent=1))
print('for:', (a.get('assessment') or {}).get('evidence_for'))
print('against:', (a.get('assessment') or {}).get('evidence_against'))
