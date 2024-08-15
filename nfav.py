import datetime
import pandas as pd

import krxStocks as kS
import fnguideFinance as fnFI

if __name__ == '__main__':

    df_krxStocks = kS.getKrxStocks()
    df_nfav = pd.DataFrame(columns = ['code', 'name', '현금및현금성자산', '유동금융자산','장기금융자산','부채','비지배주주지분자본'])

    print(df_nfav)

    for code in df_krxStocks['code']:
        code = '005930'
        content = fnFI.getFnguideFinance(code)
        result = fnFI.parseFnguideFinance(code, content)
        break


    #
    # now = datetime.datetime.now()
    #
    # collectedFilePath = "derived/nfav_{0}-{1:02d}-{2:02d}.csv".format(now.year, now.month, now.day)
    #
    # collected = pd.read_csv(collectedFilePath, sep="\t")
    # collected['code'] = collected['code'].map('{:06.0f}'.format)
    # collected['유동자산'] = pd.to_numeric(collected['유동자산_2022/09'], errors='coerce')
    # collected['부채'] = pd.to_numeric(collected['부채_2022/09'], errors='coerce')
    # collected['시가총액(보통주,억원)'] = collected['시가총액(보통주,억원)'].str.replace(",", "")
    # collected['시가총액(보통주,억원)'] = pd.to_numeric(collected['시가총액(보통주,억원)'], errors='coerce')
    # collected['당기순이익'] = pd.to_numeric(collected['당기순이익_2022/09'], errors='coerce')
    # collected = collected[~collected['유동자산'].isnull()]
    # collected = collected[~collected['부채'].isnull()]
    #
    # collected['NCAV_R'] = (collected['유동자산'] - collected['부채']) / collected['시가총액(보통주,억원)']
    # collected.sort_values(by = ['NCAV_R'], inplace=True, ascending=False)
    # 종목명최대길이  = collected['종목명'].str.len().max()
    # collected['종목명'] = collected['종목명'].apply(lambda x : x.ljust(종목명최대길이))
    #
    # collected = collected[collected['NCAV_R'] > 0]
    # collected = collected[collected['당기순이익'] > 0]
    #
    #
    #
    # print(collected[['code', 'NCAV_R', '종목명', '당기순이익', '시가총액(보통주,억원)', '유동자산', '부채', ]])
    #
    # output = collected[['code', 'NCAV_R', '종목명', '당기순이익', '시가총액(보통주,억원)', '유동자산', '부채', ]]
    #
    # # output.to_csv('ncav_output_2023-03-04.tsv', sep="\t", index=False)
    # output.to_csv('derived/ncav_output_{0}-{1:02d}-{2:02d}.csv'.format(now.year, now.month, now.day), sep="\t", index=False, encoding='utf-8-sig')
    #
