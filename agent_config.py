# agent_config.py
# 주식 매매 Agent 설정 파일
# KIS API 키 및 전략 파라미터를 여기서 관리합니다.

# =============================================================================
# KIS (한국투자증권) API 설정
# https://apiportal.koreainvestment.com/ 에서 발급
# =============================================================================
KIS_CONFIG = {
    # 실전투자 / 모의투자 구분
    "is_paper_trading": True,  # True: 모의투자, False: 실전투자

    # API 키 (KIS 개발자 포털에서 발급)
    "app_key": "YOUR_APP_KEY",
    "app_secret": "YOUR_APP_SECRET",

    # API 기본 URL
    "base_url_real": "https://openapi.koreainvestment.com:9443",
    "base_url_paper": "https://openapivts.koreainvestment.com:29443",

    # 계좌 정보
    "account_no": "YOUR_ACCOUNT_NO",  # 예: "12345678"
    "account_type": "01",             # 01: 위탁계좌
}

# =============================================================================
# 데이터 파일 경로
# =============================================================================
DATA_CONFIG = {
    "data_dir": "derived",
    "snapshot_file": "derived/snapshot_2026_04.xlsx",
    "finance_file": "derived/finance_2026_04.xlsx",
    "ratio_file": "derived/finance_ratio_2026_04.xlsx",
    "invest_idx_file": "derived/invest_idx_2026_04.xlsx",

    # NCAV 결과 파일 (calc_NCAV.py 실행 결과)
    "ncav_output_pattern": "derived/ncav_output_*.xlsx",
    "nfav_output_pattern": "derived/nfav_output_*.xlsx",
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
    "greenblatt": {
        "enabled": True,
        "top_n": 30,              # 상위 N개 종목 선정
        "max_debt_ratio": 150.0,  # 부채비율 최대값
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

    # --- NFAV 전략 (보수적 가치투자) ---
    "nfav": {
        "enabled": True,
        "min_nfav_r": 0.5,
        "max_debt_ratio": 150.0,
        "require_positive_income": True,
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
}
