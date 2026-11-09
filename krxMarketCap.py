"""
KRX Open API로 전 종목 일별 시세·시가총액을 수집한다 (1층 원천 데이터, 시가총액 기본 소스).

서비스 (인증: 헤더 AUTH_KEY = .env 의 KRX_API_KEY):
  sto/stk_bydd_trd : 유가증권 일별매매정보
  sto/ksq_bydd_trd : 코스닥 일별매매정보
  → 한 번 호출에 시장 전 종목. 시가총액(MKTCAP, 원)·상장주식수·종가 포함

- 당일 데이터는 다음 영업일에 제공되므로, 기준일부터 하루씩 거슬러 올라가 데이터가 있는 가장 최근 거래일을 쓴다.
- 응답은 derived/krx_cache/{서비스}_{YYYYMMDD}.json 에 저장한다 (과거 시세는 바뀌지 않음).

Public API:
  latest_trading_day(base=None)   : 데이터가 있는 가장 최근 거래일 'YYYYMMDD'
  collectMarketCapAll(date=None)  : 전 종목 DataFrame (종목코드, 시가총액_억원, 종가, 상장주식수, 기준일, 시장, 출처)
"""
import datetime as dt
import json
import os

import pandas as pd
import requests

from fin_utils import get_env

BASE = 'https://data-dbg.krx.co.kr/svc/apis'
SERVICES = {'KOSPI': 'sto/stk_bydd_trd', 'KOSDAQ': 'sto/ksq_bydd_trd'}
CACHE_DIR = os.path.join('derived', 'krx_cache')


def _fetch(svc, day):
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, f"{svc.replace('/', '_')}_{day}.json")
    if os.path.exists(path):
        return json.load(open(path, encoding='utf-8'))
    key = get_env('KRX_API_KEY')
    if not key:
        raise RuntimeError('.env 에 KRX_API_KEY 가 없습니다.')
    r = requests.get(f'{BASE}/{svc}', headers={'AUTH_KEY': key}, params={'basDd': day}, timeout=30)
    r.raise_for_status()
    rows = r.json().get('OutBlock_1', [])
    if rows:  # 빈 응답(아직 미제공·휴장일)은 캐시하지 않는다
        json.dump(rows, open(path, 'w', encoding='utf-8'), ensure_ascii=False)
    return rows


def latest_trading_day(base=None, max_back=10):
    d = base or dt.date.today()
    for _ in range(max_back):
        day = d.strftime('%Y%m%d')
        if d.weekday() < 5 and _fetch(SERVICES['KOSPI'], day):
            return day
        d -= dt.timedelta(days=1)
    raise RuntimeError(f'최근 {max_back}일 안에 KRX 일별매매정보가 없습니다.')


def _num(v):
    try:
        return float(str(v).replace(',', ''))
    except (TypeError, ValueError):
        return None


def collectMarketCapAll(date=None):
    day = date or latest_trading_day()
    out = []
    for mkt, svc in SERVICES.items():
        for r in _fetch(svc, day):
            cap = _num(r.get('MKTCAP'))
            out.append({'종목코드': str(r.get('ISU_CD', '')).zfill(6), 'KRX_종목명': r.get('ISU_NM'),
                        '시장': mkt, '시가총액_억원': round(cap / 1e8, 1) if cap else None,
                        '종가': _num(r.get('TDD_CLSPRC')), '상장주식수': _num(r.get('LIST_SHRS')),
                        '기준일': f'{day[:4]}-{day[4:6]}-{day[6:]}', '출처': 'KRX'})
    return pd.DataFrame(out)
