"""
FnGuide Snapshot 페이지에서 투자지표 추출
- KSE/FICS 분야
- Financial Highlight 테이블 (연결/연간 기준)
"""
import requests
from bs4 import BeautifulSoup
import pandas as pd
import re
from datetime import datetime
import multiprocessing as mp
import krxStocks
from pathlib import Path
from fin_utils import save_styled_excel


def get_snapshot_html(stock_code, use_cache=True):
    """
    FnGuide Snapshot 페이지 HTML 가져오기 (캐싱 지원)

    Args:
        stock_code: 종목코드 (6자리)
        use_cache: True면 로컬 캐시 사용

    Returns:
        HTML 문자열
    """
    # 캐시 디렉토리 설정
    cache_dir = Path("./derived/fnguide_snapshot_cache")

    # 캐시 디렉토리가 3개월 이상 지났으면 삭제
    if cache_dir.exists():
        import shutil
        import time

        # 디렉토리 생성 시간 확인
        dir_mtime = cache_dir.stat().st_mtime
        current_time = time.time()

        # 3개월 = 90일 = 90 * 24 * 60 * 60 초
        three_months_in_seconds = 90 * 24 * 60 * 60

        # 3개월 이상 지났으면 삭제
        if (current_time - dir_mtime) > three_months_in_seconds:
            print(f"[캐시 정리] 캐시 디렉토리가 3개월 이상 지나 삭제합니다: {cache_dir}")
            shutil.rmtree(cache_dir)

    if use_cache:
        # 캐시 디렉토리 생성
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file = cache_dir / f"{stock_code}.html"

        # 캐시 파일이 있으면 사용
        if cache_file.exists():
            return cache_file.read_text(encoding='utf-8')

    # HTML 다운로드
    url = f"https://comp.fnguide.com/SVO2/ASP/SVD_Main.asp?pGB=1&gicode=A{stock_code}&cID=AA&MenuYn=Y&ReportGB=&NewMenuID=101&stkGb=701"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    response = requests.get(url, headers=headers, timeout=30)
    response.encoding = 'utf-8'
    html = response.text

    # 캐시 저장
    if use_cache:
        cache_file.write_text(html, encoding='utf-8')

    return html


def extract_company_name(soup):
    """
    페이지 title에서 종목명 추출

    Args:
        soup: BeautifulSoup 객체

    Returns:
        종목명 문자열
    """
    title = soup.find('title')
    if title:
        # "삼성전자(A005930) | Snapshot | 기업정보 | Company Guide"
        title_text = title.get_text(strip=True)
        # "삼성전자(A005930)" 부분 추출
        match = re.match(r'^([^(]+)\(A\d+\)', title_text)
        if match:
            return match.group(1).strip()

    return ""


def extract_kse_fics(soup):
    """
    stxt_group에서 KSE, FICS 분야 추출

    Args:
        soup: BeautifulSoup 객체

    Returns:
        (kse_sector, fics_sector) 튜플
    """
    kse_sector = ""
    fics_sector = ""

    # stxt_group 찾기
    stxt_group = soup.find('p', class_='stxt_group')
    if stxt_group:
        spans = stxt_group.find_all('span', class_='stxt')
        for span in spans:
            text = span.get_text(strip=True)
            # &nbsp; 공백 문자 제거
            text = text.replace('\xa0', ' ')
            if text.startswith('KSE'):
                # "KSE  코스피 전기·전자" -> "코스피 전기·전자" 추출
                kse_sector = re.sub(r'^KSE\s+', '', text).strip()
            elif text.startswith('KOSDAQ'):
                # "KOSDAQ  코스닥 전기·전자" -> "코스닥 전기·전자" 추출
                kse_sector = re.sub(r'^KOSDAQ\s+', '', text).strip()
            elif text.startswith('K-OTC'):
                # "K-OTC  코스닥 전기·전자" -> "코스닥 전기·전자" 추출
                kse_sector = re.sub(r'^K-OTC\s+', '', text).strip()
            elif text.startswith('KONEX'):
                # "KONEX  코넥스 전기·전자" -> "코넥스 전기·전자" 추출
                kse_sector = re.sub(r'^KONEX\s+', '', text).strip()
            elif text.startswith('FICS'):
                # "FICS  반도체 및 관련장비" -> "반도체 및 관련장비" 추출
                fics_sector = re.sub(r'^FICS\s+', '', text).strip()

    return kse_sector, fics_sector


