"""
DART 재무제표로 재무비율·주당 지표를 직접 계산한다 (2층 파생 지표 — FnGuide ratio·snapshot 대체, 4단계)

원천
  - 사업보고서 재무제표: dartIncome 이 받아 둔 fnlttSinglAcntAll 캐시 + 한 해 전 사업보고서
  - 주식수: DART 주식의 총수 현황(stockTotqySttus) — 종목·연도마다 1회 호출, derived/dart_cache 에 캐시
  - 감가상각비: 사업보고서 XBRL 원본(fnlttXbrl) — 현금흐름표에 없는 종목만, 종목마다 1회 호출
  - 주가: KRX 일별매매정보 (결산월 마지막 거래일 종가, 최근 거래일 종가) — derived/krx_cache
사업보고서 1건에 당기·전기·전전기 값이 있으므로, 최신 보고서의 값을 먼저 쓴다(재작성 반영).
최근 4개 회계연도를 내기 위해 한 해 전 사업보고서 1건을 더 받는다(종목마다 1회 호출, 캐시).

계산 지표와 정의 (FnGuide 이용안내 기준, 컬럼 이름도 FnGuide ratio·snapshot 파일과 같다):
  {Y}(누적)_부채비율      부채총계 ÷ 자본총계 × 100
  {Y}(누적)_유동비율      유동자산 ÷ 유동부채 × 100
  {Y}(누적)_영업이익률    영업이익 ÷ 매출액 × 100          (영업이익은 회사 공시 값)
  {Y}(누적)_ROA          당기순이익 ÷ (전년 + 당기) 자산총계 평균 × 100
  {Y}(누적)_ROE          지배주주 순이익 ÷ (전년 + 당기) 지배주주지분 평균 × 100
  {Y}(누적)_총자산회전율  매출액 ÷ (전년 + 당기) 자산총계 평균
  {Y}(누적)_매출증가율    전년 대비 %
  {Y}_EPS(원)            지배주주 순이익 ÷ 기말 발행주식총수 (보통주 + 우선주, 자기주식 포함)
  {Y}_BPS(원)            지배주주지분 ÷ (기말 발행주식총수 − 자기주식수)
  {Y}_PER(배)            결산월 마지막 거래일 종가 ÷ EPS   (EPS가 0 이하면 비움)
  {Y}_PBR(배)            결산월 마지막 거래일 종가 ÷ BPS
  {Y}(누적)_ROIC         영업이익 × (1 − 실효세율) ÷ (전년 + 당기) 영업 투하자본 평균 × 100
                         투하자본 = 매출채권 + 재고자산 − 매입채무 + 유형·무형·사용권자산, 실효세율 = 법인세 ÷ 세전이익(0~50%)
  {Y}_EV/EBITDA          EV ÷ (영업이익 + 감가상각비). EV = 결산월 말 종가 × 발행주식총수 + 이자부부채 + 비지배지분 − 현금및현금성자산
                         감가상각비는 현금흐름표 본문 값을 먼저 쓰고, 없으면 사업보고서 XBRL 원본에서 읽는다(dartXbrl).
                         둘 다 없는 회사(주석에 태그를 달지 않은 소형사)는 비어 있다 — '감가상각비_출처' 열 참고
  {Y}_EV/EBIT            EV ÷ 영업이익 (감가상각비가 없어도 계산된다 — Greenblatt 원래 정의)
  {Y}(누적)_EPS증가율     위 EPS의 전년 대비 % (전년 EPS가 0 이하이거나 당기 EPS가 음수면 비움)
  {Y}_기본EPS(원)         손익계산서의 기본주당이익 (참고용, 공시 통화 그대로)
  {Y}_발행주식수, {Y}_자기주식수, {Y}_지배주주순이익(억원), {Y}_지배주주지분(억원)   계산에 쓴 원자료
  발행주식수(천주)        가장 최근 사업보고서의 발행주식총수
  현재가, 현재가_기준일, 현재가_PER(배), 현재가_PBR(배), 현재가_EV/EBITDA, 현재가_EV/EBIT   최근 거래일 종가 기준, 가장 최근 연간 값

비율은 공시 통화 그대로 계산한다(통화와 무관). 외화 공시 기업의 EPS·BPS는 원화로 환산한다
(순이익은 회계연도 평균환율, 지분은 기말환율 — dartIncome 과 같은 기준).
EPS·BPS는 결산 후의 액면분할·병합·무상증자를 반영해 현재 주식 기준으로 조정한다(_split_factor, 비고에 기록).
PER·PBR은 조정 전 값과 당시 종가로 계산한다. FnGuide EPS는 가중평균 주식수, BPS는 자기주식 장부가를 더한
지분 ÷ 발행주식총수라서 유상증자·자기주식이 있는 종목은 값이 조금 다르다(검증: scripts/compare_dart_ratio.py).
ROIC·EV는 제조업(일반 기업) 시트 종목만 계산한다. FnGuide의 투하자본은 계정별 분류가 공개돼 있지 않아
값은 다르고 순위는 비슷하다(순위상관 약 0.93).
아직 없는 것: 분기·부분누적 비율, 팩터 점수.

사용:
  python apiCollect.py dart_ratio            → derived/dart_ratio_YYYY_MM.xlsx
  python apiCollect.py dart_ratio refresh    (계산 규칙을 바꾼 뒤 다시 집계)
"""
import calendar
import datetime as dt
import json
import os
import re
import threading
import time

