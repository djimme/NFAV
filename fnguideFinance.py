"""
FnGuide Finance 페이지 데이터 수집 및 파싱

2026년 사이트 개편 후 주소: https://wcomp.fnguide.com/CompanyInfo/Finance?c_id=AA&menu_type=01&cmp_cd={종목코드}
표는 빈 틀이고 값은 페이지 안의 스크립트 데이터(finIncome, finCashFlow — 연간)에 들어 있다.
분기 값은 /CompanyInfo/getFinIncome·getFinCashFlow?freq_typ=Q 로 따로 받는다.

수집 데이터:
- 손익계산서 (연간 최근 3년 / 분기 최근 4분기)
  (항목 이름은 FnGuide 사이트 이름 그대로. DART 파일의 세전계속사업이익·순영업수익과 이름이 다르다)
  비금융:    매출액, 매출원가, 매출총이익, 판관비, 영업이익, 법인세비용차감전계속사업이익, 법인세비용, 당기순이익
  은행/증권: 순영업이익, 판관비, 영업이익, 법인세비용차감전계속사업이익, 법인세비용, 당기순이익
  보험:      영업수익, 영업비용, 영업이익, 법인세비용차감전계속사업이익, 법인세비용, 당기순이익
- 현금흐름표 (연간 최근 3년 / 분기 최근 4분기) — 업종 무관 동일 구조
  영업활동현금흐름, 투자활동현금흐름, 재무활동현금흐름, 현금성자산증가

컬럼 형식:
  연간 : {YYYY}(연간)_{지표명}       (예: 2024(연간)_당기순이익)  — 결산월에 끝나는 완전 회계연도만
  누적 : {YYYY/NQ}(누적)_{지표명}    (예: 2025/3Q(누적)_당기순이익) — 연간 표의 최근 부분연도 열
  분기 : {YYYY/NQ}_{지표명}          (예: 2024/4Q_당기순이익)

  FnGuide 연간 표는 '최근 결산 분기 + 직전 회계연도'를 함께 보여주므로(이용안내),
  기간말 월이 결산월과 다른 열은 연간이 아니라 그 시점까지의 누적값이다.

컬럼 순서:
  지표명별로 연간 데이터 컬럼이 먼저 나온 후, 분기 데이터 컬럼이 이어짐

Public API:
  getFnguideFinance(code)    : HTML 가져오기 (캐싱)
  parseFnguideFinance(html)  : 재무제표 데이터 추출 → dict 또는 None
  collectFinance(code)       : HTML 가져오기 + 파싱 통합 수집 → dict 또는 None
"""
import re

from bs4 import BeautifulSoup

from fin_utils import (fetch_fnguide_page, parse_company_name, parse_kse_fics, parse_fnguide_inline,
                       fetch_fnguide_json, append_fnguide_extra, fnguide_cache_path, fnguide_consol_typ,
                       fnguide_num)


