"""
종목별 업종 분류 수집: WI26(와이즈인덱스) + KRICS(한국거래소)

FnGuide 종목 페이지를 하나씩 받지 않고, 분류별 구성종목 목록을 받아 종목코드로 합친다.

출처:
  WI26  : 와이즈인덱스 섹터지수 구성종목 (https://www.wiseindex.com/Index/Index#/WI100 의 Components 탭)
          GET /Index/GetIndexComponets?ceil_yn=0&dt=YYYYMMDD&sec_cd=WI100  → 26개 지수를 차례로 호출
  KRICS : KRX 인덱스 사이트 '산업별 종목현황' (docs/KRICS 수집 명세.md)
          OTP 발급(GET) → 데이터 조회(POST) 2단계, 24개 산업그룹을 차례로 호출
          종목별 분류는 1·2단계(섹터·산업그룹)만 공표된다. 3·4단계 정의는 분류체계표(xlsx)에만 있다.

함수:
  collectWI26(day)      : 종목코드, 종목명, WI26코드, WI26분야, WICS대분류코드, WICS대분류
  collectKrics(day)     : 종목코드, 종목명, KRICS섹터코드, KRICS섹터, KRICS산업그룹코드, KRICS산업그룹, 상장주식수, 상장시가총액
  collectSectorMap(day) : 위 둘을 종목코드로 합쳐 derived/sector_map_YYYY_MM_DD.xlsx 로 저장
  fillWI26FromSnapshot(df): 와이즈인덱스 지수 미편입 종목의 WI26 을 FnGuide snapshot 으로 보충 (WI26출처='fnguide')

실행:
  python sectorCollect.py             # 가장 최근 거래일
  python sectorCollect.py 20261118    # 기준일 지정
"""
import datetime as dt
import os
import sys
import time

import pandas as pd
import requests

from fin_utils import save_styled_excel_multisheet

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36')
DELAY = 0.5  # 호출 사이 지연(초)

# ── WI26 ──────────────────────────────────────────────────────────────
WISE_URL = 'https://www.wiseindex.com/Index/GetIndexComponets'
WI26_CODES = ['WI100', 'WI110', 'WI200', 'WI210', 'WI220', 'WI230', 'WI240', 'WI250', 'WI260',
              'WI300', 'WI310', 'WI320', 'WI330', 'WI340', 'WI400', 'WI410',
              'WI500', 'WI510', 'WI520', 'WI600', 'WI610', 'WI620', 'WI630', 'WI640',
              'WI700', 'WI800']

# ── KRICS ─────────────────────────────────────────────────────────────
KRX_PAGE = '/contents/MKD/03/0303/03030304/MKD03030304.jsp'
KRX_OTP_URL = 'https://index.krx.co.kr/contents/COM/GenerateOTP.jspx'
KRX_DATA_URL = 'https://index.krx.co.kr/contents/IDX/99/IDX99000001.jspx'
KRX_BLD_LIST = '/IDX/03/0303/03030304/mkd03030304_03'   # 그룹별 종목 목록
KRICS_STRUCTURE_URL = ('https://index.krx.co.kr/contents/MKD/03/0303/03030301/'
                       '2026-krics-structure-korean_KRX.xlsx')

KRICS_SECTORS = {
    '10': '에너지화학', '20': '소재', '30': '산업재', '40': '모빌리티', '50': '정보기술',
    '60': '금융 및 부동산', '70': '소비재', '80': '헬스케어', '90': '미디어 및 콘텐츠',
}
KRICS_GROUPS = {
    '1010': '에너지', '1020': '기초 화학', '1030': '유틸리티',
    '2010': '소재',
    '3010': '자본재', '3020': '배터리 및 전기 장비', '3030': '기업 서비스',
    '3040': '무역 및 물류 서비스', '3050': '복합 기업',
    '4010': '자동차 및 부품', '4020': '모빌리티 서비스',
    '5010': 'IT 소프트웨어', '5020': 'IT 하드웨어', '5030': '반도체 및 디스플레이', '5040': 'IT 서비스',
    '6010': '금융', '6020': '부동산',
    '7010': '필수소비재', '7020': '자유소비재',
    '8010': '헬스케어 제품 및 서비스', '8020': '제약 및 바이오',
    '9010': '통신 서비스', '9020': '미디어', '9030': '콘텐츠',
}


