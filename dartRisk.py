"""
OpenDART 가치함정 점검 자료 수집 (감사의견 · 최근 1년 CB·BW·유상증자 · 부실 관련 공시)

싸 보이는 종목 가운데 '싼 이유가 있는' 종목을 걸러 내기 위한 자료다. 전략 쪽 필터는
strat_utils.apply_value_trap_filter 가 이 파일의 결과(derived/dart_risk_YYYY_MM.xlsx)를 읽어 적용한다.

수집 항목:
  감사의견   : 최근 사업보고서의 회계감사인·감사의견(당기), 강조사항에 '계속기업' 언급 여부
               API accnutAdtorNmNdAdtOpinion (종목당 1~2회 호출)
  주요사항보고: 최근 LOOKBACK_DAYS 일 안의 전환사채(CB)·신주인수권부사채(BW)·교환사채(EB)·유상증자 결정,
               감자 결정, 부실 관련 공시(회생절차·해산사유·영업정지·부도·채권은행 관리절차 등)
               API list (공시검색, 공시유형 B=주요사항보고) — 종목별이 아니라 달 단위로 전체를 받아 한 번에 색인한다
  발행 금액  : 위에서 걸린 종목만 상세 API(cvbdIsDecsn·bdwtIsDecsn·piicDecsn)로 권면총액·조달금액·증자방식 조회

캐시: derived/dart_cache/
  {corp}_{year}_11011_audit.json   감사의견
  list_B_{YYYYMM}_p{n}.json        공시검색 (그 달이 끝난 뒤 받은 것은 다시 받지 않고, 이번 달은 하루에 한 번 새로 받는다)
  {corp}_{api}_{YYYYMM}.json       발행 결정 상세 (수집한 달 기준, 달마다 한 번)

Public API:
  collectRisk(code, name=None, industry=None) : 종목코드 → dict (DART 고유번호가 없으면 None)
"""
import datetime as dt
import json
import os
import re
import threading
import time

import requests

from dartFinance import API, CACHE_DIR, _key, get_corp_map

LOOKBACK_DAYS = 365          # 주요사항보고서를 거슬러 올라가는 기간
# 보고서명(괄호 안 유형)에 이 낱말이 들어 있으면 해당 항목으로 센다
EVENT_KEYS = {
    'CB': ('전환사채권발행결정',),
    'BW': ('신주인수권부사채권발행결정',),
    'EB': ('교환사채권발행결정',),
    '유상증자': ('유상증자결정', '유무상증자결정'),
    '감자': ('감자결정',),
    '부실': ('회생절차', '해산사유', '영업정지', '부도발생', '파산', '채권은행', '관리절차'),
}
DETAIL_API = {'CB': 'cvbdIsDecsn', 'BW': 'bdwtIsDecsn', '유상증자': 'piicDecsn'}
# 유상증자 자금조달 목적별 금액 필드 (시설·영업양수·운영·채무상환·타법인증권취득·기타)
_PIIC_FUND = ('fdpp_fclt', 'fdpp_bsninh', 'fdpp_op', 'fdpp_dtrp', 'fdpp_ocsa', 'fdpp_etc')

_LOCK = threading.Lock()
_EVENTS = None       # {corp_code: {항목: [(접수일, 보고서명), ...]}}
_WINDOW = None       # (시작일, 종료일) yyyymmdd


def _get(endpoint, **params):
    """DART JSON 호출. 정상(000)·데이터없음(013)만 돌려주고 나머지는 원인을 알린다."""
    r = requests.get(f'{API}/{endpoint}.json', params=dict(crtfc_key=_key(), **params), timeout=60)
    j = r.json()
    if j.get('status') not in ('000', '013'):
        raise RuntimeError(f"DART {j.get('status')} {j.get('message')}")
    time.sleep(0.2)
    return j


