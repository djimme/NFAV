# agent_config.py
# 주식 매매 Agent 설정 파일
# 전략 파라미터를 여기서 관리합니다. API 키는 .env 에서 읽습니다 (커밋 금지).

from fin_utils import get_env

# =============================================================================
# KIS (한국투자증권) API 설정
# https://apiportal.koreainvestment.com/ 에서 발급
# =============================================================================
KIS_CONFIG = {
    # 실전투자 / 모의투자 구분
    "is_paper_trading": get_env("KIS_PAPER", "true").lower() == "true",  # True: 모의투자, False: 실전투자

    # API 키 (KIS 개발자 포털에서 발급) — .env 의 KIS_* 항목
    "app_key": get_env("KIS_APP_KEY", "YOUR_APP_KEY"),
    "app_secret": get_env("KIS_APP_SECRET", ""),

    # API 기본 URL
    "base_url_real": "https://openapi.koreainvestment.com:9443",
    "base_url_paper": "https://openapivts.koreainvestment.com:29443",

    # 계좌 정보
    "account_no": get_env("KIS_ACCOUNT_NO", ""),  # 예: "12345678"
    "account_type": get_env("KIS_ACCOUNT_TYPE", "01"),             # 01: 위탁계좌
}

# =============================================================================
# 데이터 파일 경로
# =============================================================================
DATA_CONFIG = {
    "data_dir": "derived",
    # 종목 목록(바탕 표)의 출처 — 환경변수(또는 .env) NFAV_BASE_SOURCE
    #   "krx"    : KRX 종목 리스트(corpCode/corplist_merged_*.xlsx) + 업종 분류 파일(sector_map) (기본값, 2026-11-28)
    #              이때 ratio_source·factor_source 도 "dart" 이면 FnGuide 수집 파일 없이 전략이 돈다
    #   "fnguide": FnGuide snapshot 파일의 종목 목록 (마켓분야가 '코스닥 전기·전자'처럼 업종까지 붙은 이름)
    "base_source": get_env("NFAV_BASE_SOURCE", "krx"),
    "corp_list_file": "corpCode/corplist_merged_[0-9]*.xlsx",
    # FnGuide 수집 결과 (python fngCollect.py all) — '*' 패턴이면 가장 최근 월 파일을 자동 선택
    #   예: snapshot_2026_04.xlsx 와 snapshot_2026_11.xlsx 가 있으면 11월 파일
    "snapshot_file": "derived/snapshot_2*.xlsx",
    #   finance(손익·현금흐름)의 기본값은 DART 파일 (python apiCollect.py dart_finance → derived/dart_finance_*.xlsx)
    #   환경변수(또는 .env) NFAV_FINANCE_FILE 로 바꿔 볼 수 있다
    #   예: NFAV_FINANCE_FILE=derived/finance_2*.xlsx  (FnGuide finance 파일 — 비교·검증용)
    "finance_file": get_env("NFAV_FINANCE_FILE", "derived/dart_finance_2*.xlsx"),
    "ratio_file": "derived/finance_ratio_2*.xlsx",
    "invest_idx_file": "derived/invest_idx_2*.xlsx",

    # 재무비율·주당 지표(EPS·BPS·PER·PBR·ROIC·EV/EBITDA 등)의 출처 — 환경변수(또는 .env) NFAV_RATIO_SOURCE
    #   "dart"   : DART·KRX로 직접 계산한 값 (기본값. python apiCollect.py dart_ratio → derived/dart_ratio_*.xlsx)
    #   "fnguide": FnGuide 수집 파일(ratio_file·invest_idx_file·snapshot_file) 값 그대로 — 비교·검증용
    "ratio_source": get_env("NFAV_RATIO_SOURCE", "dart"),
    "dart_ratio_file": "derived/dart_ratio_2*.xlsx",
    #   "current": 최근 사업연도의 PER·PBR·EV 배수를 최근 거래일 종가로 계산 / "fiscal_year_end": 결산월 말 종가(검증용)
    "dart_price_basis": get_env("NFAV_DART_PRICE_BASIS", "current"),

    # 멀티팩터 전략의 팩터 점수 출처 — 환경변수(또는 .env) NFAV_FACTOR_SOURCE
    #   "dart"   : DART·KRX 값으로 직접 계산한 점수 (기본값, 2026-11-27. python apiCollect.py factor → derived/factor_*.xlsx)
    #              수익건전성 = ROE·ROA·영업이익률, 성장성 = 매출·EPS 증가율, 밸류 = E/P·B/P,
    #              모멘텀 = 12-1개월 수익률, 변동성 = 월간 수익률 표준편차 (정의: krxFactor.py)
    #   "fnguide": FnGuide invest_idx 의 팩터 점수 (FnGuide 자체 모델, 산식 비공개) — 비교·검증용
    "factor_source": get_env("NFAV_FACTOR_SOURCE", "dart"),
    "factor_file": "derived/factor_2*.xlsx",

    # 공식 API 원천 데이터 (python apiCollect.py dart_balance / krx_marketcap) — 가장 최근 파일 사용
    #   시가총액 대체 소스: kb_marketcap → derived/market_cap_kb_*.xlsx (필요 시 아래 경로를 바꿔 사용)
    "dart_balance_file": "derived/dart_balance_*.xlsx",
    "market_cap_file": "derived/market_cap_2*.xlsx",   # KRX (market_cap_kb_* 는 제외)

    # 가치함정 점검 자료 (python apiCollect.py dart_risk → derived/dart_risk_YYYY_MM.xlsx) — 가장 최근 파일 사용
    #   감사의견, 최근 1년 CB·BW·유상증자·감자·부실 공시. 파일이 없으면 가치함정 필터를 건너뛴다
    "dart_risk_file": "derived/dart_risk_2*.xlsx",

    # 업종 분류 (python sectorCollect.py → derived/sector_map_YYYY_MM_DD.xlsx) — 가장 최근 파일 사용
    #   종목코드로 붙여 WI26분야 옆에 KRICS섹터·KRICS산업그룹 컬럼을 더한다. 파일이 없으면 건너뛴다
    "sector_map_file": "derived/sector_map_2*.xlsx",
}

