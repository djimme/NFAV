"""
OpenDART 재무제표 수집 및 파싱 (1층 원천 데이터)

FnGuide 모듈(fnguideFinance.py 등)과 같은 구조: 종목 단위 collect 함수가 dict를 반환하고,
전 종목 수집과 Excel 저장은 dartCollect.py가 맡는다.

수집 데이터 (재무상태표 + 당기순이익, 최신 공시 기준):
  유동자산, 부채총계, 자본총계, 비지배지분
  현금및현금성자산, 유동금융자산, 장기금융자산      → NFAV 금융자산
  유동금융자산_기타, 장기금융자산_기타              → 그중 계정명에 '기타'가 붙은 금액 (대여금 등 성격이 섞일 수 있음)
  이자부부채(차입금·사채·유동성장기부채·리스부채), 그중 리스부채 → NFAV B
  당기순이익(누적) — 해당 보고서의 연초 누적값
  메타: 기준기간, 보고서코드, 사업연도, 연결구분(CFS/OFS), 접수번호, 유동구분여부

API: fnlttSinglAcntAll (단일회사 전체 재무제표). 단위는 억원으로 변환.
캐시: derived/dart_cache/ — 공시 원본은 바뀌지 않으므로 삭제하지 않는다.

Public API:
  get_corp_map()          : {종목코드: DART 고유번호}
  latest_report(corp)     : 최신 공시 보고서(list rows + meta)
  parseBalance(rows)      : 재무상태표 rows → dict
  collectBalance(code)    : 종목코드 → dict (실패 시 None)
"""
import datetime as dt
import io
import json
import os
import time
import zipfile
import xml.etree.ElementTree as ET

import requests

from fin_utils import get_env

CACHE_DIR = os.path.join('derived', 'dart_cache')
API = 'https://opendart.fss.or.kr/api'
REPRT_NAME = {'11013': '1Q', '11012': '2Q', '11014': '3Q', '11011': '4Q'}
DEBT_KEYS = ('차입금', '사채', '유동성장기부채', '리스부채')
_CORP_MAP = None


def _key():
    k = get_env('DART_API_KEY')
    if not k:
        raise RuntimeError('.env 에 DART_API_KEY 가 없습니다.')
    return k


def get_corp_map():
    """종목코드 → DART 고유번호. CORPCODE.xml은 한 달에 한 번 갱신."""
    global _CORP_MAP
    if _CORP_MAP is not None:
        return _CORP_MAP
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, f'CORPCODE_{dt.date.today():%Y%m}.xml')
    if not os.path.exists(path):
        r = requests.get(f'{API}/corpCode.xml', params={'crtfc_key': _key()}, timeout=60)
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            open(path, 'wb').write(z.read('CORPCODE.xml'))
    m = {}
    for el in ET.parse(path).getroot().iter('list'):
        sc = (el.findtext('stock_code') or '').strip()
        if sc:
            m[sc] = el.findtext('corp_code').strip()
    _CORP_MAP = m   # 다 채운 뒤에 공개한다 (동시 호출 시 다른 스레드가 채우는 중인 dict를 보지 않게)
    return _CORP_MAP


def fetch_statement(corp, year, reprt, fs, recheck_nodata_days=None):
    """전체 재무제표 1건. 정상(000)·데이터없음(013)만 캐시한다.

    recheck_nodata_days: 값을 주면, 그 일수보다 오래된 '데이터 없음(013)' 캐시는 다시 조회한다
    (아직 공시되지 않았던 최근 분기 보고서가 나중에 올라오는 경우).
    """
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, f'{corp}_{year}_{reprt}_{fs}.json')
    if os.path.exists(path):
        j = json.load(open(path, encoding='utf-8'))
        stale = (recheck_nodata_days is not None and j.get('status') == '013'
                 and time.time() - os.path.getmtime(path) > recheck_nodata_days * 86400)
        if not stale:
            return j
    r = requests.get(f'{API}/fnlttSinglAcntAll.json', timeout=60,
                     params=dict(crtfc_key=_key(), corp_code=corp, bsns_year=str(year), reprt_code=reprt, fs_div=fs))
    j = r.json()
    if j.get('status') in ('000', '013'):
        json.dump(j, open(path, 'w', encoding='utf-8'), ensure_ascii=False)
    else:
        # 키 오류(010·011)·한도 초과(020)·점검(800) 등은 조용히 넘기지 않고 원인을 알린다
        raise RuntimeError(f"DART {j.get('status')} {j.get('message')}")
    time.sleep(0.2)
    return j


