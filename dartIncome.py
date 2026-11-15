"""
OpenDART 손익계산서·현금흐름표 수집 및 파싱 (1층 원천 데이터)

FnGuide finance 파일(fnguideFinance.py → derived/finance_YYYY_MM.xlsx)과 같은 컬럼 이름으로
DART 전체 재무제표(fnlttSinglAcntAll)에서 손익·현금흐름을 만든다. 호출·캐시·오류 처리는
dartFinance.fetch_statement 를 그대로 쓴다(오류 응답은 예외, derived/dart_cache 캐시).

수집 항목 (억원):
  손익   : 매출액, 매출원가, 매출총이익, 판관비, 영업수익, 영업비용, 순영업수익, 영업이익,
           세전계속사업이익, 법인세비용, 당기순이익
  현금흐름: 영업활동현금흐름, 투자활동현금흐름, 재무활동현금흐름, 현금성자산증가

컬럼 형식 (fnguideFinance.py 와 동일):
  연간 : {YYYY}(연간)_{지표}        회계연도가 끝난 해 기준. 결산월에 끝나는 완전 회계연도
  누적 : {YYYY/NQ}(누적)_{지표}     부분연도(연초~해당 분기) 누적. 반기·3분기와 가장 최근 분기
  분기 : {YYYY/NQ}_{지표}           3개월 값. 달력 분기 기준 (기간말 월로 계산)

값을 고르는 규칙:
  - 연결(CFS) 우선, 없으면 별도(OFS). 가장 최근 보고서에서 정한 구분을 과거 보고서에도 먼저 적용한다.
  - 연간 값은 '다음 해 보고서의 전기 값'이 있으면 그것을 쓴다(재작성 반영, FnGuide와 같은 기준).
    예: 2024(연간) = 2025 사업보고서의 전기, 2023(연간) = 2025 사업보고서의 전전기.
  - 분기·누적 값은 그 분기 보고서의 당기 값(공시 당시 값). 보고서가 없을 때만 다음 해 보고서의 전기 값으로 메운다.
  - 손익 분기 값 = 보고서의 3개월 값, 4분기 = 연간 − 3분기 누적. 현금흐름 분기 값 = 누적 차이.

Public API:
  company_info(corp)        : DART 기업개황 (결산월 acc_mt)
  classify_industry(name, industry) : 시트 구분 (제조업/은행업/증권업/보험업/창투업)
  parse_report(rows, q)     : 보고서 1건 → 당기·전기 누적/3개월 값
  collectFinance(code, name=None, industry=None) : 종목코드 → dict (공시가 없으면 None)
  build_finance_sheets(df)  : 업종별 시트 목록 [(시트명, DataFrame)]
"""
import calendar
import datetime as dt
import json
import os
import re
import time

import requests

import ecosFx
from dartFinance import API, CACHE_DIR, _amt, _key, fetch_statement, get_corp_map

Q_REPRT = {1: '11013', 2: '11012', 3: '11014', 4: '11011'}
WINDOW_START = (2025, 1)      # 이 달 이후에 끝나는 기간을 수집한다
RECHECK_NODATA_DAYS = 7       # 최근 분기의 '데이터 없음' 캐시는 이 기간이 지나면 다시 조회 (나중에 공시될 수 있음)
DEBUG = bool(os.environ.get('DART_FIN_DEBUG'))   # 정의 후보(현금A~E, 판관비2)를 함께 내보낸다 (검증용)

