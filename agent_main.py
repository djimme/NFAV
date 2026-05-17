#!/usr/bin/env python3
# agent_main.py
# 주식 종목 선정 및 반자동 매매 Agent
#
# 실행: python agent_main.py
#
# 워크플로우:
#   1. 재무 데이터 로드 (derived/*.xlsx)
#   2. 5가지 전략 동시 분석
#   3. 종합 랭킹 생성 & Excel 저장
#   4. 사용자 종목 검토 및 수량 입력
#   5. KIS API로 매수 주문 실행 (사용자 확인 후)
#   6. 계좌 현황 조회

import os
import sys
import datetime
import pandas as pd

# 로컬 모듈
from agent_config import (
    KIS_CONFIG, DATA_CONFIG, STRATEGY_CONFIG,
    COMPOSITE_WEIGHTS, TRADING_CONFIG, COMMON_FILTERS
)
import agent_strategies as strats
from fin_utils import save_styled_excel


# =============================================================================
# 디스플레이 유틸리티
# =============================================================================

BANNER = """
╔══════════════════════════════════════════════════════════════╗
║         📈  NFAV 주식 종목 선정 & 매매 Agent  📈             ║
║                                                              ║
║  전략: PEG · Piotroski · Greenblatt · 멀티팩터 · NCAV       ║
║  증권사: 한국투자증권 (KIS) REST API                         ║
╚══════════════════════════════════════════════════════════════╝
"""

MENU = """
┌─────────────────────────────────────────┐
│  메뉴                                   │
│  1. 전략 분석 실행 (종목 선정)           │
│  2. 최근 분석 결과 로드                  │
│  3. 종목 검토 & 매수 주문               │
│  4. 계좌 현황 조회                      │
│  5. 체결 내역 조회                      │
│  6. 개별 종목 현재가 조회               │
│  0. 종료                                │
└─────────────────────────────────────────┘
"""


def hr(char="─", width=60):
    print(char * width)


def section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


# =============================================================================
# KIS API 초기화
# =============================================================================

def init_api(use_mock: bool = False):
    """KIS API 또는 모의 API 초기화"""
    from agent_kis_api import KISApi, MockKISApi

    if use_mock:
        print("\n🔵 모의 API 모드로 실행합니다 (실제 주문 없음)")
        return MockKISApi()

    if KIS_CONFIG["app_key"] == "YOUR_APP_KEY":
        print("\n⚠️  KIS API 키가 설정되지 않았습니다.")
        print("   agent_config.py → KIS_CONFIG 에 API 키를 입력하세요.")
        print("   지금은 모의 API 모드로 계속합니다.\n")
        return None  # API 없이 종목 선정만 사용 가능

    api = KISApi(KIS_CONFIG)
    if not api.authenticate():
        print("  ❌ KIS 인증 실패. 모의 모드로 전환합니다.")
        return None
    return api


# =============================================================================
# 메뉴 1: 전략 분석 실행
# =============================================================================

def run_analysis() -> dict | None:
    """모든 전략을 실행하고 결과를 저장합니다."""
    section("전략 분석 시작")

    try:
        results = strats.run_all_strategies(
            config=DATA_CONFIG,
            strategy_cfg=STRATEGY_CONFIG,
            composite_weights=COMPOSITE_WEIGHTS,
            common_filter_cfg=COMMON_FILTERS,
        )
    except FileNotFoundError as e:
        print(f"\n❌ 오류: {e}")
        print("   agent_config.py → DATA_CONFIG 경로를 확인하세요.")
        return None

    # 결과 저장
    now = datetime.datetime.now()
    timestamp = now.strftime("%Y%m%d_%H%M")
    output_path = f"derived/agent_result_{timestamp}.xlsx"

    save_dict = {}
    label_map = {
        "composite":  "종합랭킹",
        "peg":        "PEG전략",
        "piotroski":  "Piotroski",
        "greenblatt": "Greenblatt",
        "multifactor":"멀티팩터",
        "ncav":       "NCAV",
        "nfav":       "NFAV",
    }
    for key, label in label_map.items():
        df = results.get(key, pd.DataFrame())
        if df is not None and not df.empty:
            save_dict[label] = df

    if save_dict:
        from fin_utils import save_styled_excel_multisheet
        # save_styled_excel_multisheet는 [(name, df), ...] 형식 필요
        sheets_list = list(save_dict.items())
        save_styled_excel_multisheet(sheets_list, output_path)
        print(f"\n💾 결과 저장: {output_path}")

    _show_composite_top(results.get("composite", pd.DataFrame()))
    return results


def _show_composite_top(df: pd.DataFrame, n: int = 20):
    """종합 랭킹 상위 N개 출력"""
    if df is None or df.empty:
        print("  (결과 없음)")
        return

    section(f"종합 랭킹 TOP {n}")
    score_cols = [c for c in df.columns if "점수" in c or c == "종합점수"]
    show_cols  = ["종목코드", "종목명", "마켓분야", "FICS분야"] + score_cols

    show_cols  = [c for c in show_cols if c in df.columns]
    top = df[show_cols].head(n).reset_index(drop=True)
    top.index += 1

    pd.set_option("display.max_columns", None)
    pd.set_option("display.width", 160)
    pd.set_option("display.float_format", "{:.3f}".format)
    print(top.to_string())
    hr()


