# strat_piotroski.py
# Piotroski F-Score 전략
#
# 이론:
#   Joseph Piotroski (2000) 제안. 9개 이진 기준으로 재무 건전성 점수화.
#   F-Score 8~9: 강한 재무 건전성 / 0~2: 재무 부실 위험
#
# 9개 기준 (각 1점):
#   수익성 (4점):
#     F1. ROA > 0                          (자산 대비 이익 창출 능력)
#     F2. 영업활동현금흐름 > 0              (실제 현금 창출)
#     F3. ROA 전년 대비 증가               (수익성 개선)
#     F4. 영업CF > 당기순이익              (발생주의 품질, 이익 조작 방지)
#   레버리지/유동성 (3점):
#     F5. 부채비율 전년 대비 감소          (재무 구조 개선)
#     F6. 유동비율 전년 대비 증가          (단기 유동성 개선)
#     F7. 신주 발행 없음                   (데이터 미제공 → 생략, 0 처리)
#   운영 효율성 (2점):
#     F8. 영업이익률 전년 대비 개선
#     F9. 총자산회전율 전년 대비 개선      (자산 활용 효율 개선)
#
# 동적 컬럼 선택:
#   _recent_cols(suffix, n=2) → [현재연도_컬럼, 전년도_컬럼] 자동 탐색
#   _latest_values([...], n=2) → 연간 현금흐름·순이익은 종목별로 값이 있는 가장 최근 연도 사용
#
# 필터 조건 (STRATEGY_CONFIG["piotroski"] 참조):
#   - F-Score >= min_score (기본값 6)

import pandas as pd
from strat_utils import _recent_cols, _latest_values, _normalize


def strategy_piotroski(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """
    Piotroski F-Score (0~9점) 계산.
    9가지 재무 건전성 기준을 이진 점수(0/1)로 평가.
    """
    result = df.copy()

    # --- 컬럼 동적 탐색: _recent_cols()로 연도 무관하게 최신/전년 자동 선택 ---
    def _pair(suffix):
        cols = _recent_cols(result, suffix, n=2)
        return (cols[0] if cols else None,
                cols[1] if len(cols) > 1 else None)

    roa_cur,  roa_prev  = _pair("(누적)_ROA")
    debt_cur, debt_prev = _pair("(누적)_부채비율")
    cur_cur,  cur_prev  = _pair("(누적)_유동비율")
    opm_cur,  opm_prev  = _pair("(누적)_영업이익률")
    ato_cur,  ato_prev  = _pair("(누적)_총자산회전율")
    # 연간 현금흐름·순이익은 종목별로 값이 있는 가장 최근 연도(최근 2개 연도 안)를 쓴다.
    # 결산월이 다른 몇 종목만 채워진 최신 연도 열 때문에 나머지 종목이 결측이 되는 것을 막는다.
    CF, NI = "(연간)_영업활동현금흐름", "(연간)_당기순이익"
    annual, annual_year = _latest_values(result, [CF, NI], n=2)
    cf_v, ni_v = annual[CF], annual[NI]

    scores = pd.DataFrame(index=result.index)

    # F1: ROA > 0
    if roa_cur:
        scores["F1_ROA양수"] = (pd.to_numeric(result[roa_cur], errors="coerce") > 0).astype(int)
    else:
        scores["F1_ROA양수"] = 0

    # F2: 영업현금흐름 > 0
    scores["F2_현금흐름양수"] = (cf_v > 0).astype(int)

    # F3: ROA 증가
    if roa_cur and roa_prev and roa_cur != roa_prev:
        scores["F3_ROA증가"] = (
            pd.to_numeric(result[roa_cur], errors="coerce") >
            pd.to_numeric(result[roa_prev], errors="coerce")
        ).astype(int)
    else:
        scores["F3_ROA증가"] = 0

    # F4: 영업CF > 당기순이익 (발생주의 품질)
    scores["F4_현금흐름품질"] = (cf_v > ni_v).astype(int)

    # F5: 부채비율 감소
    if debt_cur and debt_prev and debt_cur != debt_prev:
        scores["F5_부채감소"] = (
            pd.to_numeric(result[debt_cur], errors="coerce") <
            pd.to_numeric(result[debt_prev], errors="coerce")
        ).astype(int)
    else:
        scores["F5_부채감소"] = 0

    # F6: 유동비율 증가
    if cur_cur and cur_prev and cur_cur != cur_prev:
        scores["F6_유동비율증가"] = (
            pd.to_numeric(result[cur_cur], errors="coerce") >
            pd.to_numeric(result[cur_prev], errors="coerce")
        ).astype(int)
    else:
        scores["F6_유동비율증가"] = 0

    # F7: 신주발행 없음 → 데이터 없어 생략 (0 처리)
    scores["F7_신주없음"] = 0

    # F8: 영업이익률 개선
    if opm_cur and opm_prev and opm_cur != opm_prev:
        scores["F8_영업이익률개선"] = (
            pd.to_numeric(result[opm_cur], errors="coerce") >
            pd.to_numeric(result[opm_prev], errors="coerce")
        ).astype(int)
    else:
        scores["F8_영업이익률개선"] = 0

    # F9: 총자산회전율 개선
    if ato_cur and ato_prev and ato_cur != ato_prev:
        scores["F9_자산회전율개선"] = (
            pd.to_numeric(result[ato_cur], errors="coerce") >
            pd.to_numeric(result[ato_prev], errors="coerce")
        ).astype(int)
    else:
        scores["F9_자산회전율개선"] = 0

    result["F_Score"] = scores.sum(axis=1)
    result["연간기준연도"] = annual_year.astype("Int64")

    # 필터
    min_score = cfg.get("min_score", 6)
    result = result[result["F_Score"] >= min_score].copy()
    result = result.sort_values("F_Score", ascending=False)

    # 정규화 점수
    if len(result) > 0:
        result["Piotroski_점수"] = _normalize(result["F_Score"].astype(float))

    # 세부 점수 합산용 컬럼도 붙이기
    for col in scores.columns:
        result[col] = scores.loc[result.index, col]

    output_cols = (["종목코드", "종목명", "마켓분야", "WI26분야", "KRICS섹터", "KRICS산업그룹", "F_Score", "Piotroski_점수"]
                   + list(scores.columns) + ["연간기준연도"])
    output_cols = [c for c in output_cols if c in result.columns]

    print(f"  📊 Piotroski 전략: {len(result)}개 종목 선정 (F-Score ≥ {min_score})")
    return result[output_cols]
