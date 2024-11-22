import datetime
import logging
import os

import pandas as pd
import requests
from bs4 import BeautifulSoup

def getFnguideFinance(code):
    now = datetime.datetime.now()
    path = f"https://comp.fnguide.com/SVO2/ASP/SVD_Finance.asp?pGB=1&gicode=A{code}&cID=&MenuYn=Y&ReportGB=&NewMenuID=103&stkGb=701"

    downloadedFileDirectory = 'derived/fnguide_finance_{0}-{1:02d}'.format(now.year, now.month)
    downloadedFilePath = '{0}/{1}.html'.format(downloadedFileDirectory, code)

    if not os.path.exists(downloadedFileDirectory):
        os.makedirs(downloadedFileDirectory)
    content = None
    if not os.path.exists(downloadedFilePath):
        response = requests.get(path)        
        with open(downloadedFilePath, "w", encoding="utf-8") as f:
            f.write(response.text)
        content = response.content  
    else:
        content = open(downloadedFilePath, "r", encoding = "utf-8").read()

    return content

def parseFnguideFinance(code, content):
    logger = logging.getLogger("krxStocks")
    html = BeautifulSoup(content, 'html.parser')
    body = html.find('body')

    result = {}
    result['code'] = code
    result['종목명'] = html.select('#giName')[0].get_text()
    result['업종'] = html.select('#compBody > div.section.ul_corpinfo > div.corp_group1 > p > span.stxt.stxt2')[0].get_text()
    result['PER'] = html.select('#corp_group2 > dl:nth-child(1) > dd')[0].get_text()
    result['PBR'] = html.select('#corp_group2 > dl:nth-child(4) > dd')[0].get_text()

    # 손익quarter헤더 = None
    # 당기순이익quarter = None
    # if html.select_one('#divSonikQ') is not None:
    #     손익quarter헤더 = html.select_one('#divSonikQ').select_one('thead').select('th')
    #     for trs in html.select_one('#divSonikQ').select_one('tbody').select('tr'):
    #         rowName = trs.select_one('div')
    #         rowName = rowName.text if rowName else ''
    #         rowName = rowName.replace(u"\xa0",u"")
    #         # print(rowName)
    #         if ("당기순이익" == rowName):
    #             당기순이익quarter = trs.select('th, td')
    #
    #
    # for v in list(zip(손익quarter헤더,당기순이익quarter))[1:-1]:
    #     result["당기순이익_"+v[0].text] = pd.to_numeric(v[1].text.strip().replace(",", ""))
    #     # print(v)

    # 재무상태quarter = None
    # 유동자산quarter = None
    # 비유동자산quarter = None
    # 부채quarter = None
    #
    # if html.select_one('#divDaechaQ') is not None:
    #     재무상태quarter = html.select_one('#divDaechaQ').select_one('thead').select('th')
    #     for trs in html.select_one('#divDaechaQ').select_one('tbody').select('tr'):
    #         # rowName = trs.select_one('div')
    #         # rowName = rowName.text if rowName else ''
    #         # rowName = rowName.replace(u"\xa0",u"")
    #         # # print(rowName)
    #         # if (rowName.startswith("유동자산")):
    #         #     유동자산quarter = trs.select('th, td')
    #         # elif (rowName.startswith("부채")):
    #         #     부채quarter = trs.select('th, td')
    #         #
    #         name
    #
    # for v in list(zip(재무상태quarter, 유동자산quarter, 부채quarter))[1:]:
    #     # result["유동자산_"+v[0].text] = pd.to_numeric(v[1].text.strip().replace(",", ""))
    #     # result["부채_"+v[0].text] = pd.to_numeric(v[2].text.strip().replace(",", ""))
    #     print(v)

    print(result)
    return result

