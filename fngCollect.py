"""
FnGuide 기반 투자지표 수집 공통 Entry

krxStocks 종목 기본정보 + FnGuide 각 페이지 투자지표를 결합하여
전체 종목 DataFrame을 생성하고 Excel로 저장한다.

지원 모듈:
  snapshot  - FnGuide Snapshot (SVD_Main)
  finance   - FnGuide Finance (SVD_Finance)
  ratio     - FnGuide Finance Ratio (SVD_FinanceRatio)
  investidx - FnGuide Investment Index (SVD_Invest)
  all       - 위 모듈 전체를 순차적으로 수집하여 하나로 합침
"""
import pandas as pd
from datetime import datetime
import multiprocessing as mp
import krxStocks
from fin_utils import save_styled_excel, save_styled_excel_multisheet


# ── 모듈 설정 ──────────────────────────────────────────────

MODULE_CONFIG = {
    'snapshot': {
        'extra_base_fields': ['마켓분야', 'FICS분야'],
        'skip_keys': {'종목명', '마켓분야', 'FICS분야'},
        'indicator_order': [
            '영업이익률(%)', '부채비율(%)', '유보율(%)', '지배주주순이익률(%)',
            'PER(배)', 'EPS(원)', 'PBR(배)', 'BPS(원)',
            'ROA(배)', 'ROE(배)', '배당수익률(%)', '발행주식수(천주)',
        ],
        'description': 'FnGuide Snapshot (SVD_Main)',
        'output_prefix': 'snapshot',
    },
    'finance': {
        'extra_base_fields': [],
        'skip_keys': {'code', '종목명', '업종'},
        'indicator_order': ['PER', 'PBR', '당기순이익', '유동자산', '부채'],
        'description': 'FnGuide Finance (SVD_Finance)',
        'output_prefix': 'finance',
    },
    'ratio': {
        'extra_base_fields': ['마켓분야', 'FICS분야'],
        'skip_keys': {'종목명', '마켓분야', 'FICS분야'},
        'indicator_order': [
            # 안정성
            '유동비율', '부채비율', '유보율', '순차입금비율', '이자보상배율', '자기자본비율',
            '예대율', '유가증권보유율', '운용자산비율',
            # 성장성
            '매출증가율', '판관비증가율', 'EPS증가율', '영업이익증가율', 'EBITDA증가율',
            '순이익증가율', '총자산증가율', '대출채권증가율', '예수부채증가율',
            # 수익성 (ROIC → ROE 순서: 부분문자열 매칭 오작동 방지)
            '매출총이익률', '세전계속이익률', '영업이익률', 'EBITDA마진율',
            'ROIC', 'ROA', 'ROE',
            '판관비율', 'NIM', '예대마진율',
            '순이익률', '운용자산이익률', '손해율', '순사업비율',
            # 활동성
            '총자산회전율', '타인자본회전율', '자기자본회전율', '순운전자본회전율',
        ],
        'description': 'FnGuide Finance Ratio (SVD_FinanceRatio)',
        'output_prefix': 'finance_ratio',
    },
    'investidx': {
        'extra_base_fields': [],
        'skip_keys': {'code'},
        'indicator_order': ['PER'],
        'description': 'FnGuide Investment Index (SVD_Invest)',
        'output_prefix': 'invest_idx',
    },
    'all': {
        'description': 'FnGuide 전체 (Snapshot + Finance + Ratio + InvestIdx)',
        'output_prefix': 'investment_indicators',
    },
}

# 'all' 모드에서 순차 처리할 모듈 목록
_ALL_MODULES = ['snapshot', 'finance', 'ratio', 'investidx']


def _get_module_fns(module_name):
    """모듈명에 해당하는 (get_fn, parse_fn) 반환 (worker 프로세스 내에서 import)"""
    if module_name == 'snapshot':
        from fnguideSnapshot import getFnGuideSnapshot, parseFnguideSnapshot
        return getFnGuideSnapshot, parseFnguideSnapshot
    elif module_name == 'finance':
        from fnguideFinance import getFnguideFinance, parseFnguideFinance
        return getFnguideFinance, parseFnguideFinance
    elif module_name == 'ratio':
        from fnguideFinanceRatio import getFnGuideFiRatio, parseFnguideFiRatio
        return getFnGuideFiRatio, parseFnguideFiRatio
    elif module_name == 'investidx':
        from fnguideInvestIdx import getFnGuideInvestIdx, parseFnGuideInvestIdx
        return getFnGuideInvestIdx, parseFnGuideInvestIdx
    else:
        raise ValueError(f"Unknown module: {module_name}")


def _get_indicator_order(module_name):
    """모듈에 해당하는 indicator_order 반환 ('all'이면 전체 합산)"""
    if module_name == 'all':
        combined = []
        for mod in _ALL_MODULES:
            combined.extend(MODULE_CONFIG[mod]['indicator_order'])
        return combined
    return MODULE_CONFIG[module_name]['indicator_order']


# ── 단일 종목 처리 ─────────────────────────────────────────

