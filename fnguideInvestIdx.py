import datetime
import logging
import os

import pandas as pd
import requests
from bs4 import BeautifulSoup
from pandas import DataFrame, ExcelWriter


def getFnGuideInvestIdx(code):
    now = datetime.datetime.now()    
    path = f"https://comp.fnguide.com/SVO2/ASP/SVD_Invest.asp?pGB=1&gicode=A{code}&cID=&MenuYn=Y&ReportGB=&NewMenuID=105&stkGb=701"
    downloadedFileDirectory = 'derived/fnguide_InvestIdx_{0}-{1:02d}'.format(now.year, now.month)
    downloadedFilePath = '{0}/{1}.html'.format(downloadedFileDirectory, code)

    if not os.path.exists(downloadedFileDirectory):
        os.makedirs(downloadedFileDirectory)
    content = None
    if not os.path.exists(downloadedFilePath):
        response = requests.get(path)
        response.encoding = 'utf-8'
        with open(downloadedFilePath, "w", encoding="utf-8") as f:
            f.write(response.text)
        content = response.text
    else:
        content = open(downloadedFilePath, "r", encoding = "utf-8").read()

    return content

def parseFnGuideInvestIdx(content):
    logger = logging.getLogger("kkmbaekkrx")
    html = BeautifulSoup(content, 'html.parser')
    body = html.find('body')

    result = {}
    result['code'] = '??'
    
    # print('InvestIdx start')
    
    # 년도별 PER 
    foundPERs = html.find('tr', {'id':'p_grid1_9'}).find_all('td')
    cnt = len(foundPERs)
    
    for PER in foundPERs:
        tPER = "PER_y-" + str(cnt)
        hPER = PER.get_text(strip=True)
        if(hPER == "N/A"):
            result[tPER] = hPER
            continue
        
        result[tPER] = pd.to_numeric(hPER.replace(",",""))
        cnt -= 1
        # print(result[tPER])
        
    
    return result