def _num(v):
    try:
        return float(str(v).replace(',', ''))
    except (TypeError, ValueError):
        return None


# ══════════════════════════════════════════════════════════════════════
# WI26
# ══════════════════════════════════════════════════════════════════════
def _fetch_wi26(code, day, session=None):
    """와이즈인덱스 지수 구성종목 원본 list 를 돌려준다 (거래일이 아니면 빈 리스트)."""
    s = session or requests
    r = s.get(WISE_URL, params={'ceil_yn': 0, 'dt': day, 'sec_cd': code},
              headers={'User-Agent': UA, 'Referer': 'https://www.wiseindex.com/Index/Index'}, timeout=30)
    r.raise_for_status()
    return r.json().get('list', [])


def latest_wise_day(base=None, max_back=10):
    """와이즈인덱스에 구성종목 데이터가 있는 가장 최근 날짜(YYYYMMDD). 당일 장 마감 전에는 전 거래일."""
    d = base or dt.date.today()
    for _ in range(max_back):
        day = d.strftime('%Y%m%d')
        if d.weekday() < 5 and _fetch_wi26('WI100', day):
            return day
        d -= dt.timedelta(days=1)
    raise RuntimeError(f'최근 {max_back}일 안에 와이즈인덱스 구성종목 데이터가 없습니다.')


def collectWI26(day=None):
    """WI26 26개 섹터지수의 구성종목을 모아 종목별 WI26 분류를 만든다.

    Returns:
        DataFrame: 종목코드, 종목명, WI26코드, WI26분야, WICS대분류코드, WICS대분류
    """
    day = day or latest_wise_day()
    rows = []
    with requests.Session() as s:
        for code in WI26_CODES:
            items = _fetch_wi26(code, day, s)
            if not items:
                raise RuntimeError(f'[WI26] {code} 기준일 {day} 구성종목이 비어 있습니다.')
            for it in items:
                rows.append({
                    '종목코드': str(it['CMP_CD']).zfill(6),
                    '종목명': it['CMP_KOR'],
                    'WI26코드': it['IDX_CD'],
                    'WI26분야': str(it['IDX_NM_KOR']).replace('WI26', '', 1).strip(),
                    'WICS대분류코드': it.get('SEC_CD'),
                    'WICS대분류': it.get('SEC_NM_KOR'),
                })
            print(f"  [WI26] {code} {rows[-1]['WI26분야']}: {len(items)}개")
            time.sleep(DELAY)
    df = pd.DataFrame(rows)
    dup = df[df.duplicated('종목코드', keep=False)]
    if len(dup):
        print(f'  [WI26] 경고: 두 개 이상 섹터에 속한 종목 {dup["종목코드"].nunique()}개 → 첫 번째만 남김')
        df = df.drop_duplicates('종목코드')
    print(f'[WI26] 기준일 {day}: {len(df)}개 종목')
    return df


# ══════════════════════════════════════════════════════════════════════
# KRICS
# ══════════════════════════════════════════════════════════════════════
def _fetch_krics_group(session, grp, day):
    """KRX 인덱스 '산업별 종목현황'에서 산업그룹 하나의 종목 목록(block1)을 받는다."""
    otp = session.get(KRX_OTP_URL, params={'bld': KRX_BLD_LIST, 'name': 'form',
                                           '_': int(time.time() * 1000)}, timeout=30).text
    r = session.post(KRX_DATA_URL, timeout=30, data={
        'mkt_tp_cd': 'ALL', 'krics_grp_cd': grp, 'date': day, 'lang': 'ko',
        'pagePath': KRX_PAGE, 'code': otp, 'bldcode': KRX_BLD_LIST})
    r.raise_for_status()
    r.encoding = 'utf-8'
    return r.json().get('block1', [])