# =============================================================================
# 메뉴 2: 최근 결과 로드
# =============================================================================

def load_recent_results() -> dict | None:
    """가장 최근 분석 결과 파일을 로드합니다."""
    import glob
    files = sorted(glob.glob("derived/agent_result_*.xlsx"), reverse=True)
    if not files:
        print("\n⚠️ 저장된 분석 결과 없음. 먼저 분석을 실행하세요 (메뉴 1).")
        return None

    latest = files[0]
    print(f"\n📂 로딩: {latest}")
    xl = pd.ExcelFile(latest)

    results = {}
    key_map = {v: k for k, v in {
        "composite":  "종합랭킹",
        "peg":        "PEG전략",
        "piotroski":  "Piotroski",
        "greenblatt": "Greenblatt",
        "multifactor":"멀티팩터",
        "ncav":       "NCAV",
        "nfav":       "NFAV",
    }.items()}

    for sheet in xl.sheet_names:
        key = key_map.get(sheet, sheet)
        results[key] = pd.read_excel(latest, sheet_name=sheet, dtype={"종목코드": str})
        if "종목코드" in results[key].columns:
            results[key]["종목코드"] = results[key]["종목코드"].str.zfill(6)

    _show_composite_top(results.get("composite", pd.DataFrame()))
    return results


# =============================================================================
# 메뉴 3: 종목 검토 & 매수 주문
# =============================================================================

def review_and_order(results: dict, api) -> None:
    """
    종합 랭킹에서 종목을 선택하고 매수 주문을 실행합니다.
    """
    if not results or results.get("composite") is None or results["composite"].empty:
        print("\n⚠️ 분석 결과가 없습니다. 먼저 분석을 실행하세요.")
        return

    composite = results["composite"]

    section("종목 검토 & 매수 주문")

    # 종합 랭킹 출력 (상위 30개)
    top30 = composite[["종목코드", "종목명", "마켓분야", "FICS분야", "종합점수",
                        "참여전략수"]].head(30).reset_index(drop=True)
    top30.index += 1
    print(top30.to_string())
    hr()

    # 현재가 조회 여부
    if api is None:
        print("\n⚠️ KIS API 미연결 상태. 종목 선택만 가능합니다.")
        _select_only_mode(composite)
        return

    print("\n매수할 종목 번호를 입력하세요 (복수 선택 예: 1,3,5 / 전체 상위N: top10)")
    print("(엔터로 건너뛰기)")
    user_input = input("▶ ").strip()

    if not user_input:
        return

    # 종목 인덱스 파싱
    if user_input.lower().startswith("top"):
        n = int(user_input[3:]) if user_input[3:].isdigit() else 5
        selected_idx = list(range(1, n + 1))
    else:
        try:
            selected_idx = [int(x) for x in user_input.split(",")]
        except ValueError:
            print("  ❌ 잘못된 입력")
            return

    # 선택 종목 처리
    invest_per = TRADING_CONFIG.get("invest_per_stock", 1_000_000)
    budget_input = input(f"\n종목당 투자금액 (엔터 시 {invest_per:,}원): ").strip()
    if budget_input.isdigit():
        invest_per = int(budget_input)

    orders = []
    for idx in selected_idx:
        if idx < 1 or idx > len(top30):
            continue
        row = top30.iloc[idx - 1]
        code = row["종목코드"]
        name = row["종목명"]

        price_info = api.get_current_price(code)
        if "error" in price_info:
            print(f"  ❌ {code} 현재가 조회 실패: {price_info['error']}")
            continue

        qty = invest_per // price_info["price"] if price_info["price"] > 0 else 0

        print(f"\n  [{idx}] {name} ({code})")
        print(f"       현재가: {price_info['price']:,}원  등락: {price_info['change_rate']:+.2f}%")
        print(f"       투자금: {invest_per:,}원 → {qty}주 매수")

        if qty <= 0:
            print("  ⚠️ 수량 부족 (예산이 현재가보다 낮음)")
            continue

        orders.append({
            "code":  code,
            "name":  name,
            "qty":   qty,
            "price": price_info["price"],
        })

    if not orders:
        print("\n선택된 종목이 없습니다.")
        return

    # 최종 확인
    section("주문 최종 확인")
    total_amount = sum(o["qty"] * o["price"] for o in orders)
    for o in orders:
        print(f"  {o['name']} ({o['code']}) {o['qty']}주 @ {o['price']:,}원"
              f" = {o['qty'] * o['price']:,}원")
    hr()
    print(f"  총 투자금액: {total_amount:,}원")

    order_type = TRADING_CONFIG.get("order_type", "00")
    type_label  = "지정가" if order_type == "00" else "시장가"
    print(f"  주문 유형: {type_label}")

    confirm = input("\n실행할까요? (y/N): ").strip().lower()
    if confirm != "y":
        print("  주문 취소됨.")
        return

    # 주문 실행
    section("주문 실행")
    success_count = 0
    for o in orders:
        result = api.place_order(o["code"], "buy", o["qty"], o["price"], order_type)
        if result["success"]:
            print(f"  ✅ {o['name']} 매수 완료 (주문번호: {result['order_no']})")
            success_count += 1
        else:
            print(f"  ❌ {o['name']} 주문 실패: {result.get('message', '')}")

    print(f"\n  총 {success_count}/{len(orders)}개 종목 주문 완료")


