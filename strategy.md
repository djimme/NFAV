# 전략 레퍼런스

NFAV에서 사용하는 종목 선정 전략 목록. 각 전략의 이론·입력·출력·파라미터를 정리한 문서.

파라미터는 `agent_config.py`의 `STRATEGY_CONFIG`에서 설정.

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
| `{YYYY}_PER(배)` | snapshot | 주가수익비율 |
| `{YYYY}_EPS(원)` 또는 `{YYYY}_EPS` | invest_idx | 주당순이익 절대값 (4개년) |
| `{YYYY}(누적)_EPS증가율` | ratio | EPS 증가율 (fallback) |
| `{YYYY}(누적)_부채비율` | ratio | 재무 안정성 필터 |

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
| F7 | 신주 발행 없음 | (데이터 미제공 → 항상 0 처리) |

**운영 효율성 (2점)**
| 항목 | 기준 | 측정 의미 |
|------|------|----------|
| F8 | 영업이익률 전년 대비 개선 | 마진 개선 |
| F9 | 총자산회전율 전년 대비 개선 | 자산 활용 효율 개선 |

### 입력 컬럼

| 컬럼 | 출처 |
|------|------|
| `{YYYY}(누적)_ROA` (현재/전년) | ratio |
| `{YYYY}(누적)_부채비율` (현재/전년) | ratio |
| `{YYYY}(누적)_유동비율` (현재/전년) | ratio |
| `{YYYY}(누적)_영업이익률` (현재/전년) | ratio |
| `{YYYY}(누적)_총자산회전율` (현재/전년) | ratio |
| `{YYYY}(연간)_영업활동현금흐름` | finance |
| `{YYYY}(연간)_당기순이익` | finance |

### 파라미터 (STRATEGY_CONFIG["piotroski"])

| 키 | 기본값 | 설명 |
|----|--------|------|
| `enabled` | `true` | 전략 활성화 여부 |
| `min_score` | `6` | F-Score 최소 기준 |

### 출력 컬럼

`F_Score`, `Piotroski_점수`, `F1_ROA양수` ~ `F9_자산회전율개선`

---

## 3. Greenblatt Magic Formula

**파일:** `strat_greenblatt.py`

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
| `{YYYY}_EV/EBITDA` | invest_idx |
| `{YYYY}(누적)_ROIC` | ratio |
| `{YYYY}(누적)_부채비율` | ratio |

### 파라미터 (STRATEGY_CONFIG["greenblatt"])

| 키 | 기본값 | 설명 |
|----|--------|------|
| `enabled` | `true` | 전략 활성화 여부 |
| `max_debt_ratio` | `150.0` | 부채비율 상한 (%) |
| `top_n` | `30` | 선정 종목 수 |

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
| NCAV | 0.05 |
| NFAV | 0.05 |

1개 이상 전략에 포함된 종목만 최종 리스트에 등재.

---

## 새 전략 추가 방법

1. `strat_{전략명}.py` 파일 생성 (이 문서 형식으로 상단 주석 작성)
2. `agent_strategies.py`에 `from strat_{전략명} import strategy_{전략명}` 추가
3. `run_all_strategies()`에 실행 블록 추가
4. `build_composite_score()`에 점수 컬럼 연결
5. `agent_config.py`의 `STRATEGY_CONFIG`에 파라미터 추가
6. 이 문서(`strategy.md`)에 전략 설명 추가
