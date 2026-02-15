"""
fnguide_collector.py - 하위호환 re-export 모듈

기존 `import fnguide_collector` 로 사용하던 코드의 호환성을 유지하기 위한 모듈입니다.
신규 코드에서는 개별 모듈을 직접 import 하세요:
    - fnguideFinance       : getFnguideFinance, parseFnguideFinance
    - fnguideSnapshot      : getFnGuideSnapshot, parseFnguideSnapshot
    - fnguideFinanceRatio  : getFnGuideFiRatio, parseFnguideFiRatio
    - fnguideInvestIdx     : getFnGuideInvestIdx, parseFnGuideInvestIdx
"""

from fnguideFinance import getFnguideFinance, parseFnguideFinance  # noqa: F401
from fnguideSnapshot import getFnGuideSnapshot, parseFnguideSnapshot  # noqa: F401
from fnguideFinanceRatio import getFnGuideFiRatio, parseFnguideFiRatio  # noqa: F401
from fnguideInvestIdx import getFnGuideInvestIdx, parseFnGuideInvestIdx  # noqa: F401

__all__ = [
    'getFnguideFinance', 'parseFnguideFinance',
    'getFnGuideSnapshot', 'parseFnguideSnapshot',
    'getFnGuideFiRatio', 'parseFnguideFiRatio',
    'getFnGuideInvestIdx', 'parseFnGuideInvestIdx',
]
