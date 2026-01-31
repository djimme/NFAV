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
