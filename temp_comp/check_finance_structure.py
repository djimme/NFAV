import sys
sys.path.insert(0, '.')
from fin_utils import fetch_fnguide_page
from bs4 import BeautifulSoup

codes = ['138930','175330','105560','139130','024110','055550','316140','006220','323410','086790']
results = {}
for code in codes:
    content = fetch_fnguide_page(code, 'SVD_Finance.asp', '103', 'fnguide_finance_')
    html = BeautifulSoup(content, 'html.parser')
    info = {}
    name_el = html.select_one('#giName')
    info['종목명'] = name_el.get_text(strip=True) if name_el else 'N/A'
    for tab_id, tab_name in [
        ('#divSonikA', '손익A'), ('#divSonikQ', '손익Q'),
        ('#divDaechaA', '대차A'), ('#divDaechaQ', '대차Q'),
        ('#divCashA', '현금A'), ('#divCashQ', '현금Q')
    ]:
        el = html.select_one(tab_id)
        if el:
            headers = [th.get_text(strip=True) for th in el.select('thead th')]
            rows = [
                tr.select_one('div').get_text(strip=True).replace('\xa0', '')
                for tr in el.select('tbody tr')
                if tr.select_one('div')
            ]
            info[tab_name + '_헤더'] = headers
            info[tab_name + '_행'] = rows
        else:
            info[tab_name] = 'MISSING'
    results[code] = info
    print(f"OK {code} {info['종목명']}")

out = []
for tab_name in ['손익A', '손익Q', '대차A', '대차Q', '현금A', '현금Q']:
    hkey = tab_name + '_헤더'
    rkey = tab_name + '_행'
    out.append(f'\n=== [{tab_name}] ===')

    hdrs = {code: info[hkey] for code, info in results.items() if hkey in info}
    if not hdrs:
        out.append('  전체 MISSING')
        continue

    ref_code = list(hdrs.keys())[0]
    ref_h = hdrs[ref_code]
    out.append(f'  기준헤더({ref_code} {results[ref_code]["종목명"]}): {ref_h}')

    diff_h = [c for c, h in hdrs.items() if h != ref_h]
    if diff_h:
        for c in diff_h:
            out.append(f'  !! 헤더차이 {c} {results[c]["종목명"]}: {hdrs[c]}')
    else:
        out.append('  헤더: 전체 동일')

    rws = {code: info[rkey] for code, info in results.items() if rkey in info}
    if not rws:
        out.append('  행 데이터 없음')
        continue

    ref_r = rws[list(rws.keys())[0]]
    diff_r = {c: r for c, r in rws.items() if r != ref_r}

    if diff_r:
        out.append(f'  기준행({ref_code}): {len(ref_r)}행')
        out.append(f'  기준항목: {ref_r}')
        for c, r in diff_r.items():
            out.append(f'  !! 행차이 {c} {results[c]["종목명"]}: {len(r)}행')
            out.append(f'     항목: {r}')
    else:
        out.append(f'  행({len(ref_r)}개): 전체 동일')
        out.append(f'  항목: {ref_r}')

output = '\n'.join(out)
with open('temp_comp/structure_check.txt', 'w', encoding='utf-8') as f:
    f.write(output)
print('\nsaved to temp_comp/structure_check.txt')
