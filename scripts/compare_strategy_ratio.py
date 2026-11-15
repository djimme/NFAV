"""
재무비율·주당 지표의 출처를 FnGuide 4월 값에서 DART 계산 값으로 바꾸면 전략 결과가 얼마나 달라지는지 본다.
(설정의 ratio_source = "dart" 와 같은 경로 — strat_utils.apply_dart_ratio — 를 그대로 쓴다)

사용:
  python scripts/compare_strategy_ratio.py
  → derived/dart_ratio_strategy_compare_YYYY_MM.xlsx

비교 대상 (finance 파일·시가총액 등 나머지 입력은 그대로):
  A. FnGuide 그대로 (지금 기본 설정) — snapshot의 2026·2027 열은 증권사 추정치라서 PEG는 선행 PER을 쓰게 된다
  B. FnGuide 값에서 2025년까지의 실적 열만 남긴 것 (C와 같은 조건의 기준선)
  C. DART 값, 결산월 말 종가 기준 (B와 같은 방식 — 값의 차이만 본다)
  D. DART 값, 최근 거래일 종가 기준 (ratio_source = "dart" 의 기본 동작)
  Greenblatt는 EV/EBITDA 기준과 EV/EBIT 기준을 따로 낸다.
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); os.chdir(ROOT)

import pandas as pd

from agent_config import COMMON_FILTERS, DATA_CONFIG, STRATEGY_CONFIG
from fin_utils import save_styled_excel_multisheet
from strat_greenblatt import strategy_greenblatt
from strat_peg import strategy_peg
from strat_piotroski import strategy_piotroski
from strat_utils import DART_RATIO_SUFFIXES, _YEAR_COL, apply_common_filters, load_all_data, merge_base

LAST_ACTUAL_YEAR = 2025      # FnGuide 4월 파일에서 실적이 있는 마지막 연도 (그 뒤 열은 추정치)


def _drop_estimates(df):
    return df.drop(columns=[c for c in df.columns if (m := _YEAR_COL.match(c)) and int(m.group(1)) > LAST_ACTUAL_YEAR
                            and c.endswith(DART_RATIO_SUFFIXES)])


def run_all(base):
    base = apply_common_filters(base.copy(), COMMON_FILTERS)
    gb = STRATEGY_CONFIG['greenblatt']
    res = {'공통 필터 후': base, 'Piotroski': strategy_piotroski(base, STRATEGY_CONFIG['piotroski']),
           'PEG': strategy_peg(base, STRATEGY_CONFIG['peg']),
           'Greenblatt(EV/EBITDA)': strategy_greenblatt(base, dict(gb, ev_metric='EV/EBITDA')),
           'Greenblatt(EV/EBIT)': strategy_greenblatt(base, dict(gb, ev_metric='EV/EBIT'))}
    return {k: (set(v['종목코드']) if len(v) else set()) for k, v in res.items()}


if __name__ == '__main__':
    cfg = dict(DATA_CONFIG, ratio_source='fnguide')
    data = load_all_data(cfg)
    base_a = merge_base(data)
    dart_data = load_all_data(dict(cfg, ratio_source='dart'))
    res = {'A_FnGuide그대로': run_all(base_a), 'B_FnGuide실적만': run_all(_drop_estimates(base_a)),
           'C_DART(결산월말 주가)': run_all(merge_base(dict(dart_data, dart_price_basis='fiscal_year_end'))),
           'D_DART(현재가)': run_all(merge_base(dict(dart_data, dart_price_basis='current')))}
    names = dict(zip(base_a['종목코드'], base_a['종목명']))
    pairs = (('B_FnGuide실적만', 'C_DART(결산월말 주가)'), ('C_DART(결산월말 주가)', 'D_DART(현재가)'), ('A_FnGuide그대로', 'D_DART(현재가)'))
    rows, detail = [], []
    for strat in res['A_FnGuide그대로']:
        rows.append({'전략': strat, **{k: len(v[strat]) for k, v in res.items()}})
        for a, b in pairs:
            sa, sb = res[a][strat], res[b][strat]
            rows.append({'전략': f'  {a} → {b}', '둘 다': len(sa & sb), '앞에만': len(sa - sb), '뒤에만': len(sb - sa),
                         '겹침(%)': round(len(sa & sb) / len(sa | sb) * 100, 1) if sa | sb else None})
            if strat != '공통 필터 후':
                detail += [{'전략': strat, '비교': f'{a} → {b}', '구분': '앞에만', '종목코드': c, '종목명': names.get(c)} for c in sorted(sa - sb)]
                detail += [{'전략': strat, '비교': f'{a} → {b}', '구분': '뒤에만', '종목코드': c, '종목명': names.get(c)} for c in sorted(sb - sa)]
    summary = pd.DataFrame(rows)
    from strat_utils import _latest_file
    src = _latest_file(DATA_CONFIG['dart_ratio_file'])
    out = os.path.join('derived', os.path.basename(src).replace('dart_ratio_', 'dart_ratio_strategy_compare_'))
    save_styled_excel_multisheet([('요약', summary), ('달라진 종목', pd.DataFrame(detail))], out)
    pd.set_option('display.width', 250)
    print(summary.to_string(index=False)); print('저장:', out)