def _candidates(today=None):
    """최신 → 과거 순으로 시도할 (사업연도, 보고서코드). 12월 결산 기준."""
    today = today or dt.date.today()
    y = today.year
    return [(y, '11014'), (y, '11012'), (y, '11013'), (y - 1, '11011'), (y - 1, '11014')]


def latest_report(corp, prefer_fs=('CFS', 'OFS')):
    """가장 최근에 공시된 보고서를 찾는다. 연결 우선, 없으면 별도."""
    for year, reprt in _candidates():
        for fs in prefer_fs:
            j = fetch_statement(corp, year, reprt, fs)
            if j.get('status') == '000' and any(r.get('sj_div') == 'BS' for r in j['list']):
                return j['list'], dict(사업연도=year, 보고서=reprt, 기준기간=f'{year}/{REPRT_NAME[reprt]}',
                                       연결구분=fs, 접수번호=j['list'][0].get('rcept_no', ''))
    return None, None


def _amt(v):
    if v in (None, '', '-'):
        return None
    try:
        return float(str(v).replace(',', '')) / 1e8
    except ValueError:
        return None


def parseBalance(rows):
    """재무상태표를 공시 순서(ord)대로 읽어 구간(유동자산/비유동자산/유동부채/비유동부채)별로 집계한다."""
    bs = sorted([r for r in rows if r.get('sj_div') == 'BS'], key=lambda r: int(r.get('ord') or 0))
    d = dict(유동자산=None, 부채총계=None, 자본총계=None, 비지배지분=0.0, 현금및현금성자산=None,
             유동금융자산=0.0, 장기금융자산=0.0, 유동금융자산_기타=0.0, 장기금융자산_기타=0.0,
             이자부부채=0.0, 리스부채=0.0)
    sec, fin_used, debt_used = None, [], []
    ids = {r.get('account_id') for r in bs}
    for r in bs:
        aid, nm, v = r.get('account_id', ''), r.get('account_nm', '').strip(), _amt(r.get('thstrm_amount'))
        if aid == 'ifrs-full_CurrentAssets':
            d['유동자산'] = v; sec = 'ca'; continue
        if aid == 'ifrs-full_NoncurrentAssets':
            sec = 'nca'; continue
        if aid == 'ifrs-full_CurrentLiabilities':
            sec = 'cl'; continue
        if aid == 'ifrs-full_NoncurrentLiabilities':
            sec = 'ncl'; continue
        if aid in ('ifrs-full_Assets', 'ifrs-full_Equity', 'ifrs-full_EquityAndLiabilities'):
            if aid == 'ifrs-full_Equity':
                d['자본총계'] = v
            sec = None; continue
        if aid == 'ifrs-full_Liabilities':
            d['부채총계'] = v; sec = None; continue
        if aid == 'ifrs-full_NoncontrollingInterests':
            d['비지배지분'] = v or 0.0; continue
        if aid == 'ifrs-full_CashAndCashEquivalents' and d['현금및현금성자산'] is None:
            d['현금및현금성자산'] = v; continue
        if v is None:
            continue
        if sec in ('ca', 'nca') and ('금융' in nm or '단기투자' in nm) and '리스' not in nm and '매출' not in nm:
            d['유동금융자산' if sec == 'ca' else '장기금융자산'] += v
            if '기타' in nm:  # 기타유동금융자산, 기타 비유동 금융자산 등
                d['유동금융자산_기타' if sec == 'ca' else '장기금융자산_기타'] += v
            fin_used.append(f"{'유동' if sec == 'ca' else '비유동'}:{nm}")
        elif sec in ('cl', 'ncl') and any(k in nm for k in DEBT_KEYS) and '금융부채' not in nm:
            d['이자부부채'] += v
            if '리스' in nm:
                d['리스부채'] += v
            debt_used.append(nm)
    d['유동구분'] = 'ifrs-full_CurrentAssets' in ids
    d['금융자산_구성'] = ' | '.join(fin_used)
    d['이자부부채_구성'] = ' | '.join(debt_used)
    ni = [r for r in rows if r.get('sj_div') in ('IS', 'CIS') and r.get('account_id') == 'ifrs-full_ProfitLoss']
    if ni:
        r = ni[0]
        d['당기순이익(누적)'] = _amt(r.get('thstrm_add_amount')) if r.get('thstrm_add_amount') not in (None, '', '-') \
            else _amt(r.get('thstrm_amount'))
    else:
        d['당기순이익(누적)'] = None
    return d


def collectBalance(code):
    """종목코드 → 최신 재무상태표 dict (DART 고유번호가 없거나 공시가 없으면 None)."""
    corp = get_corp_map().get(code)
    if not corp:
        return None
    rows, meta = latest_report(corp)
    if rows is None:
        return None
    return {**meta, **parseBalance(rows)}
