# 전략 레퍼런스

이 저장소에서 사용하는 종목 선정 전략 목록. 각 전략의 이론·입력·출력·파라미터를 정리한 문서.
풀어 쓴 설명은 `docs/종목 선정 전략 설명.html` 참고.

파라미터는 `agent_config.py`의 `STRATEGY_CONFIG`에서 설정.

현재 상태 (2026-11-25): PEG · Piotroski · 멀티팩터 · NCAV · NFAV 사용 중, Greenblatt는 제외(`enabled = False`).
재무비율·주당 지표는 DART·KRX로 직접 계산한 값(`dart_ratio`)이 기본이고, 멀티팩터의 팩터 점수만 FnGuide 값을 쓴다.

---

## 0. 공통 필터 · 가치함정 필터

모든 전략에 앞서 `strat_utils.apply_common_filters` → `apply_value_trap_filter` 순으로 적용한다.

### 공통 필터 (COMMON_FILTERS)

| 키 | 기본값 | 설명 |
|----|--------|------|
| `exclude_spac` | True | 스팩 제외 |
| `min_market_cap_억` | 100 | 최소 시가총액(억원) |
| `exclude_no_trade` | True | KRX 기준일 거래량 0 종목(거래정지 등) 제외 |
| `min_trading_value_억` | 0 | 기준일 최소 거래대금(억원), 0이면 사용 안 함 |

### 가치함정 필터 (COMMON_FILTERS["value_trap"])

싸 보이지만 싼 이유가 있는 종목을 뺀다. 자료는 `python apiCollect.py dart_risk` → `derived/dart_risk_YYYY_MM.xlsx`
(`dartRisk.py`: DART 감사의견 API + 최근 365일 주요사항보고서 목록). 파일이 없으면 필터를 건너뛴다.
제외된 종목과 사유는 결과 파일의 `가치함정_제외` 시트에 남는다.

| 키 | 기본값 | 제외 사유 |
|----|--------|----------|
| `exclude_bad_audit` | True | 최근 사업보고서 감사의견이 한정·부적정·의견거절 |
| `exclude_going_concern` | True | 감사보고서 강조사항에 계속기업 불확실성 |
| `exclude_cb_bw` | True | 최근 1년 전환사채(CB)·신주인수권부사채(BW) 발행 결정 |
| `exclude_rights_offering` | True | 최근 1년 유상증자 결정 — 아래 "유상증자 판단"에 따라 제외·통과 |
| `exclude_distress` | True | 회생절차·해산사유·영업정지·부도·채권은행 관리절차 공시 |
| `exclude_eb` | False | 교환사채 발행 결정 (표시만) |
| `exclude_capital_reduction` | False | 감자 결정 (표시만) |
| `min_issue_to_cap_pct` | 0 | CB·BW·유상증자 금액 합계가 시가총액의 이 비율(%) 미만이면 발행 사유로는 빼지 않음. 0 = 금액과 관계없이 제외 |

감사의견을 확인할 수 없는 종목(신규 상장 등)은 빼지 않는다.

#### 유상증자 판단 (2026-11-27)

`rights_offering_mode` 가 `"judge"`(기본)면 위에서부터 차례로 보고 처음 걸리는 판정을 쓴다. `"all"` 이면 한 건이라도 있으면 뺀다.

| 순서 | 판정 | 조건 |
|------|------|------|
| 1 | 제외: 반복 조달 | 1년 안에 CB·BW도 발행했거나 유상증자 2건 이상. 합계 증자비율이 `rights_small_pct` 미만이면 반복으로 보지 않음 |
| 2 | 제외: N년 연속 영업적자 | 최근 연간 영업이익이 `rights_loss_years` 해 연속 적자 |
| 3 | 제외: 대규모·비성장 목적 | 증자비율 `rights_large_pct` 이상, 성장 목적 비중 `rights_growth_min_pct` 미만 |
| 4 | 제외: 공모·비성장 목적 | 주주배정·일반공모(제3자배정 없음), 증자비율 `rights_small_pct` 이상, 성장 목적 비중 `rights_growth_min_pct` 미만 |
| 5 | 통과: 소규모 | 증자비율 `rights_small_pct` 미만 |
| 6 | 주의: 성장 목적 | 성장 목적 비중 `rights_growth_min_pct` 이상 |
| 7 | 주의: 운영자금 등 / 주의: 자료 없음 | 나머지 (증자비율을 모르면 '자료 없음') |

