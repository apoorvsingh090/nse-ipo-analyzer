import sqlite3
c = sqlite3.connect('nse_ipo_analyzer/data/ipo_analyzer.db')
print('--- by status ---')
for r in c.execute('select status, count(*) from ipos group by status'):
    print(r)
print('--- all ipos ---')
for r in c.execute('select id, company_name, status, open_date, close_date from ipos order by id'):
    print(r)
