# agent_strategies.py
# 주식 종목 선정 전략 모음
# 각 전략은 DataFrame을 받아 점수/랭킹이 추가된 DataFrame을 반환합니다.
#
# 수록 전략:
#   1. PEG  - Peter Lynch 스타일
#   2. Piotroski F-Score
#   3. Greenblatt Magic Formula
#   4. Multi-Factor Scoring (FnGuide 팩터)
#   5. NCAV / NFAV - Benjamin Graham 스타일 (calc_NCAV.py 결과 활용)

import os
import glob
import warnings
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")


# =============================================================================
# 데이터 로더
# =============================================================================

def load_all_data(config: dict) -> dict:
    """
    4개의 xlsx 파일을 로드하고 제조업 시트를 기준으로 합칩니다.
    재무비율/재무제표는 모든 업종 시트를 수직으로 합칩니다.

    Returns:
        {
            'snapshot': DataFrame,
            'finance': DataFrame,   (모든 업종 합산)
            'ratio':   DataFrame,   (모든 업종 합산)
            'invest':  DataFrame,
        }
    """
    print("📂 데이터 파일 로딩 중...")

    data = {}

    # snapshot (단일 시트)
    snap_path = config["snapshot_file"]
    if os.path.exists(snap_path):
        data["snapshot"] = pd.read_excel(snap_path, dtype={"종목코드": str})
        data["snapshot"]["종목코드"] = data["snapshot"]["종목코드"].str.zfill(6)
        print(f"  ✅ snapshot: {len(data['snapshot'])}개 종목")
    else:
        raise FileNotFoundError(f"snapshot 파일 없음: {snap_path}")

    # invest_idx (단일 시트)
    inv_path = config["invest_idx_file"]
    if os.path.exists(inv_path):
        data["invest"] = pd.read_excel(inv_path, dtype={"종목코드": str})
        data["invest"]["종목코드"] = data["invest"]["종목코드"].str.zfill(6)
        print(f"  ✅ invest_idx: {len(data['invest'])}개 종목")
    else:
        raise FileNotFoundError(f"invest_idx 파일 없음: {inv_path}")

    # finance (여러 업종 시트 합산)
    fin_path = config["finance_file"]
    if os.path.exists(fin_path):
        fin_sheets = pd.read_excel(fin_path, sheet_name=None, dtype={"종목코드": str})
        fin_df = pd.concat(fin_sheets.values(), ignore_index=True)
        fin_df["종목코드"] = fin_df["종목코드"].str.zfill(6)
        data["finance"] = fin_df
        print(f"  ✅ finance: {len(fin_df)}개 종목")
    else:
        raise FileNotFoundError(f"finance 파일 없음: {fin_path}")

    # ratio (여러 업종 시트 합산)
    rat_path = config["ratio_file"]
    if os.path.exists(rat_path):
        rat_sheets = pd.read_excel(rat_path, sheet_name=None, dtype={"종목코드": str})
        rat_df = pd.concat(rat_sheets.values(), ignore_index=True)
        rat_df["종목코드"] = rat_df["종목코드"].str.zfill(6)
        data["ratio"] = rat_df
        print(f"  ✅ ratio: {len(rat_df)}개 종목")
    else:
        raise FileNotFoundError(f"ratio 파일 없음: {rat_path}")

    return data


def merge_base(data: dict) -> pd.DataFrame:
    """
    snapshot을 기준으로 나머지 데이터를 LEFT JOIN합니다.
    모든 전략의 공통 베이스 DataFrame이 됩니다.
    """
    base = data["snapshot"].copy()

    # finance: 핵심 컬럼만 선택 (최근 연간 영업활동현금흐름, 당기순이익)
    fin = data["finance"]
    fin_cols = ["종목코드"] + [c for c in fin.columns if "영업활동현금흐름" in c or "당기순이익" in c]
    fin_cols = list(dict.fromkeys(fin_cols))  # 중복 제거
    base = base.merge(fin[fin_cols], on="종목코드", how="left")

    # ratio: 핵심 컬럼만 선택
    rat = data["ratio"]
    keep_keywords = ["부채비율", "유동비율", "ROA", "ROE", "ROIC",
                     "EPS증가율", "영업이익률", "총자산회전율", "매출증가율"]
    rat_cols = ["종목코드"] + [c for c in rat.columns
                               if any(k in c for k in keep_keywords)]
    rat_cols = list(dict.fromkeys(rat_cols))
    base = base.merge(rat[rat_cols], on="종목코드", how="left")

    # invest_idx: 팩터 점수 및 밸류에이션
    inv = data["invest"]
    inv_keep = ["종목코드", "팩터_업종명",
                "베타_종목", "배당성_종목", "수익건전성_종목",
                "성장성_종목", "기업투자_종목", "모멘텀_종목",
                "밸류_종목", "변동성_종목", "단기 Reversal_종목"]
    # EV/EBITDA 컬럼 추가
    ev_cols = [c for c in inv.columns if "EV/EBITDA" in c]
    inv_keep += ev_cols
    inv_keep = [c for c in inv_keep if c in inv.columns]
    base = base.merge(inv[inv_keep], on="종목코드", how="left")

    return base


