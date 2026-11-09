"""
KB증권 OpenAPI로 종목별 시가총액·밸류에이션 요약을 수집한다 (대체 소스 — 기본은 krxMarketCap.py).

TR: IVM10050 종목기업개요 (POST /api/v1/ivm10050, 종목 1개씩)
반환: 시가총액(억원), 상장주식수, 전일종가, PER, PBR, EPS, BPS, 배당수익률, 외국인보유비중, 결산월

- 운영 서버만 있으므로 호출 간격을 둔다(기본 0.3초). 호출 한도는 공개되지 않았다.
- 토큰은 derived/kb_cache/token.json 에 만료 전까지 재사용한다.
- 종목별 응답은 derived/kb_cache/{YYYY-MM-DD}/{code}.json 에 날짜별로 저장한다(하루 단위 캐시).
- KRX와 같은 컬럼(시가총액_억원)을 내므로 KRX 장애 시 그대로 바꿔 쓸 수 있다. PER·PBR 검증용으로도 쓴다.

Public API:
  collectMarketCap(code) : 종목코드 → dict (실패 시 None)
"""
import datetime as dt
import json
import os
import time

import requests

from fin_utils import get_env

BASE = 'https://developer.kbsec.com:32484'
CACHE_DIR = os.path.join('derived', 'kb_cache')
TOKEN_HEADER = {'ipAddr': '', 'macAddr': ''}
# 조회 TR은 dataHeader.ipAddr 가 비어 있으면 거절된다(processCode 9999). 접속 IP를 모르면 루프백 값을 쓴다.
TR_HEADER = {'ipAddr': get_env('KB_IP_ADDR', '127.0.0.1'), 'macAddr': get_env('KB_MAC_ADDR', '00:00:00:00:00:00')}
_TOKEN = None


def _token():
    global _TOKEN
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, 'token.json')
    now = time.time()
    if _TOKEN and _TOKEN['exp'] > now + 60:
        return _TOKEN['tok']
    if os.path.exists(path):
        t = json.load(open(path, encoding='utf-8'))
        if t.get('exp', 0) > now + 60:
            _TOKEN = t
            return t['tok']
    key, sec = get_env('KB_APP_KEY'), get_env('KB_APP_SECRET')
    if not key or not sec:
        raise RuntimeError('.env 에 KB_APP_KEY / KB_APP_SECRET 이 없습니다.')
    r = requests.post(f'{BASE}/oauth2/token', timeout=15, headers={'Content-Type': 'application/json'},
                      json={'dataHeader': TOKEN_HEADER, 'dataBody': {'appKey': key, 'appSecret': sec,
                                                              'grantType': 'client_credentials'}})
    r.raise_for_status()
    body = r.json().get('dataBody', {})
    tok = body.get('access_token')
    if not tok:
        raise RuntimeError(f'KB 토큰 발급 실패: {r.json()}')
    _TOKEN = {'tok': tok, 'exp': now + int(body.get('expires_in', 3600))}
    json.dump(_TOKEN, open(path, 'w', encoding='utf-8'))
    return tok


def _call(endpoint, data_body):
    r = requests.post(f'{BASE}{endpoint}', timeout=15,
                      headers={'Content-Type': 'application/json', 'appKey': get_env('KB_APP_KEY'),
                               'Authorization': f'bearer {_token()}'},
                      json={'dataHeader': TR_HEADER, 'dataBody': data_body})
    r.raise_for_status()
    return r.json()


def _num(v):
    try:
        return float(str(v).replace(',', ''))
    except (TypeError, ValueError):
        return None


def fetch_overview(code, delay=0.3):
    day = dt.date.today().isoformat()
    path = os.path.join(CACHE_DIR, day, f'{code}.json')
    if os.path.exists(path):
        j = json.load(open(path, encoding='utf-8'))
        if j.get('dataBody'):
            return j
    j = _call('/api/v1/ivm10050', {'is_cd': code})
    if not j.get('dataBody'):  # 오류 응답은 캐시하지 않는다
        raise RuntimeError(f"KB IVM10050 실패({code}): {j.get('dataHeader', {}).get('processMessage')}")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    json.dump(j, open(path, 'w', encoding='utf-8'), ensure_ascii=False)
    time.sleep(delay)
    return j


def collectMarketCap(code):
    j = fetch_overview(code)
    b = j.get('dataBody') or {}
    if isinstance(b, list):
        b = b[0] if b else {}
    shares, price, cap_raw = _num(b.get('lstng_stk_c')), _num(b.get('bdy_cls_prc')), _num(b.get('opn_prc_tl_amt'))
    if not cap_raw and not (shares and price):
        return None
    # 시가총액 단위는 명세에 없어서, 상장주식수 × 전일종가(원)와 비교해 억원으로 맞춘다
    cap_won = shares * price if shares and price else None
    cap_eok = None
    if cap_raw and cap_won:
        for unit in (1, 1e6, 1e8):  # 원 / 백만원 / 억원
            if abs(cap_raw * unit - cap_won) / cap_won < 0.2:
                cap_eok = cap_raw * unit / 1e8
                break
    if cap_eok is None and cap_won:
        cap_eok = cap_won / 1e8
    return {'시가총액_억원': round(cap_eok, 1) if cap_eok else None, '상장주식수': shares, '전일종가': price,
            'PER': _num(b.get('per')), 'PBR': _num(b.get('pbr_p2')), 'EPS': _num(b.get('eps_p2')),
            'BPS': _num(b.get('bps_p2')), '배당수익률': _num(b.get('dvdnd_yld_p2')),
            '외국인보유비중': _num(b.get('fgnr_hld_sgrvt_p2')), '결산월_KB': b.get('clsac_mm'),
            '시총_원값': cap_raw, '기준일': dt.date.today().isoformat(), '출처': 'KB'}
