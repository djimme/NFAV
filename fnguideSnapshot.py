"""
FnGuide Snapshot 페이지 (SVD_Main.asp) 데이터 수집 및 파싱

- getFnGuideSnapshot(code)  : HTML 가져오기 (캐싱)
- parseFnguideSnapshot(html): 종목명, KSE/FICS 분야, Financial Highlight 투자지표 추출
- collectSnapshot(code)     : HTML 가져오기 + 파싱 통합 수집 → dict 또는 None
"""
import re
from datetime import datetime
from bs4 import BeautifulSoup
from fin_utils import fetch_fnguide_page, parse_company_name, parse_kse_fics


def getFnGuideSnapshot(code):
    """FnGuide Snapshot HTML 가져오기 (캐싱)"""
    return fetch_fnguide_page(code, 'SVD_Main.asp', '101', 'fnguide_snapshot_')


def parseFnguideSnapshot(html):
    """
    Snapshot HTML에서 투자지표 데이터 추출

    Args:
        html: FnGuide Snapshot HTML 문자열

    Returns:
        dict: 종목명, 마켓분야, FICS분야, 연도별 재무지표, 발행주식수
        None: Financial Highlight 테이블이 없는 경우
    """
    soup = BeautifulSoup(html, 'html.parser')

    data = {}
    data['종목명'] = parse_company_name(soup)

    kse_sector, fics_sector, fiscal_month = parse_kse_fics(soup)
    data['마켓분야'] = kse_sector
    data['FICS분야'] = fics_sector
    if fiscal_month is not None:
        data['결산월'] = fiscal_month

    highlight = _parse_financial_highlight(soup)
    if highlight is None:
        return None

    highlight_data, _ = highlight
    data.update(highlight_data)

    return data


def collectSnapshot(code):
    """
    Snapshot HTML 가져오기 + 파싱 통합 수집

    Args:
        code: 종목코드 (6자리 문자열, 예: '005930')

    Returns:
        dict: 종목명, 마켓분야, FICS분야, 연도별 재무지표, 발행주식수
        None: Financial Highlight 테이블이 없는 경우
    """
    return parseFnguideSnapshot(getFnGuideSnapshot(code))


# --- Private parse helpers ---

def _parse_financial_highlight(soup, current_year=None):
    """
    Financial Highlight 테이블(highlight_D_Y)에서 연결/연간 기준 데이터 추출

    Returns:
        (data_dict, selected_years) 튜플, 또는 None
    """
    if current_year is None:
        current_year = datetime.now().year

    table = soup.find('div', id='highlight_D_Y')
    if not table:
        return None

    table_tag = table.find('table')
    if not table_tag:
        return None

    # 헤더에서 연도/월 추출
    year_month_headers = _parse_year_headers(table_tag)

    # 연도별 최신 데이터 인덱스 선택 (현재년도 기준 과거3년 ~ 미래1년)
    year_to_latest = {}
    for i, (year, month, _, _) in enumerate(year_month_headers):
        if year < current_year - 3 or year > current_year + 1:
            continue
        if year not in year_to_latest or month > year_to_latest[year][1]:
            year_to_latest[year] = (i, month)

    selected_years = sorted(year_to_latest.keys())

    # 지표 데이터 추출
    indicators = [
        '영업이익률', '부채비율', '유보율', '지배주주순이익률',
        'PER', 'EPS', 'PBR', 'BPS', 'ROA', 'ROE',
        '배당수익률', '발행주식수'
    ]

    unit_map = {
        'PER': '(배)', 'PBR': '(배)', 'ROA': '(배)', 'ROE': '(배)',
        'EPS': '(원)', 'BPS': '(원)',
        '영업이익률': '(%)', '부채비율': '(%)', '유보율': '(%)',
        '지배주주순이익률': '(%)', '배당수익률': '(%)'
    }

    data = {}
    tbody = table_tag.find('tbody')
    if not tbody:
        return data, selected_years

    for row in tbody.find_all('tr'):
        name = _extract_indicator_name(row)
        if name not in indicators:
            continue

        values = _extract_row_values(row)

        if name == '발행주식수':
            # 가장 최근 non-None 값 하나만
            for year in reversed(selected_years):
                idx, _ = year_to_latest[year]
                if idx < len(values) and values[idx] is not None:
                    data['발행주식수(천주)'] = values[idx]
                    break
        else:
            unit = unit_map.get(name, '')
            for year in selected_years:
                idx, _ = year_to_latest[year]
                if idx < len(values):
                    data[f"{year}_{name}{unit}"] = values[idx]

    return data, selected_years


def _parse_year_headers(table_tag):
    """thead에서 (year, month, is_estimate, text) 리스트 추출"""
    headers = []
    thead = table_tag.find('thead')
    if not thead:
        return headers

    second_row = thead.find('tr', class_='td_gapcolor2')
    if not second_row:
        return headers

    for th in second_row.find_all('th', scope='col'):
        div = th.find('div')
        if not div:
            continue

        tip_in = div.find('a', class_='tip_in')
        year_text = (tip_in or div).get_text(strip=True)

        match = re.match(r'(\d{4})/(\d{2})(\(E\))?', year_text)
        if match:
            headers.append((
                int(match.group(1)),
                int(match.group(2)),
                match.group(3) is not None,
                year_text
            ))

    return headers


def _extract_indicator_name(row):
    """tbody의 tr에서 지표명 추출"""
    th = row.find('th', scope='row')
    if not th:
        return ""

    tip_in = th.find('a', class_='tip_in')
    if tip_in:
        txt_acd = tip_in.find('span', class_='txt_acd')
        if txt_acd:
            return txt_acd.get_text(strip=True)

    div = th.find('div')
    if div:
        for csize in div.find_all('span', class_='csize'):
            csize.decompose()
        return div.get_text(strip=True)

    return ""


def _extract_row_values(row):
    """tbody의 tr에서 td 값들을 float 리스트로 추출"""
    values = []
    for td in row.find_all('td'):
        text = td.get_text(strip=True)
        if text in ('\xa0', ''):
            values.append(None)
        else:
            try:
                values.append(float(text.replace(',', '')))
            except (ValueError, AttributeError):
                values.append(None)
    return values
