import pandas as pd
import numpy as np
import datetime
import os
import multiprocessing as mp
import fnguide_collector
from fin_utils import save_styled_excel


def code_to_dict(code):
    """개별 종목의 NCAV 계산에 필요한 데이터 수집"""
    try:
        snapshotHtml = fnguide_collector.getFnGuideSnapshot(code)
        financeHtml = fnguide_collector.getFnguideFinance(code)

        snapshot = fnguide_collector.parseFnguideSnapshot(snapshotHtml)
        finance = fnguide_collector.parseFnguideFinance(financeHtml)

        result = {**snapshot, **finance, 'code': code}
        return result
    except Exception as e:
        print(f"Error processing {code}: {e}")
        return {'code': code}


def calculate_ncav(collected_df):
    """
    NCAV 계산 및 필터링 함수

    NCAV (Net Current Asset Value) = 유동자산 - 총부채
    NCAV_R (NCAV Ratio) = NCAV / 시가총액

    Parameters:
    -----------
    collected_df : pd.DataFrame
        fnguide_collector에서 수집한 재무 데이터
        필요 컬럼: code, 종목명, 유동자산_YYYY/MM, 부채_YYYY/MM, 시가총액(보통주,억원), 당기순이익_YYYY/MM

    Returns:
    --------
    result_df : pd.DataFrame
        NCAV 계산 결과 DataFrame
        컬럼: code, 종목명, NCAV, NCAV_R, 시가총액(보통주,억원), 유동자산, 부채, 당기순이익
    """

    # 최신 분기 데이터 자동 선택
    유동자산_cols = [col for col in collected_df.columns if col.startswith('유동자산_')]
    부채_cols = [col for col in collected_df.columns if col.startswith('부채_')]
    당기순이익_cols = [col for col in collected_df.columns if col.startswith('당기순이익_')]

    if not 유동자산_cols or not 부채_cols:
        raise ValueError("유동자산 또는 부채 데이터가 없습니다.")

    # 최신 분기 선택 (첫 번째 컬럼이 가장 최근)
    latest_유동자산_col = 유동자산_cols[0]
    latest_부채_col = 부채_cols[0]
    latest_당기순이익_col = 당기순이익_cols[0] if 당기순이익_cols else None

    # 데이터 정제
    df = collected_df.copy()
    df['code'] = df['code'].apply(lambda x: '{:06.0f}'.format(float(x)) if pd.notna(x) else x)

    # 숫자형 변환
    df['유동자산'] = pd.to_numeric(df[latest_유동자산_col], errors='coerce')
    df['부채'] = pd.to_numeric(df[latest_부채_col], errors='coerce')

    # 시가총액 처리
    if '시가총액(보통주,억원)' in df.columns:
        if df['시가총액(보통주,억원)'].dtype == 'object':
            df['시가총액(보통주,억원)'] = df['시가총액(보통주,억원)'].str.replace(",", "")
        df['시가총액(보통주,억원)'] = pd.to_numeric(df['시가총액(보통주,억원)'], errors='coerce')

    # 당기순이익 처리
    if latest_당기순이익_col:
        df['당기순이익'] = pd.to_numeric(df[latest_당기순이익_col], errors='coerce')

    # null 제거
    df = df[~df['유동자산'].isnull()]
    df = df[~df['부채'].isnull()]
    df = df[~df['시가총액(보통주,억원)'].isnull()]

    # NCAV 계산
    df['NCAV'] = df['유동자산'] - df['부채']
    df['NCAV_R'] = df['NCAV'] / df['시가총액(보통주,억원)']

    # 필터링: NCAV_R > 0, 당기순이익 > 0
    df = df[df['NCAV_R'] > 0]
    if latest_당기순이익_col and '당기순이익' in df.columns:
        df = df[df['당기순이익'] > 0]

    # 정렬
    df.sort_values(by=['NCAV_R'], inplace=True, ascending=False)

    # 결과 DataFrame 생성
    result_cols = ['code', '종목명', 'NCAV', 'NCAV_R', '시가총액(보통주,억원)', '유동자산', '부채']
    if latest_당기순이익_col and '당기순이익' in df.columns:
        result_cols.append('당기순이익')

    result_df = df[result_cols].copy()

    return result_df


def main():
    """NCAV 데이터 수집 및 계산 메인 함수"""
    now = datetime.datetime.now()
    collectedFilePath = "derived/ncav_{0}-{1:02d}-{2:02d}.xlsx".format(now.year, now.month, now.day)

    # 데이터 수집
    if not os.path.exists(collectedFilePath):
        print("종목 리스트 로딩 중...")
        krxStocks = fnguide_collector.getKrxStocks()

        print(f"데이터 수집 중... (총 {len(krxStocks)} 종목)")
        with mp.Pool(processes=mp.cpu_count()) as pool:
            dictList = pool.map(code_to_dict, list(krxStocks['code']))

        collected = pd.DataFrame(dictList)
        save_styled_excel(collected, collectedFilePath)
        print(f"데이터 저장 완료: {collectedFilePath}")
    else:
        print(f"기존 데이터 로딩: {collectedFilePath}")
        collected = pd.read_excel(collectedFilePath)

    # NCAV 계산
    print("NCAV 계산 중...")
    result_df = calculate_ncav(collected)

    # 결과 저장
    outputFilePath = "derived/ncav_output_{0}-{1:02d}-{2:02d}.xlsx".format(now.year, now.month, now.day)
    save_styled_excel(result_df, outputFilePath)

    print(f"\n=== NCAV 계산 결과 (상위 20개) ===")
    print(result_df.head(20))
    print(f"\n총 {len(result_df)}개 종목")
    print(f"결과 저장 완료: {outputFilePath}")

    return result_df


if __name__ == '__main__':
    main()
