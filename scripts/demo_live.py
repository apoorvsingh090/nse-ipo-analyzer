from fastapi.testclient import TestClient
from nse_ipo_analyzer.api.main import app
import json
c = TestClient(app)
r = c.get('/live/upcoming', params={'enrich': False})
d = r.json()
print('status:', r.status_code, 'count:', d.get('count'), 'asof:', d.get('asof'))
for x in d.get('records', [])[:10]:
    print(f"- {x['company_name']} ({x['symbol']}, {x['segment']}, {x['status']}) "
          f"band {x['price_band_low']}-{x['price_band_high']} "
          f"{x['open_date']}->{x['close_date']} sub={x['total_sub_x']}x")