# ── 손익계산서 수집 항목 (FnGuide 항목 이름 → 컬럼명)
# 업종별로 존재하는 행만 실제 수집됨 (없는 항목은 자동 스킵)
_SONIK_TARGETS = [
    ('매출액',           '매출액'),
    ('매출원가',         '매출원가'),
    ('매출총이익',       '매출총이익'),
    ('순영업이익',       '순영업이익'),     # 은행/금융지주·증권
    ('영업수익',         '영업수익'),       # 보험
    ('영업비용',         '영업비용'),       # 보험
    ('판매비와관리비',   '판관비'),
    ('영업이익',         '영업이익'),
    ('법인세비용차감전계속사업이익', '법인세비용차감전계속사업이익'),
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


_CACHE_PREFIX = 'fnguide_finance_'


def getFnguideFinance(code):
    """FnGuide Finance HTML 가져오기 (캐싱)

    페이지에는 연간 데이터만 들어 있다. 분기 손익·현금흐름은 JSON 주소로 따로 받아
    같은 캐시 파일 끝에 붙여 둔다(finIncomeQ, finCashFlowQ) — 종목당 요청 3번.
    """
    html = fetch_fnguide_page(code, 'SVD_Finance.asp', '103', _CACHE_PREFIX)
    if parse_fnguide_inline(html, 'finIncome') is not None and 'finIncomeQ :' not in html:
        consol = fnguide_consol_typ(html)
        html = append_fnguide_extra(html, fnguide_cache_path(code, _CACHE_PREFIX), {
            'finIncomeQ': fetch_fnguide_json('getFinIncome', cmp_cd=code, freq_typ='Q', consol_typ=consol),
            'finCashFlowQ': fetch_fnguide_json('getFinCashFlow', cmp_cd=code, freq_typ='Q', consol_typ=consol),
        })
    return html


def parseFnguideFinance(html):
    """
    Finance HTML에서 손익계산서 및 현금흐름표 데이터 추출

    업종에 따라 손익계산서 항목이 자동 선택되며,
    현금흐름표는 모든 업종에서 동일한 구조로 수집된다.

    Args:
        html: FnGuide Finance HTML 문자열

    Returns:
        dict: 종목명, 마켓분야, WI26분야, 결산월, 연결여부, 연도별/분기별 손익/현금흐름 데이터
        None: 손익계산서 데이터(finIncome)가 없는 경우
    """
    soup = BeautifulSoup(html, 'html.parser')

    data = {}
    data['종목명'] = parse_company_name(soup)

    kse_sector, fics_sector, fiscal_month = parse_kse_fics(soup)
    data['마켓분야'] = kse_sector
    data['WI26분야'] = fics_sector
    if fiscal_month is not None:
        data['결산월'] = fiscal_month

    return _parse_json_finance(html, data, fiscal_month)


def collectFinance(code):
    """
    Finance HTML 가져오기 + 파싱 통합 수집

    Args:
        code: 종목코드 (6자리 문자열, 예: '005930')

    Returns:
        dict: 종목명, 마켓분야, WI26분야, 결산월, 연결여부, 연도별/분기별 손익/현금흐름 데이터
        None: 손익계산서 데이터(finIncome)가 없는 경우
    """
    return parseFnguideFinance(getFnguideFinance(code))


# --- Private parse helpers ---

def _parse_json_finance(html, data, fiscal_month):
    """페이지의 finIncome / finCashFlow (+ 분기 finIncomeQ / finCashFlowQ) 에서 값을 꺼낸다.

    연간 header: 최근 3개 회계연도 + '(최근분기)' 누적 + '(전년동기)' + '전년동기대비(%)'
    분기 header: 최근 4개 분기 (+ 손익은 전년동기 열)
    """
    income_y = parse_fnguide_inline(html, 'finIncome')
    if not income_y or not income_y.get('data'):
        return None
    data['연결여부'] = 'IFRS(연결)' if fnguide_consol_typ(html) == 'C' else 'IFRS(별도)'

    def table(name, targets, annual):
        return _process_json(parse_fnguide_inline(html, name), targets, annual, fiscal_month)

    _merge_by_metric(data, table('finIncome', _SONIK_TARGETS, True),
                     table('finIncomeQ', _SONIK_TARGETS, False), _SONIK_TARGETS)
    _merge_by_metric(data, table('finCashFlow', _CASH_TARGETS, True),
                     table('finCashFlowQ', _CASH_TARGETS, False), _CASH_TARGETS)
    return data


def _process_json(dataset, targets, annual, fiscal_month=None):
    """{header, data} 에서 targets 행을 꺼내 {col_name: {key: value}} 로 반환"""
    result = {}
    if not dataset:
        return result
    cds, date_cols = [], []
    for h in dataset.get('header') or []:
        ym = h.get('YYMM') or ''
        if re.match(r'\d{4}/\d{2}', ym) and '전년동기' not in ym:
            date_cols.append((len(cds), ym[:7]))
            cds.append(h['CD'])
    if annual:
        labeled = _annual_columns(date_cols, fiscal_month)
    else:
        labeled = [(i, p, _to_quarter_label(p)) for i, p in date_cols[-4:]]

    rows = [((r.get('NAME') or '').replace('\xa0', '').strip(), r) for r in dataset.get('data') or []]
    for prefix, col_name in targets:
        # 정확히 같은 이름을 먼저 찾는다 ('법인세비용' 이 '법인세비용차감전계속사업이익' 에 걸리지 않게)
        row = next((r for n, r in rows if n == prefix), None)
        if row is None:
            row = next((r for n, r in rows if n.startswith(prefix)), None)
        if row is None:
            continue
        entries = {f'{label}_{col_name}': fnguide_num(row.get(cds[i])) for i, _, label in labeled}
        if entries:
            result[col_name] = entries
    return result


def _to_quarter_label(period):
    """'YYYY/MM' → 'YYYY/NQ' 변환 (예: '2024/12' → '2024/4Q')"""
    year, mm = period.split('/')
    quarter = (int(mm) - 1) // 3 + 1
    return f'{year}/{quarter}Q'


def _annual_columns(date_cols, fiscal_month):
    """연간 표의 날짜 열을 (인덱스, 기간, 라벨)로 분류한다.

    - 결산월에 끝나는 열: 최근 3개 완전 회계연도 → '{YYYY}(연간)'
    - 결산월과 다른 열(최근 부분연도): 가장 최근 1개 → '{YYYY/NQ}(누적)'
    - 결산월을 모르면 기존 방식(최근 3개 열, '{YYYY}(연간)') 유지
    """
    if not fiscal_month:
        return [(i, p, f"{p.split('/')[0]}(연간)") for i, p in date_cols[-3:]]
    full = [(i, p) for i, p in date_cols if int(p.split('/')[1]) == int(fiscal_month)]
    part = [(i, p) for i, p in date_cols if int(p.split('/')[1]) != int(fiscal_month)]
    out = [(i, p, f"{p.split('/')[0]}(연간)") for i, p in full[-3:]]
    if part and (not full or part[-1][0] > full[-1][0]):
        i, p = part[-1]
        out.append((i, p, f'{_to_quarter_label(p)}(누적)'))
    return out


def _merge_by_metric(result, annual_dict, quarterly_dict, targets):
    """모든 지표의 연간 데이터를 먼저 추가한 후, 모든 지표의 분기 데이터를 추가"""
    for _, col_name in targets:
        if col_name in annual_dict:
            result.update(annual_dict[col_name])
    for _, col_name in targets:
        if col_name in quarterly_dict:
            result.update(quarterly_dict[col_name])
