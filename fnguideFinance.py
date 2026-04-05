"""
FnGuide Finance 페이지 (SVD_Finance.asp) 데이터 수집 및 파싱

수집 데이터:
- 손익계산서 (연간 최근 3년 / 분기 최근 4분기)
  비금융:    매출액, 매출원가, 매출총이익, 판관비, 영업이익, 세전계속사업이익, 법인세비용, 당기순이익
  은행/금융: 순영업수익, 판관비, 영업이익, 세전계속사업이익, 법인세비용, 당기순이익
  보험/창투: 영업수익, 영업비용, 영업이익, 세전계속사업이익, 법인세비용, 당기순이익
- 현금흐름표 (연간 최근 3년 / 분기 최근 4분기) — 업종 무관 동일 구조
  영업활동현금흐름, 투자활동현금흐름, 재무활동현금흐름, 현금성자산증가

컬럼 형식:
  연간 : {YYYY}(연간)_{지표명}    (예: 2024(연간)_당기순이익)
  분기 : {YYYY/NQ}_{지표명}       (예: 2024/4Q_당기순이익)

컬럼 순서:
  지표명별로 연간 데이터 컬럼이 먼저 나온 후, 분기 데이터 컬럼이 이어짐

Public API:
  getFnguideFinance(code)    : HTML 가져오기 (캐싱)
  parseFnguideFinance(html)  : 재무제표 데이터 추출 → dict 또는 None
  collectFinance(code)       : HTML 가져오기 + 파싱 통합 수집 → dict 또는 None
"""
import re

from bs4 import BeautifulSoup

from fin_utils import fetch_fnguide_page


# ── 손익계산서 수집 항목 (row prefix → 컬럼명)
# 업종별로 존재하는 행만 실제 수집됨 (없는 항목은 자동 스킵)
_SONIK_TARGETS = [
    ('매출액',           '매출액'),
    ('매출원가',         '매출원가'),
    ('매출총이익',       '매출총이익'),
    ('순영업수익',       '순영업수익'),     # 은행/금융지주
    ('영업수익',         '영업수익'),       # 보험/창투사
    ('영업비용',         '영업비용'),       # 보험/창투사
    ('판매비와관리비',   '판관비'),
    ('영업이익',         '영업이익'),
    ('세전계속사업이익', '세전계속사업이익'),
    ('법인세비용',       '법인세비용'),
    ('당기순이익',       '당기순이익'),
]

# ── 현금흐름표 수집 항목 (업종 무관 동일 구조)
_CASH_TARGETS = [
    ('영업활동으로인한현금흐름', '영업활동현금흐름'),
    ('투자활동으로인한현금흐름', '투자활동현금흐름'),
    ('재무활동으로인한현금흐름', '재무활동현금흐름'),
    ('현금및현금성자산의증가',   '현금성자산증가'),
]


def getFnguideFinance(code):
    """FnGuide Finance HTML 가져오기 (캐싱)"""
    return fetch_fnguide_page(code, 'SVD_Finance.asp', '103', 'fnguide_finance_')


def parseFnguideFinance(html):
    """
    Finance HTML에서 손익계산서 및 현금흐름표 데이터 추출

    업종에 따라 손익계산서 항목이 자동 선택되며,
    현금흐름표는 모든 업종에서 동일한 구조로 수집된다.

    Args:
        html: FnGuide Finance HTML 문자열

    Returns:
        dict: 종목명, 마켓분야, FICS분야, 결산월, 연결여부, 연도별/분기별 손익/현금흐름 데이터
        None: 손익계산서 연간 테이블(#divSonikY)이 없는 경우
    """
    soup = BeautifulSoup(html, 'html.parser')

    data = {}
    data['종목명'] = _parse_company_name(soup)

    kse_sector, fics_sector, fiscal_month = _parse_kse_fics(soup)
    data['마켓분야'] = kse_sector
    data['FICS분야'] = fics_sector
    if fiscal_month is not None:
        data['결산월'] = fiscal_month

    # 연결/개별 여부 (손익 연간 첫 번째 헤더 기준)
    sonik_y_el = soup.select_one('#divSonikY')
    if sonik_y_el is None:
        return None
    first_th = sonik_y_el.select_one('thead th')
    data['연결여부'] = first_th.get_text(strip=True) if first_th else ''

    # 손익계산서: 지표명별 연간 → 분기 순서로 추가
    sonik_y = _process_table(soup, '#divSonikY', _SONIK_TARGETS, annual=True)
    sonik_q = _process_table(soup, '#divSonikQ', _SONIK_TARGETS, annual=False)
    _merge_by_metric(data, sonik_y, sonik_q, _SONIK_TARGETS)

    # 현금흐름표: 지표명별 연간 → 분기 순서로 추가
    cash_y = _process_table(soup, '#divCashY', _CASH_TARGETS, annual=True)
    cash_q = _process_table(soup, '#divCashQ', _CASH_TARGETS, annual=False)
    _merge_by_metric(data, cash_y, cash_q, _CASH_TARGETS)

    return data


