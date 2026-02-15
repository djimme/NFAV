import datetime
import logging
import os

import pandas as pd
import requests
from pandas import DataFrame, ExcelWriter
from pathlib import Path
from fin_utils import save_styled_excel

def getKrxStocks():         
    base_url: str = "https://kind.krx.co.kr/corpgeneral/corpList.do"
    save_path: str = "./corpCode/comp_list.html"

    if not os.path.exists(save_path):            
        """
        KIND 상장종목현황 화면의 EXCEL 버튼과 동일한 요청을 날려 엑셀 파일을 저장한다.
        필요한 경우 params 값을 F12 개발자 도구 내 Network 탭에서 확인 후 수정한다.
        """

        # 아래 params는 예시이며, 실제로는 개발자 도구에서
        # EXCEL 버튼 클릭 시 corpList.do?method=download 로 나가는
        # 쿼리스트링을 그대로 옮겨 적어야 한다.
        params = {
            # 아래부터는 개발자도구에서 보고 그대로 세팅
            "method": "download",   # fnDownload 안에서 지정되는 다운로드용 method 값
            "searchType" : "13",  # 전체검색
        }

        headers = {
            # 최소한의 헤더 (필요 시 개발자 도구에서 복사해서 추가)
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/143.0.0.0 Safari/537.36 Edg/143.0.0.0"
            ),
            "Referer": "https://kind.krx.co.kr/corpgeneral/corpList.do?method=loadInitPage",
        }

        resp = requests.get(base_url, params=params, headers=headers)
        resp.raise_for_status()

        Path(save_path).write_bytes(resp.content)    
        print(f"saved: {save_path}")

    code_df = pd.read_html(save_path, header=0)[0]      
        
    code_df = code_df[['종목코드', '회사명', '업종', '주요제품']]
    code_df = code_df.rename(columns={'회사명': '종목명'})

    print("[   Data 예제   ] \n", code_df.head())
    return code_df

def getStocksFnguide():
    """
    FnGuide lookup_data.asp API에서 전체 종목 리스트 추출

    Returns:
        DataFrame: 종목분류, 종목코드, 종목명, 시장정보 컬럼을 가진 DataFrame
    """
    url = "https://comp.fnguide.com/SVO2/common/lookup_data.asp"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': 'https://comp.fnguide.com/SVO2/common/lookup.asp'
    }

    # 종목 분류 목록 (cmbCompGb의 value 값)
    # 0: 전체, 1: Company, 2: ETF, 8: ETN, 3: REITs, 4: SPAC
    comp_type_map = {
        '1': 'Company',
        '2': 'ETF',
        '8': 'ETN',
        '3': 'REITs',
        '4': 'SPAC'
    }

    all_stocks = []

    for comp_gb, comp_name in comp_type_map.items():
        print(f"[FnGuide] {comp_name} 종목 수집 중...")

        # lookup_data.asp API 파라미터
        # mkt_gb: 1(전체), 2(KOSPI), 3(KOSDAQ), 7(KONEX), 8(K-OTC), 6(상장예정)
        # comp_gb: 종목분류
        # s_type: 1(일반검색), 2(가나다 검색)
        # search_key1, search_key2: 검색어
        params = {
            'mkt_gb': '1',  # 전체 시장
            'comp_gb': comp_gb,
            's_type': '1',  # 일반 검색
            'search_key1': '',  # 전체
            'search_key2': ''
        }

        try:
            response = requests.get(url, params=params, headers=headers, timeout=30)
            response.encoding = 'utf-8'

            # JSON 응답 파싱
            data = response.json()

            # 데이터 처리
            # data는 [{cd: 'A005930', nm: '삼성전자', gb: '코스피', stk_gb: '701', mkt_gb: '2'}, ...] 형식
            for item in data:
                # 종목코드에서 'A' 제거
                stock_code = item.get('cd', '')
                if stock_code.startswith(('A', 'Q')) and len(stock_code) == 7:
                    stock_code = stock_code[1:]  # A 또는 Q 제거
                else:
                    continue

                stock_name = item.get('nm', '')
                market_info = item.get('gb', '')

                all_stocks.append({
                    '종목분류': comp_name,
                    '종목코드': stock_code,
                    '종목명': stock_name,
                    '시장정보': market_info
                })

            print(f"  {comp_name}: {len([s for s in all_stocks if s['종목분류'] == comp_name])}개 종목")

        except Exception as e:
            print(f"  ERROR - {comp_name} 수집 실패: {e}")
            continue

    # DataFrame 생성
    if all_stocks:
        df = pd.DataFrame(all_stocks)
        print(f"\n[FnGuide] 총 {len(df)}개 종목 수집 완료")
        print(f"[   Data 예제   ] \n{df.head()}")
        return df
    else:
        print("\n[FnGuide] 수집된 종목이 없습니다.")
        return pd.DataFrame(columns=['종목분류', '종목코드', '종목명', '시장정보'])


