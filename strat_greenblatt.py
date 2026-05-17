# strat_greenblatt.py
# Greenblatt Magic Formula 전략
#
# 이론:
#   Joel Greenblatt "The Little Book That Beats the Market" (2005).
#   두 개의 랭킹 합산으로 '좋은 기업을 싸게 사는' 종목 선정.
#
# 두 지표:
#   1. 수익수익률 (Earnings Yield) = 1 / EV/EBITDA  → 높을수록 저평가
#      (EV/EBITDA가 낮으면 → 기업가치 대비 이익이 크다 → 싸다)
#   2. 자본수익률 (ROIC)          → 높을수록 우량 기업
#
# 선정 방식:
#   두 지표를 각각 랭킹 → 랭킹 합산이 낮은 상위 N개 종목 선정
#   (Greenblatt 원본: 시장 전체 대상, 금융·유틸리티 제외 권고)
#
# 필터 조건 (STRATEGY_CONFIG["greenblatt"] 참조):
#   - EV/EBITDA > 0, ROIC > 0  (음수 = 적자 → 제외)
#   - 부채비율 <= max_debt_ratio (기본값 150%)
#   - Top N 선정 (기본값 30)

import pandas as pd
from strat_utils import _recent_cols, _best_col, _normalize


def strategy_greenblatt(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """
    Magic Formula = 수익수익률(Earnings Yield) 랭킹 + 자본수익률(ROIC) 랭킹
    두 랭킹의 합이 낮은 종목이 우량.

    수익수익률 = 1 / EV/EBITDA   (높을수록 좋음)
    자본수익률 = ROIC             (높을수록 좋음)
    """
    result = df.copy()

    ev_col   = _best_col(result, _recent_cols(result, "_EV/EBITDA"))
    roic_col = _best_col(result, _recent_cols(result, "(누적)_ROIC"))
    debt_col = _best_col(result, _recent_cols(result, "(누적)_부채비율"))

    if not ev_col or not roic_col:
        print("  ⚠️ Greenblatt 전략: 필요 컬럼 없음 (EV/EBITDA 또는 ROIC)")
        return pd.DataFrame()

    result["EV_EBITDA_사용"] = pd.to_numeric(result[ev_col], errors="coerce")
    result["ROIC_사용"] = pd.to_numeric(result[roic_col], errors="coerce")

    # EV/EBITDA는 양수여야 의미있음 (음수는 적자)
    result = result[
        result["EV_EBITDA_사용"].notna() &
        result["ROIC_사용"].notna() &
        (result["EV_EBITDA_사용"] > 0) &
        (result["ROIC_사용"] > 0)
    ].copy()

    # 부채비율 필터
    if debt_col:
        max_debt = cfg.get("max_debt_ratio", 150.0)
        result["부채비율_사용"] = pd.to_numeric(result[debt_col], errors="coerce")
        result = result[result["부채비율_사용"].fillna(999) <= max_debt]

    if len(result) == 0:
        return pd.DataFrame()

    # 수익수익률: 1/EV_EBITDA → 높을수록 좋음
    result["수익수익률"] = 1.0 / result["EV_EBITDA_사용"]

    # 랭킹 (낮을수록 = 상위권)
    result["EY_랭크"] = result["수익수익률"].rank(ascending=False)
    result["ROIC_랭크"] = result["ROIC_사용"].rank(ascending=False)
    result["Magic_랭크합"] = result["EY_랭크"] + result["ROIC_랭크"]

    # Top N 선정
    top_n = cfg.get("top_n", 30)
    result = result.nsmallest(top_n, "Magic_랭크합")

    # 정규화 점수 (랭크합이 낮을수록 좋음 → 역수)
    result["Greenblatt_점수"] = _normalize(1 / result["Magic_랭크합"])

    output_cols = ["종목코드", "종목명", "마켓분야", "FICS분야",
                   "수익수익률", "ROIC_사용", "EY_랭크", "ROIC_랭크",
                   "Magic_랭크합", "Greenblatt_점수"]
    if "부채비율_사용" in result.columns:
        output_cols.insert(5, "부채비율_사용")
    output_cols = [c for c in output_cols if c in result.columns]

    print(f"  📊 Greenblatt 전략: {len(result)}개 종목 선정")
    return result[output_cols].rename(columns={
        "ROIC_사용": "ROIC(%)",
        "부채비율_사용": "부채비율(%)",
    })