import requests

import dartIncome as D
import dartXbrl
import ecosFx
import krxMarketCap as K
from dartFinance import API, CACHE_DIR, _key, fetch_statement, get_corp_map, parseBalance

SHARE_YEARS = 4               # 주식수를 받는 최근 회계연도 수 (EPS 4개년 — PEG의 3년 성장률, EPS증가율 3개년)
_LOCK = threading.Lock()
_PRICE = {}                   # {(연, 월) 또는 'now': (거래일, {종목코드: 종가})}

_BS = [
    ('자산총계', ['ifrs-full_Assets'], ['자산총계']),
    ('유동자산', ['ifrs-full_CurrentAssets'], ['유동자산']),
    ('유동부채', ['ifrs-full_CurrentLiabilities'], ['유동부채']),
    ('부채총계', ['ifrs-full_Liabilities'], ['부채총계']),
    ('자본총계', ['ifrs-full_Equity'], ['자본총계']),
    ('지배지분', ['ifrs-full_EquityAttributableToOwnersOfParent'],
     ['지배기업의소유주에게귀속되는자본', '지배기업소유주지분', '지배기업의소유주지분', '지배기업소유주에게귀속되는자본']),
]
_BS += [   # 영업 투하자본(ROIC)용
    ('매출채권', ['ifrs-full_TradeAndOtherCurrentReceivables', 'dart_ShortTermTradeReceivable'], ['매출채권및기타채권', '매출채권']),
    ('재고자산', ['ifrs-full_Inventories'], ['재고자산']),
    ('매입채무', ['ifrs-full_TradeAndOtherCurrentPayables', 'dart_ShortTermTradePayables'], ['매입채무및기타채무', '매입채무']),
    ('유형자산', ['ifrs-full_PropertyPlantAndEquipment'], ['유형자산']),
    ('무형자산', ['ifrs-full_IntangibleAssetsOtherThanGoodwill', 'ifrs-full_IntangibleAssetsAndGoodwill'], ['무형자산']),
    ('사용권자산', ['ifrs-full_RightofuseAssets'], ['사용권자산']),
]
# 현금흐름표의 감가상각비·무형자산상각비 (조정 내역을 본문에 적은 회사만 있다 — 전체의 약 20%)
_DA_ID = {'ifrs-full_AdjustmentsForDepreciationExpense', 'ifrs-full_AdjustmentsForAmortisationExpense',
          'dart_AdjustmentsForDepreciationRightofuseAssets', 'dart_AdjustmentsForDepreciationInvestmentProperty',
          'ifrs-full_DepreciationRightofuseAssets', 'ifrs-full_AdjustmentsForDepreciationAndAmortisationExpense',
          'ifrs-full_AmortisationExpense', 'ifrs-full_DepreciationExpense', 'ifrs-full_DepreciationPropertyPlantAndEquipment'}
