import pandas as pd
import numpy as np
import datetime
import os
import multiprocessing as mp
import krxStocks
import fnguideFinance as fnFI
# import fnguideSnapshot as fnSS  # TODO: investment_indicators 결과 DataFrame으로 대체 예정
import fnguideFinanceRatio as fnFR
from fin_utils import save_styled_excel


def code_to_dict(code):
    """
    개별 종목의 NFAV 계산에 필요한 데이터 수집

    NFAV는 이론적으로 금융자산 - 이자부부채를 계산하지만,
    FnGuide에서는 세부 항목을 제공하지 않으므로 근사치 계산을 사용합니다:

    NFAV 근사치 = 유동자산 - 총부채 (NCAV와 동일한 보수적 접근)
    실무에서는 추가적인 재무제표 상세 데이터가 필요합니다.
    """
    try:
        # snapshotHtml = fnSS.getFnGuideSnapshot(code)  # TODO: investment_indicators 결과 DataFrame으로 대체 예정
        financeHtml = fnFI.getFnguideFinance(code)
        fiRatioHtml = fnFR.getFnGuideFiRatio(code)

        # snapshot = fnSS.parseFnguideSnapshot(snapshotHtml)  # TODO: investment_indicators 결과 DataFrame으로 대체 예정
        finance = fnFI.parseFnguideFinance(financeHtml)
        fiRatio = fnFR.parseFnguideFiRatio(fiRatioHtml)

        result = {**finance, **fiRatio, 'code': code}
        return result
    except Exception as e:
        print(f"Error processing {code}: {e}")
        return {'code': code}


def calculate_nfav(collected_df):
    """
    NFAV 계산 및 필터링 함수

    NFAV (Net Financial Asset Value) 개념:
    - 이론: 금융자산(현금, 단기투자, 장기투자 등) - 이자부부채(차입금, 사채 등)
    - 실무: FnGuide 데이터 한계로 인해 보수적 근사치 사용
      NFAV ≈ 유동자산 - 총부채 (NCAV와 유사하지만 더 보수적인 필터 적용)

    NFAV_R (NFAV Ratio) = NFAV / 시가총액

    Parameters:
    -----------
    collected_df : pd.DataFrame
        fnguide_collector에서 수집한 재무 데이터
        필요 컬럼: code, 종목명, 유동자산_YYYY/MM, 부채_YYYY/MM,
                  시가총액(보통주,억원), 당기순이익_YYYY/MM, 부채비율_y-N

    Returns:
    --------
    result_df : pd.DataFrame
        NFAV 계산 결과 DataFrame
        컬럼: code, 종목명, NFAV, NFAV_R, 시가총액(보통주,억원), 유동자산, 부채,
              부채비율, 당기순이익
    """

    # 최신 분기 데이터 자동 선택
    유동자산_cols = [col for col in collected_df.columns if col.startswith('유동자산_')]
    부채_cols = [col for col in collected_df.columns if col.startswith('부채_')]
    당기순이익_cols = [col for col in collected_df.columns if col.startswith('당기순이익_')]
    부채비율_cols = [col for col in collected_df.columns if col.startswith('부채비율_')]

    if not 유동자산_cols or not 부채_cols:
        raise ValueError("유동자산 또는 부채 데이터가 없습니다.")

    # 최신 분기 선택 (첫 번째 컬럼이 가장 최근)
    latest_유동자산_col = 유동자산_cols[0]
    latest_부채_col = 부채_cols[0]
    latest_당기순이익_col = 당기순이익_cols[0] if 당기순이익_cols else None
    latest_부채비율_col = 부채비율_cols[0] if 부채비율_cols else None

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

    # 부채비율 처리
    if latest_부채비율_col:
        df['부채비율'] = pd.to_numeric(df[latest_부채비율_col], errors='coerce')

    # null 제거
    df = df[~df['유동자산'].isnull()]
    df = df[~df['부채'].isnull()]
    df = df[~df['시가총액(보통주,억원)'].isnull()]

    # NFAV 계산 (보수적 근사치)
    # 주의: 실제 NFAV는 금융자산 - 이자부부채이지만,
    # 현재 데이터로는 유동자산 - 총부채로 근사
    df['NFAV'] = df['유동자산'] - df['부채']
    df['NFAV_R'] = df['NFAV'] / df['시가총액(보통주,억원)']

    # NFAV 필터링 (NCAV보다 더 보수적)
    # 1. NFAV_R > 0.5 (시가총액이 NFAV의 2배 이하)
    # 2. 당기순이익 > 0 (수익성)
    # 3. 부채비율 < 150% (재무건전성)
    df = df[df['NFAV_R'] > 0.5]

    if latest_당기순이익_col and '당기순이익' in df.columns:
        df = df[df['당기순이익'] > 0]

    if latest_부채비율_col and '부채비율' in df.columns:
        df = df[df['부채비율'] < 150]

    # 정렬
    df.sort_values(by=['NFAV_R'], inplace=True, ascending=False)

    # 결과 DataFrame 생성
    result_cols = ['code', '종목명', 'NFAV', 'NFAV_R', '시가총액(보통주,억원)', '유동자산', '부채']

    if latest_부채비율_col and '부채비율' in df.columns:
        result_cols.append('부채비율')

    if latest_당기순이익_col and '당기순이익' in df.columns:
        result_cols.append('당기순이익')

    result_df = df[result_cols].copy()

    return result_df


def main():
    """NFAV 데이터 수집 및 계산 메인 함수"""
    now = datetime.datetime.now()
    collectedFilePath = "derived/nfav_{0}-{1:02d}-{2:02d}.xlsx".format(now.year, now.month, now.day)

    # 데이터 수집
    if not os.path.exists(collectedFilePath):
        print("종목 리스트 로딩 중...")
        krxStockslist, _ = krxStocks.getCorpList()

        print(f"데이터 수집 중... (총 {len(krxStockslist)} 종목)")
        with mp.Pool(processes=mp.cpu_count()) as pool:
            dictList = pool.map(code_to_dict, list(krxStockslist['scode']))  
            
        collected = pd.DataFrame(dictList)
        save_styled_excel(collected, collectedFilePath)
        print(f"데이터 저장 완료: {collectedFilePath}")
    else:
        print(f"기존 데이터 로딩: {collectedFilePath}")
        collected = pd.read_excel(collectedFilePath)

    # NFAV 계산
    print("\nNFAV 계산 중...")
    print("주의: FnGuide 데이터 한계로 NFAV ≈ 유동자산 - 총부채로 근사 계산")
    print("      정확한 NFAV는 금융자산 - 이자부부채 필요")
    result_df = calculate_nfav(collected)

    # 결과 저장
    outputFilePath = "derived/nfav_output_{0}-{1:02d}-{2:02d}.xlsx".format(now.year, now.month, now.day)
    save_styled_excel(result_df, outputFilePath)

    print(f"\n=== NFAV 계산 결과 (상위 20개) ===")
    print(result_df.head(20))
    print(f"\n총 {len(result_df)}개 종목")
    print(f"결과 저장 완료: {outputFilePath}")

    return result_df


if __name__ == '__main__':
    main()