# ── 계정 대응: (지표, 표준계정 ID 후보, 계정명 후보) — ID가 먼저, 없으면 계정명
_IS_ACCOUNTS = [
    ('매출액', ['ifrs-full_Revenue'], ['매출액', '수익(매출액)', '매출', '영업수익']),
    ('매출원가', ['ifrs-full_CostOfSales'], ['매출원가']),
    ('매출총이익', ['ifrs-full_GrossProfit'], ['매출총이익']),
    ('판관비', ['dart_TotalSellingGeneralAdministrativeExpenses',
             'ifrs-full_SellingGeneralAndAdministrativeExpense'], ['판매비와관리비', '판매비와일반관리비']),
    ('영업비용', ['ifrs-full_OperatingExpense'], ['영업비용']),
    ('영업이익', ['dart_OperatingIncomeLoss', 'ifrs-full_ProfitLossFromOperatingActivities'], ['영업이익', '영업손익']),
    ('세전계속사업이익', ['ifrs-full_ProfitLossBeforeTax'],
     ['법인세비용차감전순이익', '법인세비용차감전계속사업이익', '법인세차감전순이익', '법인세비용차감전순손익']),
    ('법인세비용', ['ifrs-full_IncomeTaxExpenseContinuingOperations'], ['법인세비용', '법인세비용(수익)']),
    ('당기순이익', ['ifrs-full_ProfitLoss'], ['당기순이익', '분기순이익', '반기순이익', '당기순손익']),
    # 보험업: 영업수익 = 보험영업수익 + 투자영업수익 (+ 별도 줄로 공시된 기타영업수익)
    ('_보험영업수익', ['dart_OperatingIncomeInsurance'], ['보험영업수익', '보험서비스수익']),
    ('_투자영업수익', ['ifrs-full_InvestmentIncome', 'dart_OperatingIncomeInvestment'],
     ['투자영업수익', '투자서비스수익', '투자수익']),
    ('_기타영업수익', ['dart_OtherOperatingIncome'], []),
]
# 기타영업수익은 손익계산서에 '기타영업손익' 줄이 따로 있을 때만 더한다 (없으면 보험영업수익의 하위 항목)
_OTHER_OP_ID = 'ifrs-full_OtherOperatingIncomeExpense'
_CF_ACCOUNTS = [
    ('영업활동현금흐름', ['ifrs-full_CashFlowsFromUsedInOperatingActivities'], ['영업활동현금흐름', '영업활동으로인한현금흐름']),
    ('투자활동현금흐름', ['ifrs-full_CashFlowsFromUsedInInvestingActivities'], ['투자활동현금흐름', '투자활동으로인한현금흐름']),
    ('재무활동현금흐름', ['ifrs-full_CashFlowsFromUsedInFinancingActivities'], ['재무활동현금흐름', '재무활동으로인한현금흐름']),
    ('_현금증감_환율전', ['ifrs-full_IncreaseDecreaseInCashAndCashEquivalentsBeforeEffectOfExchangeRateChanges'], []),
    ('_현금증감', ['ifrs-full_IncreaseDecreaseInCashAndCashEquivalents'],
     ['현금및현금성자산의증가', '현금및현금성자산의순증가', '현금및현금성자산의증감', '현금및현금성자산의순증감']),
    ('_환율변동효과', ['ifrs-full_EffectOfExchangeRateChangesOnCashAndCashEquivalents'], []),
    ('_기초현금', ['dart_CashAndCashEquivalentsAtBeginningOfPeriodCf'], ['기초현금및현금성자산', '기초의현금및현금성자산']),
    ('_기말현금', ['dart_CashAndCashEquivalentsAtEndOfPeriodCf', 'ifrs-full_CashAndCashEquivalents'],
     ['기말현금및현금성자산', '기말의현금및현금성자산']),
]
_RAW = [m for m, _, _ in _IS_ACCOUNTS + _CF_ACCOUNTS]
_CF_SET = {m for m, _, _ in _CF_ACCOUNTS}
_STOCK = {'_기초현금', '_기말현금'}     # 잔액(누적 흐름이 아님)

# 저장할 지표 순서 (FnGuide finance 파일의 지표 이름)
_COMMON = ['영업이익', '세전계속사업이익', '법인세비용', '당기순이익',
           '영업활동현금흐름', '투자활동현금흐름', '재무활동현금흐름', '현금성자산증가']
SHEET_INDICATORS = {
    '제조업': ['매출액', '매출원가', '매출총이익', '판관비'] + _COMMON,
    '은행업': ['순영업수익', '판관비'] + _COMMON,
    '증권업': ['순영업수익', '판관비'] + _COMMON,
    '보험업': ['영업수익', '영업비용'] + _COMMON,
    '창투업': ['영업수익', '영업비용'] + _COMMON,
}
SHEET_ORDER = ['제조업', '은행업', '증권업', '보험업', '창투업']
META_COLS = ['종목코드', '종목명', '업종', '주요제품', '결산월', '연결구분', '업종구분', '최근보고서', '수집메모']