def collectFinance(code):
    """
    Finance HTML 가져오기 + 파싱 통합 수집

    Args:
        code: 종목코드 (6자리 문자열, 예: '005930')

    Returns:
        dict: 종목명, 마켓분야, FICS분야, 결산월, 연결여부, 연도별/분기별 손익/현금흐름 데이터
        None: 손익계산서 연간 테이블(#divSonikY)이 없는 경우
    """
    return parseFnguideFinance(getFnguideFinance(code))


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

    corp_group1 = soup.find('div', class_='corp_group1')
    if corp_group1:
        for h2 in corp_group1.find_all('h2'):
            h2_text = h2.get_text(strip=True)
            # print(f"  [결산월 디버그] h2 텍스트: {repr(h2_text)}")
            m = re.search(r'(\d+)월\s*결산', h2_text)
            if m:
                fiscal_month = int(m.group(1))
                # print(f"  [결산월 디버그] 추출 성공: {fiscal_month}월")
                break
        else:
            pass  # print(f"  [결산월 디버그] 모든 h2 순회 완료 - 결산월 패턴 없음")
    else:
        pass  # print(f"  [결산월 디버그] div.corp_group1 요소를 찾을 수 없음")

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


def _parse_date_columns(headers):
    """헤더 th 목록에서 날짜 컬럼의 (인덱스, 텍스트) 목록 반환 (전년동기 제외)"""
    result = []
    for i, th in enumerate(headers):
        text = th.get_text(strip=True)
        if re.match(r'\d{4}/\d{2}', text):
            result.append((i, text))
    return result


def _to_quarter_label(period):
    """'YYYY/MM' → 'YYYY/NQ' 변환 (예: '2024/12' → '2024/4Q')"""
    year, mm = period.split('/')
    quarter = (int(mm) - 1) // 3 + 1
    return f'{year}/{quarter}Q'


def _find_row(rows, prefix):
    """tbody tr 목록에서 div 텍스트가 prefix로 시작하는 행 반환"""
    for tr in rows:
        div = tr.select_one('div')
        if div is None:
            continue
        name = div.get_text(strip=True).replace('\xa0', '')
        if name == prefix or name.startswith(prefix):
            return tr
    return None


def _parse_number(text):
    """문자열을 숫자로 변환 (실패 시 None)"""
    if text in ('\xa0', '', '-', 'N/A'):
        return None
    try:
        return float(text.replace(',', ''))
    except (ValueError, AttributeError):
        return None


def _process_table(soup, section_id, targets, annual):
    """테이블에서 targets에 해당하는 행 데이터를 추출해 {col_name: {key: value}} dict로 반환"""
    result = {}
    el = soup.select_one(section_id)
    if el is None:
        return result

    headers = el.select('thead th')
    date_cols = _parse_date_columns(headers)

    if annual:
        date_cols = date_cols[:3]   # 최근 3개 완전 회계연도
    else:
        date_cols = date_cols[-4:]  # 최근 4분기

    body_rows = el.select('tbody tr')

    for prefix, col_name in targets:
        tr = _find_row(body_rows, prefix)
        if tr is None:
            continue
        cells = tr.select('th, td')
        col_entries = {}
        for col_idx, period in date_cols:
            if col_idx >= len(cells):
                continue
            raw = cells[col_idx].get_text(strip=True)
            if annual:
                period_label = f"{period.split('/')[0]}(연간)"
            else:
                period_label = _to_quarter_label(period)
            col_entries[f'{period_label}_{col_name}'] = _parse_number(raw)
        if col_entries:
            result[col_name] = col_entries
    return result


def _merge_by_metric(result, annual_dict, quarterly_dict, targets):
    """지표명별로 연간 데이터 후 분기 데이터 순서로 result에 추가"""
    for _, col_name in targets:
        if col_name in annual_dict:
            result.update(annual_dict[col_name])
        if col_name in quarterly_dict:
            result.update(quarterly_dict[col_name])
