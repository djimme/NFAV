"""
FnGuide 투자지표 페이지 데이터 수집 및 파싱

2026년 사이트 개편 후 주소: https://wcomp.fnguide.com/CompanyInfo/Invest?c_id=AA&menu_type=01&cmp_cd={종목코드}
표는 빈 틀이고 값은 페이지 안의 스크립트 데이터(invValueIndex 기업가치 지표, invStyleChart 멀티팩터)에 들어 있다.

수집 지표 (이름은 FnGuide 사이트 항목 이름 그대로):
1. 멀티팩터 스타일 분석 (invStyleChart)
   - 팩터별 종목/업종 노출도 점수 (밸류, 성장성, 모멘텀, 변동성 등)
   - 컬럼 형식: {팩터명}_종목 / {팩터명}_업종, 비교 업종 이름은 팩터_업종명

2. 기업가치 지표 (invValueIndex) — Per Share, Dividends, Multiples, FCF
   - 컬럼 형식 : {YYYY}_{지표명} (연도별 최신 기간만 수집)

Public API:
  getFnGuideInvestIdx(code)    : 투자지표 HTML 가져오기 (캐싱)
  parseFnGuideInvestIdx(html)  : 기업가치 지표 추출 → dict 또는 None
  parseMultiFactorInline(html) : 멀티팩터 데이터 추출 → dict
  collectInvestIdx(code)       : 멀티팩터 + 기업가치 지표 통합 수집 → dict 또는 None
"""
import re

from bs4 import BeautifulSoup

from fin_utils import (fetch_fnguide_page, parse_company_name, parse_kse_fics, parse_fnguide_inline,
                       fnguide_num)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def getFnGuideInvestIdx(code):
    """FnGuide 투자지표 HTML 가져오기 (캐싱)"""
    return fetch_fnguide_page(code, 'SVD_Invest.asp', '105', 'fnguide_InvestIdx_')


def parseFnGuideInvestIdx(html):
    """
    투자지표 HTML에서 기업가치 지표 데이터 추출

    Args:
        html: FnGuide 투자지표 HTML 문자열

    Returns:
        dict: 종목명, 마켓분야, WI26분야, 연도별 기업가치 지표
        None: 기업가치 지표 테이블이 없는 경우
    """
    soup = BeautifulSoup(html, 'html.parser')

    data = {}
    data['종목명'] = parse_company_name(soup)

    kse_sector, fics_sector, fiscal_month = parse_kse_fics(soup)
    data['마켓분야'] = kse_sector
    data['WI26분야'] = fics_sector
    if fiscal_month is not None:
        data['결산월'] = fiscal_month

    ev_data = _parse_value_index_json(html, fiscal_month)
    if ev_data is None:
        return None
    data.update(ev_data)

    return data


def parseMultiFactorInline(html):
    """투자지표 페이지의 멀티팩터 데이터(invStyleChart)에서 팩터별 종목/업종 노출도 점수 추출

    header 의 VAL1·VAL2 = 종목·업종 이름, data = 팩터별 {NM, VAL1(종목 점수), VAL2(업종 점수)}

    Returns:
        dict: {'팩터_업종명': '소재', '{팩터명}_종목': float, '{팩터명}_업종': float, ...}
    """
    chart = parse_fnguide_inline(html, 'invStyleChart')
    if not chart or not chart.get('data'):
        return {}
    result = {}
    names = [h for h in chart.get('header') or [] if h.get('ID') in ('VAL1', 'VAL2')]
    if len(names) >= 2:
        result['팩터_업종명'] = re.sub(r'\s*\(업종\)\s*$', '', names[1].get('NM', '')).strip()
    for row in chart['data']:
        nm = str(row.get('NM', '')).strip()
        if not nm:
            continue
        for key, label in (('VAL1', '종목'), ('VAL2', '업종')):
            if row.get(key) is not None:
                try:
                    result[f'{nm}_{label}'] = float(row[key])
                except (ValueError, TypeError):
                    pass
    return result


def collectInvestIdx(code):
    """
    투자지표 페이지의 기업가치 지표 + 멀티팩터를 통합 수집하여 반환 (같은 페이지, 요청 1번)

    fngCollect.py의 process_single_stock에서 호출된다.

    Args:
        code: 종목코드 (6자리 문자열, 예: '051910')

    Returns:
        dict: 종목명, 마켓분야, WI26분야, 멀티팩터 점수, 연도별 기업가치 지표
        None: 기업가치 지표 테이블 없음
    """
    html = getFnGuideInvestIdx(code)
    result = parseFnGuideInvestIdx(html)
    if result is None:
        return None

    result.update(parseMultiFactorInline(html))

    return result


# ---------------------------------------------------------------------------
# Private parse helpers — 기업가치 지표
# ---------------------------------------------------------------------------

def _parse_value_index_json(html, fiscal_month=None):
    """페이지의 invValueIndex 에서 Per Share / Dividends / Multiples / FCF 추출

    data 의 LVL 1 행이 지표(LVL 0 은 구분 제목, LVL 2 는 계산에 쓰인 값)이고 값은 '8,057' 같은 문자열이다.
    지표 이름은 사이트 항목 이름 그대로 낸다.

    Returns:
        dict: {'{YYYY}_{지표명}': value, ...}
        None: 데이터 없음
    """
    dataset = parse_fnguide_inline(html, 'invValueIndex')
    if not dataset or not dataset.get('data'):
        return None
    periods, cds = [], []
    for h in dataset.get('header') or []:
        m = re.match(r'(\d{4}/\d{2})', h.get('YYMM') or '')
        if m:
            periods.append(m.group(1))
            cds.append(h['CD'])
    if not periods:
        return None
    year_idx_list = _select_latest_per_year(periods)
    if fiscal_month:
        # 3월 결산처럼 같은 해에 결산 열(2026/03)과 최근분기 열(2026/06)이 함께 있으면 결산 열을 쓴다
        full = {p[:4]: i for i, p in enumerate(periods) if int(p[5:7]) == int(fiscal_month)}
        year_idx_list = [(year, full.get(year, idx)) for year, idx in year_idx_list]

    data = {}
    for row in dataset['data']:
        if row.get('LVL') != 1:
            continue
        name = (row.get('NM') or '').strip()
        indicator = name
        values = [fnguide_num(row.get(cd)) for cd in cds]
        _add_year_values(data, year_idx_list, indicator, values)
    return data


def _select_latest_per_year(periods):
    """
    기간 목록에서 연도별 가장 최근 기간의 인덱스를 선택

    Args:
        periods: ['2021/12', '2022/12', '2024/03', ...] 형태

    Returns:
        list of (year_str, col_index) — 연도 오름차순
    """
    year_to_latest = {}  # year -> (month_int, index)
    for i, period in enumerate(periods):
        match = re.match(r'(\d{4})/(\d{2})', period)
        if match:
            year, month = match.group(1), int(match.group(2))
            if year not in year_to_latest or month > year_to_latest[year][0]:
                year_to_latest[year] = (month, i)
    # 연도 오름차순 정렬 후 최근 4개년만 반환
    sorted_years = sorted(year_to_latest.items())
    return [(year, info[1]) for year, info in sorted_years[-4:]]


def _add_year_values(data, year_idx_list, indicator, values):
    """year_idx_list [(year, col_index), ...] 매핑으로 data dict에 추가"""
    for year, idx in year_idx_list:
        if idx < len(values) and values[idx] is not None:
            data[f'{year}_{indicator}'] = values[idx]