# FnGuide 업종 시트와 맞추기 위한 예외 (KRX 업종 '기타 금융업'은 지주·은행·증권·창투가 섞여 있다)
_SECURITIES_HOLDING = {'메리츠금융지주', '한국금융지주'}
_VENTURE_KEYS = ('인베스트먼트', '벤처', '창투', '기술투자', 'IB', '린드먼', '컴퍼니케이', '캡스톤', '큐캐피탈')


def classify_industry(name, industry):
    """종목명·KRX 업종으로 시트(제조업/은행업/증권업/보험업/창투업)를 정한다."""
    name, industry = name or '', industry or ''
    if industry in ('보험업', '재 보험업'):
        return '보험업'
    if industry == '은행 및 저축기관':
        return '은행업'
    if name in _SECURITIES_HOLDING or ('증권' in name and industry in ('금융 지원 서비스업', '기타 금융업')):
        return '증권업'
    if industry == '기타 금융업' and ('금융지주' in name or name in ('KB금융', '신한지주')):
        return '은행업'
    if industry in ('기타 금융업', '신탁업 및 집합투자업') and '신탁' not in name \
            and any(k in name for k in _VENTURE_KEYS):
        return '창투업'
    return '제조업'


def company_info(corp):
    """기업개황(company.json). 결산월(acc_mt)을 얻는 데 쓴다. 정상 응답만 캐시."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, f'{corp}_company.json')
    if os.path.exists(path):
        return json.load(open(path, encoding='utf-8'))
    r = requests.get(f'{API}/company.json', params=dict(crtfc_key=_key(), corp_code=corp), timeout=60)
    j = r.json()
    if j.get('status') != '000':
        raise RuntimeError(f"DART {j.get('status')} {j.get('message')}")
    json.dump(j, open(path, 'w', encoding='utf-8'), ensure_ascii=False)
    time.sleep(0.2)
    return j


def period_end(fy_end_year, q, fm):
    """(회계연도가 끝나는 해, 분기 1~4, 결산월) → 그 분기의 기간말 (연, 월)."""
    y, m0 = divmod(fy_end_year * 12 + (fm - 1) - 3 * (4 - q), 12)
    return y, m0 + 1


def _qlabel(ym):
    return f'{ym[0]}/{(ym[1] - 1) // 3 + 1}Q'


def _norm(nm):
    nm = re.sub(r'\s+', '', nm or '')
    nm = re.sub(r'^[\(\[]?[IVXⅠ-Ⅻ0-9]+[\)\].]+', '', nm)      # 'Ⅱ.' 'VI.' '1.' 같은 머리 번호
    return nm.replace('(손실)', '').replace('(수익)', '')


def _pick(rows, ids, names):
    for i in ids:
        for r in rows:
            if r.get('account_id') == i:
                return r
    want = {_norm(n) for n in names}
    for r in rows:
        if _norm(r.get('account_nm')) in want:
            return r
    return None


def _has(v):
    return v not in (None, '', '-')


def parse_report(rows, q):
    """보고서 1건에서 당기 누적(cum)·3개월(q3m), 전기 누적(prev_cum)·3개월(prev_q3m), 전전기(prev2)를 뽑는다."""
    out = dict(cum={}, q3m={}, prev_cum={}, prev_q3m={}, prev2={})
    srt = lambda div: sorted([r for r in rows if r.get('sj_div') == div], key=lambda r: int(r.get('ord') or 0))
    inc = srt('IS') + srt('CIS')      # 손익계산서를 따로 내는 회사는 IS, 단일 포괄손익계산서는 CIS
    has_other_op = any(r.get('account_id') == _OTHER_OP_ID for r in inc)
    for m, ids, names in _IS_ACCOUNTS:
        r = _pick(inc, ids, names) if (m != '_기타영업수익' or has_other_op) else None
        if r is None:
            continue
        if q == 4:
            out['cum'][m] = _amt(r.get('thstrm_amount'))
            out['prev_cum'][m] = _amt(r.get('frmtrm_amount'))
            out['prev2'][m] = _amt(r.get('bfefrmtrm_amount'))
        else:
            out['q3m'][m] = _amt(r.get('thstrm_amount'))
            out['prev_q3m'][m] = _amt(r.get('frmtrm_q_amount'))
            if q == 1:   # 1분기는 3개월 = 누적
                out['cum'][m] = _amt(r.get('thstrm_add_amount')) if _has(r.get('thstrm_add_amount')) else out['q3m'][m]
                out['prev_cum'][m] = _amt(r.get('frmtrm_add_amount')) if _has(r.get('frmtrm_add_amount')) \
                    else out['prev_q3m'][m]
            else:
                out['cum'][m] = _amt(r.get('thstrm_add_amount'))
                out['prev_cum'][m] = _amt(r.get('frmtrm_add_amount'))
    cf = srt('CF')
    for m, ids, names in _CF_ACCOUNTS:   # 현금흐름표는 항상 연초 누적
        r = _pick(cf, ids, names)
        if r is None:
            continue
        out['cum'][m] = _amt(r.get('thstrm_amount'))
        prev = r.get('frmtrm_amount') if q == 4 or not _has(r.get('frmtrm_q_amount')) else r.get('frmtrm_q_amount')
        out['prev_cum'][m] = _amt(prev)
        if q == 4:
            out['prev2'][m] = _amt(r.get('bfefrmtrm_amount'))
    for part in ('cum', 'prev_cum', 'prev2'):    # 기말 − 기초 = 연초 이후 현금 증감(환율효과 포함)
        b, e = out[part].get('_기초현금'), out[part].get('_기말현금')
        out[part]['_기말기초차'] = e - b if b is not None and e is not None else None
    return out


def _fy_end_guess(rows, q, fm):
    """(기수, 접수일로 추정한 회계연도 종료 연도). 보고서는 기간말이 지난 뒤에 접수된다."""
    r0 = rows[0]
    m = re.search(r'제\s*(\d+)\s*기', r0.get('thstrm_nm') or '')
    n = int(m.group(1)) if m else None
    filed = (r0.get('rcept_no') or '')[:8]
    if len(filed) != 8 or not filed.isdigit():
        return n, None
    fy, fmon = int(filed[:4]), int(filed[4:6])
    e = fy + 1
    while period_end(e, q, fm) >= (fy, fmon):      # 접수월보다 앞선 가장 최근 기간말
        e -= 1
    return n, e


def _fetch_reports(corp, fm, today):
    """대상 보고서를 모아 ({(회계연도 종료 연도, 분기): {fs, cum, ...}}, 주 연결구분, 표시통화 집합)을 돌려준다.

    12월 결산은 사업연도 = 종료 연도. 그 외 결산월은 DART 사업연도 표기가 보고서 종류에 따라
    다르므로(3월 결산사: 사업보고서는 종료 연도, 분기보고서는 시작 연도) 기수와 접수일로 기간을 정한다.
    """
    now = today.year * 12 + today.month
    if fm == 12:
        plan = [(y, q) for y in range(WINDOW_START[0], today.year + 1) for q in (1, 2, 3, 4)
                if WINDOW_START <= period_end(y, q, fm) <= (today.year, today.month)]
    else:
        plan = [(y, q) for y in range(WINDOW_START[0] - 1, today.year + 1) for q in (1, 2, 3, 4)]
    found, fs_main, currency = [], None, set()
    for y, q in sorted(plan, reverse=True):       # 최신부터. 처음 찾은 연결구분을 나머지에 먼저 적용
        # 아직 공시 전일 수 있는 최근 보고서만 '데이터 없음' 캐시를 다시 확인한다
        recent = now - (y * 12 + 3 * q) <= 5 if fm == 12 else y >= today.year - 1
        order = ('CFS', 'OFS') if fs_main in (None, 'CFS') else ('OFS', 'CFS')
        for fs in order:
            j = fetch_statement(corp, y, Q_REPRT[q], fs, recheck_nodata_days=RECHECK_NODATA_DAYS if recent else None)
            if j.get('status') == '000' and any(r.get('sj_div') in ('IS', 'CIS', 'CF') for r in j['list']):
                fs_main = fs_main or fs
                currency.add(j['list'][0].get('currency') or 'KRW')
                found.append((y, q, fs, j['list']))
                break
    reports = {}
    if fm == 12:
        for y, q, fs, rows in found:
            reports[(y, q)] = dict(fs=fs, **parse_report(rows, q))
        return reports, fs_main, currency
    guesses = [(_fy_end_guess(rows, q, fm), q, fs, rows) for _, q, fs, rows in found]
    # (종료 연도 − 기수)는 회사마다 일정하다. 정정공시로 접수일이 늦은 보고서가 섞여도 최솟값은 맞다
    bases = [e - n for (n, e), *_ in guesses if n is not None and e is not None]
    base = min(bases) if bases else None
    for (n, e), q, fs, rows in guesses:
        end = base + n if (base is not None and n is not None) else e
        if end is not None and (end, q) not in reports:
            reports[(end, q)] = dict(fs=fs, **parse_report(rows, q))
    return reports, fs_main, currency


def collectFinance(code, name=None, industry=None, today=None):
    """종목코드 → 손익·현금흐름 dict (DART 고유번호가 없거나 공시가 하나도 없으면 None)."""
    corp = get_corp_map().get(code)
    if not corp:
        return None
    today = today or dt.date.today()
    fm = int(company_info(corp).get('acc_mt') or 12)
    reports, fs_main, currency = _fetch_reports(corp, fm, today)
    if not reports:
        return None
    # 아래에서 y는 회계연도가 끝나는 해
    want = sorted(k for k in ((y, q) for y in range(WINDOW_START[0], today.year + 2) for q in (1, 2, 3, 4))
                  if WINDOW_START <= period_end(*k, fm) <= (today.year, today.month))
    notes = []
    sheet = classify_industry(name, industry)
    fx_cur = None               # 외화로 공시한 기업: 원화로 환산할 통화
    if currency - {'KRW'}:
        cur_txt = ','.join(sorted(currency))
        try:
            if len(currency) != 1:
                raise RuntimeError('통화 혼재')
            ecosFx.rates(cur_txt)
            fx_cur = cur_txt
            notes.append(f'표시통화 {cur_txt}(원화 환산: 손익 누적 평균환율, 현금흐름 기말환율)')
        except (RuntimeError, KeyError) as e:
            notes.append(f'표시통화 {cur_txt}(원화 환산 안 함, 단위 1억: {e})')
    if len({r['fs'] for r in reports.values()}) > 1:
        notes.append('연결·별도 혼재(' + ','.join(f'{_qlabel(period_end(y, q, fm))}:{r["fs"]}'
                                              for (y, q), r in sorted(reports.items()) if r['fs'] != fs_main) + ')')

    def own_cum(y, q, m):
        r = reports.get((y, q))
        if r is None:
            return None
        v = r['cum'].get(m)
        if v is None and q in (2, 3) and m not in _CF_SET and r['q3m'].get(m) is not None:
            p = own_cum(y, q - 1, m)       # 누적 칸이 비어 있으면 직전 누적 + 3개월
            if p is not None and reports[(y, q - 1)]['fs'] == r['fs']:
                v = p + r['q3m'][m]
        return v

    def restated_cum(y, q, m):             # 다음 해 같은 분기 보고서의 전기 값
        r = reports.get((y + 1, q))
        return r['prev_cum'].get(m) if r else None

    def cum(y, q, m):
        v = own_cum(y, q, m)
        return v if v is not None else restated_cum(y, q, m)

    def annual(y, m):                      # 재작성 값 우선: 다음 해 보고서 전기 → 당해 보고서
        v = restated_cum(y, 4, m)
        return v if v is not None else own_cum(y, 4, m)

    def quarter(y, q, m):
        r = reports.get((y, q))
        if q == 1:
            return cum(y, 1, m)
        if r is not None and q < 4 and m not in _CF_SET and r['q3m'].get(m) is not None:
            return r['q3m'][m]
        a, b = cum(y, q, m), cum(y, q - 1, m)
        ra, rb = reports.get((y, q)), reports.get((y, q - 1))
        if a is None or b is None or (ra and rb and ra['fs'] != rb['fs']):
            if r is None and q < 4:        # 보고서가 없으면 다음 해 보고서의 전기 3개월 값
                n = reports.get((y + 1, q))
                return n['prev_q3m'].get(m) if n and m not in _CF_SET else None
            return None
        return a - b

    # ── 외화 → 원화 환산 (FnGuide 값에서 역산한 기준. 한국은행 매매기준율)
    #   손익: 회계연도 시작일~기간말의 평균환율. 분기(3개월) 값에도 그 분기까지의 누적 평균환율을 곱한다
    #         4분기 = 연간 환산액 − 1~3분기 환산액
    #   현금흐름: 누적 금액 × 기간말 환율. 분기 = 누적 환산액의 차이
    def _rate(y, q, m):
        ey, em = period_end(y, q, fm)
        end = dt.date(ey, em, calendar.monthrange(ey, em)[1])
        if m in _CF_SET or m == '_기말기초차':
            return ecosFx.end_rate(fx_cur, end)
        sy, sm = period_end(y - 1, 4, fm)
        start = dt.date(sy + sm // 12, sm % 12 + 1, 1)
        return ecosFx.avg_rate(fx_cur, start, end)

    def _won(v, y, q, m):
        r = _rate(y, q, m) if v is not None else None
        return v * r if r is not None else None

    def won_quarter(y, q, m):
        if m in _CF_SET or m == '_기말기초차':
            a = _won(cum(y, q, m), y, q, m)
            if q == 1:
                return a
            b = _won(cum(y, q - 1, m), y, q - 1, m)
            return a - b if None not in (a, b) and quarter(y, q, m) is not None else None
        if q < 4:
            return _won(quarter(y, q, m), y, q, m)
        parts = [_won(annual(y, m), y, 4, m)] + [_won(quarter(y, k, m), y, k, m) for k in (1, 2, 3)]
        return parts[0] - sum(parts[1:]) if None not in parts else _won(quarter(y, 4, m), y, 4, m)

    if fx_cur:      # 출력에 쓰는 값: 환산한 것
        out_annual = lambda y, m: _won(annual(y, m), y, 4, m)
        out_cum = lambda y, q, m: _won(own_cum(y, q, m), y, q, m)
        out_quarter = won_quarter
    else:
        out_annual, out_cum, out_quarter = annual, own_cum, quarter

    def derive(get):
        """원시 계정 → FnGuide 지표 이름. get(m)은 한 기간의 원시 값."""
        d = {m: get(m) for m in _RAW + ['_기말기초차'] if m not in _STOCK}
        # 비용을 음수로 공시하는 회사가 있어 부호를 맞춘다 (비용은 양수)
        for k in ('매출원가', '판관비', '영업비용'):
            if d[k] is not None and d[k] < 0:
                d[k] = -d[k]
        pre, ni, tax = d['세전계속사업이익'], d['당기순이익'], d['법인세비용']
        if None not in (pre, ni, tax) and abs(pre - ni + tax) < abs(pre - ni - tax):
            d['법인세비용'] = -tax          # 세전이익 − 순이익과 부호가 반대면 뒤집는다
        if d['매출총이익'] is None and None not in (d['매출액'], d['매출원가']):
            d['매출총이익'] = d['매출액'] - d['매출원가']
        # 판관비는 FnGuide와 같이 '매출총이익 − 영업이익'(매출총이익 아래 영업비용 전체). 계산할 수 없으면 공시된 판관비
        if None not in (d['매출총이익'], d['영업이익']):
            d['_판관비_공시'], d['판관비'] = d['판관비'], d['매출총이익'] - d['영업이익']
        d['영업수익'] = d['매출액']
        if sheet == '보험업' and None not in (d['_보험영업수익'], d['_투자영업수익']):
            # 보험업(FnGuide 기준): 영업수익 = 보험 + 투자 (+ 기타영업수익), 영업비용 = 영업수익 − 영업이익
            d['영업수익'] = d['_보험영업수익'] + d['_투자영업수익'] + (d['_기타영업수익'] or 0.0)
            d['영업비용'] = None
        if d['영업비용'] is None and d['영업수익'] is not None and d['영업이익'] is not None:
            d['영업비용'] = d['영업수익'] - d['영업이익']
        if d['판관비'] is not None and d['영업이익'] is not None:
            d['순영업수익'] = d['영업이익'] + d['판관비']     # 순영업수익 = 영업이익 + 판관비 (FnGuide 가공 지표의 근사)
        o, i, f, fx = d['영업활동현금흐름'], d['투자활동현금흐름'], d['재무활동현금흐름'], d['_환율변동효과']
        if DEBUG:
            d['현금A'] = None if None in (o, i, f) else o + i + f + (fx or 0.0)
            d['현금B'] = d['_기말기초차']
            d['현금C'] = d['_현금증감']
            d['현금D'] = d['_현금증감_환율전']
            d['현금E'] = None if None in (o, i, f) else o + i + f
            d['판관비2'] = None if None in (d['매출총이익'], d['영업이익']) else d['매출총이익'] - d['영업이익']
        # 현금성자산증가 = 기말 − 기초 (환율변동효과 포함, FnGuide와 같은 기준). 없으면 영업+투자+재무+환율효과, 공시된 증감 순
        inc = d['_기말기초차']
        if inc is None and None not in (o, i, f):
            inc = o + i + f + (fx or 0.0)
        d['현금성자산증가'] = inc if inc is not None else d['_현금증감']
        return {k: (round(v, 2) if v is not None else None) for k, v in d.items() if not k.startswith('_')}

    latest = max(reports, key=lambda k: period_end(*k, fm))
    out = {'결산월': fm, '연결구분': fs_main, '업종구분': sheet,
           '최근보고서': _qlabel(period_end(*latest, fm)), '수집메모': ''}
    cols = {}
    # 연간: 사업보고서가 있는 해 + 그 보고서의 전기·전전기 (최신 보고서의 값이 먼저 자리를 잡는다)
    years = {}
    for (y, q), r in sorted(reports.items(), reverse=True):
        if q == 4:
            years.setdefault(y, lambda m, y=y: out_annual(y, m))
            years.setdefault(y - 1, lambda m, y=y: out_annual(y - 1, m))
            years.setdefault(y - 2, (lambda m, r=r, y=y: _won(r['prev2'].get(m), y - 2, 4, m)) if fx_cur
                             else (lambda m, r=r: r['prev2'].get(m)))
    for y in sorted(years):
        for k, v in derive(years[y]).items():
            cols[f'{y}(연간)_{k}'] = v
    # 누적: 반기·3분기 누적과, 가장 최근 보고서가 분기보고서일 때 그 누적
    for y, q in want:
        if (y, q) in reports and (q in (2, 3) or ((y, q) == latest and q < 4)):
            lab = f'{_qlabel(period_end(y, q, fm))}(누적)'
            for k, v in derive(lambda m: out_cum(y, q, m)).items():
                cols[f'{lab}_{k}'] = v
    # 분기
    for y, q in want:
        if (y, q) not in reports and (y + 1, q) not in reports:
            continue
        lab = _qlabel(period_end(y, q, fm))
        for k, v in derive(lambda m: out_quarter(y, q, m)).items():
            cols[f'{lab}_{k}'] = v
    missing = [_qlabel(period_end(y, q, fm)) for y, q in want
               if (y, q) not in reports and period_end(y, q, fm) < period_end(*latest, fm)]
    if missing:
        notes.append('보고서 없음(' + ','.join(missing) + ')')
    out['수집메모'] = ' | '.join(notes)
    out.update({k: v for k, v in cols.items() if v is not None})
    return out


# ── 시트 구성 ────────────────────────────────────────────

_COL_RE = re.compile(r'^(\d{4})(?:/(\d)Q)?(\((?:연간|누적)\))?_(.+)$')


def _col_key(c):
    """지표 안에서의 열 순서: 연간(오름차순) → 누적 → 분기."""
    y, q, kind, _ = _COL_RE.match(c).groups()
    grp = 0 if kind == '(연간)' else 1 if kind == '(누적)' else 2
    return grp, int(y), int(q or 0)


def build_finance_sheets(df):
    """수집 결과 DataFrame → 업종별 시트 [(시트명, DataFrame)] (fngCollect._build_finance_sheets 와 같은 구성)."""
    sheets = []
    for name in SHEET_ORDER:
        idf = df[df['업종구분'] == name].reset_index(drop=True)
        if idf.empty:
            continue
        cols = [c for c in META_COLS if c in idf.columns]
        for ind in SHEET_INDICATORS[name]:
            matched = [c for c in idf.columns if (m := _COL_RE.match(c)) and m.group(4) == ind and idf[c].notna().any()]
            cols += sorted(matched, key=_col_key)
        sheets.append((name, idf[cols]))
    return sheets
