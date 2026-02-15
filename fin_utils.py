import datetime
import os
import shutil

import requests
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment
from openpyxl.utils.dataframe import dataframe_to_rows


def save_styled_excel(df, filepath, sheet_name="Sheet1", index=False):
    """DataFrame을 서식이 적용된 Excel 파일로 저장한다.

    서식:
        - 글꼴: 맑은 고딕, 10pt
        - 맞춤: 상하 가운데, 좌우 가운데
    """
    wb = Workbook()
    ws = wb.active
    ws.title = sheet_name

    font = Font(name="맑은 고딕", size=10)
    alignment = Alignment(horizontal="center", vertical="center")

    for row in dataframe_to_rows(df, index=index, header=True):
        ws.append(row)

    for row in ws.iter_rows(min_row=1, max_row=ws.max_row, max_col=ws.max_column):
        for cell in row:
            cell.font = font
            cell.alignment = alignment

    wb.save(filepath)


def fetch_fnguide_page(code, asp_page, menu_id, cache_prefix):
    """FnGuide 페이지를 다운로드하고 캐싱하는 공통 함수

    Parameters:
        code         : 종목코드 (6자리 문자열)
        asp_page     : FnGuide ASP 페이지명 (예: 'SVD_Finance.asp')
        menu_id      : FnGuide NewMenuID 값 (예: '103')
        cache_prefix : 캐시 디렉토리 접두어 (예: 'fnguide_finance_')

    Returns:
        str : HTML 문자열
    """
    now = datetime.datetime.now()
    url = f"https://comp.fnguide.com/SVO2/ASP/{asp_page}?pGB=1&gicode=A{code}&cID=&MenuYn=Y&ReportGB=&NewMenuID={menu_id}&stkGb=701"

    downloadedFileDirectory = 'derived/{0}{1}-{2:02d}'.format(cache_prefix, now.year, now.month)
    downloadedFilePath = '{0}/{1}.html'.format(downloadedFileDirectory, code)

    os.makedirs(downloadedFileDirectory, exist_ok=True)

    # 이전 달 캐시 디렉토리 삭제
    currentDirName = os.path.basename(downloadedFileDirectory)
    for entry in os.listdir('derived'):
        if entry.startswith(cache_prefix) and entry != currentDirName:
            shutil.rmtree(os.path.join('derived', entry))

    if os.path.exists(downloadedFilePath):
        return open(downloadedFilePath, "r", encoding="utf-8").read()

    response = requests.get(url)
    response.encoding = 'utf-8'
    with open(downloadedFilePath, "w", encoding="utf-8") as f:
        f.write(response.text)
    return response.text