_DA_NM = re.compile(r'감가상각|무형자산상각|사용권자산상각|투자부동산상각|상각비')
_DA_EX = re.compile(r'상각후원가|대손|현재가치|할인|할증|사채|차금|채권|금융|이자|충당')
_IS = [(m, ids, names) for m, ids, names in D._IS_ACCOUNTS if m in ('매출액', '영업이익', '당기순이익')] + [
    ('세전이익', ['ifrs-full_ProfitLossBeforeTax'], ['법인세비용차감전순이익', '법인세비용차감전순이익(손실)', '법인세차감전순이익']),
    ('법인세', ['ifrs-full_IncomeTaxExpenseContinuingOperations'], ['법인세비용', '법인세비용(수익)']),
    ('지배순이익', ['ifrs-full_ProfitLossAttributableToOwnersOfParent'],
     ['지배기업의소유주에게귀속되는당기순이익', '지배기업소유주지분순이익', '지배기업의소유주', '지배기업소유주지분']),
]
_EPS = (['ifrs-full_BasicEarningsLossPerShare'], ['기본주당이익', '기본주당순이익', '기본주당순손익', '기본주당손익'])
_PERIODS = (('thstrm_amount', 0), ('frmtrm_amount', 1), ('bfefrmtrm_amount', 2))


def _num(v):
    if v in (None, '', '-'):
        return None
    try:
        return float(str(v).replace(',', ''))
    except ValueError:
        return None


def _div(a, b, k=1.0):
    return a / b * k if a is not None and b not in (None, 0) else None


def _avg(a, b):
    return (a + b) / 2 if a is not None and b is not None else None


def annual_values(reports):
    """사업보고서들 → {회계연도 종료 연도: {계정: 값(공시 통화, 원 단위)}}. 최신 보고서의 값이 먼저 자리를 잡는다."""
    vals = {}
    for (y, q), r in sorted(reports.items(), reverse=True):
        if q != 4:
            continue
        rows = r['rows']
        srt = lambda div: sorted([x for x in rows if x.get('sj_div') == div], key=lambda x: int(x.get('ord') or 0))
        bs, inc = srt('BS'), srt('IS') + srt('CIS')
        picked = [(m, D._pick(bs, ids, names)) for m, ids, names in _BS]
        picked += [(m, D._pick(inc, ids, names)) for m, ids, names in _IS]
        picked.append(('EPS', D._pick(inc, *_EPS)))
        for m, row in picked:
            if row is None:
                continue
            for field, back in _PERIODS:
                v = _num(row.get(field))
                if v is not None:
                    vals.setdefault(y - back, {}).setdefault(m, v)
        cf = srt('CF')
        da_rows = [x for x in cf if x.get('account_id') in _DA_ID
                   or (_DA_NM.search(x.get('account_nm') or '') and not _DA_EX.search(x.get('account_nm') or ''))]
        for field, back in _PERIODS:
            d = vals.setdefault(y - back, {})
            da = [v for v in (_num(x.get(field)) for x in da_rows) if v is not None]
            if da:
                d.setdefault('감가상각비', sum(da))
            if any(_num(x.get(field)) is not None for x in bs):
                # 이자부부채·현금·비지배지분은 재무상태표 수집(dartFinance.parseBalance)과 같은 규칙으로 읽는다
                pb = parseBalance(rows if field == 'thstrm_amount' else [{**x, 'thstrm_amount': x.get(field)} for x in rows])
                for m in ('이자부부채', '현금및현금성자산', '비지배지분'):
                    if pb.get(m) is not None:
                        d.setdefault(m, pb[m] * 1e8)
    return vals


