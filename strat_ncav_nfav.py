# strat_ncav_nfav.py
# NCAV / NFAV 전략 — Benjamin Graham 계열 청산가치 + 순금융자산
#
# 데이터:
#   strat_utils.merge_base()가 합친 DART 재무상태표(DART_*)와 시가총액(시가총액_억원)을 사용한다.
#   (다른 전략과 같은 방식: base DataFrame을 받아 이 모듈 안에서 계산)
#   원천: python apiCollect.py dart_balance / krx_marketcap  (대체 시가총액: kb_marketcap)
#
# NCAV (Net Current Asset Value):
#   NCAV   = 유동자산 − 부채총계
#   NCAV_R = NCAV / 시가총액
#   NCAV_R > 1 → 시총 < 순유동자산 → 극단적 저평가 (Graham 권장 ≥ 1.5)
#
# NFAV (Net Financial Asset Value) — 두 가지를 함께 계산 (2026-11 결정)
#   금융자산 = 현금및현금성자산 + 유동금융자산 + 장기금융자산
#   A (보수적, nfav.py 기준) = 금융자산 − 부채총계 − 비지배지분
#       → 회사를 지금 정리해 모든 부채를 갚고 남는 금융자산. 사경인식 NCAV 변형
#   B (재무구조)             = 금융자산 − 이자부부채(차입금·사채·유동성장기부채·리스부채)
#       → 갚아야 할 차입보다 쥐고 있는 금융자산이 얼마나 많은가 (순현금)
#   선정: B > 0 (순현금 기업)으로 거른 뒤 A_R(= A / 시가총액) 높은 순
#   보수적 옵션(exclude_other_financial=True): 계정명에 '기타'가 붙은 금융자산(기타유동금융자산 등)을 뺀다
#       → 대여금·보증금처럼 바로 현금화하기 어려운 자산이 섞여 NFAV가 부풀려지는 것을 막는다
#
# 제외:
#   금융업(은행·증권·보험)은 재무상태표에 유동/비유동 구분이 없어 계산하지 않는다.
#
# 주의:
#   소형주·저유동성 종목 집중 경향 → 실제 매수 가능성 검토 필요.
#   창투사는 보유 지분의 공정가치가 금융자산에 크게 잡혀 NFAV가 과대해질 수 있다.

import numpy as np
import pandas as pd
from strat_utils import _normalize

_NEED = ["DART_유동자산", "DART_부채총계", "시가총액_억원"]


def _num(df, col):
    return pd.to_numeric(df[col], errors="coerce") if col in df.columns else pd.Series(np.nan, index=df.index)


def _prepare(df: pd.DataFrame) -> pd.DataFrame:
    """공통 입력값 정리: 유동/비유동 구분이 있는 기업만, 숫자 변환."""
    missing = [c for c in _NEED if c not in df.columns]
    if missing:
        print(f"  ⚠️ NCAV/NFAV: 필요 컬럼 없음 {missing} → apiCollect.py 로 DART·시가총액을 먼저 수집하세요.")
        return pd.DataFrame()
    r = df.copy()
    if "DART_유동구분" in r.columns:
        r = r[r["DART_유동구분"].astype(str).str.lower().isin(["true", "1"])]
    for c in ["DART_유동자산", "DART_부채총계", "DART_자본총계", "DART_비지배지분", "DART_현금및현금성자산",
              "DART_유동금융자산", "DART_장기금융자산", "DART_유동금융자산_기타", "DART_장기금융자산_기타",
              "DART_이자부부채", "DART_리스부채",
              "DART_당기순이익(누적)", "시가총액_억원"]:
        r[c] = _num(r, c)
    r = r[r["시가총액_억원"] > 0]
    r["부채비율"] = r["DART_부채총계"] / r["DART_자본총계"] * 100
    return r


