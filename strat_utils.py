# strat_utils.py
# 전략 모듈 공통 유틸리티
# - FnGuide Excel 파일 로딩 (load_all_data, merge_base)
# - 공식 API 원천 데이터 로딩: DART 재무상태표, 시가총액 (선택, 파일이 있으면 병합)
# - 공통 종목 필터 (apply_common_filters)
# - 동적 컬럼 탐색 헬퍼 (_recent_cols, _best_col)
# - 정규화 헬퍼 (_normalize)

import os
import glob
import re
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

    # 경로에 '*'가 있으면 가장 최근 파일을 쓴다 (예: derived/snapshot_2*.xlsx → snapshot_2026_11.xlsx)
    config = dict(config)
    for k in ("snapshot_file", "invest_idx_file", "finance_file", "ratio_file"):
        if config.get(k) and "*" in config[k]:
            config[k] = _latest_file(config[k]) or config[k]

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

    # --- 공식 API 원천 데이터 (선택) — apiCollect.py 실행 결과 ---
    for key, cfg_key, label in [("dart_balance", "dart_balance_file", "DART 재무상태표"),
                                ("market_cap", "market_cap_file", "시가총액")]:
        path = _latest_file(config.get(cfg_key))
        if path:
            df = pd.read_excel(path, dtype={"종목코드": str})
            df["종목코드"] = df["종목코드"].str.zfill(6)
            data[key] = df
            print(f"  ✅ {label}: {path} ({len(df)}개 종목)")
        else:
            print(f"  ℹ️  {label} 파일 없음 ({config.get(cfg_key)}) → python apiCollect.py 로 수집")

    return data


def _latest_file(pattern):
    """경로 또는 glob 패턴에서 가장 최근 파일을 반환한다 (테스트 산출물 *_test.xlsx 제외)."""
    if not pattern:
        return None
    if "*" not in pattern:
        return pattern if os.path.exists(pattern) else None
    files = sorted(f for f in glob.glob(pattern) if not f.endswith("_test.xlsx"))
    return files[-1] if files else None


# DART 재무상태표에서 base에 합칠 컬럼 (DART_ 접두어로 FnGuide 컬럼과 구분)
DART_BALANCE_COLS = ["기준기간", "연결구분", "유동구분", "유동자산", "부채총계", "자본총계", "비지배지분",
                     "현금및현금성자산", "유동금융자산", "장기금융자산", "유동금융자산_기타", "장기금융자산_기타",
                     "이자부부채", "리스부채", "당기순이익(누적)"]
MARKET_CAP_COLS = ["시가총액_억원", "종가", "전일종가", "상장주식수", "거래량", "거래대금_억원", "기준일", "출처"]


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

    # DART 재무상태표 (있으면)
    if "dart_balance" in data:
        bal = data["dart_balance"]
        cols = [c for c in DART_BALANCE_COLS if c in bal.columns]
        bal = bal[["종목코드"] + cols].rename(columns={c: f"DART_{c}" for c in cols})
        base = base.merge(bal, on="종목코드", how="left")

    # 시가총액 (있으면)
    if "market_cap" in data:
        mc = data["market_cap"]
        cols = [c for c in MARKET_CAP_COLS if c in mc.columns]
        base = base.merge(mc[["종목코드"] + cols], on="종목코드", how="left")

    return base


# =============================================================================
# 공통 필터
# =============================================================================

def apply_common_filters(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    """모든 전략에 공통으로 적용하는 필터"""
    original = len(df)

    # SPAC 제외
    if config.get("exclude_spac", True):
        df = df[~df["종목명"].str.contains("스팩|SPAC", na=False)]

    # 최소 시가총액 필터: 실제 시가총액(시가총액_억원)이 있으면 그것을 쓰고,
    # 없으면 snapshot의 PBR × BPS × 주식수로 추정
    pbr_col = _best_col(df, _recent_cols(df, "_PBR(배)"))
    bps_col = _best_col(df, _recent_cols(df, "_BPS(원)"))
    if "발행주식수(천주)" in df.columns and pbr_col and bps_col:
        df["추정시가총액_억"] = (
            pd.to_numeric(df[pbr_col], errors="coerce") *
            pd.to_numeric(df[bps_col], errors="coerce") *
            pd.to_numeric(df["발행주식수(천주)"], errors="coerce") *
            1_000 / 1_0000_0000
        )
    # 종목별로 실제 시가총액 우선, 없으면 추정값
    cap = pd.Series(np.nan, index=df.index)
    if "시가총액_억원" in df.columns:
        cap = pd.to_numeric(df["시가총액_억원"], errors="coerce")
    if "추정시가총액_억" in df.columns:
        cap = cap.fillna(df["추정시가총액_억"])
    min_cap = config.get("min_market_cap_억", 0)
    if min_cap > 0 and cap.notna().any():
        df = df[cap.fillna(0) >= min_cap]

    # 거래 없는 종목 제외: 기준일 거래량이 0인 종목(거래정지 등)은 시가총액이 오래된 가격일 수 있다
    if config.get("exclude_no_trade", True) and "거래량" in df.columns:
        vol = pd.to_numeric(df["거래량"], errors="coerce")
        n0 = int((vol == 0).sum())
        df = df[~(vol == 0)]
        if n0:
            print(f"  🔍 거래량 0 종목 제외: {n0}개")
    min_tv = config.get("min_trading_value_억", 0)
    if min_tv and "거래대금_억원" in df.columns:
        df = df[pd.to_numeric(df["거래대금_억원"], errors="coerce").fillna(0) >= min_tv]

    print(f"  🔍 공통 필터: {original}개 → {len(df)}개")
    return df


# =============================================================================
# 헬퍼 함수
# =============================================================================

def _recent_cols(df: pd.DataFrame, suffix: str, n: int = 3) -> list:
    """
    컬럼명이 '{YYYY}{suffix}' 패턴인 것을 연도 내림차순으로 최대 n개 반환.

    예) suffix="_PER(배)"         → ["2025_PER(배)", "2024_PER(배)", ...]
        suffix="(누적)_EPS증가율" → ["2025(누적)_EPS증가율", "2024(누적)_EPS증가율", ...]
    """
    pattern = re.compile(r'^(\d{4})' + re.escape(suffix) + r'$')
    matched = sorted(
        ((int(m.group(1)), col)
         for col in df.columns
         if (m := pattern.match(col))),
        reverse=True,
    )
    return [col for _, col in matched[:n]]


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
