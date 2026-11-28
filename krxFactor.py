"""
멀티팩터 전략에 쓰는 팩터 점수를 DART·KRX 값으로 직접 계산한다 (FnGuide invest_idx 팩터 점수 대체)

원천
  - 재무 지표: derived/dart_ratio_*.xlsx (python apiCollect.py dart_ratio) — 종목별 최근 사업연도 값
  - 주가: KRX 일별매매정보 월말 종가 13개월치 + 최근 거래일 종가 — derived/krx_cache (없는 달만 새로 받는다)

팩터 정의 (모두 전 종목 대비 표준점수. 구성 지표를 각각 표준점수로 만든 뒤 평균하고 다시 표준화한다):
  수익건전성_종목 (↑)  ROE · ROA · 영업이익률
  성장성_종목     (↑)  매출증가율 · EPS증가율          (EPS증가율은 전년 EPS가 0 이하이면 비어 있다)
  밸류_종목       (↑)  E/P(EPS ÷ 현재가) · B/P(BPS ÷ 현재가)   (적자 기업은 E/P가 음수)
  모멘텀_종목     (↑)  12-1개월 수익률: 13개월 전 월말 → 1개월 전 월말 (최근 1개월은 뺀다)
  변동성_종목     (↓)  최근 12개월 월간 수익률의 표준편차
구성 지표는 위아래 5%를 잘라(윈저라이즈) 극단값의 영향을 줄인다. 구성 지표가 하나도 없으면 빈 값.

FnGuide 팩터 점수는 FnGuide 자체 모델(산식 비공개)이라 값이 같지 않다. 이름만 같게 두어
strat_multifactor 가 그대로 읽는다. 구성 지표 원값은 '팩터_' 로 시작하는 열에 함께 남긴다.

수익률의 주식수 조정: 월말 사이에 KRX 상장주식수가 딱 떨어지는 배수(2배, 1/10 등)로 바뀌었거나
1.45배 이상·0.7배 이하로 바뀌면 액면분할·병합·무상증자로 보고 그 배수만큼 주가를 조정한다.
(큰 유상증자도 이 조건에 걸릴 수 있다 — 그 달 수익률이 실제보다 높게 잡힌다)

사용: python apiCollect.py factor   → derived/factor_YYYY_MM.xlsx
"""
import datetime as dt
import glob

import numpy as np
import pandas as pd

import dartRatio as R

FACTOR_COLS = ['수익건전성_종목', '성장성_종목', '밸류_종목', '모멘텀_종목', '변동성_종목']
MONTHS = 13            # 월말 종가를 거슬러 올라가는 개월 수
MIN_RETURNS = 6        # 변동성 계산에 필요한 최소 월간 수익률 개수
_CLEAN = R._CLEAN


def _latest_ratio_file():
    files = sorted(f for f in glob.glob('derived/dart_ratio_2*.xlsx')
                   if not f.endswith('_test.xlsx') and 'compare' not in f)
    if not files:
        raise FileNotFoundError('derived/dart_ratio_*.xlsx 가 없습니다. python apiCollect.py dart_ratio 를 먼저 실행하세요.')
    return files[-1]


def _z(s):
    """위아래 5%를 자른 뒤 표준점수 (영업이익률·EPS증가율처럼 꼬리가 긴 지표가 점수를 좌우하지 않게)."""
    s = pd.to_numeric(s, errors='coerce').replace([np.inf, -np.inf], np.nan)
    if s.notna().sum() < 30:
        return pd.Series(np.nan, index=s.index)
    s = s.clip(s.quantile(0.05), s.quantile(0.95))
    sd = s.std()
    return (s - s.mean()) / sd if sd else pd.Series(np.nan, index=s.index)


def _combine(parts):
    """구성 지표 표준점수의 평균(있는 것만) → 다시 표준화."""
    return _z(pd.concat(parts, axis=1).mean(axis=1, skipna=True))


def _adj(listed_then, listed_now):
    """월말 사이 주식수 변화 배수 (분할·병합·무상증자로 보는 경우만, 아니면 1)."""
    if not listed_then or not listed_now:
        return 1.0
    r = listed_now / listed_then
    for c in _CLEAN:
        if abs(r / c - 1) <= 0.01:
            return float(c)
    return r if (r >= 1.45 or r <= 0.7) else 1.0