def collectKrics(day=None):
    """KRICS 24개 산업그룹의 종목 목록을 모아 종목별 섹터·산업그룹을 만든다.

    Returns:
        DataFrame: 종목코드, 종목명, KRICS섹터코드, KRICS섹터, KRICS산업그룹코드, KRICS산업그룹,
                   상장주식수, 상장시가총액(원)
    """
    day = day or latest_wise_day()
    rows = []
    with requests.Session() as s:
        s.headers.update({'User-Agent': UA,
                          'Referer': f'https://index.krx.co.kr{KRX_PAGE}?krics_grp_cd=5030'})
        for grp, grp_nm in KRICS_GROUPS.items():
            items = _fetch_krics_group(s, grp, day)
            if not items:
                raise RuntimeError(f'[KRICS] {grp} {grp_nm} 기준일 {day} 종목 목록이 비어 있습니다.')
            for it in items:
                rows.append({
                    '종목코드': str(it['isu_cd']).zfill(6),
                    '종목명': it['isu_abbr'],
                    'KRICS섹터코드': grp[:2],
                    'KRICS섹터': KRICS_SECTORS[grp[:2]],
                    'KRICS산업그룹코드': grp,
                    'KRICS산업그룹': grp_nm,
                    '상장주식수': _num(it.get('listshr_cnt')),
                    '상장시가총액': _num(it.get('list_mktcap')),
                })
            print(f'  [KRICS] {grp} {grp_nm}: {len(items)}개')
            time.sleep(DELAY)
    df = pd.DataFrame(rows)
    dup = df[df.duplicated('종목코드', keep=False)]
    if len(dup):
        print(f'  [KRICS] 경고: 두 개 이상 그룹에 속한 종목 {dup["종목코드"].nunique()}개 → 첫 번째만 남김')
        df = df.drop_duplicates('종목코드')
    print(f'[KRICS] 기준일 {day}: {len(df)}개 종목')
    return df


def downloadKricsStructure(path='derived/krics_structure.xlsx'):
    """KRICS 분류체계표(1~4단계 코드·이름 정의)를 받아 둔다. 이미 있으면 받지 않는다."""
    if os.path.exists(path):
        return path
    r = requests.get(KRICS_STRUCTURE_URL, headers={'User-Agent': UA}, timeout=60)
    r.raise_for_status()
    with open(path, 'wb') as f:
        f.write(r.content)
    print(f'[KRICS] 분류체계표 저장: {path}')
    return path


# ══════════════════════════════════════════════════════════════════════
# 합치기
# ══════════════════════════════════════════════════════════════════════
# FnGuide 종목 페이지의 WI26 대분류 표기 → 와이즈인덱스 표기 (나머지 22개는 같다)
FNGUIDE_WI26_ALIAS = {'비철,목재등': '비철금속', '건설,건축관련': '건설',
                      '화장품,의류,완구': '화장품,의류', '호텔,레저서비스': '호텔,레저'}


def fillWI26FromSnapshot(df, snapshot_path=None):
    """와이즈인덱스 지수에 편입되지 않아 WI26 이 빈 종목을 FnGuide snapshot 의 WI26분야로 채운다.

    먼저 derived/snapshot_YYYY_MM.xlsx 중 가장 최근 파일(또는 snapshot_path)을 쓰고,
    거기에도 없는 종목은 FnGuide Snapshot 페이지를 직접 읽는다 (월별 캐시 사용).
    채운 종목은 WI26출처 가 'fnguide' 가 된다.
    """
    import glob
    name_to_code = (df.dropna(subset=['WI26코드']).drop_duplicates('WI26분야')
                      .set_index('WI26분야')['WI26코드'])

    def apply(fng, label):
        """fng: {종목코드: FnGuide WI26 이름}. 아직 빈 종목만 채우고 채운 개수를 돌려준다."""
        filled = df['종목코드'].map(pd.Series(fng, dtype=object).astype(str).str.strip()
                                    .replace(FNGUIDE_WI26_ALIAS))
        filled = filled.where(filled.isin(name_to_code.index))  # 와이즈인덱스에 없는 이름은 버린다
        mask = df['WI26코드'].isna() & filled.notna()
        df.loc[mask, 'WI26분야'] = filled[mask]
        df.loc[mask, 'WI26코드'] = filled[mask].map(name_to_code)
        df.loc[mask, 'WI26출처'] = 'fnguide'
        print(f'[WI26] {label}: {int(mask.sum())}개 종목 보충')

    # 1) 이미 수집해 둔 snapshot 엑셀
    path = snapshot_path or next(iter(sorted(glob.glob('derived/snapshot_*.xlsx'), reverse=True)), None)
    if path:
        snap = pd.read_excel(path, dtype={'종목코드': str})
        if 'WI26분야' in snap.columns:
            snap = snap.dropna(subset=['WI26분야']).drop_duplicates('종목코드')
            apply(dict(zip(snap['종목코드'], snap['WI26분야'])), f'FnGuide snapshot 엑셀({path})')

    # 2) 엑셀에 없는 종목(리츠·인프라펀드·신규상장 등 종목 리스트에서 빠진 것)은 Snapshot 페이지를 직접 읽는다
    from bs4 import BeautifulSoup
    from fin_utils import parse_kse_fics
    from fnguideSnapshot import getFnGuideSnapshot
    fng = {}
    for code in df.loc[df['WI26코드'].isna(), '종목코드']:
        try:
            _, wi26, _ = parse_kse_fics(BeautifulSoup(getFnGuideSnapshot(code), 'html.parser'))
        except Exception as e:
            print(f'  [WI26] FnGuide Snapshot {code} 실패: {e}')
            continue
        if wi26:
            fng[code] = wi26
        time.sleep(DELAY)
    if fng:
        apply(fng, 'FnGuide Snapshot 페이지')
    return df