def extract_financial_highlight(soup, current_year=None):
    """
    Financial Highlight 테이블에서 연결/연간 기준 데이터 추출
    테이블 ID: highlight_D_Y (연결/연간)

    Args:
        soup: BeautifulSoup 객체
        current_year: 현재 연도 (None이면 datetime.now().year 사용)

    Returns:
        (data_dict, year_list) 튜플
    """
    if current_year is None:
        current_year = datetime.now().year

    # highlight_D_Y 테이블 찾기 (IFRS 연결/연간)
    table = soup.find('div', id='highlight_D_Y')
    if not table:
        print("경고: highlight_D_Y 테이블을 찾을 수 없습니다.")
        return None

    table_tag = table.find('table')
    if not table_tag:
        return None

    # 헤더에서 연도/월 추출 (두 번째 행의 th만)
    thead = table_tag.find('thead')
    year_month_headers = []  # (year, month, is_estimate, original_text) 튜플 리스트
    if thead:
        # 두 번째 tr 찾기 (td_gapcolor2 클래스)
        second_row = thead.find('tr', class_='td_gapcolor2')
        if second_row:
            th_tags = second_row.find_all('th', scope='col')
            for th in th_tags:
                div = th.find('div')
                if div:
                    # tooltip 링크의 텍스트 추출 (2025/12(E) 형식)
                    tip_in = div.find('a', class_='tip_in')
                    if tip_in:
                        year_text = tip_in.get_text(strip=True)
                    else:
                        year_text = div.get_text(strip=True)

                    # 연도/월/추정 파싱: "2023/12" 또는 "2025/12(E)"
                    match = re.match(r'(\d{4})/(\d{2})(\(E\))?', year_text)
                    if match:
                        year = int(match.group(1))
                        month = int(match.group(2))
                        is_estimate = match.group(3) is not None
                        year_month_headers.append((year, month, is_estimate, year_text))

    # 필요한 지표 목록 (순서대로)
    indicators = [
        '영업이익률',
        '부채비율',
        '유보율',
        '지배주주순이익률',
        'PER',
        'EPS',
        'PBR',
        'BPS',
        'ROA',
        'ROE',
        '배당수익률',
        '발행주식수'
    ]

    # 동일 연도 중 최신 데이터만 선택 (연도별로 가장 큰 월 선택)
    # {year: (index, month)} 형태로 저장 (추정치 구분 제거)
    year_to_latest = {}
    for i, (year, month, is_estimate, _) in enumerate(year_month_headers):
        # 필터링: 현재년도 기준 과거 3년 + 미래 2년만 포함
        if year < current_year - 3 or year > current_year + 1:
            continue

        # 동일 연도가 없거나, 더 최신 월이면 업데이트 (추정치 여부 무관)
        if year not in year_to_latest or month > year_to_latest[year][1]:
            year_to_latest[year] = (i, month)

    # 선택된 연도 정렬
    selected_years = sorted(year_to_latest.keys())

    # 데이터 추출
    data = {}
    tbody = table_tag.find('tbody')
    if tbody:
        rows = tbody.find_all('tr')
        for row in rows:
            th = row.find('th', scope='row')
            if not th:
                continue

            # 지표명 추출 (tooltip 안의 텍스트나 div 내부 텍스트)
            indicator_name = ""
            tip_in = th.find('a', class_='tip_in')
            if tip_in:
                txt_acd = tip_in.find('span', class_='txt_acd')
                if txt_acd:
                    indicator_name = txt_acd.get_text(strip=True)
            else:
                div = th.find('div')
                if div:
                    # <span class="csize">를 제거하고 텍스트 추출
                    for csize in div.find_all('span', class_='csize'):
                        csize.decompose()
                    indicator_name = div.get_text(strip=True)

            # 필요한 지표인지 확인
            if indicator_name not in indicators:
                continue

            # 데이터 값 추출
            tds = row.find_all('td')
            values = []
            for td in tds:
                value = td.get_text(strip=True)
                # &nbsp; 처리
                if value == '\xa0' or value == '':
                    value = None
                else:
                    # 쉼표 제거 후 숫자 변환
                    try:
                        value = value.replace(',', '')
                        value = float(value)
                    except (ValueError, AttributeError):
                        value = None
                values.append(value)

            # 선택된 연도의 데이터만 저장
            # 발행주식수는 추출된 데이터 중 가장 최근(None이 아닌 값 중 가장 마지막) 데이터 하나만 저장
            if indicator_name == '발행주식수':
                # 모든 연도를 역순으로 확인하여 None이 아닌 첫 번째 값 사용
                stock_count = None
                for year in reversed(selected_years):
                    idx, _ = year_to_latest[year]
                    if idx < len(values) and values[idx] is not None:
                        stock_count = values[idx]
                        break
                if stock_count is not None:
                    data['발행주식수(천주)'] = stock_count
            else:
                # 다른 지표는 연도별로 저장 (단위 포함, (E) 제거)
                for year in selected_years:
                    idx, _ = year_to_latest[year]
                    if idx < len(values):
                        # 단위 결정
                        if indicator_name in ['PER', 'PBR', 'ROA', 'ROE']:
                            unit = '(배)'
                        elif indicator_name in ['EPS', 'BPS']:
                            unit = '(원)'
                        elif indicator_name in ['영업이익률', '부채비율', '유보율', '지배주주순이익률', '배당수익률']:
                            unit = '(%)'
                        else:
                            unit = ''

                        # 컬럼명: "2023_영업이익률(%)" 형식 ((E) 제거)
                        col_name = f"{year}_{indicator_name}{unit}"
                        # 숫자 데이터 저장 (이미 float로 변환됨)
                        data[col_name] = values[idx]

    return data, selected_years