| 키 | 기본값 | 설명 |
|----|--------|------|
| `rights_offering_mode` | "judge" | "judge" = 상황 판단, "all" = 모두 제외 |
| `rights_small_pct` | 10 | 증자비율(신주 수 ÷ 증자 전 주식 수, %)이 이 값 미만이면 소규모 |
| `rights_large_pct` | 30 | 이 값 이상이면 대규모 |
| `rights_growth_min_pct` | 50 | 성장 목적(시설·영업양수·타법인 증권 취득) 비중 기준 |
| `rights_loss_years` | 3 | 연속 영업적자 햇수 기준 |

- 통과 종목과 판정은 결과 파일의 `유상증자_통과` 시트, 제외 종목은 `가치함정_제외` 시트(사유 예: `유상증자(반복 조달)`)
- CB·BW를 발행한 종목은 유상증자 판정과 관계없이 `CB·BW 발행` 사유로 빠진다
- 할인율·제3자배정 대상자·보호예수·최대주주 참여는 자료에 없어 판단에 쓰지 못한다. 기준값은 통념값이며 수익률로 검증하지 않았다
- 근거와 풀어 쓴 설명: `docs/종목 선정 전략 설명.html` 4절

---

## 1. PEG 전략 (Peter Lynch)

**파일:** `strat_peg.py`

### 이론

PEG(Price/Earnings to Growth) = PER ÷ EPS 연간 성장률(%)

Peter Lynch가 고안한 지표. 성장성을 감안한 밸류에이션으로, 단순 PER보다 성장주 평가에 적합.

| PEG 범위 | 해석 |
|----------|------|
| < 0.5 | 매우 매력적 (강력 매수 후보) |
| 0.5 ~ 1.0 | 매력적 (Lynch 기준 저평가) |
| 1.0 ~ 2.0 | 적정 가격 |
| > 2.0 | 과대평가 |

### EPS 성장률 계산 (우선순위)

1. **3년 CAGR** (절대값 EPS 4개년 필요): `(EPS_최신 / EPS_3년전)^(1/3) − 1`
   - 단일 연도 이상치에 덜 민감, 이론에 가장 부합
2. **Fallback**: 최근 3개년 연간 EPS증가율 평균

### 입력 컬럼

| 컬럼 | 출처 | 설명 |
|------|------|------|
| `{YYYY}_PER(배)` | dart_ratio | 주가수익비율 (최근 거래일 종가 기준) |
| `{YYYY}_EPS(원)` | dart_ratio | 주당순이익 절대값 (4개년) |
| `{YYYY}(누적)_EPS증가율` | dart_ratio | EPS 증가율 (fallback) |
| `{YYYY}(누적)_부채비율` | dart_ratio | 재무 안정성 필터 |

### 파라미터 (STRATEGY_CONFIG["peg"])

| 키 | 기본값 | 설명 |
|----|--------|------|
| `enabled` | `true` | 전략 활성화 여부 |
| `max_peg` | `1.0` | PEG 상한 |
| `min_eps_growth` | `0.0` | EPS 성장률 하한 (%) |
| `max_debt_ratio` | `100.0` | 부채비율 상한 (%) |

### 출력 컬럼

`PER({연도})`, `EPS증가율(%,{방법})`, `PEG`, `부채비율(%)`, `PEG_점수`

---

## 2. Piotroski F-Score

**파일:** `strat_piotroski.py`

### 이론

