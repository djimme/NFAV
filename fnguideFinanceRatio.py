import logging

import pandas as pd
from bs4 import BeautifulSoup

from fin_utils import fetch_fnguide_page


def getFnGuideFiRatio(code):
    return fetch_fnguide_page(code, 'SVD_FinanceRatio.asp', '104', 'fnguide_FinanceRatio_')


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
