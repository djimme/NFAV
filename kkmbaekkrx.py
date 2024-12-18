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

################ Dijay 추가 함수 ###############################################
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
        with open(downloadedFilePath, "w", encoding="utf-8") as f:
            f.write(response.text)
        content = response.content  
    else:
        content = open(downloadedFilePath, "r", encoding = "utf-8").read()

    return content

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
        with open(downloadedFilePath, "w", encoding="utf-8") as f:
            f.write(response.text)
        content = response.content  
    else:
        content = open(downloadedFilePath, "r", encoding = "utf-8").read()

    return content
################ Dijay 추가 함수 ###############################################

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

################ Dijay 추가 함수 ###############################################
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
################ Dijay 추가 함수 ###############################################


if __name__ == '__main__':
    df_complist = getKrxStocks()
    df_complist.to_csv(path_or_buf='./complist.csv', encoding='cp949')