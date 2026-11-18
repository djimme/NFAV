"""
FnGuide 컨센서스 페이지 데이터 수집 및 파싱 (2026년 사이트 개편 후 생긴 페이지)

주소: https://wcomp.fnguide.com/CompanyInfo/Consensus?c_id=AA&menu_type=01&cmp_cd={종목코드}
표는 빈 틀이고 값은 페이지 안의 스크립트 데이터에 들어 있다 (종목당 요청 1번).

수집 데이터:
1. 실적 추이·전망 (perforTrend, 연간) — 실적 3개 연도 + 추정 최대 3개 연도
   항목: 매출액, 영업이익, 당기순이익, 당기순이익(지배), 당기순이익(비지배), 자산총계, 부채총계, 자본총계,
         자본총계(지배), 자본총계(비지배), 자본금, EPS(원), BPS(원), 현금DPS(원), PER, PBR  (금액 단위: 억원)
   매출액·영업이익·당기순이익에는 전년동기대비(%), 컨센서스대비(%)(실적 연도만)가 딸려 있다.
   컬럼 형식: {YYYY}_{항목}          실적 연도   (예: 2025_영업이익, 2025_영업이익_컨센서스대비(%))
              {YYYY}E_{항목}         추정 연도   (예: 2026E_영업이익, 2026E_EPS(원))
2. 컨센서스 변화 (cnsTrend) — 가장 가까운 추정 연도 하나에 대해 현재·1개월전·3개월전·6개월전·1년전 값
   항목: 매출액, 영업이익, 당기순이익, EPS(원), PER, PER(Fwd. 12M), 목표주가(원), 투자의견(점수)
   컬럼 형식: 추정_{항목}_{시점}     (예: 추정_영업이익_현재, 추정_영업이익_3개월전)
              추정연도, 추정기준일
3. 리포트수 — 페이지에 실린 최근 증권사 리포트 건수 (제목·요약은 저장하지 않는다)

추정치가 없는 종목(커버하는 증권사 없음)은 추정 컬럼이 비고 실적 연도 값만 나온다.
분기 추정은 /CompanyInfo/getCnsPerforTrend?cmp_cd=…&consol_typ=C&freq_typ=Q&data_typ=2 로 따로 받아야 한다(여기서는 받지 않는다).

Public API:
  getFnGuideConsensus(code)    : HTML 가져오기 (캐싱)
  parseFnGuideConsensus(html)  : 컨센서스 데이터 추출 → dict 또는 None
  collectConsensus(code)       : HTML 가져오기 + 파싱 통합 수집 → dict 또는 None
"""
import re

from bs4 import BeautifulSoup

from fin_utils import (fetch_fnguide_page, parse_company_name, parse_kse_fics, parse_fnguide_inline,
                       fnguide_num)


# cnsTrend 의 값 열 → 시점 이름 (header 의 VAL1 이름은 사이트에서 계정명으로 잘못 나와 직접 정한다)
_TREND_POINTS = [('VAL1', '현재'), ('VAL2', '1개월전'), ('VAL3', '3개월전'), ('VAL4', '6개월전'), ('VAL5', '1년전')]


def getFnGuideConsensus(code):
    """FnGuide 컨센서스 HTML 가져오기 (캐싱)"""
    return fetch_fnguide_page(code, 'SVD_Consensus.asp', '108', 'fnguide_consensus_')


def parseFnGuideConsensus(html):
    """
    컨센서스 HTML에서 실적 추이·전망과 컨센서스 변화 추출

    Returns:
        dict: 종목명, 마켓분야, WI26분야, 결산월, 연도별 실적·추정, 추정 변화
        None: 실적 추이 데이터(perforTrend)가 없는 경우
    """
    perfor = parse_fnguide_inline(html, 'perforTrend')
    if not perfor or not perfor.get('data'):
        return None

    soup = BeautifulSoup(html, 'html.parser')
    data = {'종목명': parse_company_name(soup)}
    kse_sector, fics_sector, fiscal_month = parse_kse_fics(soup)
    data['마켓분야'] = kse_sector
    data['WI26분야'] = fics_sector
    if fiscal_month is not None:
        data['결산월'] = fiscal_month

    # 1. 실적 추이·전망: 열 = (연도 라벨, CD). 추정(E)·잠정(P) 열은 연도 뒤에 표시를 붙인다.
    columns = []
    for h in perfor.get('header') or []:
        m = re.match(r'(\d{4})/\d{2}', h.get('YYMM') or '')
        if m:
            columns.append((m.group(1) + (h.get('EP_CHK') or '').strip(), h['CD']))
    parent = ''
    for row in perfor['data']:
        name = (row.get('NAME') or '').strip()
        if row.get('P_AC_CODE'):                      # 딸린 행: 전년동기대비, 컨센서스대비
            name = f"{parent}_{name}"
        else:
            parent = name
        name += row.get('UNIT') or ''
        for label, cd in columns:
            value = fnguide_num(row.get(cd))
            if value is not None:
                data[f'{label}_{name}'] = value

    # 2. 컨센서스 변화 (페이지가 처음 보여 주는 추정 연도 = trendYYMM 의 첫 항목)
    trend = parse_fnguide_inline(html, 'cnsTrend')
    if trend and trend.get('data'):
        yymm = parse_fnguide_inline(html, 'trendYYMM') or []
        if yymm:
            data['추정연도'] = yymm[0].get('YYMM_F')
        header = trend.get('header') or []
        if header and re.match(r'\d{4}/\d{2}/\d{2}', header[0].get('NM') or ''):
            data['추정기준일'] = header[0]['NM']
        for row in trend['data']:
            name = (row.get('ACC_NM') or '').strip() + (row.get('UNIT') or '')
            for cd, point in _TREND_POINTS:
                value = fnguide_num(row.get(cd))
                if value is not None:
                    data[f'추정_{name}_{point}'] = value

    # 3. 최근 리포트 건수
    reports = parse_fnguide_inline(html, 'reports')
    if isinstance(reports, list):
        data['리포트수'] = len(reports)

    return data


def collectConsensus(code):
    """
    컨센서스 HTML 가져오기 + 파싱 통합 수집

    Args:
        code: 종목코드 (6자리 문자열, 예: '005930')

    Returns:
        dict 또는 None (parseFnGuideConsensus 참고)
    """
    return parseFnGuideConsensus(getFnGuideConsensus(code))
