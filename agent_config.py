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
    "snapshot_file": "derived/snapshot_2026_04.xlsx",
    # _v2: 부분연도 열을 '연간'으로 저장하던 파서 버그 수정 후 재생성 (scripts/rebuild_from_cache.py)
    "finance_file": "derived/finance_2026_04_v2.xlsx",
    "ratio_file": "derived/finance_ratio_2026_04_v2.xlsx",
    "invest_idx_file": "derived/invest_idx_2026_04.xlsx",

    # 공식 API 원천 데이터 (python apiCollect.py dart_balance / krx_marketcap) — 가장 최근 파일 사용
    #   시가총액 대체 소스: kb_marketcap → derived/market_cap_kb_*.xlsx (필요 시 아래 경로를 바꿔 사용)
    "dart_balance_file": "derived/dart_balance_*.xlsx",
    "market_cap_file": "derived/market_cap_2*.xlsx",   # KRX (market_cap_kb_* 는 제외)
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