def price_factors(codes, today=None):
    """월말 종가로 12-1개월 모멘텀(%)과 월간 변동성(%)을 계산한다 → (DataFrame, 최근 거래일)."""
    day_now, closes_now = R.latest_close()
    d = dt.date.fromisoformat(day_now)
    y, m = d.year, d.month
    months = []
    for _ in range(MONTHS):
        m -= 1
        if m == 0:
            y, m = y - 1, 12
        months.append((y, m))
    series = [R.month_end_close(yy, mm) for yy, mm in reversed(months)]      # 오래된 달 → 지난달
    rows = []
    for code in codes:
        pts = [s.get(code, (None, None)) for s in series]
        rets = []
        for a, b in zip(pts[:-1], pts[1:]):
            if a[0] and b[0]:
                rets.append(b[0] * _adj(a[1], b[1]) / a[0] - 1)
            else:
                rets.append(np.nan)
        got = [r for r in rets if not np.isnan(r)]
        mom = (np.prod([1 + r for r in rets]) - 1) * 100 if len(got) == len(rets) else np.nan
        # 변동성에는 지난달 말 → 최근 거래일 수익률도 넣는다
        last, now = pts[-1], closes_now.get(code, (None, None))
        vol_r = got + ([now[0] * _adj(last[1], now[1]) / last[0] - 1] if last[0] and now[0] else [])
        vol = float(np.std(vol_r, ddof=1)) * 100 if len(vol_r) >= MIN_RETURNS else np.nan
        rows.append({'종목코드': code, '팩터_모멘텀_12-1(%)': mom, '팩터_월변동성(%)': vol})
    return pd.DataFrame(rows), day_now


def collectFactorAll(codes=None):
    path = _latest_ratio_file()
    r = pd.read_excel(path, dtype={'종목코드': str})
    r['종목코드'] = r['종목코드'].str.zfill(6)
    if codes:
        r = r[r['종목코드'].isin(codes)]
    print(f'재무 지표: {path} ({len(r)}개 종목)')

    def latest(sfx):
        """종목별 최근 사업연도(현재가_기준연도)의 '{연도}{sfx}' 값."""
        out = pd.Series(np.nan, index=r.index)
        for yv in r['현재가_기준연도'].dropna().unique():
            col = f'{int(yv)}{sfx}'
            if col in r.columns:
                mk = r['현재가_기준연도'] == yv
                out[mk] = pd.to_numeric(r.loc[mk, col], errors='coerce')
        return out

    price = pd.to_numeric(r['현재가'], errors='coerce')
    price = price.where(price > 0)
    out = r[['종목코드', '종목명', '업종구분']].copy()
    out['팩터_ROE(%)'] = latest('(누적)_ROE')
    out['팩터_ROA(%)'] = latest('(누적)_ROA')
    out['팩터_영업이익률(%)'] = latest('(누적)_영업이익률')
    out['팩터_매출증가율(%)'] = latest('(누적)_매출증가율')
    out['팩터_EPS증가율(%)'] = latest('(누적)_EPS증가율')
    out['팩터_E/P(%)'] = latest('_EPS(원)') / price * 100
    out['팩터_B/P'] = latest('_BPS(원)') / price
    px, day_now = price_factors(list(out['종목코드']))
    out = out.merge(px, on='종목코드', how='left')

    z = {c: _z(out[c]) for c in out.columns if c.startswith('팩터_')}
    out['수익건전성_종목'] = _combine([z['팩터_ROE(%)'], z['팩터_ROA(%)'], z['팩터_영업이익률(%)']])
    out['성장성_종목'] = _combine([z['팩터_매출증가율(%)'], z['팩터_EPS증가율(%)']])
    out['밸류_종목'] = _combine([z['팩터_E/P(%)'], z['팩터_B/P']])
    out['모멘텀_종목'] = z['팩터_모멘텀_12-1(%)']
    out['변동성_종목'] = z['팩터_월변동성(%)']
    for c in FACTOR_COLS:
        out[c] = out[c].round(2)
    for c in [c for c in out.columns if c.startswith('팩터_')]:
        out[c] = out[c].round(4 if c == '팩터_B/P' else 2)
    out['재무_기준연도'] = r['현재가_기준연도'].values
    out['주가_기준일'] = day_now
    out['출처'] = 'DART·KRX'
    front = ['종목코드', '종목명', '업종구분'] + FACTOR_COLS
    return out[front + [c for c in out.columns if c not in front]]
