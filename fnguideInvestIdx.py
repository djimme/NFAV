"""
FnGuide 투자지표 페이지 (SVD_Invest.asp) 데이터 수집 및 파싱

수집 지표:
1. 멀티팩터 스타일 분석 (JSON API: /SVO2/json/chart/05_05/A{code}.json)
   - 12개 팩터별 종목/업종 노출도 점수 (밸류, 성장성, 모멘텀, 변동성 등)
   - 컬럼 형식: 팩터_{팩터명}_종목 / 팩터_{팩터명}_업종

2. 기업가치 지표 (HTML p_grid1_* 테이블)
   - Per Share : EPS, EBITDAPS, CFPS, SPS, BPS, DPS(보통주), DPS(1우선주), 배당성향(현금)
   - Multiples : PER, PCR, PSR, PBR, EV/Sales, EV/EBITDA
   - FCF       : 총현금흐름, 총투자, FCFF
   - 컬럼 형식 : {YYYY}_{지표명} (연도별 최신 기간만 수집)

Public API:
  getFnGuideInvestIdx(code)    : 투자지표 HTML 가져오기 (캐싱)
  parseFnGuideInvestIdx(html)  : 기업가치 지표 추출 → dict 또는 None
  getFnGuideMultiFactor(code)  : 멀티팩터 스타일 분석 JSON 가져오기 (캐싱)
  parseMultiFactorJson(data)   : 멀티팩터 데이터 추출 → dict
  collectInvestIdx(code)       : 멀티팩터 + 기업가치 지표 통합 수집 → dict 또는 None
"""
import datetime
import json
import os
import re
import shutil

import requests
from bs4 import BeautifulSoup

from fin_utils import fetch_fnguide_page


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def getFnGuideInvestIdx(code):
    """FnGuide 투자지표 HTML 가져오기 (캐싱)"""
    return fetch_fnguide_page(code, 'SVD_Invest.asp', '105', 'fnguide_InvestIdx_')


def getFnGuideMultiFactor(code):
    """
    멀티팩터 스타일 분석 JSON 가져오기 (캐싱)

    URL: https://comp.fnguide.com/SVO2/json/chart/05_05/A{code}.json
    캐시: derived/fnguide_InvestIdx_{YYYY-MM}/factor_{code}.json

    Returns:
        dict: JSON 응답 (CHART_H, CHART_D 포함), 실패 시 None
    """
    now = datetime.datetime.now()
    url = f'https://comp.fnguide.com/SVO2/json/chart/05_05/A{code}.json'

    cache_prefix = 'fnguide_InvestIdx_'
    cache_dir  = f'derived/{cache_prefix}{now.year}-{now.month:02d}'
    cache_path = f'{cache_dir}/factor_{code}.json'

    os.makedirs(cache_dir, exist_ok=True)

    # 이전 달 캐시 디렉토리 삭제
    current_dir_name = os.path.basename(cache_dir)
    for entry in os.listdir('derived'):
        if entry.startswith(cache_prefix) and entry != current_dir_name:
            shutil.rmtree(os.path.join('derived', entry))

    if os.path.exists(cache_path):
        with open(cache_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        # FnGuide JSON 응답에 UTF-8 BOM이 포함되어 resp.json()이 실패하므로
        # utf-8-sig로 직접 디코딩한다.
        data = json.loads(resp.content.decode('utf-8-sig'))
        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False)
        return data
    except Exception:
        return None


def parseMultiFactorJson(data):
    """
    멀티팩터 JSON에서 팩터별 종목/업종 노출도 점수 추출

    JSON 구조:
        CHART_H : [{"NAME": "종목명"}, {"NAME": "업종명(업종)"}]
        CHART_D : [{"NM": "팩터명", "VAL1": 종목점수, "VAL2": 업종점수}, ...]

    Returns:
        dict: {
            '팩터_업종명': '소재',
            '팩터_{팩터명}_종목': float,
            '팩터_{팩터명}_업종': float,
            ...
        }
    """
    if not data or 'CHART_D' not in data:
        return {}

    result = {}

    # 비교 업종명 추출 (CHART_H[1])
    chart_h = data.get('CHART_H', [])
    if len(chart_h) >= 2:
        sector_name = chart_h[1].get('NAME', '')
        result['팩터_업종명'] = re.sub(r'\s*\(업종\)\s*$', '', sector_name).strip()

    for row in data.get('CHART_D', []):
        nm = str(row.get('NM', '')).strip()
        if not nm:
            continue

        val1 = row.get('VAL1')
        val2 = row.get('VAL2')

        if val1 is not None:
            try:
                result[f'{nm}_종목'] = float(val1)
            except (ValueError, TypeError):
                pass

        if val2 is not None:
            try:
                result[f'{nm}_업종'] = float(val2)
            except (ValueError, TypeError):
                pass

    return result


def parseFnGuideInvestIdx(html):
    """
    투자지표 HTML에서 기업가치 지표 데이터 추출

    Args:
        html: FnGuide 투자지표 HTML 문자열

    Returns:
        dict: 종목명, 마켓분야, FICS분야, 연도별 기업가치 지표
        None: 기업가치 지표 테이블이 없는 경우
    """
    soup = BeautifulSoup(html, 'html.parser')

    data = {}
    data['종목명'] = _parse_company_name(soup)

    kse_sector, fics_sector, fiscal_month = _parse_kse_fics(soup)
    data['마켓분야'] = kse_sector
    data['FICS분야'] = fics_sector
    if fiscal_month is not None:
        data['결산월'] = fiscal_month

    ev_data = _parse_enterprise_value(soup)
    if ev_data is None:
        return None
    data.update(ev_data)

    return data