Joseph Piotroski (2000, Journal of Accounting Research) 제안.  
9개 재무 이진 기준(각 0/1점) 합산으로 재무 건전성을 정량화.  
고 BM(Book-to-Market) 종목 내에서 강한 종목을 분리하는 데 효과적.

| F-Score | 해석 |
|---------|------|
| 8 ~ 9 | 강한 재무 건전성 (매수 후보) |
| 3 ~ 7 | 보통 |
| 0 ~ 2 | 재무 부실 위험 (공매도 후보) |

### 9개 기준

**수익성 (4점)**
| 항목 | 기준 | 측정 의미 |
|------|------|----------|
| F1 | ROA > 0 | 자산 대비 이익 창출 능력 |
| F2 | 영업활동현금흐름 > 0 | 실제 현금 창출 |
| F3 | ROA 전년 대비 증가 | 수익성 개선 추세 |
| F4 | 영업CF > 당기순이익 | 발생주의 품질 (이익 조작 방지) |

**레버리지/유동성 (3점)**
| 항목 | 기준 | 측정 의미 |
|------|------|----------|
| F5 | 부채비율 전년 대비 감소 | 재무 구조 개선 |
| F6 | 유동비율 전년 대비 증가 | 단기 유동성 개선 |
| F7 | 신주 발행 없음 | (항상 0 처리 → 실제 최고점은 8점. 유상증자 종목은 가치함정 필터가 따로 제외) |

**운영 효율성 (2점)**
| 항목 | 기준 | 측정 의미 |
|------|------|----------|
| F8 | 영업이익률 전년 대비 개선 | 마진 개선 |
| F9 | 총자산회전율 전년 대비 개선 | 자산 활용 효율 개선 |

### 입력 컬럼

| 컬럼 | 출처 |
|------|------|
| `{YYYY}(누적)_ROA` (현재/전년) | dart_ratio |
| `{YYYY}(누적)_부채비율` (현재/전년) | dart_ratio |
| `{YYYY}(누적)_유동비율` (현재/전년) | dart_ratio |
| `{YYYY}(누적)_영업이익률` (현재/전년) | dart_ratio |
| `{YYYY}(누적)_총자산회전율` (현재/전년) | dart_ratio |
| `{YYYY}(연간)_영업활동현금흐름` | dart_finance |
| `{YYYY}(연간)_당기순이익` | dart_finance |

### 파라미터 (STRATEGY_CONFIG["piotroski"])

| 키 | 기본값 | 설명 |
|----|--------|------|
| `enabled` | `true` | 전략 활성화 여부 |
| `min_score` | `6` | F-Score 최소 기준 |

### 출력 컬럼

`F_Score`, `Piotroski_점수`, `F1_ROA양수` ~ `F9_자산회전율개선`

---

## 3. Greenblatt Magic Formula (현재 제외)

**파일:** `strat_greenblatt.py`

> 2026-11부터 종목 선정에서 제외(`enabled = False`). DART 기준 EV/EBITDA에 필요한 감가상각비가 일반 기업의 55%(시총 500억 미만은 27%)에만 있어 소형주가 후보에서 빠지기 때문이다. 다시 쓰려면 `enabled = True`, 필요하면 `ev_metric = "EV/EBIT"`.

### 이론

Joel Greenblatt "The Little Book That Beats the Market" (2005).  
"좋은 기업(높은 ROIC)을 싼 가격(높은 수익수익률)에 산다"는 원칙.  
개별 절대값이 아닌 **랭킹 합산**으로 선정해 과적합 방지.

### 두 지표

| 지표 | 계산식 | 의미 |
|------|--------|------|
| 수익수익률 (Earnings Yield) | 1 ÷ EV/EBITDA | 높을수록 저평가 |
| 자본수익률 (ROIC) | ROIC (%) | 높을수록 우량 기업 |

두 지표를 각각 전체 종목 랭킹 → **랭킹 합이 낮은** 상위 N개 선정.

