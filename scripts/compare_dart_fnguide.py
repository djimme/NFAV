"""
DART finance 파일(apiCollect.py dart_finance)과 FnGuide finance 파일을 칸 단위로 대조한다.

사용:
  python scripts/compare_dart_fnguide.py                       # 최신 dart_finance_*.xlsx vs finance_2026_04_v2.xlsx
  python scripts/compare_dart_fnguide.py derived/dart_finance_2026_11_test.xlsx   # 샘플(test) 파일
  → derived/dart_finance_compare_YYYY_MM[_test].xlsx
  python scripts/compare_dart_fnguide.py derived/dart_finance_2026_11.xlsx derived/finance_2026_11.xlsx
                                                               # FnGuide 파일을 직접 지정 (개편 후 11월 파일 등)
  → derived/dart_finance_compare_YYYY_MM_vs_finance_2026_11.xlsx   (기본 파일이 아니면 이름에 FnGuide 파일을 붙인다)

일치 기준: 두 값의 차이가 1억원 이하 (FnGuide는 억원 단위 반올림 값).
시트: 요약 / 지표별 / 기간별 / 불일치유형 / 종목별 / 불일치상세 / 수집실패 / 업종구분차이
"""
import glob
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); os.chdir(ROOT)

import pandas as pd

from fin_utils import save_styled_excel_multisheet

FNG_FILE = 'derived/finance_2026_04_v2.xlsx'
TOL = 1.0
# 개편 후 FnGuide(2026-11~) 항목 이름 → DART 파일(=개편 전 FnGuide) 컬럼 이름.
# 11월 FnGuide 파일은 새 사이트 이름 그대로 저장되므로, 비교할 때만 이 대응으로 맞춘다.
FNG_NEW_NAMES = {
    '법인세비용차감전계속사업이익': '세전계속사업이익',
    '순영업이익': '순영업수익',
}
COL_RE = re.compile(r'^(\d{4})(?:/(\d)Q)?(\((?:연간|누적)\))?_(.+)$')


def _load(path):
    sheets = pd.read_excel(path, sheet_name=None, dtype={'종목코드': str})
    df = pd.concat([v.assign(시트=k) for k, v in sheets.items()], ignore_index=True)
    df['종목코드'] = df['종목코드'].str.zfill(6)
    return df.drop_duplicates('종목코드').set_index('종목코드')


def _load_fng(path):
    """FnGuide finance 파일을 읽고, 개편 후 이름을 DART 쪽 이름으로 바꾼다. → (df, 바꾼 이름 목록)"""
    df = _load(path)
    renamed, mapping = set(), {}
    for col in df.columns:
        period, _, metric = col.rpartition('_')
        if period and metric in FNG_NEW_NAMES and COL_RE.match(col):
            mapping[col] = f'{period}_{FNG_NEW_NAMES[metric]}'
            renamed.add(metric)
    # 한 파일에 기존 이름과 새 이름이 함께 있으면(예전 캐시가 섞인 경우) 기존 이름 열의 빈칸만 채운다
    for new, old in mapping.items():
        if old in df.columns:
            df[old] = df[old].where(df[old].notna(), df[new])
            df = df.drop(columns=new)
    df = df.rename(columns=mapping)
    return df, sorted(renamed)


def _kind(col):
    y, q, k, m = COL_RE.match(col).groups()
    return ('연간' if k == '(연간)' else '누적' if k == '(누적)' else '분기'), col.rsplit('_', 1)[0], m


def _mismatch_type(metric, kind, a, b, sheet):
    """a=FnGuide, b=DART"""
    if abs(a + b) <= TOL:
        return '부호만 반대'
    if b != 0 and a != 0 and any(abs(a / b - r) < 0.002 for r in (1000, 0.001, 1e6, 1e-6, 100, 0.01)):
        return '단위 차이 의심'
    if metric == '현금성자산증가':
        return '현금 증가액 정의(환율변동효과·기타 조정)'
    if metric == '순영업수익':
        return '순영업수익(FnGuide 가공 지표, DART는 영업이익+판관비 근사)'
    if metric in ('영업수익', '영업비용') :
        return '금융업 영업수익·영업비용 계정 대응'
    if metric in ('판관비', '영업이익', '매출총이익', '매출원가') and sheet == '제조업':
        return '영업이익·판관비 정의(FnGuide 조정영업이익)'
    if metric in ('판관비', '영업이익'):
        return '금융업 판관비·영업이익 계정 대응'
    if kind == '연간':
        return '연간 값 차이(재작성·정정 시점 등)'
    if kind == '분기':
        return '분기 값 차이(정정·누적 차이 계산 등)'
    return '누적 값 차이'