def calc_ncav(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    r = _prepare(df)
    if r.empty:
        return r
    r = r[r["DART_유동자산"].notna() & r["DART_부채총계"].notna()]
    r["NCAV"] = r["DART_유동자산"] - r["DART_부채총계"]
    r["NCAV_R"] = r["NCAV"] / r["시가총액_억원"]
    r = r[r["NCAV_R"] > cfg.get("min_ncav_r", 0.0)]
    if cfg.get("require_positive_income", True):
        r = r[r["DART_당기순이익(누적)"] > 0]
    r = r.sort_values("NCAV_R", ascending=False)
    r["NCAV_점수"] = _normalize(r["NCAV_R"])
    cols = ["종목코드", "종목명", "DART_기준기간", "시가총액_억원", "DART_유동자산", "DART_부채총계",
            "NCAV", "NCAV_R", "DART_당기순이익(누적)", "NCAV_점수"]
    return r[[c for c in cols if c in r.columns]].reset_index(drop=True)


def calc_nfav(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    r = _prepare(df)
    if r.empty:
        return r
    r = r[r["DART_현금및현금성자산"].notna() & r["DART_부채총계"].notna()]
    r["금융자산"] = r["DART_현금및현금성자산"] + r["DART_유동금융자산"].fillna(0) + r["DART_장기금융자산"].fillna(0)
    r["기타금융자산"] = r["DART_유동금융자산_기타"].fillna(0) + r["DART_장기금융자산_기타"].fillna(0)
    if cfg.get("exclude_other_financial", False):
        r["금융자산"] = r["금융자산"] - r["기타금융자산"]
    r["NFAV_A"] = r["금융자산"] - r["DART_부채총계"] - r["DART_비지배지분"].fillna(0)
    r["NFAV_B"] = r["금융자산"] - r["DART_이자부부채"].fillna(0)
    r["NFAV_A_R"] = r["NFAV_A"] / r["시가총액_억원"]
    r["NFAV_B_R"] = r["NFAV_B"] / r["시가총액_억원"]

    # 1) 재무구조(B)로 거르기: 순현금 기업
    r = r[r["NFAV_B_R"] > cfg.get("min_nfav_b_r", 0.0)]
    # 2) 선택 필터
    if cfg.get("min_nfav_a_r") is not None:
        r = r[r["NFAV_A_R"] >= cfg["min_nfav_a_r"]]
    if cfg.get("max_debt_ratio"):
        r = r[r["부채비율"].fillna(999) <= cfg["max_debt_ratio"]]
    if cfg.get("require_positive_income", True):
        r = r[r["DART_당기순이익(누적)"] > 0]
    # 3) 보수적 가치(A)로 순위
    r = r.sort_values("NFAV_A_R", ascending=False)
    if cfg.get("top_n"):
        r = r.head(cfg["top_n"])
    r["NFAV_점수"] = _normalize(r["NFAV_A_R"])
    cols = ["종목코드", "종목명", "DART_기준기간", "시가총액_억원", "금융자산", "기타금융자산", "DART_부채총계", "DART_비지배지분",
            "DART_이자부부채", "NFAV_A", "NFAV_A_R", "NFAV_B", "NFAV_B_R", "부채비율",
            "DART_당기순이익(누적)", "NFAV_점수"]
    return r[[c for c in cols if c in r.columns]].reset_index(drop=True)


def strategy_ncav_nfav(df: pd.DataFrame, ncav_cfg: dict, nfav_cfg: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    base DataFrame(merge_base 결과)에서 NCAV와 NFAV(A/B)를 계산한다.
    반환: (ncav_df, nfav_df)
    """
    ncav_df = calc_ncav(df, ncav_cfg) if ncav_cfg.get("enabled", True) else pd.DataFrame()
    nfav_df = calc_nfav(df, nfav_cfg) if nfav_cfg.get("enabled", True) else pd.DataFrame()
    print(f"  ✅ NCAV 통과: {len(ncav_df)}개 · NFAV(B>0, A 순위) 통과: {len(nfav_df)}개")
    return ncav_df, nfav_df