def process_single_stock(args):
    """
    단일 종목 처리 (multiprocessing용)

    Args:
        args: (stock_row, module_name) 튜플
              stock_row - scode, sname, industry, products 키를 가진 딕셔너리
              module_name - MODULE_CONFIG 키 ('all' 포함)

    Returns:
        dict 또는 None
    """
    stock_row, module_name = args

    modules_to_process = _ALL_MODULES if module_name == 'all' else [module_name]

    code = stock_row['scode']

    # krxStocks 기본정보 + FnGuide 파싱 데이터 합치기
    row = {
        '종목코드': code,
        '종목명': stock_row.get('sname', ''),
        '업종': stock_row.get('industry', ''),
        '주요제품': stock_row.get('products', ''),
    }

    has_data = False

    for mod in modules_to_process:
        config = MODULE_CONFIG[mod]
        try:
            get_fn, parse_fn = _get_module_fns(mod)
            html = get_fn(code)
            indicators = parse_fn(html)
            if indicators is None:
                continue

            has_data = True

            # 종목명 보완 (krxStocks에 없을 경우 파싱 데이터에서 가져오기)
            if not row['종목명']:
                row['종목명'] = indicators.get('종목명', '')

            # 모듈별 추가 기본 필드 (예: snapshot의 마켓분야, FICS분야)
            for field in config['extra_base_fields']:
                row[field] = indicators.get(field, '')

            # 파싱 데이터 중 skip_keys를 제외한 나머지 추가
            for k, v in indicators.items():
                if k not in config['skip_keys']:
                    row[k] = v

        except Exception as e:
            print(f"  ERROR [{mod}] - {stock_row.get('sname', '')}({code}): {e}")

    if not has_data:
        return None

    return row


# ── 컬럼 정렬 ──────────────────────────────────────────────

def _col_matches_indicator(col, indicator):
    """컬럼명이 해당 지표에 속하는지 판별

    매칭 패턴:
      - 정확히 일치: '발행주식수(천주)' == '발행주식수(천주)'
      - {indicator}_{suffix}: 'EPS_y-3', '당기순이익_2022/09'
      - {year}_{indicator}: '2023_영업이익률(%)'
    """
    if col == indicator:
        return True
    if col.startswith(f'{indicator}_'):
        return True
    if f'_{indicator}' in col:
        return True
    return False


def _order_columns(df, indicator_order):
    """
    최종 DataFrame의 컬럼 순서 정렬

    indicator_order에 지정된 지표 순서대로 컬럼을 배치한다.
    각 지표 내에서는 컬럼명 알파벳순(연도순/기간순)으로 정렬된다.
    """
    base_cols = ['종목코드', '종목명', '업종', '주요제품', '마켓분야', 'FICS분야']
    ordered = [c for c in base_cols if c in df.columns]

    remaining = [c for c in df.columns if c not in ordered]

    for indicator in indicator_order:
        matched = sorted(c for c in remaining if _col_matches_indicator(c, indicator))
        ordered.extend(matched)
        remaining = [c for c in remaining if c not in matched]

    # indicator_order에 포함되지 않은 나머지 컬럼 추가
    ordered.extend(sorted(remaining))

    return df[ordered]


# ── 전종목 수집 ────────────────────────────────────────────

def collect_all_stocks(module_name='snapshot', use_multiprocessing=True):
    """
    KRX 전체 종목에 대해 투자지표 수집

    Args:
        module_name: MODULE_CONFIG 키 (snapshot, finance, ratio, investidx, all)
        use_multiprocessing: 멀티프로세싱 사용 여부

    Returns:
        DataFrame 또는 None
    """
    config = MODULE_CONFIG[module_name]

    print("=" * 50)
    print("종목 리스트 가져오기")
    print("=" * 50)

    stock_list, _ = krxStocks.getCorpList()
    print(f"\n총 {len(stock_list)}개 종목 발견")

    # market 컬럼을 제외한 dict 리스트 생성
    stock_rows = stock_list.drop(columns=['market'], errors='ignore').to_dict('records')
    args_list = [(row, module_name) for row in stock_rows]

    print("\n" + "=" * 50)
    print(f"{config['description']} 데이터 수집 시작")
    print("=" * 50)

    if use_multiprocessing:
        with mp.Pool(processes=mp.cpu_count()) as pool:
            results = pool.map(process_single_stock, args_list)
    else:
        results = [process_single_stock(args) for args in args_list]

    valid_results = [r for r in results if r is not None]
    print(f"\n성공: {len(valid_results)}개 / 전체: {len(stock_list)}개")

    if not valid_results:
        print("수집된 데이터가 없습니다.")
        return None

    df = pd.DataFrame(valid_results)
    return _order_columns(df, _get_indicator_order(module_name))


# ── Excel 저장 ─────────────────────────────────────────────

