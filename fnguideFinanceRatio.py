"""
FnGuide FinanceRatio 페이지 (SVD_FinanceRatio.asp) 데이터 수집 및 파싱

업종별 재무비율 수집:
- 연결 누적 (Annual)  : 연도별 재무비율 → 컬럼 형식 {YYYY}_{지표명}
- 연결 3개월 (Quarterly): 분기별 재무비율 → 컬럼 형식 {YYYY/MM}_{지표명}

업종별 지표 (통합 컬럼명으로 매핑):
  제조업 : 유동비율, 부채비율, 유보율, 순차입금비율, 이자보상배율, 자기자본비율,
           매출액증가율→매출증가율, 판관비증가율, EBIT증가율→영업이익증가율,
           EBITDA증가율, EPS증가율, 매출총이익률, 세전계속사업이익률→세전계속이익률,
           EBIT마진율→영업이익률, EBITDA마진율, ROA, ROE, ROIC,
           총자산회전율, 타인자본회전율, 자기자본회전율, 순운전자본회전율
  은행업 : 예대율, 이자수익증가율→매출증가율, 영업이익증가율, 순이익증가율, EPS증가율,
           총자산증가율, 대출채권증가율, 예수부채증가율, 판관비율,
           총자산이익률(ROA)→ROA, 순이자마진율(NIM)→NIM, 예대마진율, 자기자본이익률(ROE)→ROE
  증권업 : 예대율, 유가증권보유율, 부채비율, 유보율,
           순영업수익증가율→매출증가율, 영업이익증가율, 순이익증가율, EPS증가율,
           영업이익율→영업이익률, 총자산이익률(ROA)→ROA, 자기자본이익률(ROE)→ROE
  보험업 : 운용자산비율, 자기자본비율,
           보험료수익증가율→매출증가율, 영업이익증가율, 순이익증가율, EPS증가율,
           영업이익율→영업이익률, 순이익률, 운용자산이익률,
           총자산이익률(ROA)→ROA, 자기자본이익률(ROE)→ROE, 손해율, 순사업비율

Public API:
  getFnGuideFiRatio(code)    : HTML 가져오기 (캐싱)
  parseFnguideFiRatio(html)  : 재무비율 데이터 추출 → dict 또는 None
"""
import re

from bs4 import BeautifulSoup

from fin_utils import fetch_fnguide_page


# 업종별 원본 지표명 → 통합 컬럼명 매핑
INDICATOR_NAME_MAP = {
    # 안정성
    '유동비율': '유동비율',
    '부채비율': '부채비율',
    '유보율': '유보율',
    '순차입금비율': '순차입금비율',
    '이자보상배율': '이자보상배율',
    '자기자본비율': '자기자본비율',
    '예대율': '예대율',
    '유가증권보유율': '유가증권보유율',
    '운용자산비율': '운용자산비율',
    # 성장성 (업종별 매출에 해당하는 항목 통합)
    '매출액증가율': '매출증가율',
    '이자수익증가율': '매출증가율',      # 은행업
    '순영업수익증가율': '매출증가율',     # 증권업
    '보험료수익증가율': '매출증가율',     # 보험업
    '판관비증가율': '판관비증가율',
    'EBIT증가율': '영업이익증가율',       # 제조업
    '영업이익증가율': '영업이익증가율',
    'EBITDA증가율': 'EBITDA증가율',
    'EPS증가율': 'EPS증가율',
    '순이익증가율': '순이익증가율',
    '총자산증가율': '총자산증가율',
    '대출채권증가율': '대출채권증가율',
    '예수부채증가율': '예수부채증가율',
    # 수익성
    '매출총이익률': '매출총이익률',
    '세전계속사업이익률': '세전계속이익률',
    'EBIT마진율': '영업이익률',           # 제조업
    '영업이익율': '영업이익률',
    '영업이익률': '영업이익률',
    'EBITDA마진율': 'EBITDA마진율',
    'ROA': 'ROA',
    '총자산이익률': 'ROA',
    'ROE': 'ROE',
    '자기자본이익률': 'ROE',
    'ROIC': 'ROIC',
    '판관비율': '판관비율',
    '순이자마진율': 'NIM',
    '예대마진율': '예대마진율',
    '순이익률': '순이익률',
    '운용자산이익률': '운용자산이익률',
    '손해율': '손해율',
    '순사업비율': '순사업비율',
    # 활동성
    '총자산회전율': '총자산회전율',
    '타인자본회전율': '타인자본회전율',
    '자기자본회전율': '자기자본회전율',
    '순운전자본회전율': '순운전자본회전율',
}