> Greenblatt 원본 기준: 금융주·유틸리티 제외, 시총 5천만달러 이상

### 입력 컬럼

| 컬럼 | 출처 |
|------|------|
| `{YYYY}_EV/EBITDA` 또는 `{YYYY}_EV/EBIT` | dart_ratio |
| `{YYYY}(누적)_ROIC` | dart_ratio |
| `{YYYY}(누적)_부채비율` | dart_ratio |

### 파라미터 (STRATEGY_CONFIG["greenblatt"])

| 키 | 기본값 | 설명 |
|----|--------|------|
| `enabled` | `false` | 전략 활성화 여부 |
| `max_debt_ratio` | `150.0` | 부채비율 상한 (%) |
| `top_n` | `30` | 선정 종목 수 |
| `ev_metric` | `EV/EBITDA` | 수익수익률에 쓰는 배수 (`EV/EBIT` 가능, 환경변수 `NFAV_GREENBLATT_EV`) |

### 출력 컬럼

`수익수익률`, `ROIC(%)`, `EY_랭크`, `ROIC_랭크`, `Magic_랭크합`, `Greenblatt_점수`

---

## 4. 멀티팩터 스코어링

**파일:** `strat_multifactor.py`

### 이론

단일 팩터 전략은 특정 시장 국면에서 성과가 극단적으로 나빠지는 경향.  
여러 팩터를 결합하면 리스크 조정 수익률이 안정화됨 (Fama-French, AQR 연구 기반).  
FnGuide가 제공하는 팩터별 Z-Score를 가중 합산해 종합 순위 산출.

### 사용 팩터

| 팩터 | 컬럼 | 방향 | 설명 |
|------|------|------|------|
| 수익건전성 | `수익건전성_종목` | ↑ 높을수록 좋음 | 이익의 안정성·지속성 |
| 성장성 | `성장성_종목` | ↑ | 매출/이익 성장성 |
| 밸류 | `밸류_종목` | ↑ | 저평가 정도 (PBR, PER 등 역수) |
| 모멘텀 | `모멘텀_종목` | ↑ | 과거 3~12개월 가격 모멘텀 |
| 변동성 | `변동성_종목` | ↓ 낮을수록 좋음 | 가격 변동성 (가중치 음수) |

### 기본 가중치

```
수익건전성: 0.25 / 성장성: 0.25 / 밸류: 0.20 / 모멘텀: 0.15 / 변동성: -0.15
```

### 파라미터 (STRATEGY_CONFIG["multifactor"])

| 키 | 기본값 | 설명 |
|----|--------|------|
| `enabled` | `true` | 전략 활성화 여부 |
| `top_n` | `30` | 선정 종목 수 |
| `weights` | (위 기본값) | 팩터별 가중치 dict |

### 출력 컬럼

`수익건전성_종목`, `성장성_종목`, `밸류_종목`, `모멘텀_종목`, `변동성_종목`, `멀티팩터_점수`

---

## 5. NCAV / NFAV (Benjamin Graham 계열)

**파일:** `strat_ncav_nfav.py` (다른 전략과 같이 `merge_base` 결과를 받아 모듈 안에서 계산)

### 이론

기업의 청산가치·순금융자산보다 시가총액이 낮은 종목 = 극단적 저평가.

### 지표

**NCAV (Net Current Asset Value)**
```
NCAV    = 유동자산 − 부채총계
NCAV_R  = NCAV / 시가총액
```
- NCAV_R > 1: 시가총액 < 순유동자산 → 극단적 저평가 (Graham 권장 ≥ 1.5)