def create_investment_dataframe(stock_code, stock_name=""):
    """
    종목코드를 입력받아 투자지표 DataFrame 생성

    Args:
        stock_code: 종목코드 (6자리)
        stock_name: 종목명 (비어있으면 HTML에서 추출)
    """
    print(f"종목코드 {stock_code}의 투자지표를 추출합니다...")

    # HTML 가져오기 (캐싱)
    html = get_snapshot_html(stock_code)

    # HTML 파싱 (1회만)
    soup = BeautifulSoup(html, 'html.parser')

    # 종목명 추출
    if not stock_name:
        stock_name = extract_company_name(soup)

    # KSE/FICS 분야 추출
    kse_sector, fics_sector = extract_kse_fics(soup)
    print(f"  종목명: {stock_name}")
    print(f"  KOSPI/KOSDAQ: {kse_sector}")
    print(f"  FICS: {fics_sector}")

    # Financial Highlight 데이터 추출
    result = extract_financial_highlight(soup)
    if result is None:
        print("  Financial Highlight 데이터를 추출할 수 없습니다.")
        return None

    data, selected_years = result
    # 필터링된 연도만 표시
    print(f"  추출된 연도: {', '.join(map(str, selected_years))}")
    print(f"  추출된 지표 수: {len(data)}")

    # DataFrame 생성
    row_data = {
        '종목코드': stock_code,
        '종목명': stock_name,
        '마켓분야': kse_sector,
        'FICS분야': fics_sector
    }

    # Financial Highlight 데이터 추가
    row_data.update(data)

    df = pd.DataFrame([row_data])

    # 컬럼 순서 정렬
    # 기본 정보 컬럼
    base_cols = ['종목코드', '종목명', '마켓분야', 'FICS분야']

    # 지표 순서 (요청된 순서대로) - 발행주식수는 제외
    indicator_order = [
        '영업이익률',
        '부채비율',
        '유보율',
        '지배주주순이익률',
        'PER',
        'EPS',
        'PBR',
        'BPS',
        'ROA',
        'ROE',
        '배당수익률'
    ]

    # 연도 순서 생성 ((E) 제거)
    year_order = [str(year) for year in selected_years]

    # 지표별로 연도순 컬럼 생성
    ordered_cols = base_cols.copy()
    for indicator in indicator_order:
        # 각 지표에 맞는 단위 결정
        if indicator in ['PER', 'PBR', 'ROA', 'ROE']:
            unit = '(배)'
        elif indicator in ['EPS', 'BPS']:
            unit = '(원)'
        elif indicator in ['영업이익률', '부채비율', '유보율', '지배주주순이익률', '배당수익률']:
            unit = '(%)'
        else:
            unit = ''

        for year_suffix in year_order:
            col_name = f"{year_suffix}_{indicator}{unit}"
            if col_name in df.columns:
                ordered_cols.append(col_name)

    # 발행주식수는 맨 마지막에 단일 컬럼으로 추가
    if '발행주식수(천주)' in df.columns:
        ordered_cols.append('발행주식수(천주)')

    # 컬럼 순서 재정렬
    df = df[ordered_cols]

    return df


def process_single_stock(stock_info):
    """
    단일 종목 처리 (multiprocessing용)

    Args:
        stock_info: (code, name) 튜플

    Returns:
        dict 또는 None
    """
    code, name = stock_info
    try:
        df = create_investment_dataframe(code, name)
        if df is not None and not df.empty:
            return df.iloc[0].to_dict()
        return None
    except Exception as e:
        print(f"  ERROR - {name}({code}): {e}")
        return None


