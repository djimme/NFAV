# strat_utils.py
# 전략 모듈 공통 유틸리티
# - 전략 입력 파일 로딩·병합 (load_all_data, merge_base): 종목 목록은 KRX 리스트, FnGuide 파일은 필요할 때만
# - 공식 API 원천 데이터 로딩: DART 재무상태표, 시가총액 (선택, 파일이 있으면 병합)
# - 업종 분류 로딩: KRICS 섹터·산업그룹 (선택, sectorCollect.py 결과 파일이 있으면 병합)
# - 공통 종목 필터 (apply_common_filters)
# - 가치함정 필터 (apply_value_trap_filter): 감사의견 비적정, 최근 1년 CB·BW·유상증자, 부실 공시 (dartRisk.py 결과)
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
    전략 입력 파일을 로드합니다. 재무제표(finance)는 모든 업종 시트를 수직으로 합칩니다.

    FnGuide 수집 파일(snapshot·invest_idx·ratio)은 필요할 때만 읽습니다 —
    base_source·ratio_source·factor_source 가 모두 FnGuide 가 아니고 대체 파일(dart_ratio·factor)이 있으면 건너뜁니다.

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

    # 종목 목록 (base_source = "krx"): KRX 종목 리스트. 없으면 FnGuide snapshot 을 바탕 표로 쓴다
    base_source = config.get("base_source", "fnguide")
    if base_source == "krx":
        files = sorted(f for f in glob.glob(config.get("corp_list_file") or "") if "ETF" not in f)
        if files:
            cl = pd.read_excel(files[-1], dtype=str).rename(columns={
                "scode": "종목코드", "sname": "종목명", "industry": "업종", "products": "주요제품", "market": "마켓분야"})
            cl["종목코드"] = cl["종목코드"].str.zfill(6)
            data["corplist"] = cl[[c for c in ["종목코드", "종목명", "업종", "주요제품", "마켓분야"] if c in cl.columns]]
            print(f"  ✅ 종목 목록(KRX): {files[-1]} ({len(cl)}개 종목)")
        else:
            print(f"  ⚠️ KRX 종목 리스트 없음 ({config.get('corp_list_file')}) → FnGuide snapshot 을 바탕 표로 쓴다")
            base_source = "fnguide"
    # FnGuide 수집 파일이 필요한가: 바탕 표·재무비율·팩터 점수 중 하나라도 FnGuide 값을 써야 하면 읽는다
    need_fnguide = (base_source != "krx"
                    or config.get("ratio_source") != "dart" or not _latest_file(config.get("dart_ratio_file"))
                    or config.get("factor_source") != "dart" or not _latest_file(config.get("factor_file")))
    if not need_fnguide:
        print("  ℹ️  FnGuide 수집 파일(snapshot·invest_idx·ratio)은 읽지 않는다 (종목 목록·재무비율·팩터 점수 모두 DART·KRX)")

    # snapshot (단일 시트)
    snap_path = config["snapshot_file"]
    if not need_fnguide:
        pass
    elif os.path.exists(snap_path):
        data["snapshot"] = pd.read_excel(snap_path, dtype={"종목코드": str})
        data["snapshot"]["종목코드"] = data["snapshot"]["종목코드"].str.zfill(6)
        print(f"  ✅ snapshot: {len(data['snapshot'])}개 종목")
    else:
        raise FileNotFoundError(f"snapshot 파일 없음: {snap_path}")

    # invest_idx (단일 시트)
    inv_path = config["invest_idx_file"]
    if not need_fnguide:
        pass
    elif os.path.exists(inv_path):
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
    if not need_fnguide:
        pass
    elif os.path.exists(rat_path):
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

    # --- 가치함정 점검 자료 (선택) — python apiCollect.py dart_risk ---
    path = _latest_file(config.get("dart_risk_file"))
    if path:
        df = pd.read_excel(path, dtype={"종목코드": str})
        df["종목코드"] = df["종목코드"].str.zfill(6)
        data["dart_risk"] = df
        print(f"  ✅ 가치함정 점검 자료: {path} ({len(df)}개 종목)")
    else:
        print(f"  ℹ️  가치함정 점검 자료 없음 ({config.get('dart_risk_file')}) → python apiCollect.py dart_risk 로 수집")

    # --- DART·KRX로 직접 계산한 팩터 점수 (선택) — python apiCollect.py factor ---
    #   factor_source 가 "dart" 이면 invest_idx 의 FnGuide 팩터 점수를 이 파일 값으로 바꾼다 (merge_base)
    if config.get("factor_source") == "dart":
        path = _latest_file(config.get("factor_file"))
        if path:
            df = pd.read_excel(path, dtype={"종목코드": str})
            df["종목코드"] = df["종목코드"].str.zfill(6)
            data["factor"] = df
            print(f"  ✅ 팩터 점수(DART·KRX): {path} ({len(df)}개 종목)")
        else:
            print(f"  ⚠️ 팩터 점수 파일 없음 ({config.get('factor_file')}) → FnGuide 팩터 점수를 그대로 쓴다 "
                  f"(python apiCollect.py factor 로 생성)")

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
# 가치함정 점검 파일(dart_risk)에서 base에 합칠 컬럼 ('위험_' 접두어를 붙인다)
DART_RISK_COLS = ["감사의견", "감사의견_판정", "감사_사업연도", "계속기업_불확실성",
                  "CB_건수", "CB_최근일", "CB_금액_억원", "BW_건수", "BW_최근일", "BW_금액_억원",
                  "EB_건수", "EB_최근일", "유상증자_건수", "유상증자_최근일", "유상증자_금액_억원", "유상증자_방식",
                  "유상증자_증자비율", "유상증자_성장목적_비중",
                  "감자_건수", "감자_최근일", "부실_공시", "조회기간"]


