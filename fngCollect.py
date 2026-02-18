"""
FnGuide Snapshot 기반 투자지표 수집

krxStocks 종목 기본정보 + FnGuide Snapshot 투자지표를 결합하여
전체 종목 DataFrame을 생성하고 Excel로 저장한다.
"""
import re
import pandas as pd
from datetime import datetime
import multiprocessing as mp
import krxStocks
from fnguideSnapshot import getFnGuideSnapshot, parseFnguideSnapshot
from fin_utils import save_styled_excel


def process_single_stock(stock_row):
    """
    단일 종목 처리 (multiprocessing용)

    Args:
        stock_row: dict - scode, sname, industry, products 키를 가진 딕셔너리

    Returns:
        dict 또는 None
    """
    code = stock_row['scode']
    try:
        html = getFnGuideSnapshot(code)
        indicators = parseFnguideSnapshot(html)
        if indicators is None:
            return None

        # krxStocks 기본정보 + FnGuide 파싱 데이터 합치기
        row = {
            '종목코드': code,
            '종목명': stock_row.get('sname') or indicators.get('종목명', ''),
            '업종': stock_row.get('industry', ''),
            '주요제품': stock_row.get('products', ''),
            '마켓분야': indicators.get('마켓분야', ''),
            'FICS분야': indicators.get('FICS분야', ''),
        }

        # 종목명, 마켓분야, FICS분야는 이미 위에서 처리했으므로 제외
        for k, v in indicators.items():
            if k not in ('종목명', '마켓분야', 'FICS분야'):
                row[k] = v

        return row
    except Exception as e:
        print(f"  ERROR - {stock_row.get('sname', '')}({code}): {e}")
        return None


def _order_columns(df):
    """
    최종 DataFrame의 컬럼 순서 정렬

    컬럼명 패턴 '{year}_{indicator}{unit}'에서 연도를 추출하여 정렬한다.
    """
    base_cols = ['종목코드', '종목명', '업종', '주요제품', '마켓분야', 'FICS분야']

    indicator_order = [
        '영업이익률(%)', '부채비율(%)', '유보율(%)', '지배주주순이익률(%)',
        'PER(배)', 'EPS(원)', 'PBR(배)', 'BPS(원)',
        'ROA(배)', 'ROE(배)', '배당수익률(%)'
    ]

    # 컬럼명에서 연도 추출 (예: "2023_영업이익률(%)" → 2023)
    years = set()
    for col in df.columns:
        match = re.match(r'^(\d{4})_', col)
        if match:
            years.add(int(match.group(1)))
    sorted_years = sorted(years)

    # 지표별 연도순 컬럼 생성
    ordered = [c for c in base_cols if c in df.columns]
    for indicator in indicator_order:
        for year in sorted_years:
            col = f"{year}_{indicator}"
            if col in df.columns:
                ordered.append(col)

    if '발행주식수(천주)' in df.columns:
        ordered.append('발행주식수(천주)')

    # ordered에 포함되지 않은 나머지 컬럼 추가
    remaining = [c for c in df.columns if c not in ordered]
    ordered.extend(remaining)

    return df[ordered]


def collect_all_stocks(use_multiprocessing=True):
    """
    KRX 전체 종목에 대해 투자지표 수집

    Returns:
        DataFrame 또는 None
    """
    print("=" * 50)
    print("종목 리스트 가져오기")
    print("=" * 50)

    stock_list, _ = krxStocks.getCorpList()
    print(f"\n총 {len(stock_list)}개 종목 발견")

    # market 컬럼을 제외한 dict 리스트 생성
    stock_rows = stock_list.drop(columns=['market'], errors='ignore').to_dict('records')

    print("\n" + "=" * 50)
    print("투자지표 수집 시작")
    print("=" * 50)

    if use_multiprocessing:
        with mp.Pool(processes=mp.cpu_count()) as pool:
            results = pool.map(process_single_stock, stock_rows)
    else:
        results = [process_single_stock(row) for row in stock_rows]

    valid_results = [r for r in results if r is not None]
    print(f"\n성공: {len(valid_results)}개 / 전체: {len(stock_list)}개")

    if not valid_results:
        print("수집된 데이터가 없습니다.")
        return None

    df = pd.DataFrame(valid_results)
    return _order_columns(df)


def save_to_excel(df, filename=None):
    """DataFrame을 Excel 파일로 저장"""
    if filename is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"./derived/investment_indicators_{timestamp}.xlsx"

    save_styled_excel(df, filename)
    print(f"Excel 파일 저장 완료: {filename}")
    return filename


if __name__ == "__main__":
    import sys

    # python investment_indicators.py                    -> 전체 종목 수집
    # python investment_indicators.py test               -> 삼성전자만 테스트
    # python investment_indicators.py test 005930 000660 -> 지정한 종목들만 테스트

    if len(sys.argv) > 1 and sys.argv[1] == "test":
        if len(sys.argv) > 2:
            test_codes = sys.argv[2:]
        else:
            test_codes = ['005930']

        print(f"테스트 모드: {len(test_codes)}개 종목")
        results = []
        for code in test_codes:
            row = process_single_stock({'scode': code, 'sname': '', 'industry': '', 'products': ''})
            if row is not None:
                results.append(row)

        if results:
            final_df = _order_columns(pd.DataFrame(results))
        else:
            final_df = None
    else:
        final_df = collect_all_stocks(use_multiprocessing=True)

    if final_df is not None:
        print(f"\n=== 추출된 데이터 ===")
        print(f"전체 종목 수: {len(final_df)}")
        print(f"전체 컬럼 수: {len(final_df.columns)}")

        print(f"\n=== Excel 저장 ===")
        filename = save_to_excel(final_df)

        print(f"\nOK 성공적으로 완료되었습니다!")
        print(f"  파일: {filename}")
    else:
        print("\nERROR 데이터 추출에 실패했습니다.")
