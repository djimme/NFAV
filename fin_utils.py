"""
FnGuide 스크래핑 공통 유틸리티

Excel 저장:
  save_styled_excel(df, filepath)             : 단일 시트 서식 저장
  save_styled_excel_multisheet(sheets, filepath): 멀티시트 서식 저장

HTTP / 캐싱:
  fetch_fnguide_page(code, asp_page, menu_id, cache_prefix): FnGuide 페이지 다운로드 (월별 폴더 캐싱, 지난달 폴더 보관)

환경변수 (.env):
  load_env()            : 프로젝트 루트의 .env를 os.environ에 로드 (이미 설정된 값은 유지)
  get_env(name, default): .env 로드 후 값 반환

HTML 파싱 공통 헬퍼 (모든 FnGuide 모듈에서 공유):
  parse_company_name(soup): 페이지 title에서 종목명 추출
  parse_kse_fics(soup)    : 마켓분야·WI26 업종 분류 및 결산월 추출
"""
import datetime
import json
import os
import time
import re

import requests
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment
from openpyxl.utils.dataframe import dataframe_to_rows


def save_styled_excel(df, filepath, sheet_name="Sheet1", index=False):
    """DataFrame을 서식이 적용된 Excel 파일로 저장한다.

    서식:
        - 글꼴: 맑은 고딕, 10pt
        - 맞춤: 상하 가운데, 좌우 가운데
    """
    wb = Workbook()
    ws = wb.active
    ws.title = sheet_name

    font = Font(name="맑은 고딕", size=10)
    alignment = Alignment(horizontal="center", vertical="center")

    for row in dataframe_to_rows(df, index=index, header=True):
        ws.append(row)

    for row in ws.iter_rows(min_row=1, max_row=ws.max_row, max_col=ws.max_column):
        for cell in row:
            cell.font = font
            cell.alignment = alignment
            if isinstance(cell.value, (int, float)):
                cell.number_format = '#,##0.##'

    wb.save(filepath)


def save_styled_excel_multisheet(sheets, filepath):
    """여러 시트를 담은 서식 적용 Excel 파일 저장

    Args:
        sheets  : [(sheet_name, DataFrame), ...] 순서 있는 시트 목록
        filepath: 저장 경로 (예: 'derived/output.xlsx')

    서식:
        - 글꼴: 맑은 고딕, 10pt
        - 맞춤: 상하 가운데, 좌우 가운데
    """
    wb = Workbook()
    font = Font(name="맑은 고딕", size=10)
    alignment = Alignment(horizontal="center", vertical="center")

    first = True
    for sheet_name, df in sheets:
        if first:
            ws = wb.active
            ws.title = sheet_name
            first = False
        else:
            ws = wb.create_sheet(title=sheet_name)

        for row in dataframe_to_rows(df, index=False, header=True):
            ws.append(row)

        for row_cells in ws.iter_rows(min_row=1, max_row=ws.max_row, max_col=ws.max_column):
            for cell in row_cells:
                cell.font = font
                cell.alignment = alignment
                if isinstance(cell.value, (int, float)):
                    cell.number_format = '#,##0.##'

    wb.save(filepath)


# FnGuide 개편(2026년) 후 주소: {예전 ASP 페이지명: 새 CompanyInfo 경로}
FNGUIDE_NEW_PATHS = {
    "SVD_Main.asp": "Snapshot",
    "SVD_Finance.asp": "Finance",
    "SVD_FinanceRatio.asp": "FinanceRatio",
    "SVD_Invest.asp": "Invest",
    "SVD_Consensus.asp": "Consensus",
}
FNGUIDE_HOST = "https://wcomp.fnguide.com"
_FNGUIDE_HEADERS = {"User-Agent": "Mozilla/5.0"}


# 요청 간격(초): 프로세스마다 요청 직전에 이만큼 쉰다. 환경변수 FNGUIDE_DELAY 로 바꿀 수 있다.
FNGUIDE_DELAY = float(os.environ.get("FNGUIDE_DELAY", "1.0"))
_FNGUIDE_RETRY_STATUS = (403, 429, 500, 502, 503, 504)


def fnguide_get(url, **kwargs):
    """FnGuide 요청 공통 함수: 요청 전 FNGUIDE_DELAY 초 쉬고, 연결 오류·차단(429 등)이면 간격을 늘려 3번까지 다시 시도."""
    headers = {**_FNGUIDE_HEADERS, **kwargs.pop("headers", {})}
    for attempt in range(3):
        time.sleep(FNGUIDE_DELAY)
        try:
            response = requests.get(url, headers=headers, timeout=30, **kwargs)
        except requests.RequestException:
            if attempt == 2:
                raise
            time.sleep(20 * (attempt + 1))
            continue
        if response.status_code in _FNGUIDE_RETRY_STATUS and attempt < 2:
            time.sleep(30 * (attempt + 1))
            continue
        return response