def _operating_loss_streak(fin: pd.DataFrame) -> pd.DataFrame:
    """
    finance 의 '{연도}(연간)_영업이익' 열로 종목별 연속 영업적자 햇수를 센다 → ['종목코드', '위험_영업적자_연속연수'].
    값이 있는 가장 최근 연도부터 거슬러 올라가며 적자가 끊기는 곳까지 센다. 영업이익 자료가 없으면 빈 값.
    """
    cols = sorted((c for c in fin.columns if re.match(r"^\d{4}\(연간\)_영업이익$", c)), reverse=True)
    f = fin.drop_duplicates("종목코드")
    out = pd.DataFrame({"종목코드": f["종목코드"].values})
    if not cols:
        out["위험_영업적자_연속연수"] = np.nan
        return out
    vals = f[cols].apply(pd.to_numeric, errors="coerce").to_numpy()
    streak = []
    for row in vals:
        row = row[~np.isnan(row)]
        if len(row) == 0:
            streak.append(np.nan)
            continue
        n = 0
        for v in row:
            if v >= 0:
                break
            n += 1
        streak.append(n)
    out["위험_영업적자_연속연수"] = streak
    return out


def merge_base(data: dict) -> pd.DataFrame:
    """
    종목 목록(KRX 종목 리스트, 없으면 FnGuide snapshot)을 기준으로 나머지 데이터를 LEFT JOIN합니다.
    모든 전략의 공통 베이스 DataFrame이 됩니다.
    """
    if "corplist" in data:
        base = data["corplist"].copy()
        # WI26분야는 업종 분류 파일에서 가져온다 (FnGuide snapshot 과 같은 값)
        if "sector_map" in data and "WI26분야" in data["sector_map"].columns:
            base = base.merge(data["sector_map"].drop_duplicates("종목코드")[["종목코드", "WI26분야"]],
                              on="종목코드", how="left")
    else:
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

    # ratio (FnGuide, 읽었을 때만): 핵심 컬럼만 선택
    if "ratio" in data:
        rat = data["ratio"]
        keep_keywords = ["부채비율", "유동비율", "ROA", "ROE", "ROIC",
                         "EPS증가율", "영업이익률", "총자산회전율", "매출액증가율"]
        rat_cols = ["종목코드"] + [c for c in rat.columns
                                   if any(k in c for k in keep_keywords)]
        rat_cols = list(dict.fromkeys(rat_cols))
        base = base.merge(rat[rat_cols], on="종목코드", how="left")

    # invest_idx (FnGuide, 읽었을 때만): 팩터 점수 및 밸류에이션
    if "invest" in data:
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

    # 팩터 점수를 DART·KRX 계산 값으로 바꾼다 (factor_source = "dart" 일 때만)
    #   FnGuide 점수 열을 빼고 같은 이름의 열을 넣는다. 구성 지표 원값('팩터_…')과 출처도 함께 붙인다
    if "factor" in data:
        fac = data["factor"].drop_duplicates("종목코드")
        cols = [c for c in fac.columns if c.endswith("_종목") or (c.startswith("팩터_") and c != "팩터_업종명")]
        base = base.drop(columns=[c for c in cols if c in base.columns])
        base = base.merge(fac[["종목코드"] + cols], on="종목코드", how="left")
        base["팩터_출처"] = "DART·KRX"

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

    # 가치함정 점검 자료 (있으면): '위험_' 접두어로 합친다 → apply_value_trap_filter 가 읽는다
    if "dart_risk" in data:
        rk = data["dart_risk"]
        cols = [c for c in DART_RISK_COLS if c in rk.columns]
        rk = rk.drop_duplicates("종목코드")[["종목코드"] + cols].rename(columns={c: f"위험_{c}" for c in cols})
        base = base.merge(rk, on="종목코드", how="left")
        # 유상증자 판단에 쓰는 연속 영업적자 햇수 (최근 연간 영업이익부터 거슬러 올라가며 센다)
        base = base.merge(_operating_loss_streak(fin), on="종목코드", how="left")

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
# 가치함정 필터
# =============================================================================

