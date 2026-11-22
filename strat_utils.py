# strat_utils.py
# 전략 모듈 공통 유틸리티
# - FnGuide Excel 파일 로딩 (load_all_data, merge_base)
# - 공식 API 원천 데이터 로딩: DART 재무상태표, 시가총액 (선택, 파일이 있으면 병합)
# - 업종 분류 로딩: KRICS 섹터·산업그룹 (선택, sectorCollect.py 결과 파일이 있으면 병합)
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

    # --- 업종 분류 (선택) — python sectorCollect.py 실행 결과의 '종목분류' 시트 ---
    path = _latest_file(config.get("sector_map_file"))
    if path:
        df = pd.read_excel(path, sheet_name="종목분류", dtype=str)
        df["종목코드"] = df["종목코드"].str.zfill(6)
        data["sector_map"] = df
        print(f"  ✅ 업종 분류(KRICS): {path} ({len(df)}개 종목)")
    else:
        print(f"  ℹ️  업종 분류 파일 없음 ({config.get('sector_map_file')}) → python sectorCollect.py 로 수집")

    # --- DART로 직접 계산한 재무비율·주당 지표 (선택) — python apiCollect.py dart_ratio ---
    #   ratio_source 가 "dart" 이면 FnGuide snapshot·ratio·invest_idx 의 해당 값을 이 파일 값으로 바꾼다 (merge_base)
    if config.get("ratio_source") == "dart":
        path = _latest_file(config.get("dart_ratio_file"))
        if path:
            df = pd.read_excel(path, dtype={"종목코드": str})
            df["종목코드"] = df["종목코드"].str.zfill(6)
            data["dart_ratio"] = df
            data["dart_price_basis"] = config.get("dart_price_basis", "current")
            print(f"  ✅ DART 재무비율·주당 지표: {path} ({len(df)}개 종목, 주가 기준: {data['dart_price_basis']})")
        else:
            print(f"  ⚠️ DART 재무비율 파일 없음 ({config.get('dart_ratio_file')}) → FnGuide 값을 그대로 쓴다")

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
# 업종 분류 파일(sector_map)에서 base에 합칠 컬럼 — WI26분야는 snapshot 값을 그대로 쓴다
SECTOR_MAP_COLS = ["KRICS섹터", "KRICS산업그룹"]


def merge_base(data: dict) -> pd.DataFrame:
    """
    snapshot을 기준으로 나머지 데이터를 LEFT JOIN합니다.
    모든 전략의 공통 베이스 DataFrame이 됩니다.
    """
    base = data["snapshot"].copy()

    # 업종 분류 (있으면): KRICS섹터·KRICS산업그룹을 WI26분야 바로 뒤에 넣는다
    #   KRICS에 없는 종목(외국 법인·스팩 등)은 빈 값으로 남는다
    if "sector_map" in data:
        sm = data["sector_map"]
        cols = [c for c in SECTOR_MAP_COLS if c in sm.columns and c not in base.columns]
        base = base.merge(sm.drop_duplicates("종목코드")[["종목코드"] + cols], on="종목코드", how="left")
        if "WI26분야" in base.columns:
            at = base.columns.get_loc("WI26분야") + 1
            rest = [c for c in base.columns if c not in cols]
            base = base[rest[:at] + cols + rest[at:]]

    # finance: 핵심 컬럼만 선택 (최근 연간 영업활동현금흐름, 당기순이익)
    fin = data["finance"]
    fin_cols = ["종목코드"] + [c for c in fin.columns if "영업활동현금흐름" in c or "당기순이익" in c]
    fin_cols = list(dict.fromkeys(fin_cols))  # 중복 제거
    base = base.merge(fin[fin_cols], on="종목코드", how="left")

    # ratio: 핵심 컬럼만 선택
    rat = data["ratio"]
    keep_keywords = ["부채비율", "유동비율", "ROA", "ROE", "ROIC",
                     "EPS증가율", "영업이익률", "총자산회전율", "매출액증가율"]
    rat_cols = ["종목코드"] + [c for c in rat.columns
                               if any(k in c for k in keep_keywords)]
    rat_cols = list(dict.fromkeys(rat_cols))
    base = base.merge(rat[rat_cols], on="종목코드", how="left")

    # invest_idx: 팩터 점수 및 밸류에이션
    inv = data["invest"]
    inv_keep = ["종목코드", "팩터_업종명",
                "베타_종목", "배당성_종목", "수익건전성_종목",
                "성장성_종목", "기업투자_종목", "모멘텀_종목",
                "밸류_종목", "변동성_종목", "단기 Return_종목"]
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

    # DART 재무비율·주당 지표 (ratio_source = "dart" 일 때만)
    if "dart_ratio" in data:
        base = apply_dart_ratio(base, data["dart_ratio"], data.get("dart_price_basis", "current"))

    return base


# FnGuide 값 대신 DART 계산 값을 쓰는 지표 (컬럼 이름은 '{연도}{접미어}')
DART_RATIO_SUFFIXES = ("_EPS(원)", "_BPS(원)", "_PER(배)", "_PBR(배)", "(누적)_부채비율", "(누적)_유동비율",
                       "(누적)_영업이익률", "(누적)_ROA", "(누적)_ROE", "(누적)_총자산회전율", "(누적)_매출증가율",
                       "(누적)_EPS증가율", "(누적)_ROIC", "_EV/EBITDA", "_EV/EBIT")