def fnguide_cache_path(code, cache_prefix):
    """이번 달 캐시 파일 경로: derived/{cache_prefix}{YYYY-MM}/{code}.html"""
    now = datetime.datetime.now()
    return 'derived/{0}{1}-{2:02d}/{3}.html'.format(cache_prefix, now.year, now.month, code)


def fetch_fnguide_page(code, asp_page, menu_id, cache_prefix):
    """FnGuide 페이지를 다운로드하고 캐싱하는 공통 함수

    Parameters:
        code         : 종목코드 (6자리 문자열)
        asp_page     : FnGuide ASP 페이지명 (예: 'SVD_Finance.asp') — 새 주소는 FNGUIDE_NEW_PATHS 로 바꿔 쓴다
        menu_id      : 쓰지 않는다 (개편 전 주소의 NewMenuID. 호출부 호환용으로만 남김)
        cache_prefix : 캐시 디렉토리 접두어 (예: 'fnguide_finance_')

    Returns:
        str : HTML 문자열
    """
    # 2026년 사이트 개편: comp.fnguide.com/SVO2/ASP/*.asp 는 없어지고(404) wcomp.fnguide.com/CompanyInfo/* 로 바뀌었다.
    new_path = FNGUIDE_NEW_PATHS.get(asp_page)
    if not new_path:
        raise ValueError(f"알 수 없는 FnGuide 페이지: {asp_page}")
    url = f"{FNGUIDE_HOST}/CompanyInfo/{new_path}?c_id=AA&menu_type=01&cmp_cd={code}"

    downloadedFilePath = fnguide_cache_path(code, cache_prefix)
    os.makedirs(os.path.dirname(downloadedFilePath), exist_ok=True)

    # 지난달 캐시는 지우지 않고 월별 폴더로 보관한다 (2026-11 변경).
    # 컨센서스·PER 등은 그 시점에 저장하지 않으면 다시 구할 수 없어서, 월별 스냅샷이 곧 시점별 이력이 된다.

    if os.path.exists(downloadedFilePath):
        return open(downloadedFilePath, "r", encoding="utf-8").read()

    response = fnguide_get(url)
    response.encoding = 'utf-8'
    if "/Error/" in response.url:      # 없는 주소·없는 종목은 오류 페이지로 넘어간다 — 캐시에 남기지 않는다
        raise RuntimeError(f"FnGuide 페이지 없음: {asp_page} {code}")
    if response.status_code != 200:    # 차단·서버 오류 응답도 캐시에 남기지 않는다
        raise RuntimeError(f"FnGuide 응답 오류 {response.status_code}: {asp_page} {code}")
    with open(downloadedFilePath, "w", encoding="utf-8") as f:
        f.write(response.text)
    return response.text


def fetch_fnguide_json(endpoint, **params):
    """개편 후 사이트의 JSON 주소(/CompanyInfo/get*)를 불러 dataset 을 돌려준다. 실패하면 None.

    예: fetch_fnguide_json('getFinIncome', cmp_cd='005930', freq_typ='Q', consol_typ='C')
    """
    try:
        r = fnguide_get(f"{FNGUIDE_HOST}/CompanyInfo/{endpoint}", params=params,
                        headers={"X-Requested-With": "XMLHttpRequest"})
        if "/Error/" in r.url or r.status_code != 200:
            return None
        return json.loads(r.content.decode('utf-8-sig')).get('dataset')
    except (requests.RequestException, ValueError, AttributeError):
        return None


def parse_fnguide_inline(html, name):
    """개편 후 페이지의 스크립트에 인라인된 데이터 `name: {...}` (또는 [...]) 를 꺼낸다. 없으면 None.

    새 페이지의 표는 빈 틀이고 값은 `xxx.init({ cmp_cd: ..., finIncome: {"header": [...], "data": [...]}, ... })`
    형태로 들어 있다. header 는 {YYMM, CD(VAL1…)} 목록, data 의 각 행은 NAME(또는 NM)과 VAL1… 이다.
    """
    m = re.search(r'\b' + re.escape(name) + r'\s*:\s*(?=[\{\[])', html)
    if not m:
        return None
    try:
        obj, _ = json.JSONDecoder().raw_decode(html, m.end())
    except ValueError:
        return None
    return obj