def apply_value_trap_filter(df: pd.DataFrame, cfg: dict) -> tuple:
    """
    싸 보이지만 싼 이유가 있는 종목(가치함정)을 모든 전략에 앞서 뺀다.

    자료: python apiCollect.py dart_risk → derived/dart_risk_YYYY_MM.xlsx (merge_base 가 '위험_' 열로 합친다)

    제외 사유 (cfg 의 exclude_* 가 True 인 것만 적용):
      감사의견 비적정     최근 사업보고서 감사의견이 한정·부적정·의견거절
      계속기업 불확실성   감사보고서 강조사항에 '계속기업' 언급
      CB·BW 발행         최근 1년 안에 전환사채·신주인수권부사채 발행 결정
      EB 발행            최근 1년 안에 교환사채 발행 결정 (기본은 표시만)
      유상증자           최근 1년 안에 유상증자 결정 — rights_offering_mode 가 "judge"(기본)면 반복 조달·연속 영업적자·
                         규모·자금 목적·방식을 보고 판단하고(_judge_rights_offering), "all" 이면 한 건이라도 있으면 뺀다.
                         통과한 종목에는 '유상증자_판정' 열(통과: 소규모 / 주의: …)이 남는다
      감자               최근 1년 안에 감자 결정 (기본은 표시만)
      부실 공시           회생절차·해산사유·영업정지·부도·채권은행 관리절차 등

    min_issue_to_cap_pct: CB·BW·유상증자 금액 합계가 시가총액의 이 비율(%) 미만이면 발행 사유로는 빼지 않는다.
      0(기본)이면 금액과 관계없이 뺀다. 금액을 모르는 종목은 뺀다.

    반환: (통과 종목 DataFrame, 제외 종목 DataFrame — '제외사유' 열 포함)
    감사의견을 확인할 수 없는 종목(신규 상장 등)은 빼지 않는다.
    """
    empty = pd.DataFrame()
    if not cfg or not cfg.get("enabled", True):
        return df, empty
    if "위험_감사의견_판정" not in df.columns:
        print("  ⚠️ 가치함정 필터: 점검 자료가 없어 건너뜀 → python apiCollect.py dart_risk 로 수집")
        return df, empty

    def num(c):
        return pd.to_numeric(df[c], errors="coerce").fillna(0) if c in df.columns else pd.Series(0, index=df.index)

    def flag(c):
        if c not in df.columns:
            return pd.Series(False, index=df.index)
        return df[c].astype(str).str.lower().isin(["true", "1", "1.0"])

    cb_bw = (num("위험_CB_건수") + num("위험_BW_건수")) > 0
    rights = num("위험_유상증자_건수") > 0
    min_pct = cfg.get("min_issue_to_cap_pct", 0) or 0
    if min_pct > 0 and "시가총액_억원" in df.columns:
        amt = num("위험_CB_금액_억원") + num("위험_BW_금액_억원") + num("위험_유상증자_금액_억원")
        cap = pd.to_numeric(df["시가총액_억원"], errors="coerce")
        small = (amt > 0) & (cap > 0) & (amt / cap * 100 < min_pct)     # 금액을 모르면(0) 작다고 보지 않는다
        cb_bw &= ~small
        rights &= ~small

    # 유상증자: 'judge' 면 상황을 보고 판단하고(_judge_rights_offering), 'all' 이면 한 건이라도 있으면 뺀다
    df = df.copy()
    rights_label = "유상증자"
    if cfg.get("rights_offering_mode", "judge") == "judge" and "위험_유상증자_증자비율" in df.columns:
        verdict = _judge_rights_offering(df, cfg, rights, cb_bw_any=(num("위험_CB_건수") + num("위험_BW_건수")) > 0)
        df["유상증자_판정"] = verdict
        rights = verdict.str.startswith("제외")
        rights_label = None      # 사유를 판정 문구로 적는다
    elif cfg.get("rights_offering_mode", "judge") == "judge":
        print("  ⚠️ 유상증자 판단: 점검 자료에 증자비율이 없어 모두 제외로 처리 → python apiCollect.py dart_risk refresh")

    rules = [
        ("exclude_bad_audit", True, "감사의견 비적정", df["위험_감사의견_판정"].astype(str) == "비적정"),
        ("exclude_going_concern", True, "계속기업 불확실성", flag("위험_계속기업_불확실성")),
        ("exclude_cb_bw", True, "CB·BW 발행", cb_bw),
        ("exclude_eb", False, "EB 발행", num("위험_EB_건수") > 0),
        ("exclude_rights_offering", True, rights_label, rights),
        ("exclude_capital_reduction", False, "감자", num("위험_감자_건수") > 0),
        ("exclude_distress", True, "부실 공시",
         df["위험_부실_공시"].notna() & (df["위험_부실_공시"].astype(str).str.strip() != "")
         if "위험_부실_공시" in df.columns else pd.Series(False, index=df.index)),
    ]
    reason = pd.Series("", index=df.index)
    counts = []
    for key, default, label, mask in rules:
        if not cfg.get(key, default):
            continue
        mask = mask.fillna(False)
        # 유상증자를 판단 방식으로 걸렀으면 사유를 '유상증자(반복 조달)' 처럼 판정 문구로 적는다
        text = label if label else df.loc[mask, "유상증자_판정"].str.replace("제외: ", "유상증자(", regex=False) + ")"
        reason[mask] = reason[mask].where(reason[mask] == "", reason[mask] + ", ") + text
        counts.append(f"{label or '유상증자'} {int(mask.sum())}")
    out = reason != ""
    excluded = df[out].copy()
    excluded.insert(0, "제외사유", reason[out])
    keep = ["제외사유", "종목코드", "종목명", "마켓분야", "WI26분야", "KRICS섹터", "시가총액_억원"] + \
           [c for c in df.columns if c.startswith("위험_")]
    excluded = excluded[[c for c in keep if c in excluded.columns]].sort_values("제외사유").reset_index(drop=True)
    print(f"  🔍 가치함정 필터: {len(df)}개 → {len(df) - int(out.sum())}개 (제외 {int(out.sum())}개 — {' · '.join(counts)})")
    if "유상증자_판정" in df.columns:
        v = df.loc[~out, "유상증자_판정"]
        v = v[v != ""].value_counts()
        if len(v):
            print("     유상증자가 있지만 통과: " + " · ".join(f"{k} {n}" for k, n in v.items()))
    return df[~out], excluded