# ══════════════════════════════════════════════════════════════════════
def collectSectorMap(day=None, save=True):
    """WI26 과 KRICS 를 종목코드로 합친다 (한쪽에만 있는 종목도 남긴다).

    Returns:
        DataFrame: 종목코드, 종목명, WI26코드, WI26분야, KRICS섹터코드, KRICS섹터,
                   KRICS산업그룹코드, KRICS산업그룹, 상장주식수, 상장시가총액, 기준일
    """
    day = day or latest_wise_day()
    print(f'===== 업종 분류 수집 (기준일 {day}) =====')
    wi = collectWI26(day)
    kr = collectKrics(day)

    df = kr.merge(wi, on='종목코드', how='outer', suffixes=('', '_wi'))
    df['종목명'] = df['종목명'].fillna(df['종목명_wi'])
    df['WI26출처'] = df['WI26코드'].notna().map({True: 'wiseindex', False: None})
    df = fillWI26FromSnapshot(df)
    df['기준일'] = day
    df = df[['종목코드', '종목명', 'WI26코드', 'WI26분야', 'WI26출처',
             'KRICS섹터코드', 'KRICS섹터', 'KRICS산업그룹코드', 'KRICS산업그룹',
             '상장주식수', '상장시가총액', '기준일']].sort_values('종목코드').reset_index(drop=True)

    only_kr = df[df['WI26코드'].isna()]
    only_wi = df[df['KRICS산업그룹코드'].isna()]
    print(f'[합계] {len(df)}개 종목 — 둘 다 있음 {len(df) - len(only_kr) - len(only_wi)}, '
          f'KRICS만 {len(only_kr)}, WI26만 {len(only_wi)} (FnGuide 보충 후)')
    if len(only_wi):
        print('  WI26에만 있는 종목:', ', '.join(only_wi['종목명'].head(30)))
    if len(only_kr):
        print('  KRICS에만 있는 종목(앞 30개):', ', '.join(only_kr['종목명'].head(30)))

    if save:
        os.makedirs('derived', exist_ok=True)
        path = f'derived/sector_map_{day[:4]}_{day[4:6]}_{day[6:]}.xlsx'
        cross = (df.dropna(subset=['WI26분야', 'KRICS산업그룹'])
                   .groupby(['WI26코드', 'WI26분야', 'KRICS산업그룹코드', 'KRICS산업그룹'])
                   .size().reset_index(name='종목수'))
        save_styled_excel_multisheet([('종목분류', df), ('WI26', wi), ('KRICS', kr),
                                      ('WI26xKRICS', cross)], path)
        print(f'저장: {path}')
        try:
            downloadKricsStructure()
        except Exception as e:  # 분류체계표는 참고 자료라 실패해도 본 결과는 유지
            print(f'[KRICS] 분류체계표 다운로드 실패: {e}')
    return df


if __name__ == '__main__':
    collectSectorMap(sys.argv[1] if len(sys.argv) > 1 else None)