# =============================================================================
# 전략별 파라미터
# =============================================================================
STRATEGY_CONFIG = {

    # --- PEG 전략 (Peter Lynch) ---
    "peg": {
        "enabled": True,
        "max_peg": 1.0,           # PEG 최대값 (낮을수록 저평가)
        "max_debt_ratio": 100.0,  # 부채비율 최대값 (%)
        "min_eps_growth": 0.0,    # EPS 증가율 최솟값 (%)
    },

    # --- Piotroski F-Score ---
    "piotroski": {
        "enabled": True,
        "min_score": 6,           # F-Score 최소값 (0~9, 7 이상이 우량)
    },

    # --- Greenblatt Magic Formula ---
    #   2026-11-27: EV/EBIT 기준으로 다시 켰다. EV/EBITDA는 감가상각비가 일반 기업의 55%에만 있어
    #   (시가총액 500억 미만은 27%) 소형주가 후보에서 빠지기 때문에 쓰지 않는다.
    "greenblatt": {
        "enabled": True,
        "top_n": 30,              # 상위 N개 종목 선정
        "max_debt_ratio": 150.0,  # 부채비율 최대값
        # 수익수익률에 쓰는 배수: "EV/EBIT"(기본) 또는 "EV/EBITDA" — 환경변수(또는 .env) NFAV_GREENBLATT_EV
        #   EV/EBIT는 영업이익만 쓰므로 영업흑자 기업 대부분에 있고, Greenblatt의 원래 정의(EBIT ÷ EV)이기도 하다.
        #   EV/EBITDA는 감가상각비가 확인되는 약 55% 종목에만 있다 (ratio_source = "dart" 일 때).
        "ev_metric": get_env("NFAV_GREENBLATT_EV", "EV/EBIT"),
        # 영업흑자인데 EV가 음수(순현금 > 시가총액)인 종목: False = 제외(기본), True = 수익수익률 공동 1위로 포함
        "include_negative_ev": False,
    },

    # --- 멀티팩터 스코어링 ---
    "multifactor": {
        "enabled": True,
        "weights": {
            "수익건전성": 0.25,    # 수익 건전성 (높을수록 좋음)
            "성장성": 0.25,        # 성장성 (높을수록 좋음)
            "밸류": 0.20,          # 밸류 팩터 (높을수록 저평가)
            "모멘텀": 0.15,        # 모멘텀 (높을수록 강함)
            "변동성": -0.15,       # 변동성 (낮을수록 안정적, 음수 가중치)
        },
        "top_n": 30,
    },

    # --- NCAV 전략 (Benjamin Graham) ---
    "ncav": {
        "enabled": True,
        "min_ncav_r": 0.0,        # NCAV_R 최솟값 (유동자산-총부채 > 시총)
        "require_positive_income": True,
    },

    # --- NFAV 전략 (순금융자산: A 보수적 · B 재무구조) ---
    #   A = 금융자산 − 부채총계 − 비지배지분,  B = 금융자산 − 이자부부채
    #   B_R > min_nfav_b_r 로 거른 뒤 A_R 높은 순으로 top_n
    "nfav": {
        "enabled": True,
        "min_nfav_b_r": 0.0,      # NFAV_B / 시총 최솟값 (0 = 순현금 기업)
        "min_nfav_a_r": None,     # NFAV_A / 시총 최솟값 (None = 컷 없이 순위만)
        "max_debt_ratio": 150.0,  # 부채비율 최대값 (%)
        "require_positive_income": True,
        "top_n": 30,
        "exclude_other_financial": False,  # True: '기타'가 붙은 금융자산(대여금 등 섞일 수 있음)을 금융자산에서 제외
    },
}

