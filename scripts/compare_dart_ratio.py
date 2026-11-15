"""
DART로 직접 계산한 재무비율(dart_ratio)을 FnGuide 4월 ratio·snapshot·invest_idx 파일과 대조한다 (4단계 검증).

사용:
  python scripts/compare_dart_ratio.py [dart_ratio 파일]
  → derived/dart_ratio_compare_YYYY_MM.xlsx   (시트: 요약 / 지표별 / 연도별 / 종목별 / 불일치상세)

일치 기준: 차이가 0.15 이하이거나 FnGuide 값의 1% 이하 (FnGuide는 소수 첫째 자리까지 표시).
           EPS·BPS(원)은 차이 1원 이하이거나 1% 이하, PBR(배)은 0.02 이하이거나 1% 이하.
           '순위상관' 열은 두 값의 순위가 얼마나 같은지(1에 가까울수록 같은 순서 — 스크리닝 결과에 중요).
           '5% 이내' 열은 차이가 FnGuide 값의 5% 이하인 칸의 비율(정의 차이로 조금 어긋난 칸을 가려 본다).
"""
import glob
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); os.chdir(ROOT)

import pandas as pd

from fin_utils import save_styled_excel_multisheet

FNG_RATIO = 'derived/finance_ratio_2026_04_v2.xlsx'
FNG_SNAPSHOT = 'derived/snapshot_2026_04.xlsx'
FNG_INVEST = 'derived/invest_idx_2026_04.xlsx'
_SNAP_METRICS = ('_EPS(원)', '_BPS(원)', '_PER(배)', '_PBR(배)')
_TOL = {'EPS(원)': 1.0, 'BPS(원)': 1.0, 'PBR(배)': 0.02}
_COL = re.compile(r'^(\d{4})(\(누적\))?_(.+)$')


def _load_fng():
    sheets = pd.read_excel(FNG_RATIO, sheet_name=None, dtype={'종목코드': str})
    rat = pd.concat([v.assign(시트=k) for k, v in sheets.items()], ignore_index=True)
    snap = pd.read_excel(FNG_SNAPSHOT, dtype={'종목코드': str})
    eps = snap[['종목코드'] + [c for c in snap.columns if c.endswith(_SNAP_METRICS)]]
    inv = pd.read_excel(FNG_INVEST, dtype={'종목코드': str})
    inv = inv[['종목코드'] + [c for c in inv.columns if c.endswith('_EV/EBITDA')]]
    f = rat.merge(eps, on='종목코드', how='outer').merge(inv, on='종목코드', how='outer')
    f['종목코드'] = f['종목코드'].str.zfill(6)
    return f.drop_duplicates('종목코드').set_index('종목코드')


def compare(dart_path):
    dart = pd.read_excel(dart_path, dtype={'종목코드': str})
    dart['종목코드'] = dart['종목코드'].str.zfill(6)
    dart = dart.set_index('종목코드')
    fng = _load_fng()
    cols = [c for c in dart.columns if _COL.match(c) and c in fng.columns]
    codes = [c for c in dart.index if c in fng.index]
    recs = []
    for col in cols:
        y, _, metric = _COL.match(col).groups()
        a_s = pd.to_numeric(fng.loc[codes, col], errors='coerce')
        b_s = pd.to_numeric(dart.loc[codes, col], errors='coerce')
        tol = _TOL.get(metric, 0.15)
        for code, a, b in zip(codes, a_s, b_s):
            if pd.isna(a):
                continue
            if pd.isna(b):
                recs.append((code, metric, int(y), a, None, None, 'DART 값 없음', False))
                continue
            ok = abs(b - a) <= tol or abs(b - a) <= abs(a) * 0.01
            recs.append((code, metric, int(y), a, b, round(b - a, 2), '일치' if ok else '불일치',
                         ok or abs(b - a) <= abs(a) * 0.05))
    r = pd.DataFrame(recs, columns=['종목코드', '지표', '연도', 'FnGuide', 'DART', '차이', '결과', '5%이내'])
    r.insert(1, '종목명', r['종목코드'].map(dart['종목명']))
    r.insert(2, '시트', r['종목코드'].map(fng['시트']))

    def table(keys):
        g = r.groupby(keys)['결과'].value_counts().unstack(fill_value=0)
        for k in ('일치', '불일치', 'DART 값 없음'):
            if k not in g:
                g[k] = 0
        g['비교 칸'] = g['일치'] + g['불일치']
        g['일치율(%)'] = (g['일치'] / g['비교 칸'].where(g['비교 칸'] > 0) * 100).round(2)
        g['5% 이내(%)'] = (r.groupby(keys)['5%이내'].sum() / g['비교 칸'].where(g['비교 칸'] > 0) * 100).round(2)
        both = r[r['DART'].notna()]
        g['순위상관'] = both.groupby(keys).apply(lambda d: d['FnGuide'].rank().corr(d['DART'].rank()) if len(d) > 2 else None,
                                              include_groups=False).round(3)
        return g[['비교 칸', '일치', '불일치', '일치율(%)', '5% 이내(%)', '순위상관', 'DART 값 없음']].reset_index()

    cmp_ = r[r['결과'] != 'DART 값 없음']
    summary = pd.DataFrame([
        ('DART 파일', dart_path), ('FnGuide 파일', f'{FNG_RATIO}, {FNG_SNAPSHOT}, {FNG_INVEST}'),
        ('일치 기준', '차이 0.15 이하 또는 1% 이하 (EPS·BPS는 1원 또는 1%, PBR은 0.02 또는 1%)'),
        ('DART 계산 종목 수', len(dart)), ('양쪽 모두 있는 종목 수', len(codes)),
        ('비교 칸', len(cmp_)), ('일치', int((cmp_['결과'] == '일치').sum())),
        ('불일치', int((cmp_['결과'] == '불일치').sum())),
        ('일치율(%)', round((cmp_['결과'] == '일치').mean() * 100, 2) if len(cmp_) else None),
        ('DART 값 없음(FnGuide만 있음)', int((r['결과'] == 'DART 값 없음').sum())),
    ], columns=['항목', '값'])
    summary['값'] = summary['값'].astype(str)
    per_stock = table(['종목코드', '종목명', '시트']).drop(columns='순위상관').sort_values('일치율(%)')
    mm = r[r['결과'] == '불일치'].drop(columns='5%이내').sort_values(['지표', '연도', '종목코드'])
    sheets = [('요약', summary), ('지표별', table(['지표'])), ('시트별_지표별', table(['시트', '지표'])),
              ('연도별', table(['지표', '연도'])), ('종목별', per_stock), ('불일치상세', mm)]
    out = os.path.join('derived', os.path.basename(dart_path).replace('dart_ratio_', 'dart_ratio_compare_'))
    save_styled_excel_multisheet(sheets, out)
    return out, dict(sheets)


if __name__ == '__main__':
    path = sys.argv[1] if len(sys.argv) > 1 else \
        sorted(f for f in glob.glob('derived/dart_ratio_2*.xlsx') if not f.endswith('_test.xlsx'))[-1]
    out, s = compare(path)
    pd.set_option('display.width', 200); pd.set_option('display.max_rows', 100)
    for name in ('요약', '지표별', '연도별'):
        print(f'\n== {name}'); print(s[name].to_string(index=False))
    print('저장:', out)
