from fastapi.testclient import TestClient
from nse_ipo_analyzer.api.main import app
c = TestClient(app)
print('health:', c.get('/health').status_code)
print('backtest:', c.get('/models/backtest').status_code)
print('perf:', c.get('/models/performance').status_code)
print('index:', c.get('/').status_code)
ipos = c.get('/ipos').json()
print('n_ipos:', len(ipos))
