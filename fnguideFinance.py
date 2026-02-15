import logging

import pandas as pd
from bs4 import BeautifulSoup

from fin_utils import fetch_fnguide_page


def getFnguideFinance(code):
    return fetch_fnguide_page(code, 'SVD_Finance.asp', '103', 'fnguide_finance_')


def parseFnguideFinance(content):
    logger = logging.getLogger("kkmbaekkrx")
    html = BeautifulSoup(content, 'html.parser')
    body = html.find('body')

    result = {}
    result['code'] = '??'
    result['종목명'] = html.select('#giName')[0].get_text()
    result['업종'] = html.select('#compBody > div.section.ul_corpinfo > div.corp_group1 > p > span.stxt.stxt2')[0].get_text()
    result['PER'] = html.select('#corp_group2 > dl:nth-child(1) > dd')[0].get_text()
    result['PBR'] = html.select('#corp_group2 > dl:nth-child(4) > dd')[0].get_text()

    손익quarter헤더 = None
    당기순이익quarter = None
    if html.select_one('#divSonikQ') is not None:
        손익quarter헤더 = html.select_one('#divSonikQ').select_one('thead').select('th')
        for trs in html.select_one('#divSonikQ').select_one('tbody').select('tr'):
            rowName = trs.select_one('div')
            rowName = rowName.text if rowName else ''
            rowName = rowName.replace(u"\xa0",u"")
            # print(rowName)
            if ("당기순이익" == rowName):
                당기순이익quarter = trs.select('th, td')


    for v in list(zip(손익quarter헤더,당기순이익quarter))[1:-1]:
        result["당기순이익_"+v[0].text] = pd.to_numeric(v[1].text.strip().replace(",", ""))
        # print(v)

    대차quarter헤더 = None
    유동자산quarter = None
    부채quarter = None
    if html.select_one('#divDaechaQ') is not None:
        대차quarter헤더 = html.select_one('#divDaechaQ').select_one('thead').select('th')
        for trs in html.select_one('#divDaechaQ').select_one('tbody').select('tr'):
            rowName = trs.select_one('div')
            rowName = rowName.text if rowName else ''
            rowName = rowName.replace(u"\xa0",u"")
            # print(rowName)
            if (rowName.startswith("유동자산")):
                유동자산quarter = trs.select('th, td')
            elif (rowName.startswith("부채")):
                부채quarter = trs.select('th, td')

    for v in list(zip(대차quarter헤더, 유동자산quarter, 부채quarter))[1:-1]:
        result["유동자산_"+v[0].text] = pd.to_numeric(v[1].text.strip().replace(",", ""))
        result["부채_"+v[0].text] = pd.to_numeric(v[2].text.strip().replace(",", ""))
        # print(v)

    return result