# 업종 타입 상수
INDUSTRY_TYPE_MANUFACTURING = '제조업'
INDUSTRY_TYPE_BANKING       = '은행업'
INDUSTRY_TYPE_SECURITIES    = '증권업'
INDUSTRY_TYPE_INSURANCE     = '보험업'
INDUSTRY_TYPE_VENTURE       = '창투업'

# 업종별 관련 통합 지표 목록 (시트 컬럼 필터링에 사용)
INDUSTRY_INDICATORS = {
    INDUSTRY_TYPE_MANUFACTURING: [
        '유동비율', '부채비율', '유보율', '순차입금비율', '이자보상배율', '자기자본비율',
        '매출증가율', '판관비증가율', 'EPS증가율', '영업이익증가율', 'EBITDA증가율',
        '매출총이익률', '세전계속이익률', '영업이익률', 'EBITDA마진율',
        'ROIC', 'ROA', 'ROE',
        '총자산회전율', '타인자본회전율', '자기자본회전율', '순운전자본회전율',
    ],
    INDUSTRY_TYPE_BANKING: [
        '예대율',
        '매출증가율', '영업이익증가율', '순이익증가율', 'EPS증가율',
        '총자산증가율', '대출채권증가율', '예수부채증가율',
        '판관비율', 'ROA', 'NIM', '예대마진율', 'ROE',
    ],
    INDUSTRY_TYPE_SECURITIES: [
        '예대율', '유가증권보유율', '부채비율', '유보율',
        '매출증가율', '영업이익증가율', '순이익증가율', 'EPS증가율',
        '영업이익률', 'ROA', 'ROE',
    ],
    INDUSTRY_TYPE_INSURANCE: [
        '운용자산비율', '자기자본비율',
        '매출증가율', '영업이익증가율', '순이익증가율', 'EPS증가율',
        '영업이익률', '순이익률', '운용자산이익률', 'ROA', 'ROE',
        '손해율', '순사업비율',
    ],
    INDUSTRY_TYPE_VENTURE: [
        '부채비율', '유보율',
        '매출증가율', '영업이익증가율', '순이익증가율', 'EPS증가율',
        '영업이익률', '순이익률', 'ROA', 'ROE',
    ],
}


def detect_industry_type(market_sector, fics_sector):
    """
    마켓분야 + FICS분야 텍스트로 업종 타입 분류

    분류 기준:
      보험업: 마켓분야에 '보험' 포함 AND FICS분야에 '보험' 포함
      은행업: 마켓분야에 '금융' 또는 '은행' 포함 AND FICS분야에 '상업은행' 포함
      증권업: 마켓분야에 '금융' 또는 '증권' 포함 AND FICS분야에 '증권' 포함
      창투업: 마켓분야에 '금융' 포함 AND FICS분야에 '창업투자 및 종금' 포함
      그 외: 제조업

    Args:
        market_sector: 마켓분야 문자열
        fics_sector  : FICS분야 문자열

    Returns:
        str: INDUSTRY_TYPE_* 상수 중 하나 (기본값: 제조업)
    """
    market = market_sector if isinstance(market_sector, str) else ''
    fics   = fics_sector   if isinstance(fics_sector,   str) else ''

    if '보험' in market and '보험' in fics:
        return INDUSTRY_TYPE_INSURANCE
    if ('금융' in market or '은행' in market) and '상업은행' in fics:
        return INDUSTRY_TYPE_BANKING
    if ('금융' in market or '증권' in market) and '증권' in fics:
        return INDUSTRY_TYPE_SECURITIES
    if '금융' in market and '창업투자 및 종금' in fics:
        return INDUSTRY_TYPE_VENTURE
    return INDUSTRY_TYPE_MANUFACTURING


def getFnGuideFiRatio(code):
    """FnGuide FinanceRatio HTML 가져오기 (캐싱)"""
    return fetch_fnguide_page(code, 'SVD_FinanceRatio.asp', '104', 'fnguide_FinanceRatio_')


