"""
FnGuide Snapshot 페이지 데이터 수집 및 파싱

2026년 사이트 개편 후 주소: https://wcomp.fnguide.com/CompanyInfo/Snapshot?c_id=AA&menu_type=01&cmp_cd={종목코드}
Financial Highlight 표는 빈 틀이고, 값은 페이지 안의 스크립트 데이터(snpFinancial)에 들어 있다.

- getFnGuideSnapshot(code)  : HTML 가져오기 (캐싱)
- parseFnguideSnapshot(html): 종목명, 마켓분야·WI26 분야, Financial Highlight 투자지표 추출
- collectSnapshot(code)     : HTML 가져오기 + 파싱 통합 수집 → dict 또는 None
"""
import json
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
        dict: 종목명, 마켓분야, WI26분야, 연도별 재무지표, 발행주식수
        None: Financial Highlight 데이터(snpFinancial)가 없는 경우
    """
    soup = BeautifulSoup(html, 'html.parser')

    data = {}
    data['종목명'] = parse_company_name(soup)

    kse_sector, fics_sector, fiscal_month = parse_kse_fics(soup)
    data['마켓분야'] = kse_sector
    data['WI26분야'] = fics_sector
    if fiscal_month is not None:
        data['결산월'] = fiscal_month

    highlight = _parse_highlight_json(html)
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
        dict: 종목명, 마켓분야, WI26분야, 연도별 재무지표, 발행주식수
        None: Financial Highlight 테이블이 없는 경우
    """
    return parseFnguideSnapshot(getFnGuideSnapshot(code))


# --- Private parse helpers ---

# 사이트 항목 이름 → 컬럼 이름 (단위만 붙인다)
_JSON_NAMES = {'영업이익률': '영업이익률(%)', '부채비율': '부채비율(%)', '유보율': '유보율(%)',
               '순이익률(지배)': '순이익률(지배)(%)', 'PER': 'PER(배)', 'EPS': 'EPS(원)', 'PBR': 'PBR(배)',
               'BPS': 'BPS(원)', 'ROA': 'ROA(배)', 'ROE': 'ROE(배)', '현금배당수익률': '현금배당수익률(%)'}


def _parse_highlight_json(html, current_year=None):
    """페이지의 스크립트 데이터 snpFinancial 에서 연간 Financial Highlight 추출.

    header 는 앞쪽이 연간(추정치 E 포함), 뒤쪽이 분기다. 기간이 다시 과거로 돌아가는 곳에서 연간이 끝난다.
    Returns: (data_dict, selected_years) 또는 None
    """
    if current_year is None:
        current_year = datetime.now().year
    m = re.search(r'snpFinancial\s*:\s*', html)
    if not m:
        return None
    try:
        obj, _ = json.JSONDecoder().raw_decode(html, m.end())
    except ValueError:
        return None
    annual, prev = [], ''
    for h in obj.get('header') or []:
        if not h.get('YYMM'):
            continue             # 신규 상장 종목: 상장 전 연도는 YYMM 이 비어 있다
        if h['YYMM'] <= prev:
            break
        prev = h['YYMM']
        ym = re.match(r'(\d{4})/(\d{2})', h['YYMM'])
        if ym:
            annual.append((int(ym.group(1)), h['CD']))
    annual = [(y, cd) for y, cd in annual if current_year - 3 <= y <= current_year + 1]
    if not annual:
        return None

    def num(v):
        try:
            return float(str(v).replace(',', ''))
        except (TypeError, ValueError):
            return None      # 'N/A', None

    data = {}
    for row in obj.get('data') or []:
        name = (row.get('NAME') or '').strip()
        if name == '발행주식수(보통주)':
            for _, cd in reversed(annual):      # 가장 최근 값 하나 (주 → 천주)
                if num(row.get(cd)) is not None:
                    data['발행주식수(천주)'] = round(num(row[cd]) / 1000)
                    break
        elif name in _JSON_NAMES:
            for y, cd in annual:
                data[f'{y}_{_JSON_NAMES[name]}'] = num(row.get(cd))
    return data, [y for y, _ in annual]