def fetch_shares(corp, year, recheck_nodata_days=None):
    """주식의 총수 현황(사업보고서) 1건. 정상(000)·데이터없음(013)만 캐시한다."""
    path = os.path.join(CACHE_DIR, f'{corp}_{year}_11011_stock.json')
    if os.path.exists(path):
        j = json.load(open(path, encoding='utf-8'))
        stale = (recheck_nodata_days is not None and j.get('status') == '013'
                 and time.time() - os.path.getmtime(path) > recheck_nodata_days * 86400)
        if not stale:
            return j
    r = requests.get(f'{API}/stockTotqySttus.json', timeout=60,
                     params=dict(crtfc_key=_key(), corp_code=corp, bsns_year=str(year), reprt_code='11011'))
    j = r.json()
    if j.get('status') not in ('000', '013'):
        raise RuntimeError(f"DART {j.get('status')} {j.get('message')}")
    json.dump(j, open(path, 'w', encoding='utf-8'), ensure_ascii=False)
    time.sleep(0.2)
    return j


def shares_by_year(corp, fm, years, today):
    """{회계연도 종료 연도: {'총': 발행주식총수(보통+우선), '자사': 자기주식수}}."""
    ask = set(years) if fm == 12 else set(years) | {min(years) - 1}   # 12월 결산이 아니면 사업연도 표기가 어긋날 수 있다
    out = {}
    for y in sorted(ask, reverse=True):
        j = fetch_shares(corp, y, D.RECHECK_NODATA_DAYS if y >= today.year - 1 else None)
        rows = [r for r in j.get('list') or [] if _num(r.get('istc_totqy'))]
        if not rows:
            continue
        tot = [r for r in rows if (r.get('se') or '').replace(' ', '') in ('합계', '계', '총계')]
        use = tot[:1] or [r for r in rows if (r.get('se') or '') != '비고']
        end = (rows[0].get('stlm_dt') or '')[:4]
        key = int(end) if end.isdigit() else y
        out.setdefault(key, {'총': sum(_num(r.get('istc_totqy')) or 0 for r in use),
                             '자사': sum(_num(r.get('tesstk_co')) or 0 for r in use)})
    return out


def _closes(day):
    """{종목코드: (종가, 상장주식수)}"""
    return {str(r.get('ISU_CD', '')).zfill(6): (K._num(r.get('TDD_CLSPRC')), K._num(r.get('LIST_SHRS')))
            for svc in K.SERVICES.values() for r in K._fetch(svc, day)}


def month_end_close(y, m):
    """(연, 월)의 마지막 거래일 {종목코드: (종가, 상장주식수)}."""
    with _LOCK:
        if (y, m) not in _PRICE:
            d = dt.date(y, m, calendar.monthrange(y, m)[1])
            _PRICE[(y, m)] = (None, {})
            for _ in range(10):
                if d.weekday() < 5 and K._fetch(K.SERVICES['KOSPI'], d.strftime('%Y%m%d')):
                    _PRICE[(y, m)] = (d, _closes(d.strftime('%Y%m%d')))
                    break
                d -= dt.timedelta(days=1)
        return _PRICE[(y, m)][1]


def latest_close():
    """(최근 거래일 'YYYY-MM-DD', {종목코드: (종가, 상장주식수)})."""
    with _LOCK:
        if 'now' not in _PRICE:
            day = K.latest_trading_day()
            _PRICE['now'] = (f'{day[:4]}-{day[4:6]}-{day[6:]}', _closes(day))
        return _PRICE['now']


_CLEAN = (2, 3, 4, 5, 10, 20, 1.5, 0.5, 1 / 3, 0.25, 0.2, 0.1, 0.05)