**NFAV (Net Financial Asset Value)** — 두 가지를 함께 계산 (2026-11 결정)
```
금융자산 = 현금및현금성자산 + 유동금융자산 + 장기금융자산
NFAV_A  = 금융자산 − 부채총계 − 비지배지분          (보수적 · nfav.py 기준, 사경인식 NCAV 변형)
NFAV_B  = 금융자산 − 이자부부채                    (재무구조 · 순현금)
          이자부부채 = 차입금 + 사채 + 유동성장기부채 + 리스부채
```
- 선정: `NFAV_B_R > min_nfav_b_r`(기본 0, 순현금 기업)로 거른 뒤 `NFAV_A_R` 높은 순으로 `top_n`
- 검산: NFAV_B − NFAV_A = (부채총계 − 이자부부채) + 비지배지분 = 이자 없는 영업부채 + 비지배지분

### 데이터 소스

`strat_utils.load_all_data()`가 읽어 `merge_base()`에서 `DART_*` 컬럼으로 합친다.
- `derived/dart_balance_YYYY_MM.xlsx` ← `python apiCollect.py dart_balance` (OpenDART 최신 재무상태표)
- `derived/market_cap_YYYY_MM_DD.xlsx` ← `python apiCollect.py krx_marketcap` (KRX Open API, 전 종목 일괄 · 대체: `kb_marketcap`)

### 파라미터 (STRATEGY_CONFIG)

| 키 | 기본값 | 설명 |
|----|--------|------|
| `ncav.min_ncav_r` | 0.0 | NCAV_R 최솟값 |
| `ncav.require_positive_income` | True | 당기순이익(누적) > 0 |
| `nfav.min_nfav_b_r` | 0.0 | NFAV_B / 시총 최솟값 |
| `nfav.min_nfav_a_r` | None | NFAV_A / 시총 최솟값 (None = 순위만) |
| `nfav.max_debt_ratio` | 150.0 | 부채비율(%) 최대값 |
| `nfav.top_n` | 30 | 선정 종목 수 |
| `nfav.exclude_other_financial` | False | True면 계정명에 '기타'가 붙은 금융자산(대여금·보증금 등 섞일 수 있음)을 금융자산에서 제외 |
| `COMMON_FILTERS.exclude_no_trade` | True | KRX 기준일 거래량 0 종목(거래정지 등) 제외 — 모든 전략 공통 |

### 주의사항

- 금융업(은행·증권·보험)은 유동/비유동 구분이 없어 제외
- 창투사는 보유 지분 공정가치가 금융자산에 크게 잡혀 NFAV가 과대해질 수 있음
- 소형주·저유동성 종목 집중 경향 → 실제 매수 가능성 별도 검토
- 이전 방식(`calc_NCAV.py`, `calc_NFAV.py` → `*_output_*.xlsx`)은 더 이상 쓰지 않음 (파일은 보존)

---

## 종합 스코어링

각 전략의 정규화 점수(0~1)에 가중치를 곱해 종합 점수 산출.

```
종합점수 = Σ (전략_점수 × 가중치)  [해당 전략에 포함된 종목만 가중치 적용]
```

### 기본 가중치 (COMPOSITE_WEIGHTS)

| 전략 | 가중치 |
|------|--------|
| PEG | 0.20 |
| Piotroski | 0.25 |
| Greenblatt | 0.25 |
| 멀티팩터 | 0.20 |
| NCAV | 0.10 |
| NFAV | 0.05 (설정에 없어 코드 기본값) |

1개 이상 전략에 포함된 종목만 최종 리스트에 등재. Greenblatt는 제외 중이라 점수가 없다.
가중치 합으로 나누지 않으므로, 여러 전략을 동시에 통과한 종목일수록 종합점수가 높아진다.

---

## 새 전략 추가 방법

1. `strat_{전략명}.py` 파일 생성 (이 문서 형식으로 상단 주석 작성)
2. `agent_strategies.py`에 `from strat_{전략명} import strategy_{전략명}` 추가
3. `run_all_strategies()`에 실행 블록 추가
4. `build_composite_score()`에 점수 컬럼 연결
5. `agent_config.py`의 `STRATEGY_CONFIG`에 파라미터 추가
6. 이 문서(`strategy.md`)에 전략 설명 추가
