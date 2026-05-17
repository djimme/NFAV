# strat_multifactor.py
# 멀티팩터 스코어링 전략 (FnGuide 팩터 Z-Score 활용)
#
# 이론:
#   단일 팩터 전략보다 여러 팩터를 결합할 때 리스크 조정 수익률이 안정적
#   (Fama-French, AQR 등 학술 연구 기반).
#   FnGuide가 제공하는 팩터별 Z-Score를 가중 합산해 종합 점수 산출.
#
# 사용 팩터 (FnGuide 투자지표 — 종목 기준):
#   수익건전성_종목 (↑): 이익의 안정성·지속성 (ROE, ROA 변동성 등)
#   성장성_종목     (↑): 매출/이익 성장성
#   밸류_종목       (↑): 저평가 정도 (PBR, PER, PSR 등 역수 합산)
#   모멘텀_종목     (↑): 과거 가격 모멘텀 (3~12개월)
#   변동성_종목     (↓): 낮을수록 안정적 (가중치 음수)
#
# 가중치 (STRATEGY_CONFIG["multifactor"]["weights"] 참조):
#   수익건전성 0.25 / 성장성 0.25 / 밸류 0.20 / 모멘텀 0.15 / 변동성 -0.15
#
# 참고: 팩터 컬럼에는 연도 접두사가 없으므로 동적 탐색 불필요

import pandas as pd
from strat_utils import _normalize


def strategy_multifactor(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """
    FnGuide에서 제공하는 팩터 점수(Z-score)를 가중 합산해 종합 점수를 산출합니다.

    팩터 (종목 기준):
        수익건전성_종목 (↑) : 이익의 안정성/지속성
        성장성_종목     (↑) : 매출/이익 성장성
        밸류_종목       (↑) : 저평가 (PBR, PER 등)
        모멘텀_종목     (↑) : 가격 모멘텀
        변동성_종목     (↓) : 낮을수록 안정적
    """
    result = df.copy()
    weights = cfg.get("weights", {
        "수익건전성": 0.25, "성장성": 0.25, "밸류": 0.20,
        "모멘텀": 0.15, "변동성": -0.15
    })

    factor_map = {
        "수익건전성": "수익건전성_종목",
        "성장성":     "성장성_종목",
        "밸류":       "밸류_종목",
        "모멘텀":     "모멘텀_종목",
        "변동성":     "변동성_종목",
    }

    # 팩터 컬럼 존재 확인
    missing = [col for col in factor_map.values() if col not in result.columns]
    if missing:
        print(f"  ⚠️ 멀티팩터: 일부 팩터 없음 → {missing}")

    # 점수 계산
    result["멀티팩터_점수"] = 0.0
    for factor_name, col in factor_map.items():
        if col in result.columns:
            w = weights.get(factor_name, 0)
            result["멀티팩터_점수"] += w * pd.to_numeric(result[col], errors="coerce").fillna(0)

    # 결측 종목 제거
    factor_cols = [c for c in factor_map.values() if c in result.columns]
    result = result.dropna(subset=factor_cols[:2])  # 최소 2개 팩터 필요

    # Top N
    top_n = cfg.get("top_n", 30)
    result = result.nlargest(top_n, "멀티팩터_점수")
    result["멀티팩터_점수"] = _normalize(result["멀티팩터_점수"])

    output_cols = ["종목코드", "종목명", "마켓분야", "FICS분야"] + factor_cols + ["멀티팩터_점수"]
    output_cols = [c for c in output_cols if c in result.columns]

    print(f"  📊 멀티팩터 전략: {len(result)}개 종목 선정")
    return result[output_cols]
