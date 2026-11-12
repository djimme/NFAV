"""
finance 파일만 바꿔서(FnGuide 4월 ↔ DART) Piotroski·PEG 결과가 어떻게 달라지는지 비교한다.
snapshot·ratio·invest_idx 등 나머지 입력과 전략 코드는 그대로 둔다.

사용:
  python scripts/compare_strategy_finance.py
  → derived/dart_finance_strategy_compare_YYYY_MM.xlsx

비교 대상:
  A. FnGuide 4월 finance (기본 설정)
  B. DART finance 파일 그대로
  C. DART finance 에서 '최신 연간 열'을 대부분 종목에 값이 있는 최근 연도로 맞춘 것
     — Piotroski는 전 종목에 '가장 최근 연도의 (연간) 열' 하나를 쓰므로, 3·6월 결산사 몇 곳만 값이 있는
       2026(연간) 열이 생기면 나머지 종목의 현금흐름 점수(F2·F4)가 0이 된다. C는 그 영향을 뺀 비교다.
"""
import glob
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); os.chdir(ROOT)

import pandas as pd

from agent_config import COMMON_FILTERS, DATA_CONFIG, STRATEGY_CONFIG
from fin_utils import save_styled_excel_multisheet
from strat_peg import strategy_peg
from strat_piotroski import strategy_piotroski
from strat_utils import apply_common_filters, load_all_data, merge_base, _recent_cols

FNG_FILE = 'derived/finance_2026_04_v2.xlsx'


def run(finance_file, drop_sparse_annual=False):
    data = load_all_data(dict(DATA_CONFIG, finance_file=finance_file))
    note = ''
    if drop_sparse_annual:
        fin = data['finance']
        n = len(fin)
        for suffix in ('(연간)_영업활동현금흐름', '(연간)_당기순이익'):
            for col in _recent_cols(fin, suffix, n=5):
                if fin[col].notna().sum() >= n * 0.5:     # 절반 이상 종목에 값이 있는 최근 연도에서 멈춘다
                    break
                fin = fin.drop(columns=[col])
                note += f'{col} 제외 '
        data['finance'] = fin
    base = apply_common_filters(merge_base(data), COMMON_FILTERS)
    cf = _recent_cols(base, '(연간)_영업활동현금흐름')[:1]
    ni = _recent_cols(base, '(연간)_당기순이익')[:1]
    # min_score 0으로 전 종목 점수를 받은 뒤, 설정된 기준 점수로 통과 여부를 계산한다
    pio_all = strategy_piotroski(base, dict(STRATEGY_CONFIG['piotroski'], min_score=0))
    yrs = pio_all['연간기준연도'].value_counts(dropna=False).sort_index(ascending=False)
    info = {'finance 파일': finance_file, '공통 필터 후 종목 수': len(base),
            '가장 최근 영업CF 열': cf[0] if cf else '',
            '그 열에 값이 있는 종목 수': int(base[cf[0]].notna().sum()) if cf else 0,
            '가장 최근 순이익 열': ni[0] if ni else '',
            'Piotroski 연간 기준연도별 종목 수': ', '.join(f'{"없음" if pd.isna(y) else int(y)}: {c}' for y, c in yrs.items()),
            '비고': note}
    peg = strategy_peg(base, STRATEGY_CONFIG['peg'])
    return info, pio_all, peg


if __name__ == '__main__':
    dart_file = sorted(f for f in glob.glob('derived/dart_finance_2*.xlsx') if not f.endswith('_test.xlsx'))[-1]
    min_score = STRATEGY_CONFIG['piotroski']['min_score']
    runs = {'A_FnGuide4월': run(FNG_FILE), 'B_DART그대로': run(dart_file), 'C_DART연도맞춤': run(dart_file, True)}

    rows, pio = [], None
    for name, (info, p, peg) in runs.items():
        rows.append({'구분': name, **info, f'Piotroski 통과(F≥{min_score})': int((p['F_Score'] >= min_score).sum()),
                     'F2 통과': int(p['F2_현금흐름양수'].sum()), 'F4 통과': int(p['F4_현금흐름품질'].sum()),
                     '평균 F_Score': round(p['F_Score'].mean(), 3), 'PEG 통과': len(peg)})
        s = p.set_index('종목코드')[['종목명', 'F_Score', 'F2_현금흐름양수', 'F4_현금흐름품질']].add_suffix(f'_{name[0]}')
        pio = s if pio is None else pio.join(s, how='outer')
    summary = pd.DataFrame(rows)
    pio = pio.reset_index()
    pio.insert(1, '종목명', pio['종목명_A'].fillna(pio['종목명_B']))
    pio = pio.drop(columns=['종목명_A', '종목명_B', '종목명_C'])
    for x in 'ABC':
        pio[f'통과_{x}'] = pio[f'F_Score_{x}'] >= min_score
    changes = []
    for x in 'BC':
        a, b = pio['통과_A'], pio[f'통과_{x}']
        changes.append({'비교': f'A → {x}', '둘 다 통과': int((a & b).sum()), 'A만 통과(탈락)': int((a & ~b).sum()),
                        f'{x}만 통과(신규)': int((~a & b).sum()),
                        'F_Score 달라진 종목': int((pio['F_Score_A'] != pio[f'F_Score_{x}']).sum()),
                        'F2 달라진 종목': int((pio['F2_현금흐름양수_A'] != pio[f'F2_현금흐름양수_{x}']).sum()),
                        'F4 달라진 종목': int((pio['F4_현금흐름품질_A'] != pio[f'F4_현금흐름품질_{x}']).sum())})
    changes = pd.DataFrame(changes)
    diff = pio[(pio['통과_A'] != pio['통과_C']) | (pio['F_Score_A'] != pio['F_Score_C'])].copy()
    for x in 'ABC':
        pio[f'통과_{x}'] = pio[f'통과_{x}'].astype(int)
        diff[f'통과_{x}'] = diff[f'통과_{x}'].astype(int)
    pegA, pegB = runs['A_FnGuide4월'][2], runs['B_DART그대로'][2]
    peg_cmp = pd.DataFrame([{'PEG 통과(A)': len(pegA), 'PEG 통과(B)': len(pegB),
                             '종목 구성 동일': str(set(pegA['종목코드']) == set(pegB['종목코드'])),
                             '설명': 'PEG는 finance 파일을 쓰지 않는다(PER=snapshot, EPS=invest_idx, 부채비율=ratio)'}])
    out = os.path.join('derived', os.path.basename(dart_file).replace('dart_finance_', 'dart_finance_strategy_compare_'))
    save_styled_excel_multisheet([('요약', summary), ('Piotroski_변화', changes), ('PEG', peg_cmp),
                                  ('Piotroski_A대C_차이종목', diff), ('Piotroski_전종목', pio)], out)
    pd.set_option('display.width', 250); pd.set_option('display.max_columns', 30)
    print(summary.T.to_string()); print(changes.T.to_string()); print(peg_cmp.T.to_string())
    print('저장:', out)
