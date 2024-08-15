import datetime
import logging
import os

import pandas as pd
import requests
from bs4 import BeautifulSoup


def getFnGuideSnapshot(code):
    now = datetime.datetime.now()    
    path = f"https://comp.fnguide.com/SVO2/ASP/SVD_Main.asp?pGB=1&gicode=A{code}&cID=&MenuYn=Y&ReportGB=&NewMenuID=101&stkGb=701"
    downloadedFileDirectory = 'derived/fnguide_snapshot_{0}-{1:02d}'.format(now.year, now.month)
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

def parseFnguideSnapshot(content):
    logger = logging.getLogger("kkmbaekkrx")
    html = BeautifulSoup(content, 'html.parser')
    body = html.find('body')

    result = {}
    result['code'] = '??'
    # result['종목명'] = html.select('#giName')[0].get_text()
    # result['업종'] = html.select('#compBody > div.section.ul_corpinfo > div.corp_group1 > p > span.stxt.stxt2')[0].get_text()
    # result['PER'] = html.select('#corp_group2 > dl:nth-child(1) > dd')[0].get_text()
    # result['PBR'] = html.select('#corp_group2 > dl:nth-child(4) > dd')[0].get_text()    

    # marketcap
    for th in html.select('th'):
        anchor = th.select('a')
        if not anchor:
            continue
        if anchor[0].get_text() != "시가총액":
            continue
        span = th.select("span")
        if not span:
            continue
        if span[0].get_text() != "(보통주,억원)":
            continue

        for sibling in th.next_siblings:
            logger.info(sibling)
            if sibling.name == "td":
                result['시가총액(보통주,억원)'] = pd.to_numeric(sibling.get_text(strip=True).replace(",",""))
                break
   
    FinancialHighlight연결연간Header = None
    if html.select_one('#highlight_D_Y') is not None:
        # FinancialHighlight연결연간Header = html.select_one('#highlight_D_Y').select_one('thead').select_one()
        for th in html.select_one('#highlight_D_Y').select('th'):
            div = th.select('div')
            if span:
                one = 1
            else:
                continue
            
            txt = div[0].get_text().replace(u"\xa0",u"")
            if txt != '지배주주순이익':
                continue           

            for sibling in th.next_siblings:
                logger.info(sibling)
                if sibling.name == 'td':
                    try:
                        result['지배주주순이익'] = pd.to_numeric(sibling.get_text(strip=True).replace(",", ""))
                    except ValueError:
                        one = 1                    
                    
    return result