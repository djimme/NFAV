# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

NFAV is a Korean stock market value investing analysis tool that calculates financial metrics to identify undervalued stocks. It focuses on:
- **NFAV/NCAV**: Net Current Asset Value ratio - identifies stocks trading below net current assets
- **PL/PEG**: Price-to-Earnings Growth ratio analysis for growth investing

The project scrapes financial data from Korean sources (DART, KRX, FnGuide) and generates ranked Excel outputs of promising stocks.

## Excel 저장 규칙

데이터를 파일로 저장할 때는 반드시 Excel(.xlsx) 형식을 사용하고, `fin_utils.save_styled_excel()` 함수를 통해 저장한다. CSV 저장은 사용하지 않는다.

적용되는 서식:
- 글꼴: 맑은 고딕, 10pt
- 맞춤: 상하 가운데, 좌우 가운데

```python
from fin_utils import save_styled_excel
save_styled_excel(df, "derived/output.xlsx")
```

## 커밋 메세지 포맷

1. **기능: [간단한 설명]**
2. **변경사항 (사용자: X% | Claude: Y%)**
   - 사용자 작성 (X%): [사용자가 작성한 변경사항들]
   - Claude 작성 (Y%): [Claude가 작성한 변경사항들 (파일 경로 포함)]

   🤖 Generated with Claude Code / Co-Authored-By: Claude <noreply@anthropic.com>

<!--
## Code Quality Tools

After modifying code, always run linting and type checking:

```bash
# Run all checks (recommended)
ruff check .              # Fast linter (checks style, imports, bugs)
mypy .                    # Type checker
flake8 .                  # Traditional linter

# Auto-fix issues with ruff
ruff check --fix .        # Auto-fix linting issues
ruff format .             # Auto-format code

# Run specific file checks
ruff check ncav_datagen.py
mypy ncav_datagen.py
```

Configuration files:

- [pyproject.toml](pyproject.toml) - ruff and mypy settings
- [.flake8](.flake8) - flake8 settings

All tools are configured to:

- Allow Korean variable names (한글 변수명 허용)
- Use 120 character line length
- Exclude venv, derived, and corpCode directories
-->

## Running Analysis Scripts

### NCAV Analysis
```bash
python ncav_datagen.py    # Generate NCAV data (uses multiprocessing)
python ncav_2023-03-04.py # Calculate NCAV ratios and filter stocks
```

### PL/PEG Analysis
```bash
python plpeg_datagen.py   # Generate PL/PEG data (uses multiprocessing)
python plpeg_calc.py      # Calculate PEG ratios and filter stocks
```

### NFAV Analysis (WIP)
```bash
python nfav.py            # Current development - NFAV implementation
```

### OpenDART API Scripts
```bash
python opendartAPI.py              # Test DART/KRX API access and corp code fetching
python extractCorp.py              # Extract listed companies from CORPCODE.xml
python dart_financial_indexes.py  # Collect financial indexes (profitability & growth) for all listed companies
```

## Code Architecture

### Data Pipeline Flow

1. **Stock List Acquisition** ([krxStocks.py](krxStocks.py))
   - Reads from `complist_1110.xlsx` or `comp_list.xlsx`
   - Filters out SPACs (Special Purpose Acquisition Companies)
   - Outputs: DataFrame with code, name, industry, main_product

2. **Data Collection** (Multiprocessing)
   - [ncav_datagen.py](ncav_datagen.py) or [plpeg_datagen.py](plpeg_datagen.py)
   - Uses `multiprocessing.Pool` to fetch data for all stocks in parallel
   - Each worker calls `code_to_dict(code)` which:
     - Fetches HTML from FnGuide endpoints
     - Parses financial data
     - Returns dictionary of metrics
   - Outputs: TSV file in `derived/` directory

3. **Calculation & Filtering**
   - [ncav_2023-03-04.py](ncav_2023-03-04.py): NCAV_R = (Current Assets - Liabilities) / Market Cap
   - [plpeg_calc.py](plpeg_calc.py): PEG = PER / EPS_3yr_growth
   - Apply filters (positive values, debt ratios, profitability)
   - Outputs: Ranked CSV with top candidates

### Data Source Modules

**[fnguide_collector.py](fnguide_collector.py)** - Main FnGuide data collection orchestrator with functions for:
- `getKrxStocks()` - Load stock list
- `getFnguideFinance(code)` - Download financial statements page
- `getFnGuideSnapshot(code)` - Download snapshot/overview page
- `getFnGuideFiRatio(code)` - Download financial ratios page
- `getFnGuideInvestIdx(code)` - Download investment indicators page
- `parseFnguideFinance(content)` - Parse quarterly P&L and balance sheet
- `parseFnguideSnapshot(content)` - Parse market cap and controlling shareholder profit
- `parseFnguideFiRatio(content)` - Parse debt ratios, EPS, EPS growth (yearly & quarterly)
- `parseFnGuideInvestIdx(content)` - Parse yearly PER values

