# strat_ncav_nfav.py
# NCAV / NFAV 전략 — Benjamin Graham 스타일
#
# 이론:
#   Benjamin Graham "The Intelligent Investor" 기반.
#   기업의 청산가치(순유동자산)보다 시가총액이 낮은 종목을 극단적 저평가로 봄.
#
# NCAV (Net Current Asset Value):
#   NCAV = 유동자산 - 총부채
#   NCAV_R = NCAV / 시가총액
#   NCAV_R > 1 → 시총 < 순유동자산 → 극단적 저평가
#   Graham 기준: NCAV_R >= 1.5 권장
#
# NFAV (Net Fixed Asset Value):
#   유동자산뿐 아니라 비유동자산(토지·건물 등)도 일부 반영한 확장 지표
#   → 제조업·부동산 비중이 높은 기업에 유리
#
# 데이터 소스:
#   calc_NCAV.py / calc_NFAV.py 실행 결과 파일 (derived/ncav_output_*.xlsx 등)
#   → 이 모듈은 사전 계산된 결과를 로드만 함
#
# 주의:
#   NCAV 전략은 소형주·저유동성 종목 집중 경향 → 실제 매수 가능성 검토 필요

import glob
import pandas as pd
from strat_utils import _normalize


def strategy_ncav_nfav(config: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    calc_NCAV.py / calc_NFAV.py 실행 결과 파일을 로드합니다.
    결과 파일이 없으면 빈 DataFrame 반환.

    반환: (ncav_df, nfav_df)
    """
    def load_latest(pattern):
        files = sorted(glob.glob(pattern), reverse=True)
        if not files:
            return pd.DataFrame()
        df = pd.read_excel(files[0], dtype={"code": str})
        if "code" in df.columns:
            df["종목코드"] = df["code"].str.zfill(6)
        print(f"  ✅ {pattern}: {files[0]} ({len(df)}개)")
        return df

    ncav_df = load_latest(config.get("ncav_output_pattern", "derived/ncav_output_*.xlsx"))
    nfav_df = load_latest(config.get("nfav_output_pattern", "derived/nfav_output_*.xlsx"))

    if ncav_df.empty:
        print("  ℹ️  NCAV 결과 파일 없음. calc_NCAV.py를 먼저 실행하세요.")
    if nfav_df.empty:
        print("  ℹ️  NFAV 결과 파일 없음. calc_NFAV.py를 먼저 실행하세요.")

    # 정규화 점수 추가
    for df_, col in [(ncav_df, "NCAV_R"), (nfav_df, "NFAV_R")]:
        if not df_.empty and col in df_.columns:
            score_col = col.replace("_R", "_점수")
            df_[score_col] = _normalize(pd.to_numeric(df_[col], errors="coerce"))

    return ncav_df, nfav_df
