import datetime
import os
import multiprocessing as mp
import sys

import pandas as pd

from fin_utils import save_styled_excel
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

    # dfPEG = dfPEG[dfPEG['EPS_3yr'] > 0]
    # dfPEG = dfPEG[dfPEG['PEG'] <=0.5]
    # dfPEG = dfPEG[dfPEG['PER_y-3'] > 0]
    # dfPEG = dfPEG[dfPEG['부채비율_y-3'] <= 100]
    
    # dfPEG = dfPEG.sort_values(by=['PEG', 'PER_y-3','부채비율_y-3'], ascending=[True, False, True],ignore_index=True)

    res_cols = ['code', '종목명', '업종', 'PEG', 'EPS_3yr', '부채비율_y-3']
    dfPEG_res = dfPEG[res_cols]    
    # dfPEG_res.to_excel("./derived/dfPEG_res.xlsx", sheet_name="Sheet1", index=False)

    return dfPEG_res

################################################
def select_stocks(df):
    
    dfRes = pd.DataFrame()
    
    return dfRes
################################################

if __name__ == '__main__':
    now = datetime.datetime.now()    
    collectedFilePath = "derived/plpeg_{0}-{1:02d}.xlsx".format(now.year, now.month)
    testcollectedFilePath = "derived/plpeg_test_{0}-{1:02d}.xlsx".format(now.year, now.month)
    PEGoutputFilePath = "derived/peg_output_{0}-{1:02d}.xlsx".format(now.year, now.month)
    collected = pd.DataFrame()
    stock_codes = []

    # 명령행 인자로 테스트 모드 선택
    # python plpeg_datagen.py                    -> 전체 종목의 PEG 계산(fnguide)
    # python plpeg_datagen.py test               -> 005930, 078930, 011070 테스트

    if len(sys.argv) > 1 and sys.argv[1] == "test":
        # test mode
        stock_codes = ['005930','078930','011070']

        with mp.Pool(processes = mp.cpu_count()) as pool:
            dictList = pool.map(code_to_dict, stock_codes)  
        collected = pd.DataFrame.from_records(dictList)

        ## test Dataframe 확인용 XLSX 파일 생성 코드
        save_styled_excel(collected, testcollectedFilePath)

    else:
        # full mode
        if not os.path.exists(collectedFilePath):
            # krxStocks = fnguide_collector.getKrxStocks()
            krxStocks = krxStocks.getStocksFnguide()        
            stock_codes = list(krxStocks[krxStocks['종목분류']=='Company']['종목코드'])       
            # stock_codes = list(krxStocks['종목코드'])
        
            with mp.Pool(processes = mp.cpu_count()) as pool:
                dictList = pool.map(code_to_dict, stock_codes)
                
            collected = pd.DataFrame.from_records(dictList)
            
            ## Dataframe 확인용 XLSX 파일 생성 코드            
            save_styled_excel(collected, collectedFilePath)
            
        else:
            collected = pd.read_excel(collectedFilePath)
        
    peg_df = plpeg_calc(collected)
    
    ## Dataframe 확인용 CSV 파일 생성 코드
    save_styled_excel(peg_df, PEGoutputFilePath)
    
    ################################################
    stock_selected = select_stocks(peg_df)
    ################################################