def parseFnguideFiRatio(html):
    """
    FinanceRatio HTML에서 연결 누적/3개월 재무비율 데이터 추출

    업종(제조업/은행업/증권업/보험업)에 따라 다른 지표를
    INDICATOR_NAME_MAP을 통해 통합 컬럼명으로 자동 매핑한다.

    Args:
        html: FnGuide FinanceRatio HTML 문자열

    Returns:
        dict: 종목명, 마켓분야, FICS분야, 연도별/분기별 재무비율
        None: 연결 누적 테이블이 없는 경우
    """
    soup = BeautifulSoup(html, 'html.parser')

    data = {}
    data['종목명'] = _parse_company_name(soup)

    kse_sector, fics_sector, fiscal_month = _parse_kse_fics(soup)
    data['마켓분야'] = kse_sector
    data['FICS분야'] = fics_sector
    if fiscal_month is not None:
        data['결산월'] = fiscal_month

    # 연결 누적 (Annual) — 컬럼 형식: {YYYY}_{지표명}, 연도별 최신 기간, 최근 4개년
    annual_data = _parse_grid_section(soup, 'grid1', period_format='year', max_periods=4)
    if annual_data is None:
        return None
    data.update(annual_data)

    # 연결 3개월 (Quarterly) — 컬럼 형식: {YYYY/MM}_{지표명}, 최근 3기간
    quarterly_data = _parse_grid_section(soup, 'grid2', period_format='yearmonth', max_periods=3)
    if quarterly_data is not None:
        data.update(quarterly_data)

    return data


# --- Private parse helpers ---

def _parse_company_name(soup):
    """페이지 title에서 종목명 추출"""
    title = soup.find('title')
    if title:
        title_text = title.get_text(strip=True)
        match = re.match(r'^([^(]+)\(A\d+\)', title_text)
        if match:
            return match.group(1).strip()
    return ''


def _parse_kse_fics(soup):
    """KSE/FICS 분야 및 결산월 추출 → (kse_sector, fics_sector, fiscal_month)

    - KSE/FICS : p.stxt_group 내 span.stxt
    - 결산월    : div.corp_group1 > h2 에서 "12월 결산" 형식
    """
    kse_sector = ''
    fics_sector = ''
    fiscal_month = None

    # 결산월: div.corp_group1 내 h2 태그를 순회하여 "12월 결산" 패턴 추출
    corp_group1 = soup.find('div', class_='corp_group1')
    if corp_group1:
        for h2 in corp_group1.find_all('h2'):
            h2_text = h2.get_text(strip=True)
            print(f"  [결산월 디버그] h2 텍스트: {repr(h2_text)}")
            m = re.search(r'(\d+)월\s*결산', h2_text)
            if m:
                fiscal_month = int(m.group(1))
                print(f"  [결산월 디버그] 추출 성공: {fiscal_month}월")
                break
        else:
            print(f"  [결산월 디버그] 모든 h2 순회 완료 - 결산월 패턴 없음")
    else:
        print(f"  [결산월 디버그] div.corp_group1 요소를 찾을 수 없음")

    stxt_group = soup.find('p', class_='stxt_group')
    if not stxt_group:
        return kse_sector, fics_sector, fiscal_month

    for span in stxt_group.find_all('span', class_='stxt'):
        text = span.get_text(strip=True).replace('\xa0', ' ')

        if text.startswith('FICS'):
            fics_sector = re.sub(r'^FICS\s+', '', text).strip()
        else:
            for prefix in ('KSE', 'KOSDAQ', 'K-OTC', 'KONEX'):
                if text.startswith(prefix):
                    kse_sector = re.sub(rf'^{prefix}\s+', '', text).strip()
                    break

    return kse_sector, fics_sector, fiscal_month


