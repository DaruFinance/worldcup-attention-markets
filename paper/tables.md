# Tables — When the World Watches Football

## Table 1. Sample description

|   tournament |   matches |   played |   knockout |   usa |   euro |   gbp |   jpy |   goals |
|-------------:|----------:|---------:|-----------:|------:|-------:|------:|------:|--------:|
|         2018 |        64 |       64 |         16 |     0 |     23 |     7 |     4 |     169 |
|         2022 |        64 |       64 |         16 |     4 |     26 |     5 |     4 |     172 |
|         2026 |       104 |        4 |         32 |     3 |     24 |     6 |     3 |       0 |


## Table 3/5. Cross-market during-match effect (2018+2022)

| group         |   absret |   hlrange |   ltrades |    lvol |
|:--------------|---------:|----------:|----------:|--------:|
| ALL           |        0 |   -0      |    0.0232 |  0.023  |
| crypto_spot   |       -0 |   -0      |   -0.0162 | -0.0272 |
| crypto_perp   |       -0 |   -0.0001 |   -0.0406 | -0.0398 |
| equity_fut    |        0 |    0      |   -0.0128 | -0.0298 |
| commodity_fut |        0 |    0      |    0.0576 |  0.0699 |
| fx_fut        |        0 |    0      |    0.0927 |  0.1043 |


_log-point coef on Match; ***/**/* = p<.01/.05/.10; SE clustered by date; instrument×weekday×minute-of-day + date FE._


## Table 4. Domestic-team heterogeneity

|                         | absret    | ltrades    | lvol       |
|:------------------------|:----------|:-----------|:-----------|
| ('6B', '6B match')      | +0.0000   | +0.1057    | +0.1218    |
| ('6B', '6B x domestic') | -0.0000** | -0.3640*** | -0.4159*** |
| ('6E', '6E match')      | -0.0000   | +0.0109    | +0.0032    |
| ('6E', '6E x domestic') | +0.0000   | +0.1560    | +0.1944*   |
| ('6J', '6J match')      | +0.0000   | +0.1190*   | +0.1356*   |
| ('6J', '6J x domestic') | -0.0000   | +0.0860    | +0.0756    |
| ('ES', 'ES match')      | +0.0000   | -0.0361    | -0.0559    |
| ('ES', 'ES x domestic') | -0.0000   | +0.1014    | +0.0894    |
| ('NQ', 'NQ match')      | +0.0000   | +0.0025    | -0.0131    |
| ('NQ', 'NQ x domestic') | -0.0000   | +0.2277**  | +0.3041**  |


## Table 4b. Knockout heterogeneity

|                                     |   absret |   ltrades |    lvol |
|:------------------------------------|---------:|----------:|--------:|
| ('commodity_fut', 'knockout extra') |   0      |    0.0624 |  0.0314 |
| ('commodity_fut', 'match(group)')   |   0      |    0.0435 |  0.0628 |
| ('crypto_perp', 'knockout extra')   |   0      |    0.1361 |  0.1643 |
| ('crypto_perp', 'match(group)')     |  -0.0001 |   -0.0808 | -0.0884 |
| ('crypto_spot', 'knockout extra')   |  -0      |    0.0101 |  0.0299 |
| ('crypto_spot', 'match(group)')     |   0      |   -0.0193 | -0.0361 |
| ('equity_fut', 'knockout extra')    |   0.0001 |    0.1414 |  0.1253 |
| ('equity_fut', 'match(group)')      |  -0      |   -0.0436 | -0.057  |
| ('fx_fut', 'knockout extra')        |   0      |    0.1679 |  0.1283 |
| ('fx_fut', 'match(group)')          |  -0      |    0.0551 |  0.0756 |


## Table 7. Placebo (crypto; shifted match windows — should be ~0)

| term          |    coef |     se |      p |
|:--------------|--------:|-------:|-------:|
| lvol +1day    |  0.0241 | 0.0415 | 0.5627 |
| ltrades +1day |  0.0139 | 0.0339 | 0.6814 |
| absret +1day  | -0      | 0      | 0.4566 |
| hlrange +1day | -0      | 0.0001 | 0.5701 |
| lvol +3h      | -0.0764 | 0.0486 | 0.118  |
| ltrades +3h   | -0.0712 | 0.0392 | 0.0717 |
| absret +3h    | -0      | 0      | 0.3757 |
| hlrange +3h   | -0.0001 | 0.0001 | 0.2924 |
| lvol -1day    | -0.0417 | 0.0371 | 0.2628 |
| ltrades -1day | -0.0305 | 0.0306 | 0.3212 |
| absret -1day  | -0      | 0      | 0.2256 |
| hlrange -1day | -0.0001 | 0      | 0.2341 |


## Goal-window effects (crypto)

| outcome    | window   |    coef |     se |      p |
|:-----------|:---------|--------:|-------:|-------:|
| lvol       | g5       | -0.081  | 0.0517 | 0.1196 |
| lvol       | g15      | -0.0704 | 0.0419 | 0.095  |
| ltrades    | g5       | -0.0689 | 0.0419 | 0.1023 |
| ltrades    | g15      | -0.0502 | 0.0357 | 0.1613 |
| absret     | g5       | -0      | 0      | 0.4565 |
| absret     | g15      | -0      | 0      | 0.4226 |
| signed_imb | g5       | -0.0044 | 0.0072 | 0.5443 |
| signed_imb | g15      |  0.01   | 0.0059 | 0.0916 |


## 2026 live out-of-sample (partial)

| group         | outcome   |    coef |     se |      p |
|:--------------|:----------|--------:|-------:|-------:|
| crypto_spot   | lvol      |  0.1172 | 0.2842 | 0.6841 |
| crypto_spot   | ltrades   | -0.1736 | 0.2611 | 0.5131 |
| crypto_spot   | absret    | -0.0001 | 0.0001 | 0.583  |
| crypto_spot   | hlrange   | -0.0001 | 0.0002 | 0.7299 |
| crypto_perp   | lvol      | -0.2528 | 0.3743 | 0.5064 |
| crypto_perp   | ltrades   | -0.1656 | 0.2982 | 0.5843 |
| crypto_perp   | absret    | -0.0001 | 0.0001 | 0.5712 |
| crypto_perp   | hlrange   | -0.0001 | 0.0002 | 0.6853 |
| equity_fut    | lvol      | -0.1107 | 0.1946 | 0.5792 |
| equity_fut    | ltrades   | -0.0863 | 0.234  | 0.7182 |
| equity_fut    | absret    |  0      | 0.0002 | 0.848  |
| equity_fut    | hlrange   | -0.0001 | 0.0001 | 0.3426 |
| commodity_fut | lvol      |  0.1815 | 0.4277 | 0.6782 |
| commodity_fut | ltrades   |  0.1622 | 0.4217 | 0.7068 |
| commodity_fut | absret    |  0.0001 | 0.0002 | 0.541  |
| commodity_fut | hlrange   |  0.0001 | 0.0003 | 0.6236 |
| fx_fut        | lvol      |  0.4535 | 0.5065 | 0.3869 |
| fx_fut        | ltrades   |  0.442  | 0.4001 | 0.2893 |
| fx_fut        | absret    |  0      | 0      | 0.4352 |
| fx_fut        | hlrange   |  0      | 0      | 0.3169 |
