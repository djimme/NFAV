import sys
sys.path.insert(0, '.')
from fin_utils import fetch_fnguide_page
from bs4 import BeautifulSoup

# 한 종목만 상세 확인
code = '138930'
content = fetch_fnguide_page(code, 'SVD_Finance.asp', '103', 'fnguide_finance_')
html = BeautifulSoup(content, 'html.parser')

# div id 목록 확인
divs_with_id = html.find_all('div', id=True)
print(f"=== {code} 모든 div id 목록 ===")
for d in divs_with_id:
    print(f"  #{d['id']}")

# table id 목록
tables_with_id = html.find_all('table', id=True)
print(f"\n=== table id 목록 ===")
for t in tables_with_id:
    print(f"  #{t['id']}")

# 탭 버튼/링크 확인
print(f"\n=== 탭 구조 (li, button, a 중 '연간','분기' 관련) ===")
for el in html.find_all(['li', 'button', 'a']):
    text = el.get_text(strip=True)
    if '연간' in text or '분기' in text or '年' in text or 'Annual' in text:
        print(f"  <{el.name} id={el.get('id','')}>: {text[:60]}")

# Section 구조 파악
print(f"\n=== section / article 구조 ===")
for el in html.find_all(['section', 'article']):
    print(f"  <{el.name} id={el.get('id','')} class={el.get('class','')}>")
