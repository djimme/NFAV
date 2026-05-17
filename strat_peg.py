# strat_peg.py
# PEG 전략 — Peter Lynch 스타일
#
# 이론:
#   PEG = PER / EPS 연간 성장률(%)
#   Lynch: PEG < 1 → 성장 대비 저평가, 매력적인 매수 기회
#   PEG < 0.5 → 매우 매력적 / PEG 1~2 → 적정 / PEG > 2 → 과대평가
#
# EPS 성장률 계산 방법 (우선순위):
#   1. 3년 CAGR: (EPS_최신 / EPS_3년전)^(1/3) - 1  [절대값 EPS 4개년 필요]
#      → 단일 연도 변동에 덜 민감, 이론에 가장 부합
#   2. Fallback: 최근 3개년 연간 EPS증가율 평균
#      → invest_idx의 (누적)_EPS증가율 컬럼 활용
#
# 필터 조건 (STRATEGY_CONFIG["peg"] 참조):
#   - PEG > 0 and PEG <= max_peg (기본값 1.0)
#   - EPS 성장률 > min_eps_growth (기본값 0%)
#   - PER > 0
#   - 부채비율 <= max_debt_ratio (기본값 100%)
#
# 출력:
#   PER, EPS증가율(%), PEG, 부채비율(%), PEG_점수(0~1 정규화)

import numpy as np
import pandas as pd
from strat_utils import _recent_cols, _best_col, _normalize


def strategy_peg(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """
    PEG = PER / EPS증가율
    낮을수록 성장 대비 저평가. Lynch는 PEG < 1을 매력적으로 봄.
    """
    result = df.copy()

    # --- 컬럼 동적 탐색 (연도 하드코딩 없음) ---
    per_col  = _best_col(result, _recent_cols(result, "_PER(배)"))
    debt_col = _best_col(result, _recent_cols(result, "(누적)_부채비율"))

    if not per_col:
        print("  ⚠️ PEG 전략: PER 컬럼 없음")
        return pd.DataFrame()

    result["PER_사용"] = pd.to_numeric(result[per_col], errors="coerce")

    # EPS 성장률: 3년 CAGR 우선 (invest_idx의 절대값 EPS 활용)
    # 컬럼명은 파서에 따라 "{year}_EPS(원)" 또는 "{year}_EPS" 두 가지 가능
    eps_abs_cols = _recent_cols(result, "_EPS(원)", n=4) or _recent_cols(result, "_EPS", n=4)
    if len(eps_abs_cols) >= 4:
        eps_new = pd.to_numeric(result[eps_abs_cols[0]], errors="coerce")
        eps_old = pd.to_numeric(result[eps_abs_cols[3]], errors="coerce")
        valid   = (eps_new > 0) & (eps_old > 0)
        result["EPS증가율_사용"] = np.nan
        result.loc[valid, "EPS증가율_사용"] = (
            ((eps_new[valid] / eps_old[valid]) ** (1 / 3) - 1) * 100
        )
        eps_method = "3yr CAGR"
    else:
        # fallback: 최근 3개년 연간 EPS증가율 평균
        eps_gr_cols = _recent_cols(result, "(누적)_EPS증가율", n=3)
        if not eps_gr_cols:
            print("  ⚠️ PEG 전략: EPS 데이터 없음")
            return pd.DataFrame()
        result["EPS증가율_사용"] = (
            result[eps_gr_cols].apply(pd.to_numeric, errors="coerce").mean(axis=1)
        )
        eps_method = f"{len(eps_gr_cols)}yr평균"

    result["PEG"] = result["PER_사용"] / result["EPS증가율_사용"]

    # 부채비율
    if debt_col:
        result["부채비율_사용"] = pd.to_numeric(result[debt_col], errors="coerce")
    else:
        result["부채비율_사용"] = np.nan

    # 필터링
    max_peg = cfg.get("max_peg", 1.0)
    max_debt = cfg.get("max_debt_ratio", 100.0)
    min_eps = cfg.get("min_eps_growth", 0.0)

    mask = (
        result["PEG"].notna() &
        (result["PEG"] > 0) &
        (result["PEG"] <= max_peg) &
        (result["EPS증가율_사용"] > min_eps) &
        (result["PER_사용"] > 0)
    )
    if debt_col:
        mask &= (result["부채비율_사용"].fillna(999) <= max_debt)

    result = result[mask].copy()

    # 점수: PEG가 낮을수록 좋음 → 역수로 정규화
    if len(result) > 0:
        result["PEG_점수"] = 1 / result["PEG"]
        result["PEG_점수"] = _normalize(result["PEG_점수"])
        result = result.sort_values("PEG_점수", ascending=False)

    output_cols = ["종목코드", "종목명", "마켓분야", "FICS분야",
                   "PER_사용", "EPS증가율_사용", "PEG", "부채비율_사용", "PEG_점수"]
    output_cols = [c for c in output_cols if c in result.columns]

    print(f"  📊 PEG 전략: {len(result)}개 종목 선정 (EPS성장률: {eps_method})")
    return result[output_cols].rename(columns={
        "PER_사용": f"PER({per_col[:4]})",
        "EPS증가율_사용": f"EPS증가율(%,{eps_method})",
        "부채비율_사용": "부채비율(%)"
    })