def compare(dart_path, fng_path=None):
    fng_path = fng_path or FNG_FILE
    dart = _load(dart_path)
    fng, renamed = _load_fng(fng_path)
    is_test = dart_path.endswith('_test.xlsx')
    codes = [c for c in dart.index if c in fng.index]
    dcols = [c for c in dart.columns if COL_RE.match(c)]
    fcols = [c for c in fng.columns if COL_RE.match(c)]
    common = [c for c in fcols if c in dcols]
    # 종목 단위로 설명되는 차이 (칸별 유형보다 먼저 적용)
    stock_type = {}
    for code in codes:
        memo = str(dart.at[code, '수집메모']) if '수집메모' in dart.columns else ''
        if '환산 안 함' in memo:
            stock_type[code] = '외화 표시 기업(DART는 공시 통화, FnGuide는 원화 환산)'
        elif '표시통화' in memo:
            stock_type[code] = '외화 표시 기업(원화 환산 후 차이: 환율 반올림·원본 금액 차이)'
        elif pd.notna(fng.at[code, '결산월']) and int(fng.at[code, '결산월']) != int(dart.at[code, '결산월']):
            stock_type[code] = '결산월 불일치(결산기 변경: FnGuide 4월 기준과 DART 현재 기준이 다름)'
        elif '혼재' in memo:
            stock_type[code] = '연결·별도 혼재(기간에 따라 연결재무제표 유무가 다름)'
    recs = []
    for col in fcols:
        kind, period, metric = _kind(col)
        f = pd.to_numeric(fng.loc[codes, col], errors='coerce')
        d = pd.to_numeric(dart.loc[codes, col], errors='coerce') if col in dcols else pd.Series(float('nan'), index=codes)
        for code in codes:
            a, b = f[code], d[code]
            if pd.isna(a):
                continue
            sheet = fng.at[code, '시트']
            if pd.isna(b):
                recs.append((code, sheet, metric, kind, period, a, None, None, 'DART 값 없음', ''))
            elif abs(a - b) <= TOL:
                recs.append((code, sheet, metric, kind, period, a, b, round(b - a, 2), '일치', ''))
            else:
                recs.append((code, sheet, metric, kind, period, a, b, round(b - a, 2), '불일치',
                             stock_type.get(code) or _mismatch_type(metric, kind, a, b, sheet)))
    r = pd.DataFrame(recs, columns=['종목코드', 'FnGuide시트', '지표', '구분', '기간', 'FnGuide', 'DART', '차이', '결과', '불일치유형'])
    r.insert(1, '종목명', r['종목코드'].map(fng['종목명']))
    both = r[r['결과'] != 'DART 값 없음']

    def rate(g):
        n, ok = len(g), int((g['결과'] == '일치').sum())
        return pd.Series({'비교 칸': n, '일치': ok, '불일치': n - ok, '일치율(%)': round(100 * ok / n, 2) if n else None})

    def table(keys, src=both):
        t = src.groupby(keys, sort=False).apply(rate).reset_index()
        miss = r[r['결과'] == 'DART 값 없음'].groupby(keys).size().rename('DART 값 없음(FnGuide만 있음)').reset_index()
        return t.merge(miss, on=keys, how='left').fillna({'DART 값 없음(FnGuide만 있음)': 0})

    # 수집 실패·누락
    import apiCollect
    base = apiCollect.latest_corp_list()
    tmp = os.path.join('derived', '_api_tmp', f'dart_finance{"_test" if is_test else ""}.pkl')
    state = pd.read_pickle(tmp) if os.path.exists(tmp) else {'rows': {}, 'nodata': [], 'fail': {}}
    fails = []
    if not is_test:
        from dartFinance import get_corp_map
        cm = get_corp_map()
        for row in base.itertuples(index=False):
            if row.scode in dart.index:
                continue
            if row.scode in state['fail']:
                why = '수집 오류: ' + state['fail'][row.scode]
            elif row.scode not in cm:
                why = 'DART 고유번호 없음(CORPCODE에 종목코드 없음)'
            elif row.scode in state['nodata']:
                why = '대상 기간(2025년 이후)에 재무제표 공시 없음(신규상장·스팩 등)'
            else:
                why = '미수집'
            fails.append((row.scode, row.sname, row.industry, why, 'O' if row.scode in fng.index else ''))
    fails = pd.DataFrame(fails, columns=['종목코드', '종목명', '업종', '이유', 'FnGuide 4월 파일에 있음'])

    summary = pd.DataFrame([
        ('DART 파일', dart_path), ('FnGuide 파일', fng_path), ('일치 기준', f'차이 {TOL}억원 이하'),
        ('FnGuide 새 이름 → 비교에 쓴 이름', ', '.join(f'{n} → {FNG_NEW_NAMES[n]}' for n in renamed) or '(없음)'),
        ('DART 수집 종목 수', len(dart)), ('FnGuide 종목 수', len(fng)), ('양쪽 모두 있는 종목 수', len(codes)),
        ('종목 리스트 대비 수집하지 못한 종목 수', len(fails)),
        ('FnGuide에 값이 있는 칸', len(r)), ('그중 DART에도 값이 있는 칸(비교 칸)', len(both)),
        ('일치', int((both['결과'] == '일치').sum())), ('불일치', int((both['결과'] == '불일치').sum())),
        ('일치율(%)', round(100 * (both['결과'] == '일치').mean(), 2) if len(both) else None),
        ('DART 값 없음(FnGuide만 있음)', int((r['결과'] == 'DART 값 없음').sum())),
        ('전 칸 일치 종목 수', int((both.groupby('종목코드')['결과'].apply(lambda s: (s == '일치').all())).sum())),
        ('공통 컬럼 수 / FnGuide 컬럼 수', f'{len(common)} / {len(fcols)}'),
    ], columns=['항목', '값'])
    summary['값'] = summary['값'].astype(str)

    mm = both[both['결과'] == '불일치']
    types = mm.groupby('불일치유형').agg(건수=('차이', 'size'), 종목수=('종목코드', 'nunique')).reset_index() \
        .sort_values('건수', ascending=False)
    types_sheet = mm.groupby(['FnGuide시트', '불일치유형']).size().rename('건수').reset_index()
    per_stock = table(['종목코드', '종목명', 'FnGuide시트']).sort_values('일치율(%)')
    meta = dart[[c for c in ['연결구분', '결산월', '업종구분', '최근보고서', '수집메모'] if c in dart.columns]]
    per_stock = per_stock.merge(meta, left_on='종목코드', right_index=True, how='left')
    cls = dart.loc[codes, ['종목명', '업종', '업종구분']].assign(FnGuide시트=fng.loc[codes, '시트'])
    cls = cls[cls['업종구분'] != cls['FnGuide시트']].reset_index()
    nodart = r[r['결과'] == 'DART 값 없음'].groupby(['FnGuide시트', '지표', '구분']).agg(
        칸수=('기간', 'size'), 종목수=('종목코드', 'nunique')).reset_index()

    sheets = [('요약', summary), ('지표별', table(['FnGuide시트', '지표'])), ('기간별', table(['구분', '기간'])),
              ('불일치유형', types), ('불일치유형_시트별', types_sheet), ('종목별', per_stock),
              ('DART값없음', nodart), ('불일치상세', mm.sort_values(['종목코드', '지표', '기간']).head(200000)),
              ('수집실패', fails), ('업종구분차이', cls)]
    out = os.path.basename(dart_path).replace('dart_finance_', 'dart_finance_compare_')
    if os.path.normpath(fng_path) != os.path.normpath(FNG_FILE):      # 기본(4월) 비교 결과를 덮어쓰지 않는다
        out = out.replace('.xlsx', f'_vs_{os.path.splitext(os.path.basename(fng_path))[0]}.xlsx')
    out = os.path.join('derived', out)
    save_styled_excel_multisheet([(n, d if len(d) else pd.DataFrame({'(없음)': []})) for n, d in sheets], out)
    return out, dict(sheets)


if __name__ == '__main__':
    if len(sys.argv) > 1:
        path = sys.argv[1]
    else:
        path = sorted(f for f in glob.glob('derived/dart_finance_2*.xlsx') if not f.endswith('_test.xlsx'))[-1]
    out, s = compare(path, sys.argv[2] if len(sys.argv) > 2 else None)
    pd.set_option('display.width', 250); pd.set_option('display.max_rows', 200); pd.set_option('display.max_colwidth', 60)
    for name in ('요약', '지표별', '기간별', '불일치유형'):
        print(f'\n== {name}'); print(s[name].to_string(index=False))
    print('\n수집 실패:', len(s['수집실패']), '/ 업종구분 차이:', len(s['업종구분차이']))
    print('저장:', out)
