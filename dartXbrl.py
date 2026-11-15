"""
DART XBRL 원본 파일에서 감가상각비·무형자산상각비를 읽는다 (EBITDA 계산용, 1층 원천 데이터)

전체 재무제표 API(fnlttSinglAcntAll)는 현금흐름표의 조정 내역을 본문에 적은 회사(약 20%)만 감가상각비를 준다.
사업보고서의 XBRL 원본(fnlttXbrl.xml, 접수번호마다 zip 1건)에는 주석까지 태그가 달려 있어 대부분 회사에 있다.

- zip(0.1~1.5MB)은 저장하지 않고, 감가상각·상각 관련 사실(fact)만 derived/dart_cache/{고유번호}_{접수번호}_xbrl_da.json 에 둔다.
  추출 규칙을 바꿔도 다시 내려받지 않는다.
- 한 보고서에 당기(CFY)·전기(PFY)·전전기(BPFY) 값이 함께 있다.

값을 고르는 순서 (연결/별도는 재무제표와 같은 쪽, 세부 구분 축이 없는 합계 값만):
  1. 현금흐름표 조정 항목: 감가상각비 + 무형자산상각비 + 사용권자산·투자부동산 감가상각비 (또는 합산 계정)
  2. 비용의 성격별 분류 주석: 감가상각비 + 무형자산상각비 (또는 합산 계정)
  3. 자산 변동 내역 주석: 유형자산 감가상각 + 무형자산 상각 + 사용권자산·투자부동산 감가상각

Public API:
  fetch_da_facts(corp, rcept_no)        : [(계정, 컨텍스트, 값)] (캐시)
  depreciation(facts, fs)               : {0(당기)·1(전기)·2(전전기): (금액(원), 규칙 번호)}
"""
import io
import json
import os
import re
import time
import zipfile

import requests

from dartFinance import API, CACHE_DIR, _key

_FACT = re.compile(r'<((?:ifrs-full|dart):\w*(?:Depreciation|Amortisation)\w*)\s([^>]*)>([^<]*)</')
_CTX = re.compile(r'contextRef="([^"]+)"')
# 컨텍스트 ID: {C|P|BP}FY{연도}dFY_..._{Consolidated|Separate}Member[_추가 축]
_CTX_ID = re.compile(r'^(C|P|BP)FY\d{4}dFY_ifrs-full_ConsolidatedAndSeparateFinancialStatementsAxis_ifrs-full_'
                     r'(Consolidated|Separate)Member(.*)$')
_REPORTED = '_ifrs-full_CarryingAmountAccumulatedDepreciationAmortisationAndImpairmentAndGrossCarryingAmountAxis_dart_ReportedAmountMember'
_BACK = {'C': 0, 'P': 1, 'BP': 2}

_RULES = [   # (합산 계정, [더하는 계정들 — 첫 계정은 반드시 있어야 한다])
    ('ifrs-full:AdjustmentsForDepreciationAndAmortisationExpense',
     ['ifrs-full:AdjustmentsForDepreciationExpense', 'ifrs-full:AdjustmentsForAmortisationExpense',
      'dart:AdjustmentsForDepreciationRightofuseAssets', 'dart:AdjustmentsForDepreciationInvestmentProperty']),
    ('ifrs-full:DepreciationAndAmortisationExpense',
     ['ifrs-full:DepreciationExpense', 'ifrs-full:AmortisationExpense']),
    (None,
     ['ifrs-full:DepreciationPropertyPlantAndEquipment', 'ifrs-full:AmortisationIntangibleAssetsOtherThanGoodwill',
      'ifrs-full:DepreciationRightofuseAssets', 'ifrs-full:DepreciationInvestmentProperty']),
]


def fetch_da_facts(corp, rcept_no):
    """XBRL 원본에서 감가상각·상각 관련 사실만 뽑아 돌려준다. XBRL이 없는 보고서는 빈 목록(캐시)."""
    path = os.path.join(CACHE_DIR, f'{corp}_{rcept_no}_xbrl_da.json')
    if os.path.exists(path):
        return json.load(open(path, encoding='utf-8'))
    r = requests.get(f'{API}/fnlttXbrl.xml', timeout=180,
                     params=dict(crtfc_key=_key(), rcept_no=rcept_no, reprt_code='11011'))
    facts = []
    if r.content[:2] == b'PK':
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            names = [n for n in z.namelist() if n.endswith('.xbrl')]
            if names:
                text = z.read(names[0]).decode('utf-8', 'ignore')
                for el, attrs, val in _FACT.findall(text):
                    c = _CTX.search(attrs)
                    try:
                        facts.append((el, c.group(1), float(val)))
                    except (AttributeError, ValueError):
                        continue
    else:
        m = re.search(rb'<status>(\d+)</status>\s*<message>([^<]*)</message>', r.content)
        status = m.group(1).decode() if m else '?'
        if status not in ('013', '014'):      # 013 데이터 없음, 014 파일 없음 → 빈 목록으로 캐시. 그 밖(한도 초과 등)은 알린다
            raise RuntimeError(f"DART XBRL {status} {m.group(2).decode('utf-8', 'ignore') if m else ''}")
    json.dump(facts, open(path, 'w', encoding='utf-8'))
    time.sleep(0.3)
    return facts


def depreciation(facts, fs):
    """{0: 당기, 1: 전기, 2: 전전기} → (감가상각비 + 무형자산상각비(원), 규칙 번호 1~3)."""
    member = 'Consolidated' if fs == 'CFS' else 'Separate'
    by_back = {}
    for el, ctx, val in facts:
        m = _CTX_ID.match(ctx)
        if not m or m.group(2) != member or m.group(3) not in ('', _REPORTED):
            continue
        d = by_back.setdefault(_BACK[m.group(1)], {})
        if m.group(3) == '' or el not in d:       # 축이 없는 값이 먼저
            d[el] = abs(val)
    out = {}
    for back, d in by_back.items():
        for i, (total, parts) in enumerate(_RULES, 1):
            if total and d.get(total):
                out[back] = (d[total], i)
                break
            if d.get(parts[0]):
                out[back] = (sum(d.get(p, 0) for p in parts), i)
                break
    return out