def append_fnguide_extra(html, cache_path, extras):
    """추가로 받은 JSON(예: 분기 손익)을 캐시 HTML 끝에 붙여 저장한다 → parse_fnguide_inline 으로 다시 읽힌다.

    extras: {이름: dataset}. 값이 None 인 항목은 건너뛴다.
    """
    extras = {k: v for k, v in extras.items() if v is not None}
    if not extras:
        return html
    body = ',\n'.join(f'{k} : {json.dumps(v, ensure_ascii=False)}' for k, v in extras.items())
    html += f'\n<script type="application/json" class="nfav-extra">\n{body}\n</script>\n'
    with open(cache_path, "w", encoding="utf-8") as f:
        f.write(html)
    return html


def fnguide_consol_typ(html):
    """개편 후 페이지에서 선택된 재무제표 기준: 'C'(연결) 또는 'P'(별도). 못 찾으면 'C'."""
    m = re.search(r'id="consTyp">(.*?)</div>', html, re.S)
    if m:
        ac = re.search(r'class="[^"]*\bac\b[^"]*"\s+value="(\w)"', m.group(1))
        if ac:
            return ac.group(1)
    m = re.search(r"consol_typ\s*:\s*'(\w)'", html)
    return m.group(1) if m else 'C'


def fnguide_num(v):
    """'1,234.5' → 1234.5. None·''·'N/A'·'-' 는 None."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).replace(',', '').strip())
    except ValueError:
        return None


# ── FnGuide HTML 공통 파싱 헬퍼 ────────────────────────────────────────────────
# 모든 FnGuide 페이지(Snapshot/Finance/FinanceRatio/InvestIdx)가 공유하는
# 공통 헤더 파싱 로직. 각 모듈에 중복 선언하지 않고 여기서 import하여 사용한다.

def parse_company_name(soup) -> str:
    """페이지 title 태그에서 종목명 추출

    FnGuide 페이지 title 형식: '삼성전자(A005930) ...' (개편 후 '삼성전자(005930) | Snapshot ...') → '삼성전자'
    """
    title = soup.find('title')
    if title:
        match = re.match(r'^([^(]+)\(A?\w{6}\)', title.get_text(strip=True))
        if match:
            return match.group(1).strip()
    return ''


def parse_kse_fics(soup) -> tuple:
    """마켓분야·WI26 업종 분류 및 결산월 추출 → (kse_sector, wi26_sector, fiscal_month)

    - 마켓분야('코스피 전기·전자')·WI26('WI26 반도체') : p.stxt_group 내 span.stxt
      (2026년 개편 후 FnGuide 는 FICS 대신 WI26 분류만 보여 준다. FICS 는 더 이상 읽지 않는다.)
    - 결산월    : div.corp_group1 > h2 에서 "12월 결산" 형식 (없으면 None)
    """
    kse_sector = ''
    fics_sector = ''
    fiscal_month = None

    corp_group1 = soup.find('div', class_='corp_group1')
    if corp_group1:
        for h2 in corp_group1.find_all('h2'):
            m = re.search(r'(\d+)월\s*결산', h2.get_text(strip=True))
            if m:
                fiscal_month = int(m.group(1))
                break

    stxt_group = soup.find('p', class_='stxt_group')
    if not stxt_group:
        return kse_sector, fics_sector, fiscal_month

    for span in stxt_group.find_all('span', class_='stxt'):
        text = span.get_text(strip=True).replace('\xa0', ' ')
        if text.startswith('WI26'):
            fics_sector = re.sub(r'^WI26\s+', '', text).strip()
        elif text.startswith(('코스피 ', '코스닥 ', '코넥스 ')):   # 시장 업종: '코스피 전기·전자'
            kse_sector = text

    return kse_sector, fics_sector, fiscal_month



# ── 환경변수 (.env) ─────────────────────────────────────────

_ENV_LOADED = False


def load_env(path=None):
    """프로젝트 루트의 .env 파일을 읽어 os.environ에 넣는다 (python-dotenv 없이 동작).

    - 이미 환경변수로 설정된 값은 덮어쓰지 않는다.
    - '#'으로 시작하는 줄과 빈 줄은 무시한다.
    """
    global _ENV_LOADED
    if _ENV_LOADED and path is None:
        return
    path = path or os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
    if os.path.exists(path):
        with open(path, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                k, v = line.split('=', 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"\''))
    _ENV_LOADED = True


def get_env(name, default=None):
    """.env를 로드한 뒤 환경변수 값을 반환한다. 비어 있으면 default."""
    load_env()
    v = os.environ.get(name, '')
    return v if v else default
