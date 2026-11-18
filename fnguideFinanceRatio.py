"""
FnGuide FinanceRatio 페이지 데이터 수집 및 파싱

2026년 사이트 개편 후 주소: https://wcomp.fnguide.com/CompanyInfo/FinanceRatio?c_id=AA&menu_type=01&cmp_cd={종목코드}
표는 빈 틀이고 값은 페이지 안의 스크립트 데이터(rtoAccumulate 연간, rtoAccumulate3Month 분기)에 들어 있다.

업종별 재무비율 수집:
- 연결 누적 (Annual)  : 연도별 재무비율 → 컬럼 형식 {YYYY(누적)}_{지표명}  (결산월에 끝나는 완전 회계연도)
                        최근 부분연도 열은 {YYYY/NQ(부분누적)}_{지표명} 으로 분리
- 연결 3개월 (Quarterly): 분기별 재무비율 → 컬럼 형식 {YYYY/MM}_{지표명}

지표 이름은 FnGuide 사이트 항목 이름 그대로 쓴다 (업종별 목록은 아래 INDUSTRY_INDICATORS).
DART 계산 값(dart_ratio)과는 이름이 다른 지표가 있다 (예: 매출액증가율 ↔ DART 매출증가율).

Public API:
  getFnGuideFiRatio(code)    : HTML 가져오기 (캐싱)
  parseFnguideFiRatio(html)  : 재무비율 데이터 추출 → dict 또는 None
  collectFinanceRatio(code)  : HTML 가져오기 + 파싱 통합 수집 → dict 또는 None
"""
import re

from bs4 import BeautifulSoup

from fin_utils import (fetch_fnguide_page, parse_company_name, parse_kse_fics, parse_fnguide_inline,
                       fnguide_num)


# 업종 타입 상수
INDUSTRY_TYPE_MANUFACTURING = '제조업'
INDUSTRY_TYPE_BANKING       = '은행업'
INDUSTRY_TYPE_SECURITIES    = '증권업'
INDUSTRY_TYPE_INSURANCE     = '보험업'

# 업종별 지표 목록 (시트 컬럼 필터링에 사용) — FnGuide 항목 이름 그대로
INDUSTRY_INDICATORS = {
    INDUSTRY_TYPE_MANUFACTURING: [
        '유동비율', '당좌비율', '부채비율', '유보율', '순부채비율', '이자보상배율', '자기자본비율',
        '매출액증가율', '판매비와관리비증가율', 'EPS증가율', '영업이익증가율', 'EBITDA증가율',
        '매출총이익률', '세전계속사업이익률', '영업이익률', 'EBITDA마진율',
        'ROIC', 'ROA', 'ROE',
        '총자산회전율', '총부채회전율', '자기자본회전율', '순운전자본회전율',
    ],
    INDUSTRY_TYPE_BANKING: [
        '예대율',
        '매출액증가율', '영업이익증가율', '당기순이익증가율(지배)', 'EPS증가율',
        '총자산증가율', '대출채권증가율', '예수부채증가율',
        'ROA', '순이자마진율', '예대마진율', 'ROE',
    ],
    INDUSTRY_TYPE_SECURITIES: [
        '예대율', '유가증권보유율', '부채비율', '유보율',
        '매출액증가율', '영업이익증가율', '당기순이익증가율(지배)', 'EPS증가율',
        '영업이익률', '영업수지율', '순이자마진율', 'ROA', 'ROE',
    ],
    INDUSTRY_TYPE_INSURANCE: [
        '운용자산비율', '자기자본비율',
        '매출액증가율', '영업이익증가율', '당기순이익증가율(지배)', 'EPS증가율',
        '영업이익률', '당기순이익이익률(지배)', 'ROA', 'ROE',
        '손해율', '순사업비율',
    ],
}
# 업종 시트에 들어온 종목이 다른 업종 양식의 표를 쓰는 경우가 있어(예: 은행업 시트의 기타금융 회사),
# 다른 업종의 지표도 뒤에 붙여 둔다 (값이 없는 열은 시트를 만들 때 빠진다)
_ALL_INDICATORS = list(dict.fromkeys(i for v in INDUSTRY_INDICATORS.values() for i in v))
for _indicators in INDUSTRY_INDICATORS.values():
    _indicators.extend(i for i in _ALL_INDICATORS if i not in _indicators)


def detect_industry_type(market_sector, fics_sector):
    """
    마켓분야 + WI26분야 텍스트로 업종 타입 분류

    분류 기준:
      보험업: 마켓분야에 '보험' 포함 AND WI26분야에 '보험' 포함
      은행업: 마켓분야에 '금융' 또는 '은행' 포함 AND WI26분야가 '은행'
              (WI26 '은행'은 소분류 '기타금융'을 포함하므로 지주·카드·캐피탈 등도 여기 들어온다)
      증권업: 마켓분야에 '금융' 또는 '증권' 포함 AND WI26분야에 '증권' 포함
      그 외: 제조업
    (FICS 의 '창업투자 및 종금'에 해당하는 WI26 분류가 없어 창투업 구분은 없앴다)

    Args:
        market_sector: 마켓분야 문자열
        fics_sector  : WI26분야 문자열

    Returns:
        str: INDUSTRY_TYPE_* 상수 중 하나 (기본값: 제조업)
    """
    market = market_sector if isinstance(market_sector, str) else ''
    fics   = fics_sector   if isinstance(fics_sector,   str) else ''

    if '보험' in market and '보험' in fics:
        return INDUSTRY_TYPE_INSURANCE
    if ('금융' in market or '은행' in market) and fics == '은행':
        return INDUSTRY_TYPE_BANKING
    if ('금융' in market or '증권' in market) and '증권' in fics:
        return INDUSTRY_TYPE_SECURITIES
    return INDUSTRY_TYPE_MANUFACTURING


