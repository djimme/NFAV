# agent_kis_api.py
# 한국투자증권 (KIS) REST API 래퍼
# 공식 문서: https://apiportal.koreainvestment.com/
#
# 기능:
#   - 액세스 토큰 발급 / 자동 갱신
#   - 계좌 잔고 조회
#   - 현재가 조회
#   - 매수 / 매도 주문
#   - 체결 내역 조회
#   - 보유 종목 조회

import json
import time
import requests
from datetime import datetime, timedelta
from pathlib import Path


TOKEN_CACHE_FILE = ".kis_token_cache.json"


class KISApi:
    """
    한국투자증권 OpenAPI REST 래퍼

    사용 예시:
        cfg = {...}  # agent_config.KIS_CONFIG
        api = KISApi(cfg)
        api.authenticate()

        price = api.get_current_price("005930")   # 삼성전자 현재가
        api.place_order("005930", "buy", qty=1, price=70000)
    """

    def __init__(self, config: dict):
        self.app_key    = config["app_key"]
        self.app_secret = config["app_secret"]
        self.account_no = config["account_no"]
        self.account_type = config.get("account_type", "01")
        self.is_paper   = config.get("is_paper_trading", True)

        self.base_url = (config["base_url_paper"] if self.is_paper
                         else config["base_url_real"])

        self.access_token = None
        self.token_expire = None

        env_label = "🟡 모의투자" if self.is_paper else "🟢 실전투자"
        print(f"  KIS API 초기화 완료 ({env_label})")

    # ------------------------------------------------------------------
    # 인증
    # ------------------------------------------------------------------

    def authenticate(self) -> bool:
        """액세스 토큰 발급 (캐시된 토큰 재사용)"""
        # 캐시 확인
        if self._load_token_cache():
            print("  ✅ 토큰 캐시 사용 중")
            return True

        url = f"{self.base_url}/oauth2/tokenP"
        payload = {
            "grant_type": "client_credentials",
            "appkey":     self.app_key,
            "appsecret":  self.app_secret,
        }
        resp = requests.post(url, json=payload, timeout=10)
        if resp.status_code != 200:
            print(f"  ❌ 인증 실패: {resp.status_code} {resp.text}")
            return False

        data = resp.json()
        self.access_token = data["access_token"]
        # 만료 시간은 보통 1일
        self.token_expire = datetime.now() + timedelta(hours=23)
        self._save_token_cache()
        print("  ✅ 인증 성공 (토큰 발급)")
        return True

    def _headers(self, tr_id: str, extra: dict = None) -> dict:
        """공통 헤더 생성"""
        if not self.access_token or datetime.now() >= self.token_expire:
            self.authenticate()
        h = {
            "Content-Type":  "application/json; charset=utf-8",
            "authorization": f"Bearer {self.access_token}",
            "appkey":        self.app_key,
            "appsecret":     self.app_secret,
            "tr_id":         tr_id,
            "custtype":      "P",
        }
        if extra:
            h.update(extra)
        return h

    def _load_token_cache(self) -> bool:
        cache = Path(TOKEN_CACHE_FILE)
        if not cache.exists():
            return False
        try:
            with open(cache) as f:
                d = json.load(f)
            expire = datetime.fromisoformat(d["expire"])
            if datetime.now() < expire:
                self.access_token = d["token"]
                self.token_expire = expire
                return True
        except Exception:
            pass
        return False

    def _save_token_cache(self):
        with open(TOKEN_CACHE_FILE, "w") as f:
            json.dump({
                "token":  self.access_token,
                "expire": self.token_expire.isoformat(),
            }, f)

    # ------------------------------------------------------------------
    # 현재가 조회
    # ------------------------------------------------------------------

    def get_current_price(self, stock_code: str) -> dict:
        """
        국내 주식 현재가 조회

        Returns:
            {
                "code": "005930",
                "name": "삼성전자",
                "price": 70000,      # 현재가 (원)
                "open": 69500,
                "high": 70500,
                "low": 69000,
                "volume": 12345678,  # 거래량
                "change_rate": 1.23  # 등락률 (%)
            }
        """
        url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-price"
        tr_id = "FHKST01010100"

        params = {
            "fid_cond_mrkt_div_code": "J",
            "fid_input_iscd": stock_code,
        }
        resp = requests.get(url, headers=self._headers(tr_id), params=params, timeout=10)

        if resp.status_code != 200:
            return {"error": f"HTTP {resp.status_code}"}

        d = resp.json()
        if d.get("rt_cd") != "0":
            return {"error": d.get("msg1", "조회 실패")}

        o = d["output"]
        return {
            "code":        stock_code,
            "name":        o.get("hts_kor_isnm", ""),
            "price":       int(o.get("stck_prpr", 0)),
            "open":        int(o.get("stck_oprc", 0)),
            "high":        int(o.get("stck_hgpr", 0)),
            "low":         int(o.get("stck_lwpr", 0)),
            "volume":      int(o.get("acml_vol", 0)),
            "change_rate": float(o.get("prdy_ctrt", 0)),
        }

    def get_prices_batch(self, codes: list, delay_sec: float = 0.2) -> dict:
        """여러 종목 현재가 일괄 조회 (API 부하 방지 딜레이 포함)"""
        result = {}
        for code in codes:
            result[code] = self.get_current_price(code)
            time.sleep(delay_sec)
        return result

    # ------------------------------------------------------------------
    # 계좌 조회
    # ------------------------------------------------------------------

    def get_account_balance(self) -> dict:
        """
        계좌 잔고 및 보유 종목 조회

        Returns:
            {
                "cash": 1234567,           # 예수금 (원)
                "total_eval": 9876543,     # 총 평가금액
                "holdings": [
                    {
                        "code": "005930",
                        "name": "삼성전자",
                        "qty": 10,
                        "avg_price": 68000,
                        "current_price": 70000,
                        "profit_loss": 20000,
                        "profit_rate": 2.94,
                    },
                    ...
                ]
            }
        """
        url = f"{self.base_url}/uapi/domestic-stock/v1/trading/inquire-balance"
        # 실전: TTTC8434R / 모의: VTTC8434R
        tr_id = "VTTC8434R" if self.is_paper else "TTTC8434R"

        params = {
            "CANO":             self.account_no,
            "ACNT_PRDT_CD":     self.account_type,
            "AFHR_FLPR_YN":     "N",
            "OFL_YN":           "",
            "INQR_DVSN":        "02",
            "UNPR_DVSN":        "01",
            "FUND_STTL_ICLD_YN":"N",
            "FNCG_AMT_AUTO_RDPT_YN": "N",
            "PRCS_DVSN":        "01",
            "CTX_AREA_FK100":   "",
            "CTX_AREA_NK100":   "",
        }
        resp = requests.get(url, headers=self._headers(tr_id), params=params, timeout=10)

        if resp.status_code != 200:
            return {"error": f"HTTP {resp.status_code}"}

        d = resp.json()
        if d.get("rt_cd") != "0":
            return {"error": d.get("msg1", "조회 실패")}

        output2 = d.get("output2", [{}])[0]
        cash       = int(output2.get("dnca_tot_amt", 0))
        total_eval = int(output2.get("tot_evlu_amt", 0))

        holdings = []
        for item in d.get("output1", []):
            qty = int(item.get("hldg_qty", 0))
            if qty == 0:
                continue
            holdings.append({
                "code":          item.get("pdno", ""),
                "name":          item.get("prdt_name", ""),
                "qty":           qty,
                "avg_price":     int(item.get("pchs_avg_pric", 0)),
                "current_price": int(item.get("prpr", 0)),
                "eval_amount":   int(item.get("evlu_amt", 0)),
                "profit_loss":   int(item.get("evlu_pfls_amt", 0)),
                "profit_rate":   float(item.get("evlu_pfls_rt", 0)),
            })

        return {
            "cash":       cash,
            "total_eval": total_eval,
            "holdings":   holdings,
        }

    # ------------------------------------------------------------------
    # 주문
    # ------------------------------------------------------------------

    def place_order(self, stock_code: str, side: str, qty: int,
                    price: int = 0, order_type: str = "00") -> dict:
        """
        매수 / 매도 주문 실행

        Args:
            stock_code: 종목코드 (6자리)
            side:       "buy" | "sell"
            qty:        주문 수량
            price:      주문가격 (원). 시장가 주문 시 0
            order_type: "00" 지정가 | "01" 시장가

        Returns:
            {"success": True, "order_no": "...", "message": "..."}
        """
        url = f"{self.base_url}/uapi/domestic-stock/v1/trading/order-cash"

        # 실전/모의 TR ID 구분
        if self.is_paper:
            tr_id = "VTTC0012U" if side == "buy" else "VTTC0011U"
        else:
            tr_id = "TTTC0012U" if side == "buy" else "TTTC0011U"

        payload = {
            "CANO":             self.account_no,
            "ACNT_PRDT_CD":     self.account_type,
            "PDNO":             stock_code,
            "ORD_DVSN":         order_type,
            "ORD_QTY":          str(qty),
            "ORD_UNPR":         "0" if order_type == "01" else str(price),
            "EXCG_ID_DVSN_CD":  "KRX",
        }

        side_kr = "매수" if side == "buy" else "매도"
        print(f"  📤 {side_kr} 주문 → {stock_code} {qty}주 @ {price:,}원")

        resp = requests.post(url, headers=self._headers(tr_id), json=payload, timeout=10)

        if resp.status_code != 200:
            return {"success": False, "error": f"HTTP {resp.status_code}", "message": resp.text}

        d = resp.json()
        if d.get("rt_cd") != "0":
            return {"success": False, "error": d.get("rt_cd"), "message": d.get("msg1", "")}

        output = d.get("output", {})
        return {
            "success":  True,
            "order_no": output.get("ODNO", ""),
            "message":  d.get("msg1", "주문 완료"),
        }

    def place_market_order(self, stock_code: str, side: str, qty: int) -> dict:
        """시장가 주문 단축 메서드"""
        return self.place_order(stock_code, side, qty, price=0, order_type="01")

    # ------------------------------------------------------------------
    # 주문 가능 수량 계산 (예수금 기반)
    # ------------------------------------------------------------------

    def calc_order_qty(self, stock_code: str, budget: int) -> int:
        """
        예산과 현재가를 기반으로 최대 매수 수량 계산

        Args:
            stock_code: 종목코드
            budget:     투자 예산 (원)

        Returns:
            매수 가능 수량 (정수)
        """
        price_info = self.get_current_price(stock_code)
        if "error" in price_info:
            print(f"  ⚠️ {stock_code} 현재가 조회 실패: {price_info['error']}")
            return 0

        current_price = price_info["price"]
        if current_price <= 0:
            return 0

        qty = budget // current_price
        print(f"  💰 {stock_code}: 현재가 {current_price:,}원 → 예산 {budget:,}원 → {qty}주 매수 가능")
        return int(qty)

    # ------------------------------------------------------------------
    # 체결 내역 조회
    # ------------------------------------------------------------------

    def get_order_history(self, date: str = None) -> list:
        """
        당일 또는 특정일 주문 체결 내역 조회

        Args:
            date: "YYYYMMDD" 형식. None이면 오늘

        Returns:
            [{"code", "name", "side", "qty", "price", "status"}, ...]
        """
        if date is None:
            date = datetime.now().strftime("%Y%m%d")

        url = f"{self.base_url}/uapi/domestic-stock/v1/trading/inquire-daily-ccld"
        tr_id = "VTTC0081R" if self.is_paper else "TTTC0081R"

        params = {
            "CANO":             self.account_no,
            "ACNT_PRDT_CD":     self.account_type,
            "INQR_STRT_DT":     date,
            "INQR_END_DT":      date,
            "SLL_BUY_DVSN_CD":  "00",  # 00: 전체
            "INQR_DVSN":        "00",
            "PDNO":             "",
            "CCLD_DVSN":        "01",
            "ORD_GNO_BRNO":     "",
            "ODNO":             "",
            "INQR_DVSN_3":      "00",
            "INQR_DVSN_1":      "",
            "CTX_AREA_FK100":   "",
            "CTX_AREA_NK100":   "",
        }

        resp = requests.get(url, headers=self._headers(tr_id), params=params, timeout=10)
        if resp.status_code != 200:
            return []

        d = resp.json()
        if d.get("rt_cd") != "0":
            return []

        history = []
        for item in d.get("output1", []):
            history.append({
                "code":   item.get("pdno", ""),
                "name":   item.get("prdt_name", ""),
                "side":   "매수" if item.get("sll_buy_dvsn_cd") == "02" else "매도",
                "qty":    int(item.get("ord_qty", 0)),
                "price":  int(item.get("avg_prvs", 0)),
                "status": item.get("ord_tmd", ""),
            })
        return history


