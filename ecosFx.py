"""
한국은행 ECOS Open API — 일별 대원화 매매기준율 (통계표 731Y001 '주요국 통화의 대원화환율')

DART에 외화로 공시된 재무제표를 원화로 환산할 때 쓴다 (dartIncome.py).
  평균환율 avg_rate(통화, 시작일, 종료일) : 기간 중 영업일 매매기준율의 단순 평균 (손익계산서)
  기말환율 end_rate(통화, 기준일)         : 기준일(휴일이면 그 직전 영업일)의 매매기준율 (현금흐름표)

인증키는 .env 의 ECOS_API_KEY (https://ecos.bok.or.kr/api/ 에서 발급).
캐시: derived/ecos_cache/fx_{통화}.json — 하루 한 번만 새로 받는다.
"""
import bisect
import datetime as dt
import json
import os
import threading

import requests

from fin_utils import get_env

API = 'https://ecos.bok.or.kr/api/StatisticSearch'
STAT = '731Y001'
CACHE_DIR = os.path.join('derived', 'ecos_cache')
START = '20210101'
# 통화 → (ECOS 항목코드, 고시 단위). 엔·루피아·동은 100단위로 고시된다
ITEMS = {
    'USD': ('0000001', 1), 'JPY': ('0000002', 100), 'EUR': ('0000003', 1), 'GBP': ('0000012', 1),
    'CAD': ('0000013', 1), 'CHF': ('0000014', 1), 'HKD': ('0000015', 1), 'AUD': ('0000017', 1),
    'SGD': ('0000024', 1), 'CNY': ('0000053', 1), 'TWD': ('0000031', 1), 'VND': ('0000035', 100),
    'IDR': ('0000029', 100),
}
_LOCK = threading.Lock()
_MEM = {}      # 통화 → (날짜 리스트 'YYYYMMDD', 환율 리스트 — 통화 1단위당 원)


def _key():
    k = get_env('ECOS_API_KEY', '')
    if not k:
        raise RuntimeError('ECOS_API_KEY 가 .env 에 없습니다')
    return k


def _download(cur, end):
    item, unit = ITEMS[cur]
    rows, start = [], 1
    while True:
        url = f'{API}/{_key()}/json/kr/{start}/{start + 9999}/{STAT}/D/{START}/{end}/{item}'
        try:
            j = requests.get(url, timeout=60).json()
        except requests.RequestException as e:      # 예외 메시지의 URL에 인증키가 들어가지 않게 한다
            raise RuntimeError(f'ECOS 요청 실패: {type(e).__name__}') from None
        if 'StatisticSearch' not in j:
            res = j.get('RESULT', {})
            raise RuntimeError(f"ECOS {res.get('CODE')} {res.get('MESSAGE')}")
        part = j['StatisticSearch']['row']
        rows += [(r['TIME'], float(r['DATA_VALUE']) / unit) for r in part if r.get('DATA_VALUE')]
        if start + len(part) > int(j['StatisticSearch']['list_total_count']) or not part:
            break
        start += len(part)
    return sorted(rows)


def rates(cur):
    """통화의 일별 매매기준율 (날짜 리스트, 환율 리스트). 지원하지 않는 통화면 KeyError."""
    if cur not in ITEMS:
        raise KeyError(f'지원하지 않는 통화: {cur}')
    with _LOCK:
        if cur in _MEM:
            return _MEM[cur]
        today = dt.date.today().strftime('%Y%m%d')
        path = os.path.join(CACHE_DIR, f'fx_{cur}.json')
        data = json.load(open(path, encoding='utf-8')) if os.path.exists(path) else None
        if data is None or data.get('fetched') != today:
            try:
                data = {'fetched': today, 'rows': _download(cur, today)}
                os.makedirs(CACHE_DIR, exist_ok=True)
                json.dump(data, open(path, 'w', encoding='utf-8'))
            except RuntimeError:
                if data is None:        # 받아 둔 캐시가 있으면 그것을 쓴다
                    raise
        _MEM[cur] = ([d for d, _ in data['rows']], [v for _, v in data['rows']])
        return _MEM[cur]


def _s(d):
    return d.strftime('%Y%m%d') if isinstance(d, dt.date) else str(d)


def avg_rate(cur, start, end):
    """start~end(포함) 영업일 매매기준율의 단순 평균. 자료가 없으면 None."""
    days, vals = rates(cur)
    i, j = bisect.bisect_left(days, _s(start)), bisect.bisect_right(days, _s(end))
    return sum(vals[i:j]) / (j - i) if j > i else None


def end_rate(cur, day):
    """day(휴일이면 직전 영업일)의 매매기준율. 자료가 없으면 None."""
    days, vals = rates(cur)
    j = bisect.bisect_right(days, _s(day))
    return vals[j - 1] if j else None


if __name__ == '__main__':
    for c in ('USD', 'CNY', 'JPY', 'GBP'):
        print(c, '2024 평균', round(avg_rate(c, '20240101', '20241231'), 2),
              '2024 기말', round(end_rate(c, '20241231'), 2), '자료 수', len(rates(c)[0]))
