# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, '.')
from fin_utils import fetch_fnguide_page
from bs4 import BeautifulSoup

new_codes = ['016610','078020','005940','001510','130610','030210','003540','138040',
             '006800','001270','016360','001290','001720','003470','001200','003460',
             '190650','039490','071050','001750','003530','001500']

prev_ref_code = '138930'  # BNK금융지주 (앞서 9개 종목 기준)
all_codes = new_codes + [prev_ref_code]

results = {}
for code in all_codes:
    content = fetch_fnguide_page(code, 'SVD_Finance.asp', '103', 'fnguide_finance_')
    html = BeautifulSoup(content, 'html.parser')
    info = {}
    name_el = html.select_one('#giName')
    info['종목명'] = name_el.get_text(strip=True) if name_el else 'N/A'
    for tab_id, tab_name in [
        ('#divSonikY', '손익Y'), ('#divSonikQ', '손익Q'),
        ('#divDaechaY', '대차Y'), ('#divDaechaQ', '대차Q'),
        ('#divCashY', '현금Y'), ('#divCashQ', '현금Q')
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
    print('OK ' + code + ' ' + info['종목명'])


def compare_group(codes, label, results):
    out = ['', '='*70, '  ' + label, '='*70]
    for tab_name in ['손익Y', '손익Q', '대차Y', '대차Q', '현금Y', '현금Q']:
        hkey = tab_name + '_헤더'
        rkey = tab_name + '_행'
        out.append('')
        out.append('  --- [' + tab_name + '] ---')

        hdrs = {c: results[c][hkey] for c in codes if hkey in results[c]}
        missing_codes = [c for c in codes if results[c].get(tab_name) == 'MISSING']
        if missing_codes:
            names = [c + '(' + results[c]['종목명'] + ')' for c in missing_codes]
            out.append('  MISSING: ' + str(names))

        if not hdrs:
            out.append('  전체 MISSING')
            continue

        ref_code = list(hdrs.keys())[0]
        ref_h = hdrs[ref_code]
        diff_h = {c: h for c, h in hdrs.items() if h != ref_h}

        if diff_h:
            out.append('  헤더: 불일치 있음')
            out.append('  기준(' + ref_code + ' ' + results[ref_code]['종목명'] + '): ' + str(ref_h))
            for c, h in diff_h.items():
                out.append('  !! ' + c + ' ' + results[c]['종목명'] + ': ' + str(h))
        else:
            out.append('  헤더: 전체 동일 -> ' + str(ref_h))

        rws = {c: results[c][rkey] for c in codes if rkey in results[c]}
        if not rws:
            out.append('  행 데이터 없음')
            continue

        ref_r = rws[list(rws.keys())[0]]
        diff_r = {c: r for c, r in rws.items() if r != ref_r}

        if diff_r:
            out.append('  행: 불일치 있음')
            out.append('  기준(' + ref_code + ' ' + results[ref_code]['종목명'] + '): ' + str(len(ref_r)) + '행 -> ' + str(ref_r))
            for c, r in diff_r.items():
                ref_set = set(ref_r)
                cur_set = set(r)
                only_in_ref = ref_set - cur_set
                only_in_cur = cur_set - ref_set
                out.append('  !! ' + c + ' ' + results[c]['종목명'] + ': ' + str(len(r)) + '행')
                if only_in_ref:
                    out.append('     기준에만 있는 항목: ' + str(sorted(only_in_ref)))
                if only_in_cur:
                    out.append('     ' + c + '에만 있는 항목: ' + str(sorted(only_in_cur)))
        else:
            out.append('  행(' + str(len(ref_r)) + '개): 전체 동일 -> ' + str(ref_r))
    return out


out = []

# 1) 신규 22개 종목 내부 비교
out += compare_group(new_codes, '신규 22개 종목 내부 비교', results)

# 2) 신규 1개 vs 이전 9개 기준 종목 비교
sample_new = new_codes[0]
out += compare_group(
    [sample_new, prev_ref_code],
    '신규(' + sample_new + ' ' + results[sample_new]['종목명'] + ') vs 이전기준(' + prev_ref_code + ' ' + results[prev_ref_code]['종목명'] + ')',
    results
)

output = '\n'.join(out)
with open('temp_comp/structure_check3.txt', 'w', encoding='utf-8') as f:
    f.write(output)
print('\nsaved to temp_comp/structure_check3.txt')