def _select_only_mode(composite: pd.DataFrame) -> None:
    """API 없이 종목만 선택해서 출력"""
    top30 = composite.head(30).reset_index(drop=True)
    top30.index += 1
    print("\n관심 종목 번호를 입력하세요 (예: 1,3,5 / 엔터로 건너뛰기)")
    user_input = input("▶ ").strip()
    if not user_input:
        return
    try:
        selected_idx = [int(x) for x in user_input.split(",")]
    except ValueError:
        return

    print("\n\n=== 선택한 관심 종목 ===")
    for idx in selected_idx:
        if 1 <= idx <= len(top30):
            row = top30.iloc[idx - 1]
            print(f"  {idx}. {row['종목명']} ({row['종목코드']}) - {row.get('마켓분야','')}")
    hr()


# =============================================================================
# 메뉴 4: 계좌 현황
# =============================================================================

def show_account(api) -> None:
    if api is None:
        print("\n⚠️ KIS API 미연결")
        return

    section("계좌 현황")
    bal = api.get_account_balance()

    if "error" in bal:
        print(f"  ❌ 조회 실패: {bal['error']}")
        return

    print(f"  💰 예수금:      {bal['cash']:>15,}원")
    print(f"  📊 총 평가금액: {bal['total_eval']:>15,}원")
    total = bal["cash"] + bal["total_eval"]
    print(f"  🏦 총 자산:     {total:>15,}원")
    hr()

    holdings = bal.get("holdings", [])
    if holdings:
        print(f"\n  보유 종목 ({len(holdings)}개)")
        hr()
        header = f"  {'종목코드':>8}  {'종목명':<12}  {'수량':>6}  {'평균단가':>10}  {'현재가':>10}  {'손익':>12}  {'수익률':>7}"
        print(header)
        hr()
        for h in holdings:
            print(f"  {h['code']:>8}  {h['name']:<12}  {h['qty']:>6}  "
                  f"{h['avg_price']:>10,}  {h['current_price']:>10,}  "
                  f"{h['profit_loss']:>+12,}  {h['profit_rate']:>+6.2f}%")
    else:
        print("\n  보유 종목 없음")
    hr()


# =============================================================================
# 메뉴 5: 체결 내역
# =============================================================================

def show_order_history(api) -> None:
    if api is None:
        print("\n⚠️ KIS API 미연결")
        return

    section("체결 내역 (오늘)")
    history = api.get_order_history()

    if not history:
        print("  오늘 체결 내역 없음")
        return

    for h in history:
        print(f"  {h['side']}  {h['code']} {h['name']}  "
              f"{h['qty']}주 @ {h['price']:,}원  [{h['status']}]")
    hr()


# =============================================================================
# 메뉴 6: 현재가 조회
# =============================================================================

def show_price(api) -> None:
    if api is None:
        print("\n⚠️ KIS API 미연결")
        return

    code = input("\n종목코드 입력 (예: 005930): ").strip().zfill(6)
    info = api.get_current_price(code)

    if "error" in info:
        print(f"  ❌ {info['error']}")
        return

    section(f"{info['name']} ({code}) 현재가")
    print(f"  현재가: {info['price']:>12,}원  ({info['change_rate']:+.2f}%)")
    print(f"  시가:   {info['open']:>12,}원")
    print(f"  고가:   {info['high']:>12,}원")
    print(f"  저가:   {info['low']:>12,}원")
    print(f"  거래량: {info['volume']:>12,}주")
    hr()


# =============================================================================
# 메인 루프
# =============================================================================

def main():
    print(BANNER)

    # API 초기화
    print("KIS API 설정 확인 중...")
    use_mock = "--mock" in sys.argv
    api = init_api(use_mock=use_mock)

    results = None

    while True:
        print(MENU)
        choice = input("▶ 메뉴 선택: ").strip()

        if choice == "1":
            results = run_analysis()

        elif choice == "2":
            results = load_recent_results()

        elif choice == "3":
            if results is None:
                print("\n⚠️ 분석 결과 없음. 먼저 1번(전략 분석) 또는 2번(결과 로드)을 실행하세요.")
            else:
                review_and_order(results, api)

        elif choice == "4":
            show_account(api)

        elif choice == "5":
            show_order_history(api)

        elif choice == "6":
            show_price(api)

        elif choice == "0":
            print("\n👋 Agent를 종료합니다. 수익나세요! 📈\n")
            break

        else:
            print("  잘못된 입력입니다.")


if __name__ == "__main__":
    main()
