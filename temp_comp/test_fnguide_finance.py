# -*- coding: utf-8 -*-
"""parseFnguideFinance 동작 검증: 은행(138930), 보험(005830), 창투(241520) 3종목"""
import sys
sys.path.insert(0, '.')
from fnguideFinance import getFnguideFinance, parseFnguideFinance

test_cases = [
    ('138930', 'bank'),
    ('005830', 'insurance'),
    ('241520', 'venture'),
]

for code, label in test_cases:
    html = getFnguideFinance(code)
    result = parseFnguideFinance(html)
    if result is None:
        print(f'[{label} {code}] None')
        continue

    lines = []
    lines.append(f'=== [{label} {code}] name={result.get("name", result.get("종목명","?"))} ===')
    lines.append(f'  mkt={result.get("mkt", result.get("마켓분야","?"))}  fics={result.get("fics", result.get("FICS분야","?"))}')
    lines.append(f'  fiscal={result.get("fiscal", result.get("결산월","?"))}  consol={result.get("consol", result.get("연결여부","?"))}')

    annual = sorted([k for k in result if len(k) > 4 and k[:4].isdigit() and k[4] == '_' and '/' not in k])
    qtr    = sorted([k for k in result if len(k) > 7 and k[:4].isdigit() and '/' in k[4:8]])

    lines.append(f'  --- annual ({len(annual)}) ---')
    for k in annual:
        lines.append(f'    {k}: {result[k]}')
    lines.append(f'  --- quarterly ({len(qtr)}) ---')
    for k in qtr:
        lines.append(f'    {k}: {result[k]}')

    with open('temp_comp/test_finance_result.txt', 'a', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n\n')

print('done -> temp_comp/test_finance_result.txt')
