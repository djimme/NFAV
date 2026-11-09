"""
공식 API 기반 전 종목 수집 Entry (1층 원천 데이터) — fngCollect.py와 같은 사용법

지원 모듈:
  dart_balance  - OpenDART 최신 재무상태표 + 당기순이익(누적)  → derived/dart_balance_YYYY_MM.xlsx
  krx_marketcap - KRX Open API 전 종목 시가총액·종가·상장주식수 (기본) → derived/market_cap_YYYY_MM_DD.xlsx
                  (시장별 1회 호출로 전 종목. 파일명의 날짜는 KRX 기준 거래일)
  kb_marketcap  - KB증권 종목기업개요 시가총액·PER·PBR (대체 소스, 종목별 호출) → derived/market_cap_kb_YYYY_MM_DD.xlsx

사용:
  python apiCollect.py dart_balance                  # 전 종목
  python apiCollect.py krx_marketcap
  python apiCollect.py dart_balance test 005930 000020

주의:
  - API 호출 한도 때문에 순차 실행한다(DART 하루 2만 건, KB는 한도 미공개).
  - 응답은 derived/dart_cache, derived/kb_cache 에 저장되어 중단 후 다시 실행하면 이어서 진행된다.
  - 종목 리스트는 corpCode/ 의 가장 최근 corplist_merged_*.xlsx 를 읽는다.
    (krxStocks.getCorpList()는 지난달 파일을 지우고 새로 받으므로 여기서는 호출하지 않는다)
"""
import datetime as dt
import glob
import os
import sys

import pandas as pd

from fin_utils import save_styled_excel

MODULE_CONFIG = {
    'dart_balance': {
        'description': 'OpenDART 재무상태표 (fnlttSinglAcntAll)',
        'output': lambda now: f'derived/dart_balance_{now:%Y_%m}.xlsx',
    },
    'krx_marketcap': {
        'description': 'KRX 일별매매정보 시가총액 (유가증권·코스닥)',
        'output': None,  # KRX 기준 거래일로 파일명을 정한다
        'bulk': True,
    },
    'kb_marketcap': {
        'description': 'KB증권 시가총액 (IVM10050, 대체 소스)',
        'output': lambda now: f'derived/market_cap_kb_{now:%Y_%m_%d}.xlsx',
    },
}


def _get_collect_fn(module):
    if module == 'dart_balance':
        from dartFinance import collectBalance
        return collectBalance
    if module == 'kb_marketcap':
        from kbMarketCap import collectMarketCap
        return collectMarketCap
    raise ValueError(module)


def latest_corp_list():
    files = sorted(glob.glob('corpCode/corplist_merged_[0-9]*.xlsx'))
    files = [f for f in files if 'ETF' not in f]
    if not files:
        raise FileNotFoundError('corpCode/corplist_merged_*.xlsx 가 없습니다. krxStocks.py 로 먼저 만드세요.')
    df = pd.read_excel(files[-1], dtype={'scode': str})
    df['scode'] = df['scode'].str.zfill(6)
    print(f'종목 리스트: {files[-1]} ({len(df)}개)')
    return df


def collect_bulk(module, codes=None):
    """전 종목을 한 번에 주는 소스(KRX). 종목 리스트(corplist)에 있는 종목만 남긴다."""
    from krxMarketCap import collectMarketCapAll
    df = collectMarketCapAll()
    base = latest_corp_list()
    if codes:
        base = base[base['scode'].isin(codes)]
    info = base.rename(columns={'scode': '종목코드', 'sname': '종목명', 'industry': '업종', 'products': '주요제품'})
    df = info[['종목코드', '종목명', '업종', '주요제품']].merge(df, on='종목코드', how='inner')
    print(f"KRX 기준일 {df['기준일'].iloc[0] if len(df) else '-'}: {len(df)} / {len(base)} 종목 매칭")
    return df


def collect(module, codes=None):
    if MODULE_CONFIG[module].get('bulk'):
        return collect_bulk(module, codes)
    fn = _get_collect_fn(module)
    base = latest_corp_list()
    if codes:
        base = base[base['scode'].isin(codes)]
    rows, fail = [], []
    for i, r in enumerate(base.itertuples(index=False), 1):
        try:
            d = fn(r.scode)
        except Exception as e:  # 한 종목 실패가 전체를 멈추지 않게
            d = None
            fail.append((r.scode, str(e)[:80]))
        if d:
            rows.append({'종목코드': r.scode, '종목명': r.sname, '업종': r.industry, '주요제품': r.products, **d})
        if i % 100 == 0:
            print(f'  {i}/{len(base)} (성공 {len(rows)}, 실패 {len(fail)})', flush=True)
    print(f'성공 {len(rows)} / 전체 {len(base)}, 실패 {len(fail)}')
    for c, e in fail[:10]:
        print('   실패', c, e)
    return pd.DataFrame(rows)


if __name__ == '__main__':
    args = sys.argv[1:]
    if not args or args[0] not in MODULE_CONFIG:
        print('사용법: python apiCollect.py <module> [test codes...]')
        print('  module:', ', '.join(MODULE_CONFIG))
        sys.exit(1)
    module = args[0]
    codes = args[2:] if len(args) > 1 and args[1] == 'test' else None
    if len(args) > 1 and args[1] == 'test' and not codes:
        codes = ['005930']
    print(f"모듈: {MODULE_CONFIG[module]['description']}")
    df = collect(module, codes)
    if not df.empty:
        if module == 'krx_marketcap':
            out = f"derived/market_cap_{df['기준일'].iloc[0].replace('-', '_')}.xlsx"
        else:
            out = MODULE_CONFIG[module]['output'](dt.datetime.now())
        if codes:
            out = out.replace('.xlsx', '_test.xlsx')
        save_styled_excel(df, out)
        print('저장:', out)