def _filter_industry_columns(df, indicators):
    """업종 지표 목록에 매칭되는 컬럼만 추출 (기본 컬럼 포함, 정렬 유지)"""
    base_cols = [c for c in ['종목코드', '종목명', '업종', '주요제품', '마켓분야', 'FICS분야'] if c in df.columns]
    remaining = [c for c in df.columns if c not in base_cols]

    ordered = []
    for indicator in indicators:
        matched = sorted(c for c in remaining if _col_matches_indicator(c, indicator))
        ordered.extend(matched)
        remaining = [c for c in remaining if c not in matched]

    return base_cols + ordered


def _build_ratio_sheets(df):
    """
    Finance Ratio DataFrame을 업종별 시트 리스트로 분리

    Returns:
        [(sheet_name, DataFrame), ...] — 데이터가 있는 업종만 포함
    """
    from fnguideFinanceRatio import (
        detect_industry_type, INDUSTRY_INDICATORS,
        INDUSTRY_TYPE_MANUFACTURING, INDUSTRY_TYPE_BANKING,
        INDUSTRY_TYPE_SECURITIES, INDUSTRY_TYPE_INSURANCE,
        INDUSTRY_TYPE_VENTURE,
    )

    industry_order = [
        INDUSTRY_TYPE_MANUFACTURING,
        INDUSTRY_TYPE_BANKING,
        INDUSTRY_TYPE_SECURITIES,
        INDUSTRY_TYPE_INSURANCE,
        INDUSTRY_TYPE_VENTURE,
    ]

    market_col = '마켓분야' if '마켓분야' in df.columns else None
    fics_col   = 'FICS분야' if 'FICS분야' in df.columns else None

    def get_type(row):
        market = row[market_col] if market_col else ''
        fics   = row[fics_col]   if fics_col   else ''
        return detect_industry_type(market, fics)

    df = df.copy()
    df['_itype'] = df.apply(get_type, axis=1)

    sheets = []
    for itype in industry_order:
        idf = df[df['_itype'] == itype].drop(columns=['_itype']).reset_index(drop=True)
        if idf.empty:
            continue
        cols = _filter_industry_columns(idf, INDUSTRY_INDICATORS.get(itype, []))
        # 값이 하나라도 있는 컬럼만 유지 (기본 컬럼은 항상 포함)
        base = [c for c in ['종목코드', '종목명', '업종', '주요제품', '마켓분야', 'FICS분야'] if c in cols]
        indicator_cols = [c for c in cols if c not in base and idf[c].notna().any()]
        sheets.append((itype, idf[base + indicator_cols]))

    return sheets


def save_to_excel(df, module_name='snapshot', filename=None):
    """DataFrame을 Excel 파일로 저장 (ratio 모듈은 업종별 멀티시트)"""
    if filename is None:
        config = MODULE_CONFIG[module_name]
        now = datetime.now()
        filename = f"./derived/{config['output_prefix']}_{now.year}_{now.month:02d}.xlsx"

    if module_name == 'ratio':
        sheets = _build_ratio_sheets(df)
        if sheets:
            save_styled_excel_multisheet(sheets, filename)
        else:
            save_styled_excel(df, filename)
    else:
        save_styled_excel(df, filename)

    print(f"Excel 파일 저장 완료: {filename}")
    return filename


# ── CLI ────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    # python fngCollect.py snapshot                     -> snapshot 전종목 수집
    # python fngCollect.py finance                      -> finance 전종목 수집
    # python fngCollect.py ratio                        -> ratio 전종목 수집
    # python fngCollect.py investidx                    -> investidx 전종목 수집
    # python fngCollect.py all                          -> 전체 모듈 순차 수집
    # python fngCollect.py snapshot test                -> snapshot 삼성전자만 테스트
    # python fngCollect.py snapshot test 005930 000660  -> snapshot 지정 종목 테스트

    available = list(MODULE_CONFIG.keys())
    args = sys.argv[1:]

    if not args or args[0] not in available:
        print(f"사용법: python fngCollect.py <module> [test [codes...]]")
        print(f"  module: {', '.join(available)}")
        sys.exit(1)

    module_name = args[0]
    rest = args[1:]

    print(f"모듈: {MODULE_CONFIG[module_name]['description']}")

    if rest and rest[0] == "test":
        test_codes = rest[1:] if len(rest) > 1 else ['005930']
        print(f"테스트 모드: {len(test_codes)}개 종목")

        results = []
        for code in test_codes:
            row = process_single_stock(
                ({'scode': code, 'sname': '', 'industry': '', 'products': ''}, module_name)
            )
            if row is not None:
                results.append(row)

        if results:
            final_df = _order_columns(
                pd.DataFrame(results), _get_indicator_order(module_name)
            )
        else:
            final_df = None
    else:
        final_df = collect_all_stocks(module_name=module_name, use_multiprocessing=True)

    if final_df is not None:
        print(f"\n=== 추출된 데이터 ===")
        print(f"전체 종목 수: {len(final_df)}")
        print(f"전체 컬럼 수: {len(final_df.columns)}")

        print(f"\n=== Excel 저장 ===")
        filename = save_to_excel(final_df, module_name=module_name)

        print(f"\nOK 성공적으로 완료되었습니다!")
        print(f"  파일: {filename}")
    else:
        print("\nERROR 데이터 추출에 실패했습니다.")
