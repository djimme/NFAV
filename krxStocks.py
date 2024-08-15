
import datetime
import logging
import os

import pandas as pd
import requests
from bs4 import BeautifulSoup
from pandas import DataFrame, ExcelWriter

def getKrxStocks():  
    #code_df = pd.read_html('http://kind.krx.co.kr/corpgeneral/corpList.do?method=download&searchType=13', header=0)[0]
    
    code_df = pd.read_excel('./comp_list.xlsx', sheet_name='comp_list')
    
    code_df['종목코드'] = code_df['종목코드'].map("{:06d}".format)
    code_df = code_df[~code_df['회사명'].str.contains('스팩')]
    
    code_df.reset_index(inplace=True)  
        
    code_df = code_df[['종목코드', '회사명', '업종', '주요제품']]
    code_df = code_df.rename(columns={'종목코드': 'code', '회사명':'name', '업종' : 'industry', '주요제품' : 'main_product'})

    return code_df


if __name__ == '__main__':
    df_complist = getKrxStocks()
    df_complist.to_csv(path_or_buf='./complist.csv', encoding='cp949')