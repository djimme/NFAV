import logging

import pandas as pd
from bs4 import BeautifulSoup

from fin_utils import fetch_fnguide_page


def getFnGuideInvestIdx(code):
    return fetch_fnguide_page(code, 'SVD_Invest.asp', '105', 'fnguide_InvestIdx_')


def parseFnGuideInvestIdx(content):
    logger = logging.getLogger("kkmbaekkrx")
    html = BeautifulSoup(content, 'html.parser')
    body = html.find('body')

    result = {}
    result['code'] = '??'

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
