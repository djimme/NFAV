# strat_multifactor.py
# 멀티팩터 스코어링 전략 (팩터 표준점수 가중 합산)
#
# 이론:
#   단일 팩터 전략보다 여러 팩터를 결합할 때 리스크 조정 수익률이 안정적
#   (Fama-French, AQR 등 학술 연구 기반).
#   팩터별 표준점수를 가중 합산해 종합 점수 산출.
#
# 팩터 점수 출처 (agent_config.DATA_CONFIG["factor_source"]):
#   "dart"(기본)  DART·KRX 값으로 직접 계산 — python apiCollect.py factor (정의: krxFactor.py)
#     수익건전성_종목 (↑): ROE · ROA · 영업이익률
#     성장성_종목     (↑): 매출증가율 · EPS증가율
#     밸류_종목       (↑): E/P · B/P
#     모멘텀_종목     (↑): 12-1개월 수익률
#     변동성_종목     (↓): 월간 수익률 표준편차 (가중치 음수)
#   "fnguide"     FnGuide invest_idx 의 팩터 점수 (FnGuide 자체 모델, 산식 비공개)
#
# 가중치 (STRATEGY_CONFIG["multifactor"]["weights"] 참조):
#   수익건전성 0.25 / 성장성 0.25 / 밸류 0.20 / 모멘텀 0.15 / 변동성 -0.15
#
# 참고: 팩터 컬럼에는 연도 접두사가 없으므로 동적 탐색 불필요

import pandas as pd
from strat_utils import _normalize


def strategy_multifactor(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """
    팩터 점수(표준점수)를 가중 합산해 종합 점수를 산출합니다. (점수 출처는 파일 머리말 참고)

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

    output_cols = ["종목코드", "종목명", "마켓분야", "WI26분야", "KRICS섹터", "KRICS산업그룹"] + factor_cols + ["멀티팩터_점수", "팩터_출처"]
    output_cols = [c for c in output_cols if c in result.columns]

    print(f"  📊 멀티팩터 전략: {len(result)}개 종목 선정")
    return result[output_cols]