def _split_factor(listed_then, listed_now, sh):
    """결산 후 액면분할·병합·무상증자로 주식수가 바뀐 배수(없으면 1).

    KRX 상장주식수(보통주)의 결산월 말 대비 최근 배수가 딱 떨어지는 값(2배, 1/10 등)이거나
    무상증자 배수(자기주식에는 배정하지 않으므로 1 + k × (1 − 자기주식 비율))와 같을 때만 조정한다.
    유상증자·전환 등 그 밖의 증감은 조정하지 않는다.
    """
    if not listed_then or not listed_now:
        return 1.0
    r = listed_now / listed_then
    for c in _CLEAN:
        if abs(r / c - 1) <= 0.01:
            return float(c)
    if sh['자사'] > 0:
        for k in (1, 2, 0.5):
            rr = 1 + k * (1 - sh['자사'] / sh['총'])
            if abs(r / rr - 1) <= 0.003:
                return rr
    return 1.0


def _invested(v):
    """영업 투하자본 = 매출채권 + 재고자산 − 매입채무 + 유형자산 + 무형자산 + 사용권자산 (유형자산이 없으면 None)."""
    if not v or v.get('유형자산') is None:
        return None
    z = lambda k: v.get(k) or 0
    return z('매출채권') + z('재고자산') - z('매입채무') + z('유형자산') + z('무형자산') + z('사용권자산')