def _cached(path, fetch, valid_after=None):
    """캐시가 있으면 읽고 없으면 받아서 저장한다. valid_after(타임스탬프)보다 먼저 받은 캐시는 다시 받는다."""
    if os.path.exists(path) and (valid_after is None or os.path.getmtime(path) > valid_after):
        return json.load(open(path, encoding='utf-8'))
    j = fetch()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    json.dump(j, open(path, 'w', encoding='utf-8'), ensure_ascii=False)
    return j


# ── 주요사항보고서 색인 ─────────────────────────────────────────────────────

def _month_list(year, month, today):
    """한 달 치 주요사항보고서 목록. 그 달이 끝난 뒤에 받은 캐시만 쓴다 (이번 달은 하루에 한 번 새로 받는다)."""
    first = dt.date(year, month, 1)
    next_first = dt.date(year + (month == 12), month % 12 + 1, 1)
    last = min(next_first - dt.timedelta(days=1), today)
    # 지난달: 다음 달 1일 이후에 받은 캐시면 완전하다. 이번 달: 오늘 0시 이후에 받은 캐시만 쓴다
    cutoff = dt.datetime.combine(min(next_first, today), dt.time()).timestamp()
    rows, page, total = [], 1, 1
    while page <= total:
        path = os.path.join(CACHE_DIR, f'list_B_{year}{month:02d}_p{page}.json')
        j = _cached(path, lambda p=page: _get('list', bgn_de=f'{first:%Y%m%d}', end_de=f'{last:%Y%m%d}',
                                              pblntf_ty='B', page_count=100, page_no=p),
                    valid_after=cutoff)
        rows += j.get('list', [])
        total = int(j.get('total_page') or 1)
        page += 1
    return rows


def _classify(report_nm):
    """보고서명 → 항목 목록. 예: '[기재정정]주요사항보고서(전환사채권발행결정)' → ['CB']"""
    return [k for k, words in EVENT_KEYS.items() if any(w in report_nm for w in words)]


def load_events(today=None):
    """최근 LOOKBACK_DAYS 일의 주요사항보고서를 종목(고유번호)별·항목별로 색인한다 (한 번만 만든다)."""
    global _EVENTS, _WINDOW
    with _LOCK:
        if _EVENTS is not None:
            return _EVENTS
        today = today or dt.date.today()
        start = today - dt.timedelta(days=LOOKBACK_DAYS)
        ev, y, m = {}, start.year, start.month
        while (y, m) <= (today.year, today.month):
            for r in _month_list(y, m, today):
                if not (f'{start:%Y%m%d}' <= r.get('rcept_dt', '') <= f'{today:%Y%m%d}'):
                    continue
                for k in _classify(r.get('report_nm', '')):
                    ev.setdefault(r['corp_code'], {}).setdefault(k, []).append((r['rcept_dt'], r['report_nm'].strip()))
            y, m = (y + 1, 1) if m == 12 else (y, m + 1)
        _WINDOW = (f'{start:%Y%m%d}', f'{today:%Y%m%d}')
        _EVENTS = ev
        print(f'주요사항보고서 색인: {_WINDOW[0]}~{_WINDOW[1]}, 해당 공시가 있는 회사 {len(ev)}개')
        return _EVENTS


# ── 감사의견 ───────────────────────────────────────────────────────────────

def _norm(s):
    return re.sub(r'\s+', '', s or '')


def judge_opinion(opinion):
    """감사의견 문구 → '적정' / '비적정' / '확인불가'. ('부적정'에도 '적정'이 들어 있어 순서가 중요하다)"""
    o = _norm(opinion)
    if not o or o in ('-', '해당사항없음'):
        return '확인불가'
    if any(w in o for w in ('한정', '부적정', '거절')):
        return '비적정'
    return '적정' if '적정' in o else '확인불가'


def fetch_audit(corp, today=None):
    """최근 사업보고서의 감사의견 행 목록. 최근 사업연도에 없으면 한 해 전을 본다."""
    today = today or dt.date.today()
    for year in (today.year - 1, today.year - 2):
        path = os.path.join(CACHE_DIR, f'{corp}_{year}_11011_audit.json')
        j = _cached(path, lambda y=year: _get('accnutAdtorNmNdAdtOpinion', corp_code=corp,
                                              bsns_year=str(y), reprt_code='11011'))
        if j.get('status') == '000' and j.get('list'):
            return j['list'], year
    return [], None