def collectCorpList():
    """KRX KIND와 FnGuide API 데이터를 합쳐 종목 리스트를 생성한다.

    FnGuide 기준 종목에 KRX의 업종/주요제품 정보를 병합한다.
    KRX에 없는 종목은 'NA'로 채운다.

    Returns:
        DataFrame: 종목분류, 종목코드, 종목명, 시장정보, 업종, 주요제품
    """
    df_fnguide = getStocksFnguide()
    df_krx = getKrxStocks()[['종목코드', '업종', '주요제품']]

    # KRX 종목코드를 6자리 문자열로 변환 (pd.read_html이 정수로 읽는 경우 대비)
    df_krx['종목코드'] = df_krx['종목코드'].astype(str).str.zfill(6)

    df_merged = df_fnguide.merge(df_krx, on='종목코드', how='left')
    df_merged[['업종', '주요제품']] = df_merged[['업종', '주요제품']].fillna('NA')

    df_merged = df_merged[~df_merged['시장정보'].str.contains('코넥스|K-OTC')]

    df_ETF_ETN = df_merged[df_merged['종목분류'].str.contains('ETF|ETN')][['종목분류', '종목코드', '종목명']]

    df_merged = df_merged[~df_merged['종목분류'].str.contains('ETF|ETN')]
    df_merged = df_merged[~df_merged['종목분류'].str.contains('SPAC|REITs')]
    df_merged = df_merged[~df_merged['종목명'].str.contains('스팩')]

    df_merged = df_merged.drop('종목분류', axis=1)

    df_merged = df_merged.rename(columns={
        '종목코드': 'scode',
        '종목명': 'sname',
        '시장정보': 'market',
        '업종': 'industry',
        '주요제품': 'products'
    })

    df_ETF_ETN = df_ETF_ETN.rename(columns={
        '종목분류': 'category',
        '종목코드': 'scode',
        '종목명': 'sname'
    })

    print(f"\n[collectCorpList] 총 {len(df_merged)}개 종목 (업종 매핑: {len(df_merged[df_merged['industry'] != 'NA'])}개)")
    return df_merged, df_ETF_ETN


def getCorpList(mode='merged'):
    """종목 리스트를 수집하여 Excel로 저장하고 DataFrame으로 반환한다.

    동일 월 Excel이 있으면 읽어서 반환하고,
    이전 달 Excel이 있으면 삭제 후 새로 수집한다.

    Parameters:
        mode: 'merged' (FnGuide + KRX 병합), 'krx' (KRX만), 'fnguide' (FnGuide만)

    Returns:
        tuple: (df_complist, df_etf_etn) - mode가 'merged'가 아니면 df_etf_etn은 None
    """
    now = datetime.datetime.now()
    corpListPath = "./corpCode/corplist_{0}_{1}{2:02d}.xlsx".format(mode, now.year, now.month)
    etfEtnPath = corpListPath.replace('.xlsx', '_ETF_ETN.xlsx')

    # 동일 월 파일이 있으면 읽어서 반환
    if os.path.exists(corpListPath):
        print(f"[getCorpList] 기존 파일 사용: {corpListPath}")
        df_complist = pd.read_excel(corpListPath, dtype={'종목코드': str})
        df_etf_etn = None
        if mode == 'merged' and os.path.exists(etfEtnPath):
            df_etf_etn = pd.read_excel(etfEtnPath, dtype={'종목코드': str})
        return df_complist, df_etf_etn

    # 이전 달 파일 삭제
    os.makedirs('./corpCode', exist_ok=True)
    prefix = f"corplist_{mode}_"
    for entry in os.listdir('./corpCode'):
        if entry.startswith(prefix):
            os.remove(os.path.join('./corpCode', entry))

    # 데이터 수집
    print("="*10 + " Collect Corp List " + "="*10)
    df_etf_etn = None
    if mode == 'krx':
        df_complist = getKrxStocks()
    elif mode == 'fnguide':
        df_complist = getStocksFnguide()
    else:
        df_complist, df_etf_etn = collectCorpList()

    # Excel 저장
    save_styled_excel(df_complist, corpListPath, sheet_name="CorpList")
    if df_etf_etn is not None:
        save_styled_excel(df_etf_etn, etfEtnPath, sheet_name="ETF_ETN")

    print(f"엑셀 파일 저장 완료: {corpListPath}")
    return df_complist, df_etf_etn


if __name__ == '__main__':
    import sys

    # 명령행 인자로 테스트 모드 선택
    # python krxStocks.py               -> 종목 수집 (FnGuide + KRX 병합)
    # python krxStocks.py --krx         -> KRX KIND만 수집
    # python krxStocks.py --fnguide     -> FnGuide API만 수집

    if '--krx' in sys.argv:
        mode = 'krx'
    elif '--fnguide' in sys.argv:
        mode = 'fnguide'
    else:
        mode = 'merged'

    df_complist, df_etf_etn = getCorpList(mode)