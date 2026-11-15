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
    # FnGuide 수집 결과 (python fngCollect.py all) — '*' 패턴이면 가장 최근 월 파일을 자동 선택
    #   예: snapshot_2026_04.xlsx 와 snapshot_2026_11.xlsx 가 있으면 11월 파일
    #   finance·ratio 의 2026_04_v2 는 파서 수정 후 4월 캐시로 재생성한 파일 (scripts/rebuild_from_cache.py)
    "snapshot_file": "derived/snapshot_2*.xlsx",
    #   finance 는 환경변수(또는 .env) NFAV_FINANCE_FILE 로 바꿔 볼 수 있다 — 기본값은 FnGuide 파일 그대로
    #   예: NFAV_FINANCE_FILE=derived/dart_finance_2*.xlsx  (DART 손익·현금흐름, python apiCollect.py dart_finance)
    "finance_file": get_env("NFAV_FINANCE_FILE", "derived/finance_2*.xlsx"),
    "ratio_file": "derived/finance_ratio_2*.xlsx",
    "invest_idx_file": "derived/invest_idx_2*.xlsx",

    # 재무비율·주당 지표(EPS·BPS·PER·PBR·ROIC·EV/EBITDA 등)의 출처 — 환경변수(또는 .env) NFAV_RATIO_SOURCE
    #   "dart"   : DART·KRX로 직접 계산한 값 (기본값. python apiCollect.py dart_ratio → derived/dart_ratio_*.xlsx)
    #   "fnguide": FnGuide 4월 파일 값 그대로 (2026-04 이후 갱신되지 않는다 — 비교·검증용)
    "ratio_source": get_env("NFAV_RATIO_SOURCE", "dart"),
    "dart_ratio_file": "derived/dart_ratio_2*.xlsx",
    #   "current": 최근 사업연도의 PER·PBR·EV 배수를 최근 거래일 종가로 계산 / "fiscal_year_end": 결산월 말 종가(검증용)
    "dart_price_basis": get_env("NFAV_DART_PRICE_BASIS", "current"),

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
    #   2026-11: 종목 선정에서 일단 제외한다(enabled = False). DART 값으로 바꾸면 EV/EBITDA에 필요한 감가상각비가
    #   일반 기업의 55%에만 있고(현금흐름표 20% + XBRL 주석 35%), 시가총액 500억 미만은 27%뿐이라 소형주가
    #   후보에서 빠지기 때문이다. 다시 쓰려면 True 로 바꾸고, 필요하면 ev_metric 을 "EV/EBIT" 로 둔다.
    "greenblatt": {
        "enabled": False,
        "top_n": 30,              # 상위 N개 종목 선정
        "max_debt_ratio": 150.0,  # 부채비율 최대값
        # 수익수익률에 쓰는 배수: "EV/EBITDA"(기본) 또는 "EV/EBIT"
        #   DART 값을 쓸 때(ratio_source = "dart") EV/EBITDA는 감가상각비가 확인되는 약 55% 종목에만 있다.
        #   EV/EBIT는 영업이익만 쓰므로 대부분 종목에 있고, Greenblatt의 원래 정의(EBIT ÷ EV)이기도 하다.
        "ev_metric": get_env("NFAV_GREENBLATT_EV", "EV/EBITDA"),
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
}
