import datetime
import os
import multiprocessing as mp

import pandas as pd

from fin_utils import save_styled_excel
import krxStocks
import fnguideFinance as fnFI
# import fnguideSnapshot as fnSS  # TODO: investment_indicators 결과 DataFrame으로 대체 예정
import fnguideFinanceRatio as fnFR

def code_to_dict(code):
    try:
        # snapshotHtml = fnSS.getFnGuideSnapshot(code)  # TODO: investment_indicators 결과 DataFrame으로 대체 예정
        financeHtml = fnFI.getFnguideFinance(code)
        fiRatioHtml = fnFR.getFnGuideFiRatio(code)

        # snapshot = fnSS.parseFnguideSnapshot(snapshotHtml)  # TODO: investment_indicators 결과 DataFrame으로 대체 예정
        finance = fnFI.parseFnguideFinance(financeHtml)
        fiRatio = fnFR.parseFnguideFiRatio(fiRatioHtml)

        result = { **finance, **fiRatio, 'code' : code }            
        print(code)
        return result
    except Exception as e:
        print(code, "exception", e)
    return {}

if __name__ == '__main__':
    now = datetime.datetime.now()    
    # collectedFilePath = "derived/ncav_{0}-{1:02d}-{2:02d}.tsv".format(now.year, now.month, now.day)
    collectedFilePath = "derived/ncav_{0}-{1:02d}-{2:02d}.xlsx".format(now.year, now.month, now.day)

    if not os.path.exists(collectedFilePath):
        krxStockslist, _ = krxStocks.getCorpList()
        collected = pd.DataFrame()

        with mp.Pool(processes = mp.cpu_count()) as pool:
            dictList = pool.map(code_to_dict, list(krxStockslist['scode']))
    
        # dictList = code_to_dict('005930')

        collected = pd.DataFrame.from_records([dictList])
        print(collected)
        save_styled_excel(collected, collectedFilePath)

    collected = pd.read_excel(collectedFilePath)
    print(collected)