def _parse_grid_section(soup, grid_id, period_format='year', max_periods=None):
    """
    grid1(연결 누적) 또는 grid2(연결 3개월) 섹션에서 재무비율 추출

    Args:
        soup         : BeautifulSoup 객체
        grid_id      : 'grid1' (연간) 또는 'grid2' (분기)
        period_format: 'year' → {YYYY} (연도별 최신 기간 사용), 'yearmonth' → {YYYY/MM}
        max_periods  : 수집할 최대 기간 수 (None이면 전체)

    Returns:
        dict: {'{period}_{unified_indicator}': float, ...}
        None: 해당 grid 테이블 없음
    """
    sample_row = soup.find('tr', id=re.compile(rf'^p_{grid_id}_\d+$'))
    if not sample_row:
        return None

    table = sample_row.find_parent('table')
    if not table:
        return None

    periods = _parse_section_headers(table)
    if not periods:
        return None

    # (period_key, original_col_index) 목록 생성
    if period_format == 'year':
        # 연도별 가장 최근 월의 인덱스 선택 후 최근 max_periods년
        year_to_latest = {}
        for i, (year, month) in enumerate(periods):
            if year not in year_to_latest or month > year_to_latest[year][0]:
                year_to_latest[year] = (month, i)
        sorted_years = sorted(year_to_latest.items())
        if max_periods:
            sorted_years = sorted_years[-max_periods:]
        key_idx_list = [(str(year), info[1]) for year, info in sorted_years]
    else:
        # 분기: 최근 max_periods 기간
        selected = periods[-max_periods:] if max_periods else periods
        offset = len(periods) - len(selected)
        key_idx_list = [
            (f'{year}/{month:02d}', offset + i)
            for i, (year, month) in enumerate(selected)
        ]

    data = {}
    for row in table.find_all('tr', id=re.compile(rf'^p_{grid_id}_\d+$')):
        indicator_raw = _extract_row_header(row)
        if not indicator_raw:
            continue

        unified_name = _map_indicator_name(indicator_raw)
        if not unified_name:
            continue

        values = _extract_row_values(row)

        for period_key, idx in key_idx_list:
            if idx < len(values) and values[idx] is not None:
                data[f'{period_key}_{unified_name}'] = values[idx]

    return data


def _parse_section_headers(table):
    """
    thead에서 기간 레이블 리스트 추출 → [(year, month), ...]

    FnGuide FinanceRatio 페이지의 헤더 형식: YYYY/MM 또는 YYYY/MM(E)
    """
    headers = []
    thead = table.find('thead')
    if not thead:
        return headers

    # td_gapcolor2 클래스 행 우선, 없으면 마지막 thead 행
    header_row = thead.find('tr', class_='td_gapcolor2')
    if not header_row:
        rows = thead.find_all('tr')
        header_row = rows[-1] if rows else None

    if not header_row:
        return headers

    for th in header_row.find_all(['th', 'td']):
        tip_in = th.find('a', class_='tip_in')
        text = (tip_in or th).get_text(strip=True)

        match = re.match(r'(\d{4})/(\d{2})', text)
        if match:
            headers.append((int(match.group(1)), int(match.group(2))))

    return headers


def _extract_row_header(row):
    """tr에서 지표명(th 텍스트) 추출 및 정규화"""
    th = row.find('th')
    if not th:
        return ''

    # tip_in 링크 내의 txt_acd span 우선
    tip_in = th.find('a', class_='tip_in')
    if tip_in:
        txt_acd = tip_in.find('span', class_='txt_acd')
        if txt_acd:
            return txt_acd.get_text(strip=True)
        return tip_in.get_text(strip=True)

    # div 내 텍스트 (단위 표시 csize span 제거 후)
    div = th.find('div')
    if div:
        for csize in div.find_all('span', class_='csize'):
            csize.decompose()
        return div.get_text(strip=True)

    return th.get_text(strip=True)


def _extract_row_values(row):
    """tr에서 td 값들을 float 또는 None 리스트로 추출"""
    values = []
    for td in row.find_all('td'):
        text = td.get_text(strip=True)
        if text in ('\xa0', '', '-', 'N/A'):
            values.append(None)
        else:
            try:
                values.append(float(text.replace(',', '')))
            except (ValueError, AttributeError):
                values.append(None)
    return values


def _map_indicator_name(raw_name):
    """
    원본 지표명 → 통합 컬럼명 변환

    매핑 순서:
      1. 직접 매핑
      2. 괄호 제거 후 재시도 (예: '총자산이익률(ROA)' → '총자산이익률')
      3. 공백 제거 후 재시도

    Returns:
        str: 통합 컬럼명, 없으면 None
    """
    if raw_name in INDICATOR_NAME_MAP:
        return INDICATOR_NAME_MAP[raw_name]

    without_paren = re.sub(r'\([^)]+\)', '', raw_name).strip()
    if without_paren in INDICATOR_NAME_MAP:
        return INDICATOR_NAME_MAP[without_paren]

    compact = without_paren.replace(' ', '')
    if compact in INDICATOR_NAME_MAP:
        return INDICATOR_NAME_MAP[compact]

    return None