_YEAR_COL = re.compile(r"^(\d{4})(?=[_(])")


def apply_dart_ratio(base: pd.DataFrame, dart: pd.DataFrame, price_basis: str = "current") -> pd.DataFrame:
    """
    base 의 FnGuide 재무비율·주당 지표 열을 DART 계산 값(dart_ratio 파일)으로 바꾼다.

    - FnGuide 쪽의 같은 지표 열은 연도와 관계없이 모두 뺀다 (2026·2027년 열은 증권사 추정치).
    - 종목마다 최근 사업연도가 다르다(3·6월 결산사는 2026, 12월 결산사는 2025). 전략은 '가장 최근 연도 열
      하나'를 전 종목에 쓰므로, 각 종목의 최근 사업연도 값을 기준연도(가장 많은 종목의 최근 사업연도) 열에
      맞춰 넣는다. 한 해 전 값은 기준연도 − 1 열에 들어간다. 실제 사업연도는 'DART_기준사업연도' 열에 적는다.
    - price_basis = "current": 기준연도의 PER·PBR·EV/EBITDA·EV/EBIT 는 최근 거래일 종가 기준 값을 쓴다.
      "fiscal_year_end": 결산월 말 종가 기준 값을 그대로 쓴다 (FnGuide 표와 같은 방식, 검증용).
    """
    def is_metric(c):
        return bool(_YEAR_COL.match(c)) and c.endswith(DART_RATIO_SUFFIXES)

    # FnGuide 는 매출 증가율을 '매출액증가율'로 준다 (DART 파일의 '매출증가율'과 같은 지표라 함께 뺀다)
    out = base.drop(columns=[c for c in base.columns if is_metric(c) or
                             (_YEAR_COL.match(c) and c.endswith("(누적)_매출액증가율"))] +
                    [c for c in ("발행주식수(천주)",) if c in base.columns])
    d = dart.set_index("종목코드")
    years = sorted({int(_YEAR_COL.match(c).group(1)) for c in d.columns if is_metric(c)})
    # 종목별 최근 사업연도: 재무비율이나 EPS가 하나라도 있는 가장 최근 연도
    latest = pd.Series(np.nan, index=d.index)
    for y in sorted(years, reverse=True):
        cols = [c for c in (f"{y}(누적)_부채비율", f"{y}_EPS(원)") if c in d.columns]
        has = d[cols].notna().any(axis=1) if cols else pd.Series(False, index=d.index)
        latest[latest.isna() & has] = y
    if latest.notna().sum() == 0:
        return base
    ref = int(latest.mode().iloc[0])
    aligned = pd.DataFrame(index=d.index)
    for k in range(len(years)):
        for sfx in DART_RATIO_SUFFIXES:
            col = pd.Series(np.nan, index=d.index)
            for ly in latest.dropna().unique():
                src = f"{int(ly) - k}{sfx}"
                if src in d.columns:
                    m = latest == ly
                    col[m] = pd.to_numeric(d.loc[m, src], errors="coerce")
            if col.notna().any():
                aligned[f"{ref - k}{sfx}"] = col
    if price_basis == "current":
        for sfx, src in (("_PER(배)", "현재가_PER(배)"), ("_PBR(배)", "현재가_PBR(배)"),
                         ("_EV/EBITDA", "현재가_EV/EBITDA"), ("_EV/EBIT", "현재가_EV/EBIT")):
            if src in d.columns:
                aligned[f"{ref}{sfx}"] = pd.to_numeric(d[src], errors="coerce")
    aligned["DART_기준사업연도"] = latest.astype("Int64")
    for c in ("발행주식수(천주)", "현재가_기준일"):
        if c in d.columns:
            aligned[c] = d[c]
    return out.merge(aligned.reset_index(), on="종목코드", how="left")


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


def _latest_values(df: pd.DataFrame, suffixes: list, n: int = 2) -> tuple:
    """
    종목(행)마다 '값이 있는 가장 최근 연도'의 값을 고른다.

    전 종목에 같은 연도 열 하나를 쓰면, 결산월이 달라 몇 종목만 값이 있는 최신 연도 열
    (예: 3·6월 결산사만 채워진 2026(연간))이 생겼을 때 나머지 종목이 모두 결측이 된다.

    연도는 suffixes[0] 에 값이 있는지로 정하고, 나머지 suffix 는 같은 연도의 값을 쓴다
    (서로 다른 연도의 값을 비교하지 않도록). 최근 n개 연도까지만 거슬러 올라간다.

    반환: (값 DataFrame — 컬럼은 suffixes, 선택된 연도 Series — 값이 없으면 NaN)
    """
    pattern = re.compile(r'^(\d{4})' + re.escape(suffixes[0]) + r'$')
    years = sorted((int(m.group(1)) for c in df.columns if (m := pattern.match(c))), reverse=True)[:n]
    vals = pd.DataFrame(float('nan'), index=df.index, columns=suffixes)
    year = pd.Series(float('nan'), index=df.index)
    for y in years:
        key = pd.to_numeric(df[f'{y}{suffixes[0]}'], errors='coerce')
        take = year.isna() & key.notna()
        for s in suffixes:
            col = f'{y}{s}'
            if col in df.columns:
                vals.loc[take, s] = pd.to_numeric(df.loc[take, col], errors='coerce')
        year[take] = y
    return vals, year


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
