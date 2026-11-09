"""
FnGuide 캐시 HTML만으로 derived xlsx를 다시 만든다 (네트워크·캐시 삭제 없음).

fngCollect.py를 그대로 돌리면 fetch_fnguide_page가 '지난달 캐시 폴더'를 지우고
새로 내려받으므로, 파서를 고친 뒤 과거 시점 데이터를 재생성할 때는 이 스크립트를 쓴다.

사용:
  python scripts/rebuild_from_cache.py finance 2026-04      # → derived/finance_2026_04_v2.xlsx
  python scripts/rebuild_from_cache.py ratio   2026-04      # → derived/finance_ratio_2026_04_v2.xlsx
  (중간 결과는 derived/_rebuild_tmp/ 에 저장되어, 중단돼도 이어서 실행된다)
"""
import os, sys, pickle, multiprocessing as mp
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); os.chdir(ROOT)

CACHE_PREFIX = {'finance': 'fnguide_finance_', 'ratio': 'fnguide_FinanceRatio_'}
MONTH = None


def _cached_fetch(code, asp_page, menu_id, cache_prefix):
    p = os.path.join('derived', f'{cache_prefix}{MONTH}', f'{code}.html')
    if not os.path.exists(p):
        raise FileNotFoundError(p)
    return open(p, encoding='utf-8').read()


def _init(month):
    global MONTH
    MONTH = month
    import fin_utils, fnguideFinance, fnguideFinanceRatio
    fin_utils.fetch_fnguide_page = _cached_fetch
    fnguideFinance.fetch_fnguide_page = _cached_fetch
    fnguideFinanceRatio.fetch_fnguide_page = _cached_fetch


def _work(args):
    row, module = args
    import fngCollect
    try:
        return fngCollect.process_single_stock((row, module))
    except Exception as e:  # 한 종목 실패가 전체를 멈추지 않게
        return None


def main(module, month):
    import fngCollect, pandas as pd
    tmp = os.path.join('derived', '_rebuild_tmp', f'{module}_{month}')
    os.makedirs(tmp, exist_ok=True)
    # krxStocks.getCorpList()는 지난달 파일을 지우고 새로 받으므로, 해당 월 파일을 직접 읽는다
    stock_list = pd.read_excel(f"corpCode/corplist_merged_{month.replace('-', '')}.xlsx", dtype={'scode': str})
    stock_list['scode'] = stock_list['scode'].str.zfill(6)
    rows = stock_list.drop(columns=['market'], errors='ignore').to_dict('records')
    cached = set(f[:6] for f in os.listdir(os.path.join('derived', f'{CACHE_PREFIX[module]}{month}')))
    rows = [r for r in rows if r['scode'] in cached]
    chunk = 200
    for s in range(0, len(rows), chunk):
        part = os.path.join(tmp, f'part_{s:05d}.pkl')
        if os.path.exists(part):
            continue
        with mp.Pool(mp.cpu_count(), initializer=_init, initargs=(month,)) as pool:
            res = pool.map(_work, [(r, module) for r in rows[s:s + chunk]])
        pickle.dump([r for r in res if r], open(part, 'wb'))
        print(f'{module} {s + chunk}/{len(rows)}', flush=True)
    results = []
    for f in sorted(os.listdir(tmp)):
        results += pickle.load(open(os.path.join(tmp, f), 'rb'))
    df = fngCollect._order_columns(pd.DataFrame(results), fngCollect._get_indicator_order(module))
    out = {'finance': 'finance', 'ratio': 'finance_ratio'}[module]
    fngCollect.save_to_excel(df, module_name=module, filename=f"derived/{out}_{month.replace('-', '_')}_v2.xlsx")
    print('done', len(df))


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