# =============================================================================
# 모의 API (실제 KIS 연결 없이 로컬 테스트용)
# =============================================================================

class MockKISApi:
    """
    KIS API 없이 로컬에서 테스트할 수 있는 모의 구현체.
    실제 주문을 실행하지 않으며 콘솔 출력으로 대체합니다.
    """

    def __init__(self):
        self._holdings = {}
        self._cash = 10_000_000  # 가상 예수금 1천만원
        print("  🔵 모의 API 모드 (실제 주문 없음)")

    def authenticate(self): return True

    def get_current_price(self, code: str) -> dict:
        import random
        price = random.randint(5000, 100000)
        return {"code": code, "name": f"종목_{code}", "price": price,
                "change_rate": round(random.uniform(-3, 3), 2)}

    def get_account_balance(self) -> dict:
        return {
            "cash":     self._cash,
            "total_eval": sum(v["qty"] * v["avg_price"]
                              for v in self._holdings.values()),
            "holdings": list(self._holdings.values()),
        }

    def place_order(self, code: str, side: str, qty: int,
                    price: int = 0, order_type: str = "00") -> dict:
        price_info = self.get_current_price(code)
        exec_price = price if price > 0 else price_info["price"]
        amount = exec_price * qty
        side_kr = "매수" if side == "buy" else "매도"

        print(f"  [모의] {side_kr}: {code} {qty}주 @ {exec_price:,}원 = {amount:,}원")

        if side == "buy":
            self._cash -= amount
            if code in self._holdings:
                old = self._holdings[code]
                total_qty   = old["qty"] + qty
                avg_price   = (old["avg_price"] * old["qty"] + exec_price * qty) // total_qty
                self._holdings[code] = {"code": code, "name": code,
                                        "qty": total_qty, "avg_price": avg_price,
                                        "current_price": exec_price}
            else:
                self._holdings[code] = {"code": code, "name": code,
                                        "qty": qty, "avg_price": exec_price,
                                        "current_price": exec_price}
        else:
            self._cash += amount
            if code in self._holdings:
                self._holdings[code]["qty"] -= qty
                if self._holdings[code]["qty"] <= 0:
                    del self._holdings[code]

        return {"success": True, "order_no": f"MOCK-{int(time.time())}", "message": f"{side_kr} 완료"}

    def place_market_order(self, code: str, side: str, qty: int) -> dict:
        return self.place_order(code, side, qty)

    def calc_order_qty(self, code: str, budget: int) -> int:
        price = self.get_current_price(code)["price"]
        return budget // price

    def get_order_history(self, date=None) -> list:
        return []
