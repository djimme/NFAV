"""
공식 API 기반 전 종목 수집 Entry (1층 원천 데이터) — fngCollect.py와 같은 사용법

지원 모듈:
  dart_balance  - OpenDART 최신 재무상태표 + 당기순이익(누적)  → derived/dart_balance_YYYY_MM.xlsx
  dart_finance  - OpenDART 손익계산서·현금흐름표 (연간·누적·분기, 업종별 시트) → derived/dart_finance_YYYY_MM.xlsx
                  (FnGuide finance 파일과 같은 컬럼 이름. 종목당 보고서 5~7건을 조회한다)
  krx_marketcap - KRX Open API 전 종목 시가총액·종가·상장주식수 (기본) → derived/market_cap_YYYY_MM_DD.xlsx
                  (시장별 1회 호출로 전 종목. 파일명의 날짜는 KRX 기준 거래일)
  kb_marketcap  - KB증권 종목기업개요 시가총액·PER·PBR (대체 소스, 종목별 호출) → derived/market_cap_kb_YYYY_MM_DD.xlsx

사용:
  python apiCollect.py dart_balance                  # 전 종목
  python apiCollect.py krx_marketcap
  python apiCollect.py dart_balance test 005930 000020
  python apiCollect.py dart_balance refresh            # 진행 기록 무시하고 다시 집계 (파싱 규칙을 바꾼 뒤)

주의:
  - API 호출 한도 때문에 순차 실행한다(DART 하루 2만 건, KB는 한도 미공개).
  - 응답은 derived/dart_cache, derived/kb_cache 에, 진행 상황은 derived/_api_tmp/ 에 저장되어
    중단 후 다시 실행하면 이어서 진행된다(실패 종목은 재시도). 실패 원인은 _api_tmp/*_failures.txt 에 남는다.
  - 종목 리스트는 corpCode/ 의 가장 최근 corplist_merged_*.xlsx 를 읽는다.
    (krxStocks.getCorpList()는 지난달 파일을 지우고 새로 받으므로 여기서는 호출하지 않는다)
"""
import datetime as dt
import glob
import os
import sys

import pandas as pd

from fin_utils import save_styled_excel, save_styled_excel_multisheet

REFRESH = False

MODULE_CONFIG = {
    'dart_balance': {
        'description': 'OpenDART 재무상태표 (fnlttSinglAcntAll)',
        'output': lambda now: f'derived/dart_balance_{now:%Y_%m}.xlsx',
        'workers': 3,  # 동시 호출 수 (DART 과다 호출 제한을 고려해 작게 유지)
    },
    'dart_finance': {
        'description': 'OpenDART 손익계산서·현금흐름표 (fnlttSinglAcntAll)',
        'output': lambda now: f'derived/dart_finance_{now:%Y_%m}.xlsx',
        'workers': 3,
        'row_args': True,   # 수집 함수에 종목명·업종도 넘긴다 (업종별 시트 구분)
        'sheets': True,     # 업종별 멀티시트로 저장
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
    if module == 'dart_finance':
        from dartIncome import collectFinance
        return collectFinance
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
    # 중간 저장: 100종목마다 derived/_api_tmp/{module}.pkl 에 저장하고, 다시 실행하면 이어서 진행
    tmp = os.path.join('derived', '_api_tmp', f'{module}{"_test" if codes else ""}.pkl')
    os.makedirs(os.path.dirname(tmp), exist_ok=True)
    fresh = {'rows': {}, 'nodata': [], 'fail': {}}
    state = fresh if (REFRESH or not os.path.exists(tmp)) else pd.read_pickle(tmp)
    if REFRESH:
        print('refresh: 진행 기록을 무시하고 처음부터 다시 만든다 (API 응답 캐시는 그대로 사용)')
    done = set(state['rows']) | set(state['nodata'])
    todo = [r for r in base.itertuples(index=False) if r.scode not in done]
    print(f'이어서 진행: 완료 {len(done)}, 남은 종목 {len(todo)}')
    new_fail = 0
    workers = MODULE_CONFIG[module].get('workers', 1)
    from concurrent.futures import ThreadPoolExecutor

    row_args = MODULE_CONFIG[module].get('row_args')

    def _run(r):
        try:
            return r, (fn(r.scode, r.sname, r.industry) if row_args else fn(r.scode)), None
        except Exception as e:
            return r, None, e

    pool = ThreadPoolExecutor(max_workers=workers)
    for i, (r, d, err) in enumerate(pool.map(_run, todo), 1):
        try:
            if err:
                raise err
            state['fail'].pop(r.scode, None)
            if d:
                state['rows'][r.scode] = {'종목코드': r.scode, '종목명': r.sname, '업종': r.industry,
                                          '주요제품': r.products, **d}
            else:
                state['nodata'].append(r.scode)  # 고유번호 없음·공시 없음
        except Exception as e:  # 한 종목 실패가 전체를 멈추지 않게 (실패 종목은 다음 실행 때 다시 시도)
            state['fail'][r.scode] = str(e)[:120]
            new_fail += 1
            # 처음 20종목이 모두 실패하면 키·네트워크 문제로 보고 중단
            if i == 20 and new_fail == 20:
                pd.to_pickle(state, tmp)
                raise SystemExit(f'처음 20종목이 모두 실패해 중단합니다. 원인: {str(e)[:200]}')
        if i % 100 == 0 or i == len(todo):
            pd.to_pickle(state, tmp)
            print(f"  {i}/{len(todo)} (누적 성공 {len(state['rows'])}, 공시없음 {len(state['nodata'])}, "
                  f"실패 {len(state['fail'])})", flush=True)
    pd.to_pickle(state, tmp)
    print(f"성공 {len(state['rows'])} / 전체 {len(base)}, 공시없음 {len(state['nodata'])}, 실패 {len(state['fail'])}")
    if state['fail']:
        log = os.path.join('derived', '_api_tmp', f'{module}_failures.txt')
        with open(log, 'w', encoding='utf-8') as f:
            for c, e in state['fail'].items():
                f.write(f'{c}\t{e}\n')
        print(f'   실패 목록: {log} (다시 실행하면 실패 종목만 재시도)')
        for c, e in list(state['fail'].items())[:5]:
            print('   실패', c, e)
        # 실패 종목은 다음 실행에서 다시 시도되도록 완료 목록에 넣지 않는다
    # 진행 기록에는 지난 리스트의 종목(상장폐지 등)도 남아 있을 수 있어, 이번 종목 리스트에 있는 것만 내보낸다
    keep = set(base['scode'])
    return pd.DataFrame([v for c, v in state['rows'].items() if c in keep])


if __name__ == '__main__':
    args = sys.argv[1:]
    if not args or args[0] not in MODULE_CONFIG:
        print('사용법: python apiCollect.py <module> [test codes...]')
        print('  module:', ', '.join(MODULE_CONFIG))
        sys.exit(1)
    module = args[0]
    if 'refresh' in args:
        REFRESH = True
        args = [a for a in args if a != 'refresh']
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
        if MODULE_CONFIG[module].get('sheets'):
            from dartIncome import build_finance_sheets
            save_styled_excel_multisheet(build_finance_sheets(df), out)
        else:
            save_styled_excel(df, out)
        print('저장:', out)