def parse_audit(rows, year):
    """감사의견 행 → dict. 당기 행이 여러 개(연결·별도)면 하나라도 비적정이면 비적정으로 본다."""
    cur = [r for r in rows if '당기' in _norm(r.get('bsns_year'))] or rows[:1]
    if not cur:
        return dict(감사의견=None, 감사의견_판정='확인불가', 감사인=None, 계속기업_불확실성=False,
                    강조사항=None, 감사_사업연도=None)
    judges = [judge_opinion(r.get('adt_opinion')) for r in cur]
    worst = '비적정' if '비적정' in judges else ('적정' if '적정' in judges else '확인불가')
    pick = cur[judges.index(worst)]
    emph = ' / '.join(dict.fromkeys(_norm(r.get('emphs_matter')) and r.get('emphs_matter').strip() for r in cur
                                    if _norm(r.get('emphs_matter')) not in ('', '-', '해당사항없음')))
    spc = ' '.join((r.get('adt_reprt_spcmnt_matter') or '') for r in cur)
    return dict(감사의견=(pick.get('adt_opinion') or '').strip() or None, 감사의견_판정=worst,
                감사인=(pick.get('adtor') or '').strip() or None,
                계속기업_불확실성='계속기업' in _norm(emph + spc),
                강조사항=emph[:300] or None, 감사_사업연도=year)


# ── 발행 결정 상세 (걸린 종목만) ────────────────────────────────────────────

def _won(v):
    try:
        return float(str(v).replace(',', '')) / 1e8
    except (TypeError, ValueError):
        return 0.0


def fetch_detail(corp, kind):
    """CB·BW·유상증자 결정 상세 → (금액 합계 억원, 방식 문자열). 같은 결정의 정정은 접수번호가 달라도 한 건으로 온다."""
    bgn, end = _WINDOW
    path = os.path.join(CACHE_DIR, f'{corp}_{DETAIL_API[kind]}_{end[:6]}.json')     # 달 단위로 한 번만 받는다
    j = _cached(path, lambda: _get(DETAIL_API[kind], corp_code=corp, bgn_de=bgn, end_de=end))
    rows = j.get('list', []) if j.get('status') == '000' else []
    if kind == '유상증자':
        amt = sum(sum(_won(r.get(f)) for f in _PIIC_FUND) for r in rows)
        how = ' | '.join(dict.fromkeys((r.get('ic_mthn') or '').strip() for r in rows if r.get('ic_mthn')))
        return amt, how
    return sum(_won(r.get('bd_fta')) for r in rows), ''


# ── 종목 단위 수집 ─────────────────────────────────────────────────────────

def collectRisk(code, name=None, industry=None):
    """종목코드 → 가치함정 점검 dict (DART 고유번호가 없으면 None)."""
    corp = get_corp_map().get(code)
    if not corp:
        return None
    events = load_events().get(corp, {})
    rows, year = fetch_audit(corp)
    d = parse_audit(rows, year)
    for k in EVENT_KEYS:
        items = events.get(k, [])
        originals = [x for x in items if not x[1].startswith('[')]     # 정정·첨부추가 공시는 건수에서 뺀다
        d[f'{k}_건수'] = len(originals) or (1 if items else 0)
        d[f'{k}_최근일'] = max(x[0] for x in items) if items else None
    for k in DETAIL_API:
        amt, how = fetch_detail(corp, k) if events.get(k) else (0.0, '')
        d[f'{k}_금액_억원'] = round(amt, 1) if amt else None
        if k == '유상증자':
            d['유상증자_방식'] = how or None
    d['부실_공시'] = ' | '.join(dict.fromkeys(re.sub(r'^.*\((.*)\)\s*$', r'\1', x[1]) for x in events.get('부실', []))) or None
    d['조회기간'] = f'{_WINDOW[0]}~{_WINDOW[1]}'
    return d