# =============================================================================
# 종합 스코어링 가중치 (각 전략의 영향력)
# =============================================================================
COMPOSITE_WEIGHTS = {
    "peg": 0.20,
    "piotroski": 0.25,
    "greenblatt": 0.25,
    "multifactor": 0.20,
    "ncav": 0.10,
}

# =============================================================================
# 매매 설정
# =============================================================================
TRADING_CONFIG = {
    "max_stocks": 10,             # 최대 보유 종목 수
    "invest_per_stock": 1_000_000,  # 종목당 투자금액 (원) - 기본값
    "order_type": "00",           # 00: 지정가, 01: 시장가
    "order_condition": "0",       # 0: 일반주문
}

# =============================================================================
# 공통 필터 (모든 전략에 공통 적용)
# =============================================================================
COMMON_FILTERS = {
    "exclude_markets": [],         # 제외할 마켓 (예: ["코스닥 우량기업부"])
    "min_market_cap_억": 100,      # 최소 시가총액 (억원)
    "exclude_spac": True,          # SPAC(기업인수목적회사) 제외
    "exclude_no_trade": True,      # KRX 기준일 거래량 0 종목(거래정지 등) 제외
    "min_trading_value_억": 0,     # 기준일 최소 거래대금(억원), 0이면 사용 안 함

    # --- 가치함정 필터 (2026-11-25) — 모든 전략에 앞서 적용. 자료: python apiCollect.py dart_risk ---
    #   제외된 종목과 사유는 결과 파일의 '가치함정_제외' 시트에 남는다
    "value_trap": {
        "enabled": True,
        "exclude_bad_audit": True,          # 최근 사업보고서 감사의견이 한정·부적정·의견거절
        "exclude_going_concern": True,      # 감사보고서 강조사항에 계속기업 불확실성
        "exclude_cb_bw": True,              # 최근 1년 전환사채(CB)·신주인수권부사채(BW) 발행 결정
        "exclude_rights_offering": True,    # 최근 1년 유상증자 결정 — 아래 rights_offering_mode 에 따라 판단
        # 유상증자 판단 방식 (2026-11-27): "judge" = 상황을 보고 판단, "all" = 한 건이라도 있으면 제외
        #   judge 순서: ① 반복 조달(CB·BW 동반 또는 2건 이상. 합계 증자비율이 small 미만이면 반복 아님) → 제외
        #               ② loss_years 해 연속 영업적자 → 제외
        #               ③ 증자비율 large 이상이고 성장 목적 비중이 growth_min 미만 → 제외
        #               ④ 주주배정·일반공모이고 증자비율 small 이상, 성장 목적 비중이 growth_min 미만 → 제외
        #               ⑤ 증자비율 small 미만 → 통과  ⑥ 성장 목적 비중 growth_min 이상 → 통과(주의)  ⑦ 나머지 → 통과(주의)
        #   성장 목적 = 시설자금 + 영업양수자금 + 타법인 증권 취득자금. 통과 종목은 결과 파일 '유상증자_통과' 시트에 남는다
        "rights_offering_mode": "judge",
        "rights_small_pct": 10,             # 증자비율(신주 수 ÷ 증자 전 주식 수, %)이 이 값 미만이면 소규모
        "rights_large_pct": 30,             # 이 값 이상이면 대규모
        "rights_growth_min_pct": 50,        # 성장 목적 비중(%)이 이 값 이상이면 성장 목적 증자로 본다
        "rights_loss_years": 3,             # 연속 영업적자 햇수 기준
        "exclude_distress": True,           # 회생절차·해산사유·영업정지·부도·채권은행 관리절차 공시
        "exclude_eb": False,                # 교환사채(EB) — 자기주식·타사 주식이 대상이라 희석이 없을 수 있어 표시만
        "exclude_capital_reduction": False, # 감자 — 무상감자(결손 보전)와 유상감자(주주환원)가 섞여 있어 표시만
        # CB·BW·유상증자 금액 합계가 시가총액의 이 비율(%) 미만이면 발행 사유로는 빼지 않는다. 0 = 금액과 관계없이 뺀다
        "min_issue_to_cap_pct": 0,
    },
}
