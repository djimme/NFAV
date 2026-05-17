# agent_strategies.py
# 전략 통합 진입점
#
# 개별 전략: strat_peg.py, strat_piotroski.py, strat_greenblatt.py,
#             strat_multifactor.py, strat_ncav_nfav.py
# 공통 유틸리티: strat_utils.py
#
# 새 전략 추가 방법:
#   1. strat_{전략명}.py 파일 생성
#   2. 이 파일에 import 한 줄 추가
#   3. run_all_strategies()에 실행 블록 추가

import numpy as np
import pandas as pd

from strat_utils import load_all_data, merge_base, apply_common_filters
from strat_peg import strategy_peg
from strat_piotroski import strategy_piotroski
from strat_greenblatt import strategy_greenblatt
from strat_multifactor import strategy_multifactor
from strat_ncav_nfav import strategy_ncav_nfav


# =============================================================================
# 종합 스코어링 & 최종 종목 선정
# =============================================================================

def build_composite_score(
    base_df: pd.DataFrame,
    peg_df: pd.DataFrame,
    piotroski_df: pd.DataFrame,
    greenblatt_df: pd.DataFrame,
    multifactor_df: pd.DataFrame,
    ncav_df: pd.DataFrame,
    nfav_df: pd.DataFrame,
    weights: dict,
) -> pd.DataFrame:
    """
    각 전략 결과를 base_df에 LEFT JOIN해 종합 점수를 산출합니다.

    점수가 있는 전략에만 가중치 적용.
    """
    result = base_df[["종목코드", "종목명", "마켓분야", "FICS분야"]].copy()

    joins = [
        (peg_df,        "PEG_점수",         "peg"),
        (piotroski_df,  "Piotroski_점수",   "piotroski"),
        (greenblatt_df, "Greenblatt_점수",  "greenblatt"),
        (multifactor_df,"멀티팩터_점수",    "multifactor"),
    ]

    for df_, score_col, key in joins:
        if not df_.empty and score_col in df_.columns:
            sub = df_[["종목코드", score_col]].copy()
            result = result.merge(sub, on="종목코드", how="left")
        else:
            result[score_col] = np.nan

    # NCAV/NFAV 점수
    for df_, score_col, key in [(ncav_df, "NCAV_점수", "ncav"),
                                  (nfav_df, "NFAV_점수", "nfav")]:
        if not df_.empty and score_col in df_.columns:
            sub = df_[["종목코드", score_col]].copy()
            result = result.merge(sub, on="종목코드", how="left")
        else:
            result[score_col if score_col not in result.columns else score_col + "_x"] = np.nan

    # 종합 점수 계산 (참여 전략 수로 정규화)
    score_cols_map = {
        "PEG_점수":        weights.get("peg", 0.20),
        "Piotroski_점수":  weights.get("piotroski", 0.25),
        "Greenblatt_점수": weights.get("greenblatt", 0.25),
        "멀티팩터_점수":   weights.get("multifactor", 0.20),
        "NCAV_점수":       weights.get("ncav", 0.05),
        "NFAV_점수":       weights.get("nfav", 0.05),
    }

    result["종합점수"] = 0.0
    result["참여전략수"] = 0
    total_weight = 0.0

    for col, w in score_cols_map.items():
        if col in result.columns:
            has_score = result[col].notna()
            result.loc[has_score, "종합점수"] += result.loc[has_score, col] * w
            result.loc[has_score, "참여전략수"] += 1
            total_weight += w

    # 최소 1개 전략에 포함된 종목만
    result = result[result["참여전략수"] >= 1].copy()
    result = result.sort_values("종합점수", ascending=False)

    return result


# =============================================================================
# 전략 실행 통합 함수
# =============================================================================

def run_all_strategies(config: dict, strategy_cfg: dict, composite_weights: dict,
                       common_filter_cfg: dict) -> dict:
    """
    모든 전략을 순서대로 실행하고 결과를 dict로 반환합니다.

    Returns:
        {
            'peg': DataFrame,
            'piotroski': DataFrame,
            'greenblatt': DataFrame,
            'multifactor': DataFrame,
            'ncav': DataFrame,
            'nfav': DataFrame,
            'composite': DataFrame,  # 종합 랭킹
        }
    """
    print("\n" + "="*60)
    print("📈 전략 분석 시작")
    print("="*60)

    # 1. 데이터 로드
    data = load_all_data(config)
    base = merge_base(data)
    base = apply_common_filters(base, common_filter_cfg)

    results = {}

    # 2. 각 전략 실행
    print("\n[1/5] PEG 전략 (Peter Lynch)")
    results["peg"] = strategy_peg(base, strategy_cfg.get("peg", {})) \
        if strategy_cfg.get("peg", {}).get("enabled", True) else pd.DataFrame()

    print("\n[2/5] Piotroski F-Score")
    results["piotroski"] = strategy_piotroski(base, strategy_cfg.get("piotroski", {})) \
        if strategy_cfg.get("piotroski", {}).get("enabled", True) else pd.DataFrame()

    print("\n[3/5] Greenblatt Magic Formula")
    results["greenblatt"] = strategy_greenblatt(base, strategy_cfg.get("greenblatt", {})) \
        if strategy_cfg.get("greenblatt", {}).get("enabled", True) else pd.DataFrame()

    print("\n[4/5] 멀티팩터 스코어링")
    results["multifactor"] = strategy_multifactor(base, strategy_cfg.get("multifactor", {})) \
        if strategy_cfg.get("multifactor", {}).get("enabled", True) else pd.DataFrame()

    print("\n[5/5] NCAV / NFAV (Benjamin Graham)")
    ncav_df, nfav_df = strategy_ncav_nfav(config)
    results["ncav"] = ncav_df
    results["nfav"] = nfav_df

    # 3. 종합 스코어
    print("\n[종합] 전략 결과 통합 중...")
    results["composite"] = build_composite_score(
        base_df=base,
        peg_df=results["peg"],
        piotroski_df=results["piotroski"],
        greenblatt_df=results["greenblatt"],
        multifactor_df=results["multifactor"],
        ncav_df=results["ncav"],
        nfav_df=results["nfav"],
        weights=composite_weights,
    )

    n_composite = len(results["composite"])
    print(f"\n✅ 종합 종목 리스트: {n_composite}개 종목 (1개 이상 전략 통과)")

    return results