def collect_all_stocks(use_multiprocessing=True, use_fnguide=False):
    """
    KRX 전체 종목에 대해 투자지표 수집

    Args:
        use_multiprocessing: True면 멀티프로세싱 사용
        use_fnguide: True면 getStocksFnguide() 사용, False면 getKrxStocks() 사용

    Returns:
        DataFrame
    """
    print("=" * 50)
    print("종목 리스트 가져오기")
    print("=" * 50)

    if use_fnguide:
        # FnGuide API에서 종목 리스트 가져오기
        print("소스: FnGuide API")
        stock_list_all = krxStocks.getStocksFnguide()

        # Company 분류만 필터링
        stock_list = stock_list_all[stock_list_all['종목분류'] == 'Company'].copy()
        # 시장정보에 '코넥스' 또는 'K-OTC' 포함된 데이터 제거
        stock_list = stock_list[~stock_list['시장정보'].str.contains('코넥스|K-OTC', na=False)].copy()
        # '종목명'에 '스팩'이 들어간 데이터 제거
        stock_list = stock_list[~stock_list['종목명'].str.contains('스팩', na=False)].copy()
        
        print(f"\n총 {len(stock_list)}개 Company 종목 발견 (전체 {len(stock_list_all)}개 중)")

        # (code, name) 튜플 리스트 생성
        stock_infos = [(row['종목코드'], row['종목명']) for _, row in stock_list.iterrows()]
    else:
        # KRX KIND에서 종목 리스트 가져오기
        print("소스: KRX KIND")
        stock_list = krxStocks.getKrxStocks()
        print(f"\n총 {len(stock_list)}개 종목 발견")

        # (code, name) 튜플 리스트 생성
        stock_infos = [(row['code'], row['name']) for _, row in stock_list.iterrows()]

    print("\n" + "=" * 50)
    print("투자지표 수집 시작")
    print("=" * 50)

    if use_multiprocessing:
        # 멀티프로세싱 사용
        with mp.Pool(processes=mp.cpu_count()) as pool:
            results = pool.map(process_single_stock, stock_infos)
    else:
        # 순차 처리
        results = [process_single_stock(info) for info in stock_infos]

    # None이 아닌 결과만 필터링
    valid_results = [r for r in results if r is not None]

    print(f"\n성공: {len(valid_results)}개 / 전체: {len(stock_list)}개")

    # DataFrame 생성
    if valid_results:
        df = pd.DataFrame(valid_results)
        return df
    else:
        print("수집된 데이터가 없습니다.")
        return None


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

    # 명령행 인자로 테스트 모드 선택
    # python investment_indicators.py                    -> 전체 종목 수집 (KRX KIND)
    # python investment_indicators.py --fnguide          -> 전체 종목 수집 (FnGuide API)
    # python investment_indicators.py test               -> 삼성전자만 테스트
    # python investment_indicators.py test 005930 000660 -> 지정한 종목들만 테스트

    # FnGuide 사용 여부 플래그 (기본값: False)
    use_fnguide_flag = '--fnguide' in sys.argv
    if use_fnguide_flag:
        sys.argv.remove('--fnguide')

    if len(sys.argv) > 1 and sys.argv[1] == "test":
        # 테스트 모드
        if len(sys.argv) > 2:
            # 지정한 종목 코드들만
            test_codes = sys.argv[2:]
            print(f"테스트 모드: {len(test_codes)}개 종목")
            results = []
            for code in test_codes:
                df = create_investment_dataframe(code)
                if df is not None:
                    results.append(df)

            if results:
                final_df = pd.concat(results, ignore_index=True)
            else:
                final_df = None
        else:
            # 삼성전자만 테스트
            print("테스트 모드: 삼성전자(005930)")
            final_df = create_investment_dataframe("005930")
    else:
        # 전체 종목 수집
        final_df = collect_all_stocks(use_multiprocessing=True, use_fnguide=use_fnguide_flag)

    if final_df is not None:
        # 결과 출력
        print("\n=== 추출된 데이터 ===")
        print(f"전체 종목 수: {len(final_df)}")
        print(f"전체 컬럼 수: {len(final_df.columns)}")

        # Excel 저장
        print("\n=== Excel 저장 ===")
        filename = save_to_excel(final_df)

        print(f"\nOK 성공적으로 완료되었습니다!")
        print(f"  파일: {filename}")
    else:
        print("\nERROR 데이터 추출에 실패했습니다.")
