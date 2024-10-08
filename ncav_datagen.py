import datetime
import os
import multiprocessing as mp

import pandas as pd

import kkmbaekkrx

def code_to_dict(code):
    try:
        snapshotHtml = kkmbaekkrx.getFnGuideSnapshot(code)
        financeHtml = kkmbaekkrx.getFnguideFinance(code)
        fiRatioHtml = kkmbaekkrx.getFnGuideFiRatio(code)
        
        snapshot = kkmbaekkrx.parseFnguideSnapshot(snapshotHtml)
        finance = kkmbaekkrx.parseFnguideFinance(financeHtml)
        fiRatio = kkmbaekkrx.parseFnguideFiRatio(fiRatioHtml)
        
        result = { **snapshot, **finance, **fiRatio, 'code' : code }            
        # result = {**fiRatio, 'code' : code }            
        print(code)
        return result
    except Exception as e:
        print(code, "exception", e)
    return {}

if __name__ == '__main__':
    now = datetime.datetime.now()    
    # collectedFilePath = "derived/ncav_{0}-{1:02d}-{2:02d}.tsv".format(now.year, now.month, now.day)
    collectedFilePath = "derived/ncav_{0}-{1:02d}-{2:02d}.csv".format(now.year, now.month, now.day)

    if not os.path.exists(collectedFilePath):
        krxStocks = kkmbaekkrx.getKrxStocks()
        collected = pd.DataFrame()
        
        with mp.Pool(processes = mp.cpu_count()) as pool:
            dictList = pool.map(code_to_dict, list(krxStocks['code']))

        # dictList = code_to_dict('005930')

        collected = pd.DataFrame.from_records([dictList])
        print(collected)
        # collected.to_csv(collectedFilePath, sep="\t")
        collected.to_csv(collectedFilePath, sep="\t", encoding='utf-8-sig')

    collected = pd.read_csv(collectedFilePath, sep="\t")
    print(collected)