def rights_offering_passed(df: pd.DataFrame) -> pd.DataFrame:
    """가치함정 필터를 통과한 종목 가운데 최근 1년 유상증자가 있는 종목과 판정 (결과 파일의 '유상증자_통과' 시트)."""
    if "유상증자_판정" not in df.columns:
        return pd.DataFrame()
    keep = ["유상증자_판정", "종목코드", "종목명", "마켓분야", "WI26분야", "KRICS섹터", "시가총액_억원",
            "위험_유상증자_건수", "위험_유상증자_최근일", "위험_유상증자_금액_억원", "위험_유상증자_방식",
            "위험_유상증자_증자비율", "위험_유상증자_성장목적_비중", "위험_영업적자_연속연수"]
    out = df[df["유상증자_판정"] != ""]
    return out[[c for c in keep if c in out.columns]].sort_values(["유상증자_판정", "종목코드"]).reset_index(drop=True)


def _judge_rights_offering(df: pd.DataFrame, cfg: dict, rights: pd.Series, cb_bw_any: pd.Series) -> pd.Series:
    """
    최근 1년 유상증자가 있는 종목을 상황에 따라 판정한다 (2026-11-27. 근거: docs/종목 선정 전략 설명.html).
    위에서부터 차례로 보고 처음 걸리는 판정을 쓴다. 유상증자가 없는 종목은 빈 문자열.

      1 제외: 반복 조달              CB·BW도 발행했거나 유상증자가 2건 이상. 단, 합계 증자비율이 small 미만이면 반복으로 보지 않는다
      2 제외: N년 연속 영업적자       최근 연간 영업이익이 loss_years 해 연속 적자
      3 제외: 대규모·비성장 목적      증자비율 large 이상이고 성장 목적(시설·영업양수·타법인 증권) 비중이 growth 미만
      4 제외: 공모·비성장 목적        주주배정·일반공모(제3자배정 없음)이고 증자비율 small 이상, 성장 목적 비중이 growth 미만
      5 통과: 소규모                 증자비율 small 미만
      6 주의: 성장 목적               성장 목적 비중이 growth 이상
      7 주의: 운영자금 등 / 주의: 자료 없음   나머지 (증자비율을 모르면 '자료 없음')

    기준값(cfg): rights_small_pct 10, rights_large_pct 30, rights_growth_min_pct 50, rights_loss_years 3
    """
    small = cfg.get("rights_small_pct", 10)
    large = cfg.get("rights_large_pct", 30)
    growth_min = cfg.get("rights_growth_min_pct", 50)
    loss_years = cfg.get("rights_loss_years", 3)

    def col(c):
        return pd.to_numeric(df[c], errors="coerce") if c in df.columns else pd.Series(np.nan, index=df.index)

    ratio = col("위험_유상증자_증자비율")                 # 모르면 NaN → 크기 비교는 모두 False
    growth = col("위험_유상증자_성장목적_비중") >= growth_min
    count = col("위험_유상증자_건수").fillna(0)
    how = df["위험_유상증자_방식"].fillna("").astype(str) if "위험_유상증자_방식" in df.columns \
        else pd.Series("", index=df.index)
    public_only = how.str.contains("주주배정|일반공모|주주우선") & ~how.str.contains("제3자")
    is_small = ratio < small

    steps = [
        ("제외: 반복 조달", (cb_bw_any | (count >= 2)) & ~is_small),
        (f"제외: {loss_years}년 연속 영업적자", col("위험_영업적자_연속연수") >= loss_years),
        ("제외: 대규모·비성장 목적", (ratio >= large) & ~growth),
        ("제외: 공모·비성장 목적", public_only & (ratio >= small) & ~growth),
        ("통과: 소규모", is_small),
        ("주의: 성장 목적", growth),
        ("주의: 자료 없음", ratio.isna()),
        ("주의: 운영자금 등", pd.Series(True, index=df.index)),
    ]
    verdict = pd.Series("", index=df.index)
    for label, mask in steps:
        hit = rights & (verdict == "") & mask.fillna(False)
        verdict[hit] = label
    return verdict


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
