import datetime
import pandas as pd
from fin_utils import save_styled_excel

if __name__ == '__main__':
    now = datetime.datetime.now()    
    collectedFilePath = "derived/plpeg_{0}-{1:02d}.csv".format(now.year, now.month)
    
    # cols = ['code', '종목명', '업종', 'PEG_y', 'EPS_3분기 평균', '부채비율']
    # dfPEG = pd.DataFrame(columns=cols)
    dfPEG = pd.DataFrame()
    
    # dfPEG = collected.loc[:,['code','종목명','업종', ]]
    
    collected = pd.read_csv(collectedFilePath)
    collected['code'] = collected['code'].map('{:06.0f}'.format)
    collected['시가총액(보통주,억원)'] = collected['시가총액(보통주,억원)'].str.replace(",", "")
    collected['시가총액(보통주,억원)'] = pd.to_numeric(collected['시가총액(보통주,억원)'], errors='coerce')
    collected['당기순이익'] = pd.to_numeric(collected['당기순이익_2022/09'], errors='coerce')
    collected['EPS_3분기 평균'] = collected.loc[:, ['EPS증가율_q-1','EPS증가율_q-2','EPS증가율_q-3']].mean(axis=1)

    collected = collected[collected['PEG_y'] > 0 ] 
    collected = collected[collected['PEG_y'] <= 0.5 ] 
    collected = collected[collected['부채비율'].astype('float') <= 100]
    collected = collected[~collected['EPS_3분기 평균'].isnull()]
    collected = collected[collected['EPS_3분기 평균'] > 0]
    
    collected = collected.sort_values(by=['PEG_y', 'EPS_3분기 평균', '부채비율'], ascending=[True, False, True],ignore_index=True)

    cols = ['code', '종목명', 'PEG_y', 'EPS_3분기 평균', '부채비율']
    print(collected[cols])

    output = collected[cols]
    save_styled_excel(output, 'derived/peg_output_{0}-{1:02d}.xlsx'.format(now.year, now.month))
    


# Unnamed: 0          0
# code              57  / All
# 종목명             57  / 재무제표
# 업종               57  / 재무제표
# PER                57  / 재무제표
# PBR                57  / 재무제표  
# 시가총액(보통주,억원)       57  / 스냅샷
# 부채비율                      / 스냅샷(?), 재무비율
# 지배주주순이익                   / 스냅샷 
# 당기순이익_yyyy/q-4    2580
# 당기순이익_yyyy/q-3   2580
# 당기순이익_yyyy/q-2   2580
# 당기순이익_yyyy/q-1   2580
# 유동자산_yyyy/q-4     2580
# 부채_yyyy/q-4       2580
# 유동자산_yyyy/q-3     2580
# 부채_yyyy/q-3  2580
# 유동자산_yyyy/q-2     2580
# 부채_yyyy/q-2       2580
# dtype: int64