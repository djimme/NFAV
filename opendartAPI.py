# 모듈 import
import os
import requests
import json
import pandas as pd
from datetime import datetime as dt
from io import BytesIO
from zipfile import ZipFile

DART_Key = '6910d085745fd20ba0ad84fa3018c7b7413e4128'
KRX_Key = 'E8A07ADE017345F185BF733EC27EC3AD4B809F63'

def getCorpCode(api_key):#인증키 입력

    if not os.path.exists('./corpCode'):
        # XML download
        url_CorpCode = 'https://opendart.fss.or.kr/api/corpCode.xml'
        params ={'crtfc_key' : api_key}

        res_CorpCode = requests.get(url_CorpCode, params=params)

        with ZipFile(BytesIO(res_CorpCode.content)) as zf:
            zf.extractall('.\corpCode')

    # XML to dataframe
    df_corpCode = pd.read_xml('./corpCode/CORPCODE.xml', xpath='.//list', dtype='str')
    df_corpCode = (df_corpCode.loc[df_corpCode['stock_code'].notnull()]).reset_index(drop=True)

    df_corpCode.to_csv('./corpCode/corpCode.csv', index=False, encoding='utf-8-sig')

    print(df_corpCode)

    return df_corpCode

def getStockPrice(api_key):
    # today = dt.today().date().strftime('%Y%m%d')
    # print(today)

    today = '20241119'  # for testing purpose, replace with dt.today().date().strftime('%Y%m%d') when you use it in your environment.

    url_StockPrice_KOSPI = "http://data-dbg.krx.co.kr/svc/apis/sto/stk_bydd_trd"

    headers = {"AUTH_KEY" : api_key }
    params = {'basDd' : today}

    res_StockPrice_KOSPI = requests.get(url_StockPrice_KOSPI, headers=headers, params=params)

    res_StockPrice_KOSPI.raise_for_status() # 200 OK or 4xx, 5xx error check.
    res_StockPrice_KOSPI_json = res_StockPrice_KOSPI.json()
    json_data = res_StockPrice_KOSPI_json['OutBlock_1']

    df_Stocks = pd.DataFrame(json_data, columns=['MKT_NM', 'ISU_CD', 'ISU_NM', 'TDD_CLSPRC', 'FLUC_RT', 'MKTCAP', 'LIST_SHRS'])
    # print(df_Stocks)

    url_StockPrice_KOSDAQ = 'http://data-dbg.krx.co.kr/svc/apis/sto/ksq_bydd_trd'

    res_StockPrice_KOSDAQ = requests.get(url_StockPrice_KOSDAQ, headers=headers, params=params)

    res_StockPrice_KOSDAQ.raise_for_status()  # 200 OK or 4xx, 5xx error check.
    res_StockPrice_KOSDAQ_json = res_StockPrice_KOSDAQ.json()
    json_dataQ = res_StockPrice_KOSDAQ_json['OutBlock_1']

    df_StocksQ = pd.DataFrame(json_dataQ, columns=['MKT_NM', 'ISU_CD', 'ISU_NM', 'TDD_CLSPRC', 'FLUC_RT', 'MKTCAP', 'LIST_SHRS'])
    # print(df_StocksQ)

    df_Stocks = pd.concat([df_Stocks, df_StocksQ], ignore_index=True)
    print(df_Stocks)

    df_Stocks.to_csv('./corpCode/stockPrice.csv', index=False, encoding='utf-8-sig' )
    return df_Stocks

def getCorpMajorFi(df_corp, api_key):
    cols = ['현금', '유동자산', '비유동자산', '부채', '비지배지분']
    df_corpMajorFi = pd.DataFrame(columns = cols)
    #url 입력
    url = 'https://opendart.fss.or.kr/api/fnlttSinglAcntAll.json'

    dt_year = dt.today().year

    params ={'crtfc_key' : api_key ,
             'corp_code' : '00126380',
             'bsns_year' : dt_year,
             'reprt_code' : '11012',
             'fs_div' : 'CFS'}

    res_CorpMajorFi = requests.get(url, params=params)

    # # json 내용
    content = res_CorpMajorFi.json()

    for l in content['list']:
        account_nm = l.get('account_nm')

        match account_nm:
            case '현금및현금성자산':
                print('현금및현금성자산: {}'.format(l['thstrm_amount']))
            case '유동자산':
                print('유동자산: {}'.format(l['thstrm_amount']))
            case '비유동자산':
                print('비유동자산: {}'.format(l['thstrm_amount']))
            case '부채총계':
                print('부채총계: {}'.format(l['thstrm_amount']))
            case '비지배지분':
                if (l['sj_nm'] == '재무상태표'):
                    print('비지배지분: {}'.format(l['thstrm_amount']))

    print(json.dumps(content['list'], ensure_ascii=False, indent=4))

    # 깔끔한 출력 위한 코드
    # print(df_corpMajorFi)
    # print(json.dumps(content, ensure_ascii=False, indent=4))

    return df_corpMajorFi

if __name__ == '__main__':
    df_corpCode = getCorpCode(DART_Key)
    df_Stocks = getStockPrice(KRX_Key)
    df_corpMajorFi = getCorpMajorFi(df_corpCode, DART_Key)