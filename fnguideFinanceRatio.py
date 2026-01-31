import datetime
import logging
import os

import pandas as pd
import requests
from bs4 import BeautifulSoup
from pandas import DataFrame, ExcelWriter


def getFnGuideFiRatio(code):
    now = datetime.datetime.now()    
    path = f"https://comp.fnguide.com/SVO2/ASP/SVD_FinanceRatio.asp?pGB=1&gicode=A{code}&cID=&MenuYn=Y&ReportGB=&NewMenuID=104&stkGb=701"
    downloadedFileDirectory = 'derived/fnguide_FinanceRatio_{0}-{1:02d}'.format(now.year, now.month)
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

def parseFnguideFiRatio(content):
    logger = logging.getLogger("kkmbaekkrx")
    html = BeautifulSoup(content, 'html.parser')
    body = html.find('body')

    result = {}
    result['code'] = '??'
    result['종목명'] = html.select('#giName')[0].get_text()
    result['업종'] = html.select('#compBody > div.section.ul_corpinfo > div.corp_group1 > p > span.stxt.stxt2')[0].get_text()
    result['PER'] = html.select('#corp_group2 > dl:nth-child(1) > dd')[0].get_text()
    result['PBR'] = html.select('#corp_group2 > dl:nth-child(4) > dd')[0].get_text()

    재무비율누적헤더 = None
    tFiRatio = html.find('table', {"class" : 'us_table_ty1 h_fix zigbg_no'})
    # print(tFiRatio)
            
    # if html.select_one('#divDaechaQ') is not None:
    #     대차quarter헤더 = html.select_one('#divDaechaQ').select_one('thead').select('th')
    #     for trs in html.select_one('#divDaechaQ').select_one('tbody').select('tr'):
    #         rowName = trs.select_one('div')
    #         rowName = rowName.text if rowName else ''
    #         rowName = rowName.replace(u"\xa0",u"")            
    #         # print(rowName)
    #         if (rowName.startswith("유동자산")):
    #             유동자산quarter = trs.select('th, td')
    #         elif (rowName.startswith("부채")):
    #             부채quarter = trs.select('th, td')
    
    # for v in list(zip(대차quarter헤더, 유동자산quarter, 부채quarter))[1:-1]:
    #     result["유동자산_"+v[0].text] = v[1].text.replace(",", "")
    #     result["부채_"+v[0].text] = v[2].text.replace(",", "")      
    #     # print(v)


    # print('FiRatio start')
    
    # 년도별 부채비율
    debt_ratios = html.find('tr', {'id':'p_grid1_3'}).find_all('td')
    cnt = len(debt_ratios)
    for dR in debt_ratios:
        tDR = '부채비율_y-'+str(cnt)
        result[tDR] = pd.to_numeric(dR.get_text(strip=True).replace(",", ""))
        cnt -= 1
        # print(result[tDR])
    
    # 년도별 EPS 증가율 및 년도별 EPS 
    EPS_incR = html.find('tr', {'id':'p_grid1_12'}).find_all('td')
    cnt = len(EPS_incR)
    for epsInc in EPS_incR:
        tepsInc = 'EPS증가율_y-'+str(cnt)
        result[tepsInc] = pd.to_numeric(epsInc.get_text(strip=True).replace(",",""))
        cnt -= 1
        # print(result[tepsInc])
        
    # 과거 년도별 EPS
    tEPSs = html.find_all("tr", {"class":"c_grid1_12 rwf acd_dep2_sub"})
    # print(tEPSs)
    
    foundEPSs = tEPSs[0].find_all('td')
    cnt = len(foundEPSs) + 1
        
    # 과거 년도별 EPS의 1년전 EPS 은 EPS(-1Y)를 활용
    EPS = 'EPS_y-'+str(cnt)
    result[EPS] = pd.to_numeric(tEPSs[1].find('td').get_text(strip=True).replace(",",""))
    # print(result[EPS])
    cnt -= 1
    
    for EPSs in foundEPSs:
        EPS = 'EPS_y-'+ str(cnt)
        result[EPS] = pd.to_numeric(EPSs.get_text(strip=True).replace(",",""))
        # print(result[EPS])
        cnt -= 1
            
    # 분기별 EPS 증가율(YoY)
    EPS_incQR = html.find('tr', {'id':'p_grid2_4'}).find_all('td')
    cnt = len(EPS_incQR)
    for epsInc in EPS_incQR:
        tepsInc = 'EPS증가율_q-'+str(cnt)
        result[tepsInc] = pd.to_numeric(epsInc.get_text(strip=True).replace(",",""))
        cnt -= 1
        # print(result[tepsInc])
    
    # 과거 분기별 EPS
    foundEPSs = html.find("tr", {"class":"c_grid2_4 rwf acd_dep2_sub"}).find_all('td')
    cnt = len(foundEPSs)
    for EPSs in foundEPSs:
        EPS = 'EPS_q-'+ str(cnt)
        result[EPS] = pd.to_numeric(EPSs.get_text(strip=True).replace(",",""))
        # print(result[EPS])
        cnt -= 1
    
    return result