def collectInvestIdx(code):
    """
    투자지표 HTML + 멀티팩터 JSON을 통합 수집하여 반환

    fngCollect.py의 process_single_stock에서 호출된다.

    Args:
        code: 종목코드 (6자리 문자열, 예: '051910')

    Returns:
        dict: 종목명, 마켓분야, FICS분야, 멀티팩터 점수, 연도별 기업가치 지표
        None: 기업가치 지표 테이블 없음
    """
    html = getFnGuideInvestIdx(code)
    result = parseFnGuideInvestIdx(html)
    if result is None:
        return None

    factor_json = getFnGuideMultiFactor(code)
    if factor_json:
        result.update(parseMultiFactorJson(factor_json))

    return result


# ---------------------------------------------------------------------------
# Private parse helpers — 기업가치 지표
# ---------------------------------------------------------------------------

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


def _find_table_by_caption(soup, caption_text):
    """caption 텍스트로 table 태그 탐색"""
    for caption in soup.find_all('caption'):
        if caption_text in caption.get_text(strip=True):
            return caption.find_parent('table')
    return None


def _parse_enterprise_value(soup):
    """
    기업가치 지표 테이블에서 Per Share / Multiples / FCF 데이터 추출

    Returns:
        dict: {'{YYYY/MM}_{지표명}': value, ...}
        None: 테이블 없음
    """
    table = _find_table_by_caption(soup, '기업가치 지표')
    if not table:
        return None

    periods = _parse_ev_periods(table)
    if not periods:
        return None

    # 연도별 가장 최근 기간의 (year, index) 목록
    year_idx_list = _select_latest_per_year(periods)

    data = {}
    tbody = table.find('tbody')
    if not tbody:
        return data

    in_fcf = False

    for row in tbody.find_all('tr'):
        row_classes = row.get('class') or []
        row_id      = row.get('id', '')

        # 섹션 헤더 행: FCF 섹션 진입 여부 감지
        if 'tbody_tit' in row_classes:
            if 'FCF' in row.get_text():
                in_fcf = True
            continue

        # p_grid1_* 하위 상세 행 제외 (display:none)
        if any(cls.startswith('c_grid') for cls in row_classes):
            continue

        # Per Share / Multiples 최상위 행 (id="p_grid1_N")
        if re.match(r'^p_grid1_\d+$', row_id):
            indicator = _extract_ev_row_name(row)
            if indicator:
                values = _extract_td_values(row)
                _add_year_values(data, year_idx_list, indicator, values)
            continue

        # FCF 섹션 최상위 행 (3개 nbsp 들여쓰기, 4개 이상은 하위 항목)
        if in_fcf and 'rwf' in row_classes and 'acd_dep_start_close' not in row_classes:
            raw = _extract_ev_row_name_raw(row)
            if raw.startswith('\xa0\xa0\xa0') and not raw.startswith('\xa0\xa0\xa0\xa0'):
                indicator = raw.strip()
                values = _extract_td_values(row)
                _add_year_values(data, year_idx_list, indicator, values)

    return data


def _parse_ev_periods(table):
    """기업가치 지표 테이블 헤더에서 기간 목록 추출 → ['2021/12', '2022/12', ...]"""
    periods = []
    thead = table.find('thead')
    if not thead:
        return periods

    header_row = thead.find('tr')
    if not header_row:
        return periods

    for th in header_row.find_all('th'):
        text = th.get_text(strip=True)
        match = re.match(r'(\d{4}/\d{2})', text)
        if match:
            periods.append(match.group(1))

    return periods


def _extract_ev_row_name_raw(row):
    """기업가치 지표 행의 th에서 지표명 원문(nbsp 포함) 반환"""
    th = row.find('th')
    if not th:
        return ''

    tip_in = th.find('a', class_='tip_in')
    if tip_in:
        txt_acd = tip_in.find('span', class_='txt_acd')
        if txt_acd:
            return txt_acd.get_text()

    div = th.find('div')
    if div:
        for csize in div.find_all('span', class_='csize'):
            csize.decompose()
        return div.get_text()

    return th.get_text()


def _extract_ev_row_name(row):
    """기업가치 지표 행의 th에서 지표명 추출 (공백·nbsp 제거)"""
    return _extract_ev_row_name_raw(row).strip()


def _extract_td_values(row):
    """
    tr의 td 요소에서 숫자 값 리스트 추출

    처리 우선순위:
      1. title 속성 (고정밀도 값)
      2. td 텍스트 (<span class='tcr'> 음수 포함 가능)
      3. &nbsp; / '-' / 'N/A' → None
    """
    values = []
    for td in row.find_all('td'):
        title = td.get('title', '').strip()
        if title and title not in ('\xa0', '-', 'N/A', ''):
            try:
                values.append(float(title.replace(',', '')))
                continue
            except ValueError:
                pass

        text = td.get_text(strip=True).replace('\xa0', '').strip()
        if text in ('', '-', 'N/A'):
            values.append(None)
        else:
            try:
                values.append(float(text.replace(',', '')))
            except ValueError:
                values.append(None)

    return values


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