# =============================================================================
# 공통 필터 적용
# =============================================================================

def apply_common_filters(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    """모든 전략에 공통으로 적용하는 필터"""
    original = len(df)

    # SPAC 제외
    if config.get("exclude_spac", True):
        df = df[~df["종목명"].str.contains("스팩|SPAC", na=False)]

    # 최소 시가총액 필터 (snapshot의 BPS * 발행주식수로 근사)
    # 직접 시가총액 컬럼이 없으므로 PBR × BPS × 주식수로 추정
    if "발행주식수(천주)" in df.columns and "2025_PBR(배)" in df.columns and "2025_BPS(원)" in df.columns:
        df["추정시가총액_억"] = (
            pd.to_numeric(df["2025_PBR(배)"], errors="coerce") *
            pd.to_numeric(df["2025_BPS(원)"], errors="coerce") *
            pd.to_numeric(df["발행주식수(천주)"], errors="coerce") *
            1_000 / 1_0000_0000
        )
        min_cap = config.get("min_market_cap_억", 0)
        if min_cap > 0:
            df = df[df["추정시가총액_억"].fillna(0) >= min_cap]

    print(f"  🔍 공통 필터: {original}개 → {len(df)}개")
    return df


# =============================================================================
# 1. PEG 전략 (Peter Lynch)
# =============================================================================

def strategy_peg(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """
    PEG = PER / EPS증가율
    낮을수록 성장 대비 저평가. Lynch는 PEG < 1을 매력적으로 봄.

    사용 컬럼:
        2024_PER(배)         → snapshot
        2024(누적)_EPS증가율 → ratio
        2025(누적)_부채비율  → ratio
    """
    result = df.copy()

    # 컬럼 선택 (2024 기준 - 2025는 아직 미확정 종목 많음)
    per_col = _best_col(result, ["2024_PER(배)", "2023_PER(배)"])
    eps_gr_col = _best_col(result, ["2024(누적)_EPS증가율", "2023(누적)_EPS증가율"])
    debt_col = _best_col(result, ["2025(누적)_부채비율", "2024(누적)_부채비율"])

    if not per_col or not eps_gr_col:
        print("  ⚠️ PEG 전략: 필요 컬럼 없음")
        return pd.DataFrame()

    result["PER_사용"] = pd.to_numeric(result[per_col], errors="coerce")
    result["EPS증가율_사용"] = pd.to_numeric(result[eps_gr_col], errors="coerce")
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

    print(f"  📊 PEG 전략: {len(result)}개 종목 선정")
    return result[output_cols].rename(columns={
        "PER_사용": f"PER({per_col[:4]})",
        "EPS증가율_사용": "EPS증가율(%)",
        "부채비율_사용": "부채비율(%)"
    })


# =============================================================================
# 2. Piotroski F-Score
# =============================================================================

def strategy_piotroski(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """
    Piotroski F-Score (0~9점) 계산.
    9가지 재무 건전성 기준을 이진 점수(0/1)로 평가.

    수익성 (4점):
      F1. ROA > 0
      F2. 영업활동현금흐름 > 0
      F3. ROA 전년 대비 증가
      F4. 영업현금흐름 > 당기순이익 (발생주의 품질)

    레버리지/유동성 (3점):
      F5. 부채비율 감소
      F6. 유동비율 증가
      F7. 신주 발행 없음 (데이터 미제공 → 생략)

    운영 효율성 (2점):
      F8. 영업이익률 개선
      F9. 총자산회전율 개선
    """
    result = df.copy()

    # --- 컬럼 탐색 ---
    roa_cur  = _best_col(result, ["2025(누적)_ROA", "2024(누적)_ROA"])
    roa_prev = _best_col(result, ["2024(누적)_ROA", "2023(누적)_ROA"])
    debt_cur  = _best_col(result, ["2025(누적)_부채비율", "2024(누적)_부채비율"])
    debt_prev = _best_col(result, ["2024(누적)_부채비율", "2023(누적)_부채비율"])
    cur_cur   = _best_col(result, ["2025(누적)_유동비율", "2024(누적)_유동비율"])
    cur_prev  = _best_col(result, ["2024(누적)_유동비율", "2023(누적)_유동비율"])
    opm_cur   = _best_col(result, ["2025(누적)_영업이익률", "2024(누적)_영업이익률"])
    opm_prev  = _best_col(result, ["2024(누적)_영업이익률", "2023(누적)_영업이익률"])
    ato_cur   = _best_col(result, ["2025(누적)_총자산회전율", "2024(누적)_총자산회전율"])
    ato_prev  = _best_col(result, ["2024(누적)_총자산회전율", "2023(누적)_총자산회전율"])
    cf_col    = _best_col(result, ["2025(연간)_영업활동현금흐름", "2024(연간)_영업활동현금흐름"])
    ni_col    = _best_col(result, ["2025(연간)_당기순이익", "2024(연간)_당기순이익"])

    scores = pd.DataFrame(index=result.index)

    # F1: ROA > 0
    if roa_cur:
        scores["F1_ROA양수"] = (pd.to_numeric(result[roa_cur], errors="coerce") > 0).astype(int)
    else:
        scores["F1_ROA양수"] = 0

    # F2: 영업현금흐름 > 0
    if cf_col:
        scores["F2_현금흐름양수"] = (pd.to_numeric(result[cf_col], errors="coerce") > 0).astype(int)
    else:
        scores["F2_현금흐름양수"] = 0

    # F3: ROA 증가
    if roa_cur and roa_prev and roa_cur != roa_prev:
        scores["F3_ROA증가"] = (
            pd.to_numeric(result[roa_cur], errors="coerce") >
            pd.to_numeric(result[roa_prev], errors="coerce")
        ).astype(int)
    else:
        scores["F3_ROA증가"] = 0

    # F4: 영업CF > 당기순이익 (발생주의 품질)
    if cf_col and ni_col:
        cf_v = pd.to_numeric(result[cf_col], errors="coerce")
        ni_v = pd.to_numeric(result[ni_col], errors="coerce")
        scores["F4_현금흐름품질"] = (cf_v > ni_v).astype(int)
    else:
        scores["F4_현금흐름품질"] = 0

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

    output_cols = (["종목코드", "종목명", "마켓분야", "FICS분야", "F_Score", "Piotroski_점수"]
                   + list(scores.columns))
    output_cols = [c for c in output_cols if c in result.columns]

    print(f"  📊 Piotroski 전략: {len(result)}개 종목 선정 (F-Score ≥ {min_score})")
    return result[output_cols]


# =============================================================================
# 3. Greenblatt Magic Formula
# =============================================================================

def strategy_greenblatt(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """
    Magic Formula = 수익수익률(Earnings Yield) 랭킹 + 자본수익률(ROIC) 랭킹
    두 랭킹의 합이 낮은 종목이 우량.

    수익수익률 = 1 / EV/EBITDA   (높을수록 좋음)
    자본수익률 = ROIC             (높을수록 좋음)
    """
    result = df.copy()

    ev_col   = _best_col(result, ["2024_EV/EBITDA", "2023_EV/EBITDA"])
    roic_col = _best_col(result, ["2025(누적)_ROIC", "2024(누적)_ROIC"])
    debt_col = _best_col(result, ["2025(누적)_부채비율", "2024(누적)_부채비율"])

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


# =============================================================================
# 4. 멀티팩터 전략 (FnGuide 팩터 점수 활용)
# =============================================================================

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


# =============================================================================
# 5. NCAV / NFAV (Benjamin Graham)
# =============================================================================

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
# 유틸리티
# =============================================================================

def _best_col(df: pd.DataFrame, candidates: list) -> str | None:
    """후보 컬럼 중 DataFrame에 존재하는 첫 번째 반환"""
    for c in candidates:
        if c in df.columns:
            return c
    return None


def _normalize(series: pd.Series) -> pd.Series:
    """0~1 Min-Max 정규화"""
    s = pd.to_numeric(series, errors="coerce")
    mn, mx = s.min(), s.max()
    if mx == mn:
        return pd.Series(0.5, index=s.index)
    return (s - mn) / (mx - mn)


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
