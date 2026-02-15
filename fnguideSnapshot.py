import logging

import pandas as pd
from bs4 import BeautifulSoup

from fin_utils import fetch_fnguide_page


def getFnGuideSnapshot(code):
    return fetch_fnguide_page(code, 'SVD_Main.asp', '101', 'fnguide_snapshot_')


def parseFnguideSnapshot(content):
    logger = logging.getLogger("kkmbaekkrx")
    html = BeautifulSoup(content, 'html.parser')
    body = html.find('body')

    result = {}
    result['code'] = '??'

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