def _fx(cur, y, fm):
    """외화 공시 기업의 (회계연도 평균환율, 기말환율). 원화면 (1, 1)."""
    if cur == 'KRW':
        return 1.0, 1.0
    ey, em = D.period_end(y, 4, fm)
    end = dt.date(ey, em, calendar.monthrange(ey, em)[1])
    sy, sm = D.period_end(y - 1, 4, fm)
    start = dt.date(sy + sm // 12, sm % 12 + 1, 1)
    return ecosFx.avg_rate(cur, start, end), ecosFx.end_rate(cur, end)


def _add_older_annual(corp, fm, reports, fs_main):
    """가장 최근 사업보고서의 한 해 전 사업보고서를 더한다 (당기·전기·전전기 → 4개 연도 값을 얻기 위해).

    dartIncome 은 최근 1~2년 보고서만 받으므로 여기서 1건을 더 받는다(캐시됨). 연결구분이 같은 것만 쓴다.
    """
    ys = [y for (y, q) in reports if q == 4]
    if not ys or max(ys) - 1 in ys or not fs_main:
        return
    j = fetch_statement(corp, max(ys) - 1, D.Q_REPRT[4], fs_main)
    if j.get('status') != '000' or not j.get('list'):
        return
    rows = j['list']
    key = max(ys) - 1
    if fm != 12:                       # 12월 결산이 아니면 접수일로 회계연도 종료 연도를 확인한다
        _, e = D._fy_end_guess(rows, 4, fm)
        key = e or key
    reports.setdefault((key, 4), dict(fs=fs_main, rows=rows))


def collectRatio(code, name=None, industry=None, today=None):
    """종목코드 → 재무비율·주당 지표 dict (DART 고유번호가 없거나 사업보고서가 없으면 None)."""
    corp = get_corp_map().get(code)
    if not corp:
        return None
    today = today or dt.date.today()
    fm = int(D.company_info(corp).get('acc_mt') or 12)
    reports, fs_main, currency = D._fetch_reports(corp, fm, today)
    _add_older_annual(corp, fm, reports, fs_main)
    vals = annual_values(reports)
    if not vals:
        return None
    da_src = ''
    if D.classify_industry(name, industry) == '제조업':
        ymax = max(y for (y, q) in reports if q == 4)
        if vals.get(ymax, {}).get('감가상각비') is not None:
            da_src = '현금흐름표'
        elif not code.startswith('9'):
            # 현금흐름표 본문에 감가상각비가 없으면 최근 사업보고서의 XBRL 원본(주석 포함)에서 읽는다
            rep = reports[(ymax, 4)]
            found = dartXbrl.depreciation(dartXbrl.fetch_da_facts(corp, rep['rows'][0].get('rcept_no')), rep['fs'])
            for back, (v, rule) in found.items():
                vals.setdefault(ymax - back, {}).setdefault('감가상각비', v)
            if 0 in found:
                da_src = f'XBRL(규칙 {found[0][1]})'
    vals = {y: v for y, v in vals.items() if y > max(vals) - SHARE_YEARS}    # 최근 4개 회계연도만 낸다
    cur = ','.join(sorted(currency)) or 'KRW'
    out = {'결산월': fm, '연결구분': fs_main, '업종구분': D.classify_industry(name, industry), '표시통화': cur}
    notes = []
    share_years = sorted(vals)[-SHARE_YEARS:]
    if code.startswith('9'):
        # 외국 기업(주식예탁증서 등): DART 주식수는 원주 기준이라 상장 증권 수와 다르다 → KRX 상장주식수를 쓴다
        shares = {}
        for y in share_years:
            n = month_end_close(*D.period_end(y, 4, fm)).get(code, (None, None))[1]
            if n:
                shares[y] = {'총': n, '자사': 0}
        notes.append('주식수: KRX 상장주식수(외국 기업)')
    else:
        shares = shares_by_year(corp, fm, share_years, today)
    if cur != 'KRW':
        try:
            if len(currency) != 1:
                raise RuntimeError('통화 혼재')
            ecosFx.rates(cur)
        except (RuntimeError, KeyError) as e:
            notes.append(f'주당 지표 계산 안 함(환율 없음: {e})')
            shares = {}
    eps_by_year, last, ev_now = {}, None, None
    non_fin = out['업종구분'] == '제조업'       # ROIC·EV는 금융업에는 계산하지 않는다 (FnGuide도 같다)
    day_now, closes_now = latest_close()
    price_now, listed_now = closes_now.get(code, (None, None))
    for y in sorted(vals):
        c, p = vals[y], vals.get(y - 1, {})
        g = c.get
        ni_ctrl = g('지배순이익', g('당기순이익'))       # 별도재무제표는 지배주주 구분이 없다
        eq_ctrl, eq_ctrl_p = g('지배지분', g('자본총계')), p.get('지배지분', p.get('자본총계'))
        ratios = {
            '(누적)_부채비율': _div(g('부채총계'), g('자본총계'), 100),
            '(누적)_유동비율': _div(g('유동자산'), g('유동부채'), 100),
            '(누적)_영업이익률': _div(g('영업이익'), g('매출액'), 100),
            '(누적)_ROA': _div(g('당기순이익'), _avg(g('자산총계'), p.get('자산총계')), 100),
            '(누적)_ROE': _div(ni_ctrl, _avg(eq_ctrl, eq_ctrl_p), 100),
            '(누적)_총자산회전율': _div(g('매출액'), _avg(g('자산총계'), p.get('자산총계'))),
            '(누적)_매출증가율': (g('매출액') / p['매출액'] - 1) * 100
            if g('매출액') is not None and p.get('매출액') not in (None, 0) else None,
            '_기본EPS(원)': g('EPS'),
        }
        if non_fin:
            ic, ic_p = _invested(c), _invested(p)
            tax_rate = min(max(g('법인세', 0) / g('세전이익'), 0), 0.5) if (g('세전이익') or 0) > 0 else 0.0
            if g('영업이익') is not None and ic is not None and ic_p is not None and (ic + ic_p) > 0:
                ratios['(누적)_ROIC'] = g('영업이익') * (1 - tax_rate) / ((ic + ic_p) / 2) * 100
        sh = shares.get(y)
        if sh and sh['총'] > 0:
            avg_r, end_r = _fx(cur, y, fm)
            price, listed = month_end_close(*D.period_end(y, 4, fm)).get(code, (None, None))
            if listed and not code.startswith('9') and not 0.5 <= sh['총'] / listed <= 3:
                # 공시 주식수가 상장주식수와 자릿수부터 다르면(단위 오기 등) KRX 상장주식수를 쓴다
                notes.append(f"{y} 주식수 공시 오류 의심({sh['총']:,.0f}주) → KRX 상장주식수 사용")
                sh = shares[y] = {'총': listed, '자사': 0}
            f = _split_factor(listed, listed_now, sh)
            if f != 1:
                notes.append(f'{y} 주당 지표를 결산 후 주식수 변화({f:.2f}배: 분할·병합·무상증자 추정)에 맞춰 조정')
            eps0 = _div(ni_ctrl * avg_r if ni_ctrl is not None else None, sh['총'])
            bps0 = _div(eq_ctrl * end_r if eq_ctrl is not None else None, sh['총'] - sh['자사'])
            eps, bps = (eps0 / f if eps0 is not None else None), (bps0 / f if bps0 is not None else None)
            eps_p = eps_by_year.get(y - 1)
            ratios.update({
                '_EPS(원)': eps, '_BPS(원)': bps,
                '_PER(배)': _div(price, eps0) if eps0 is not None and eps0 > 0 else None,
                '_PBR(배)': _div(price, bps0) if bps0 is not None and bps0 > 0 else None,
                '(누적)_EPS증가율': (eps - eps_p) / eps_p * 100
                if eps is not None and eps_p is not None and eps_p > 0 and eps >= 0 else None,
                '_발행주식수': sh['총'], '_자기주식수': sh['자사'],
                '_지배주주순이익(억원)': ni_ctrl * avg_r / 1e8 if ni_ctrl is not None else None,
                '_지배주주지분(억원)': eq_ctrl * end_r / 1e8 if eq_ctrl is not None else None,
            })
            eps_by_year[y] = eps
            ebit = g('영업이익') * avg_r if g('영업이익') is not None else None
            ebitda = ebit + g('감가상각비') * avg_r if ebit is not None and g('감가상각비') is not None else None
            net_debt = ((g('이자부부채') or 0) + (g('비지배지분') or 0) - (g('현금및현금성자산') or 0)) * end_r \
                if non_fin and g('이자부부채') is not None else None
            if net_debt is not None and price:
                ev = price * sh['총'] + net_debt
                ratios.update({
                    '_EV(억원)': ev / 1e8, '_EBITDA(억원)': ebitda / 1e8 if ebitda is not None else None,
                    '_감가상각비(억원)': g('감가상각비') * avg_r / 1e8 if g('감가상각비') is not None else None,
                    '_EV/EBITDA': ev / ebitda if ebitda is not None and ebitda > 0 else None,
                    '_EV/EBIT': ev / ebit if ebit is not None and ebit > 0 else None,
                })
            ev_now = (sh['총'] * f, net_debt, ebit, ebitda)
            if eps is not None or bps is not None:
                last = (y, eps, bps, sh['총'] * f)
        for k, v in ratios.items():
            if v is not None:
                out[f'{y}{k}'] = round(v, 2)
    if last:
        y, eps, bps, tot = last
        day, price = day_now, price_now
        out['발행주식수(천주)'] = round(tot / 1000)
        if price:
            out.update({'현재가': price, '현재가_기준일': day, '현재가_기준연도': y})
            if eps is not None and eps > 0:
                out['현재가_PER(배)'] = round(price / eps, 2)
            if bps is not None and bps > 0:
                out['현재가_PBR(배)'] = round(price / bps, 2)
            n_now, net_debt, ebit, ebitda = ev_now
            if net_debt is not None:
                ev = price * n_now + net_debt
                if ebitda is not None and ebitda > 0:
                    out['현재가_EV/EBITDA'] = round(ev / ebitda, 2)
                if ebit is not None and ebit > 0:
                    out['현재가_EV/EBIT'] = round(ev / ebit, 2)
    elif share_years:
        notes.append('주식수 없음(DART 주식의 총수 현황 미제출)')
    out['감가상각비_출처'] = da_src
    out['비고'] = ' / '.join(notes)
    return out
