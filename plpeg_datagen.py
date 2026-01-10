import datetime
import os
import multiprocessing as mp

import pandas as pd

import fnguide_collector
import krxStocks

def code_to_dict(code):
    try:
        # snapshotHtml = fnguide_collector.getFnGuideSnapshot(code)      # Snapshot 페이지
        # financeHtml = fnguide_collector.getFnguideFinance(code)        # 재무제표 페이지
        fiRatioHtml = fnguide_collector.getFnGuideFiRatio(code)        # 재무비율 페이지
        InvestIdxHtml = fnguide_collector.getFnGuideInvestIdx(code)    # 투자지표 페이지

        # snapshot = fnguide_collector.parseFnguideSnapshot(snapshotHtml)
        # finance = fnguide_collector.parseFnguideFinance(financeHtml)
        fiRatio = fnguide_collector.parseFnguideFiRatio(fiRatioHtml)
        investIdx = fnguide_collector.parseFnGuideInvestIdx(InvestIdxHtml)
        
        # result = { **snapshot, **finance, **fiRatio, **investIdx, 'code' : code }            
        result = {**fiRatio, **investIdx,  'code' : code }            
        print(code)
        return result
    except Exception as e:
        print(code, "exception", e)
    return {}

def plpeg_calc(df):
    
    cols = ['code', '종목명', '업종', 'PER_y-3', '부채비율_y-3' , 'EPS_y-3', 'EPS_y-6']
    
    dfPEG = df.loc[:, cols]
    dfPEG.dropna(subset="PER_y-3", inplace=True)
    
    # dfPEG.to_csv("./derived/dfPEG.csv", encoding='utf-8-sig')
    dfPEG['EPS_y-6'].fillna(1)
    
    dfPEG['EPS_3yr'] = 100*(dfPEG['EPS_y-3']-dfPEG['EPS_y-6'])/dfPEG['EPS_y-6']
    dfPEG['PEG'] = dfPEG['PER_y-3']/dfPEG['EPS_3yr']

    dfPEG = dfPEG[dfPEG['EPS_3yr'] > 0]
    dfPEG = dfPEG[dfPEG['PEG'] <=0.5]
    dfPEG = dfPEG[dfPEG['PER_y-3'] > 0]
    dfPEG = dfPEG[dfPEG['부채비율_y-3'] <= 100]
    
    dfPEG = dfPEG.sort_values(by=['PEG', 'PER_y-3','부채비율_y-3'], ascending=[True, False, True],ignore_index=True)

    res_cols = ['code', '종목명', '업종', 'PEG', 'EPS_3yr', '부채비율_y-3']
    dfRes = dfPEG[res_cols]
    # dfRes.to_csv("./derived/dfRES.csv", encoding='utf-8-sig')
    return dfRes

################################################
def select_stocks(df):
    
    dfRes = pd.DataFrame()
    
    return dfRes
################################################

if __name__ == '__main__':
    now = datetime.datetime.now()    
    collectedFilePath = "derived/plpeg_{0}-{1:02d}.csv".format(now.year, now.month)
    PEGoutputFilePath = "derived/peg_output_{0}-{1:02d}.csv".format(now.year, now.month)
    collected = pd.DataFrame()

    if not os.path.exists(collectedFilePath):
        krxStocks = fnguide_collector.getKrxStocks()
        # collected = pd.DataFrame()
        
        with mp.Pool(processes = mp.cpu_count()) as pool:
            dictList = pool.map(code_to_dict, list(krxStocks['code']))
            # dictList = pool.map(code_to_dict, list(['005930','078930','011070']))
            
        collected = pd.DataFrame.from_records(dictList)
        
        ## Dataframe 확인용 CSV 파일 생성 코드
        collected.to_csv(collectedFilePath, encoding='utf-8-sig')
        
    else:
        collected = pd.read_csv(collectedFilePath)
    
    peg_df = plpeg_calc(collected)
    
    ## Dataframe 확인용 CSV 파일 생성 코드
    ## peg_df.to_csv(PEGoutputFilePath, encoding='utf-8-sig')
    
    ################################################
    stock_selected = select_stocks(peg_df)
    ################################################
