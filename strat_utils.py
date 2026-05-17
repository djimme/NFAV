# strat_utils.py
# 전략 모듈 공통 유틸리티
# - FnGuide Excel 파일 로딩 (load_all_data, merge_base)
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
# 공통 필터
# =============================================================================

def apply_common_filters(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    """모든 전략에 공통으로 적용하는 필터"""
    original = len(df)

    # SPAC 제외
    if config.get("exclude_spac", True):
        df = df[~df["종목명"].str.contains("스팩|SPAC", na=False)]

    # 최소 시가총액 필터 (snapshot의 BPS * 발행주식수로 근사)
    # 직접 시가총액 컬럼이 없으므로 PBR × BPS × 주식수로 추정
    pbr_col = _best_col(df, _recent_cols(df, "_PBR(배)"))
    bps_col = _best_col(df, _recent_cols(df, "_BPS(원)"))
    if "발행주식수(천주)" in df.columns and pbr_col and bps_col:
        df["추정시가총액_억"] = (
            pd.to_numeric(df[pbr_col], errors="coerce") *
            pd.to_numeric(df[bps_col], errors="coerce") *
            pd.to_numeric(df["발행주식수(천주)"], errors="coerce") *
            1_000 / 1_0000_0000
        )
        min_cap = config.get("min_market_cap_억", 0)
        if min_cap > 0:
            df = df[df["추정시가총액_억"].fillna(0) >= min_cap]

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