**Individual module files** (contain subset of above functions):
- [fnguideFinance.py](fnguideFinance.py) - Financial statements
- [fnguideSnapshot.py](fnguideSnapshot.py) - Market snapshot
- [fnguideFinanceRatio.py](fnguideFinanceRatio.py) - Financial ratios
- [fnguideInvestIdx.py](fnguideInvestIdx.py) - Investment indicators

**DART API Modules** - Korea's financial disclosure system access:

- [opendartAPI.py](opendartAPI.py) - Original DART/KRX API testing script:
  - `getCorpCode(api_key)` - Downloads corporate code XML, converts to CSV
  - `getStockPrice(api_key)` - Fetches KOSPI/KOSDAQ daily trading data
  - `getCorpMajorFi(df_corp, api_key)` - Fetches major financial items from consolidated statements

- [extractCorp.py](extractCorp.py) - Utility to extract listed companies:
  - `extract_listed_corp_codes(xml_path)` - Parses CORPCODE.xml to extract companies with stock codes
  - Returns list of dicts with corp_code, stock_code, corp_name

- [dart_financial_indexes.py](dart_financial_indexes.py) - Production script for bulk financial data collection:
  - `extract_listed_corp_codes(xml_path)` - Same as extractCorp.py
  - `call_fnltt_cmpny_indx()` - Calls DART multi-company financial index API
  - `collect_financial_indexes()` - Orchestrates batch collection of profitability (M210000) and growth (M230000) indexes
  - Processes up to 100 companies per API call with 0.5s delay between requests
  - Outputs timestamped Excel file: `financial_indexes_{datetime}.xlsx`

### Caching Strategy

All FnGuide scrapers implement local file caching:
- Downloads saved to `derived/fnguide_{type}_{YYYY-MM}/` directories
- File naming: `{stock_code}.html`
- If file exists, reads from disk instead of making HTTP request
- This prevents redundant requests and enables offline development

### Output Files

Generated files in `derived/` directory:
- `ncav_{YYYY-MM-DD}.csv` - Raw NCAV data (all stocks)
- `ncav_output_{YYYY-MM-DD}.csv` - Filtered NCAV results
- `plpeg_{YYYY-MM}.csv` - Raw PL/PEG data (all stocks)
- `peg_output_{YYYY-MM}.csv` - Filtered PEG results

## API Keys

API keys are hardcoded in multiple files:

- [opendartAPI.py](opendartAPI.py): `DART_Key`, `KRX_Key`
- [dart_financial_indexes.py](dart_financial_indexes.py): `DART_API_KEY`

When working with these files, be careful not to expose or commit updated API keys.

## Key Financial Formulas

### NCAV (Net Current Asset Value)
```
NCAV_R = (Current Assets - Total Liabilities) / Market Cap
```
Filters: NCAV_R > 0, Net Income > 0

### PL/PEG (Price/Earnings to Growth)
```
EPS_3yr = 100 * (EPS_y-3 - EPS_y-6) / EPS_y-6
PEG = PER_y-3 / EPS_3yr
```
Filters: EPS_3yr > 0, PEG <= 0.5, PER > 0, Debt Ratio <= 100

## Data Structures

### Stock Code
Korean stock codes are 6-digit strings (e.g., '005930' for Samsung Electronics). Always format with leading zeros.

### FnGuide Metric Naming Convention
- Suffixes: `_y-N` (yearly data N years ago), `_q-N` (quarterly data N quarters ago)
- Examples: `EPS_y-3`, `부채비율_y-3`, `EPS증가율_q-1`
- Quarter dates: `{YYYY}/{MM}` format (e.g., '2022/09')

### Parser Output Format
All parsers return dictionaries with:
- Basic info: `code`, `종목명` (name), `업종` (industry)
- Metrics: PER, PBR, EPS variants, debt ratios, etc.
- Time-series data with date/period suffixes

## Multiprocessing Usage

Data generation scripts use Python's `multiprocessing.Pool`:
```python
with mp.Pool(processes=mp.cpu_count()) as pool:
    dictList = pool.map(code_to_dict, list(krxStocks['code']))
```

Each worker process independently fetches and parses data for one stock. Results are combined into a DataFrame at the end.

## Korean Text Handling

- CSV output uses `encoding='utf-8-sig'` (BOM for Excel compatibility)
- BeautifulSoup parsing handles Korean characters (`u"\xa0"` replacements)
- Column names and data are in Korean - preserve exact naming when modifying