def getFnGuideFiRatio(code):
    """FnGuide FinanceRatio HTML 가져오기 (캐싱)"""
    return fetch_fnguide_page(code, 'SVD_FinanceRatio.asp', '104', 'fnguide_FinanceRatio_')


def parseFnguideFiRatio(html):
    """
    FinanceRatio HTML에서 연결 누적/3개월 재무비율 데이터 추출

    지표 이름은 FnGuide 사이트 항목 이름 그대로 컬럼 이름에 쓴다.

    Args:
        html: FnGuide FinanceRatio HTML 문자열

    Returns:
        dict: 종목명, 마켓분야, WI26분야, 연도별/분기별 재무비율
        None: 연결 누적 데이터(rtoAccumulate)가 없는 경우
    """
    soup = BeautifulSoup(html, 'html.parser')

    data = {}
    data['종목명'] = parse_company_name(soup)

    kse_sector, fics_sector, fiscal_month = parse_kse_fics(soup)
    data['마켓분야'] = kse_sector
    data['WI26분야'] = fics_sector
    if fiscal_month is not None:
        data['결산월'] = fiscal_month

    # 연결 누적 (Annual) — 컬럼 형식: {YYYY(누적)}_{지표명}, 최근 4개년 (값은 스크립트 데이터 rtoAccumulate)
    annual_data = _parse_json_section(parse_fnguide_inline(html, 'rtoAccumulate'), 'year', 4, fiscal_month)
    if annual_data is None:
        return None
    data.update(annual_data)

    # 연결 3개월 (Quarterly) — 컬럼 형식: {YYYY/NQ}_{지표명}, 최근 3기간
    quarterly_data = _parse_json_section(parse_fnguide_inline(html, 'rtoAccumulate3Month'), 'yearmonth', 3)
    if quarterly_data is not None:
        data.update(quarterly_data)

    return data


def collectFinanceRatio(code):
    """
    FinanceRatio HTML 가져오기 + 파싱 통합 수집

    Args:
        code: 종목코드 (6자리 문자열, 예: '005930')

    Returns:
        dict: 종목명, 마켓분야, WI26분야, 연도별/분기별 재무비율
        None: 연결 누적 테이블이 없는 경우
    """
    return parseFnguideFiRatio(getFnGuideFiRatio(code))


# --- Private parse helpers ---

def _parse_json_section(dataset, period_format='year', max_periods=None, fiscal_month=None):
    """{header, data} 에서 재무비율 추출 → {'{기간}_{지표명}': float}

    data 의 LVL 1 행이 비율이고(LVL 0 은 구분 제목, LVL 2 는 계산에 쓰인 금액), 값은 header 의 CD(VAL1…) 열에 있다.
    """
    if not dataset or not dataset.get('data'):
        return None
    periods, cds = [], []
    for h in dataset.get('header') or []:
        m = re.match(r'(\d{4})/(\d{2})', h.get('YYMM') or '')
        if m:
            periods.append((int(m.group(1)), int(m.group(2))))
            cds.append(h['CD'])
    if not periods:
        return None
    key_idx_list = _period_keys(periods, period_format, max_periods, fiscal_month)

    data = {}
    for row in dataset['data']:
        if row.get('LVL') != 1:
            continue
        # 사이트 항목 이름을 그대로 컬럼 이름으로 쓴다 (FnGuide 값을 DART 와 비교할 때 이름이 다른 정의를 가리지 않게).
        unified_name = (row.get('NM') or '').replace('\xa0', ' ').strip()
        if not unified_name:
            continue
        for period_key, idx in key_idx_list:
            value = fnguide_num(row.get(cds[idx]))
            if value is not None:
                data[f'{period_key}_{unified_name}'] = value
    return data


def _period_keys(periods, period_format, max_periods, fiscal_month):
    """[(year, month), ...] → [(기간 키, 열 인덱스), ...]"""
    # (period_key, original_col_index) 목록 생성
    if period_format == 'year' and fiscal_month:
        # 결산월에 끝나는 열만 '{YYYY}(누적)' (완전 회계연도), 최근 부분연도 1개는 따로 라벨
        full = [(y, m, i) for i, (y, m) in enumerate(periods) if int(m) == int(fiscal_month)]
        part = [(y, m, i) for i, (y, m) in enumerate(periods) if int(m) != int(fiscal_month)]
        if max_periods:
            full = full[-max_periods:]
        key_idx_list = [(f'{y}(누적)', i) for y, m, i in full]
        if part and (not full or part[-1][2] > full[-1][2]):
            y, m, i = part[-1]
            key_idx_list.append((f'{y}/{_month_to_quarter(m)}(부분누적)', i))
    elif period_format == 'year':
        # 결산월 정보가 없으면 기존 방식: 연도별 가장 최근 월의 인덱스 선택 후 최근 max_periods년
        year_to_latest = {}
        for i, (year, month) in enumerate(periods):
            if year not in year_to_latest or month > year_to_latest[year][0]:
                year_to_latest[year] = (month, i)
        sorted_years = sorted(year_to_latest.items())
        if max_periods:
            sorted_years = sorted_years[-max_periods:]
        key_idx_list = [(f'{year}(누적)', info[1]) for year, info in sorted_years]
    else:
        # 분기: 최근 max_periods 기간
        selected = periods[-max_periods:] if max_periods else periods
        offset = len(periods) - len(selected)
        key_idx_list = [
            (f'{year}/{_month_to_quarter(month)}', offset + i)
            for i, (year, month) in enumerate(selected)
        ]
    return key_idx_list


def _month_to_quarter(month):
    """월 → 분기 문자열 변환 (예: 12 → '4Q')"""
    return f'{(month - 1) // 3 + 1}Q'

