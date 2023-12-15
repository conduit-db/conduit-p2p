# Copyright (c) 2020-2023, Hayden Donnelly
#
# All rights reserved.
#
# Licensed under the MIT License; see LICENCE for details.

TX_OFFSETS = [
    83,
    268,
    494,
    720,
    946,
    1172,
    1395,
    1618,
    1911,
    2243,
    2576,
    2909,
    3243,
    3577,
    3911,
    4245,
    4579,
    4912,
    5247,
    5582,
    5917,
    6252,
    6588,
    6920,
    7254,
    7589,
    7924,
    8260,
    8593,
    8927,
    9262,
    9596,
    9932,
    10268,
    10602,
    10937,
    11273,
    11609,
    11943,
    12279,
    12614,
    12949,
    13285,
    13621,
    13956,
    14292,
    14626,
    14960,
    15296,
    15632,
    15968,
    16303,
    16637,
    16970,
    17305,
    17641,
    17977,
    18313,
    18646,
    18982,
    19316,
    19650,
    19986,
    20319,
    20655,
    20989,
    21325,
    21659,
    21992,
    22327,
    22661,
    23033,
    23258,
    23483,
    23706,
    23929,
    24414,
    25046,
    25272,
    25498,
    25724,
    25949,
    26174,
    26399,
    26624,
    26850,
    27076,
    27302,
    27528,
    27754,
    28218,
    28591,
    28782,
    29076,
    29573,
    30094,
    30531,
    31639,
    31862,
    32086,
    32310,
    32534,
    32758,
    32982,
    33207,
    33432,
    33657,
    33883,
    34109,
    34481,
    35443,
    35667,
    36040,
    36265,
    36491,
    36716,
    36942,
    38052,
    38276,
    38501,
    38727,
    38950,
    39174,
    39366,
    39626,
    39999,
    41370,
    41596,
    42284,
    44132,
    44321,
    44842,
    45067,
    45439,
    45664,
    46359,
    47309,
    47500,
    47691,
    47882,
    48073,
    48264,
    48487,
    48712,
    48937,
    49162,
    49387,
    49642,
    49867,
    50092,
    50317,
    50573,
    50798,
    51023,
    51248,
    51473,
    51698,
    51923,
    52148,
    52374,
    52599,
    52791,
    53017,
    53241,
    53467,
    53693,
    53919,
    54145,
    54369,
    54595,
    54821,
    55047,
    55273,
    55499,
    55723,
    55949,
    56173,
    56399,
    56625,
    56851,
    57077,
    57303,
    57529,
    57721,
    57978,
    58348,
    58574,
    58946,
    59319,
    59544,
    59736,
    60256,
    60594,
    62000,
    62225,
    62887,
    63703,
    64075,
    64448,
    64821,
    65195,
    65569,
    65792,
    65981,
    66170,
    66427,
    66684,
    66942,
    67133,
    67324,
    67515,
    67706,
    68040,
    68374,
    68968,
    69337,
    69706,
    70075,
    70267,
    70459,
    70651,
    70843,
    71035,
    71227,
    71419,
    71611,
    71832,
    72055,
    72278,
    72501,
    72725,
    72950,
    73174,
    73547,
    73772,
    73997,
    74222,
    74447,
    74672,
    74895,
    75120,
    75345,
    75570,
    75793,
    76018,
    76243,
    76468,
    76988,
    81186,
    82272,
    82498,
    82723,
    82948,
    83174,
    83695,
    84658,
    84884,
    85110,
    85336,
    85562,
    85788,
    86014,
    86388,
    86613,
    86987,
    87568,
    87893,
    88153,
    88378,
    88634,
    89299,
    89525,
    89929,
    90153,
    90378,
    92229,
    93486,
    93677,
    94788,
    95044,
    95301,
    95558,
    95784,
    96894,
    97152,
    97410,
    97668,
    97891,
    98115,
    98340,
    98565,
    98790,
    99015,
    99240,
    99465,
    99690,
    99915,
    100140,
    100365,
    100590,
    100815,
    101040,
    101265,
    101491,
    101682,
    101908,
    102134,
    102324,
    102550,
    102776,
    103002,
    103228,
    103454,
    103680,
    103906,
    104132,
    104568,
    105600,
    106415,
    110261,
    110484,
    110855,
    111228,
    111601,
    111827,
    112052,
    112277,
    112503,
    113273,
    113530,
    113787,
    114044,
    114299,
    114556,
    114813,
    115070,
    115327,
    115584,
    115842,
    116100,
    116358,
    116616,
    116874,
    117395,
    117916,
    123156,
    125003,
    125297,
    125914,
    126286,
    127368,
    127741,
    128114,
    129020,
    129209,
    129398,
    129702,
    130106,
    130512,
    130770,
    131139,
    131512,
    132032,
    132367,
    132702,
    133034,
    133366,
    133701,
    134036,
    134371,
    134706,
    135039,
    135374,
    135709,
    136043,
    136377,
    136711,
    137047,
    137382,
    137718,
    138052,
    138386,
    138719,
    139055,
    139391,
    139726,
    140061,
    140396,
    140729,
    141061,
    141398,
    141835,
    142569,
    143270,
    143493,
    143865,
    144237,
    144610,
    144983,
    145207,
    145577,
    145951,
    146325,
    146699,
    147073,
    147447,
    147821,
    148195,
    148420,
    148794,
    149168,
    149542,
    149734,
    150108,
    150482,
    151904,
    152275,
    152500,
    152725,
    152950,
    153141,
    153366,
    153591,
    153816,
    154041,
    154266,
    154491,
    154716,
    154941,
    155166,
    155391,
    155616,
    155841,
    156066,
    156291,
    156516,
    156741,
    156966,
    157191,
    158335,
    159148,
    159520,
    160252,
    160622,
    160846,
    161070,
    161293,
    161517,
    161741,
    161965,
    162188,
    162414,
    164717,
    165011,
    165237,
    165970,
    166162,
    166533,
    166759,
    166984,
    167210,
    167436,
    167662,
    167888,
    168114,
    168340,
    168532,
    168758,
    168984,
    169210,
    169436,
    169662,
    169888,
    170259,
    170485,
    170711,
    170937,
    171162,
    171535,
    171761,
    172134,
    172666,
    173036,
    173406,
    173629,
    174001,
    174190,
    174379,
    174897,
    175269,
    175640,
    176011,
    176382,
    176606,
    176977,
    177200,
    177571,
    177942,
    178165,
    178536,
    179055,
    179281,
    179654,
    244898,
    245270,
    245495,
    245867,
    246239,
    246462,
    246831,
    247941,
    248131,
    248948,
    249138,
    257471,
    257992,
    258957,
    259330,
    259703,
    260077,
    260302,
    260676,
    261050,
    261424,
    261615,
    261806,
    261997,
    262613,
    262805,
    262997,
    263189,
    263414,
    263606,
    263944,
    264283,
    264622,
    265355,
    318096,
    318322,
    319101,
    319327,
    320142,
    320923,
    322523,
    322749,
    323151,
    323933,
    324454,
    325629,
    326116,
    328359,
    328582,
    328808,
    329441,
    330074,
    330469,
    331579,
    372068,
    372863,
    373121,
    373344,
    373569,
    378784,
    380159,
    380561,
    380963,
    381365,
    381768,
    382171,
    382657,
    386520,
    386924,
    387328,
    387732,
    388136,
    388540,
    388944,
    389348,
    389606,
    389863,
    390121,
    390378,
    390716,
    391120,
    391524,
    391929,
    392334,
    392739,
    393144,
    393549,
    393954,
    394210,
    394615,
    394841,
    395213,
    395618,
    396023,
    396279,
    396684,
    397943,
    398317,
    398950,
    399356,
    399762,
    400165,
    400571,
    400977,
    401383,
    401609,
    402864,
    403677,
    404491,
    404898,
    405305,
    406119,
    406526,
    407340,
    407747,
    408561,
    409375,
    410190,
    411005,
    411820,
    412635,
    413450,
    414266,
    414458,
    414866,
    415682,
    416090,
    416907,
    417524,
    421143,
    421940,
    423160,
    482309,
    541517,
    542628,
    601828,
    602053,
    602278,
    603390,
    612930,
    613342,
    614007,
    614420,
    614832,
    616413,
    617081,
    617483,
    618217,
    618443,
    619111,
    619631,
    620300,
    620822,
    621344,
    621599,
    621970,
    622772,
    623144,
    623516,
    623888,
    624260,
    625107,
    625480,
    625853,
    626226,
    626599,
    626972,
    627346,
    627773,
    628201,
    628630,
    629059,
    629432,
    629861,
    630290,
    630719,
    631148,
    631578,
    632008,
    632231,
    632454,
    632677,
    632900,
    633123,
    633346,
    633569,
    633792,
    634015,
    634238,
    634461,
    634684,
    634907,
    635130,
    635353,
    635576,
    635799,
    636022,
    636245,
    636468,
    636691,
    636914,
    637137,
    637360,
    637583,
    637806,
    638030,
    638255,
    638478,
    638701,
    638924,
    639147,
    639370,
    639593,
    639816,
    640039,
    640860,
    641084,
    641308,
    641532,
    641756,
    641979,
    642202,
    642426,
    642649,
    642872,
    643096,
    643319,
    643543,
    643766,
    643990,
    644214,
    644438,
    644662,
    644886,
    645110,
    645334,
    645558,
    645782,
    646006,
    646230,
    646454,
    646678,
    646902,
    647126,
    647350,
    647574,
    647798,
    648022,
    648246,
    648469,
    648692,
    648916,
    649139,
    649363,
    649587,
    649811,
    650035,
    650258,
    650482,
    650705,
    650929,
    651152,
    651376,
    651600,
    651824,
    665145,
    665579,
    665804,
    666178,
    666403,
    666742,
    666967,
    667192,
    667417,
    667642,
    667867,
    668058,
    668283,
    668507,
    668730,
    668953,
    669177,
    669402,
    669627,
    669850,
    670075,
    670300,
    670525,
    670750,
    670975,
    671200,
    671425,
    671650,
    672085,
    672520,
    672956,
    673392,
    673828,
    674264,
    674490,
    674926,
    675362,
    675798,
    676234,
    676670,
    677106,
    677542,
    677768,
    677993,
    678219,
    678445,
    678671,
    678896,
    679122,
    679348,
    679574,
    679797,
    680023,
    680249,
    680475,
    680701,
    680927,
    681153,
    681379,
    681605,
    681831,
    682057,
    682249,
    682475,
    682701,
    682927,
    683153,
    683379,
    683605,
    683831,
    684057,
    684283,
    684538,
    684764,
    684989,
    685215,
    685441,
    685667,
    685893,
    686119,
    686344,
    686570,
    686795,
    687021,
    687247,
    687473,
    687699,
    688136,
    688573,
    689010,
    689447,
    689884,
    690321,
    690758,
    691195,
    691452,
    691889,
    692326,
    692763,
    693200,
    693637,
    694074,
    694511,
    694948,
    695385,
    695822,
    696259,
    696696,
    697133,
    697570,
    698007,
    698444,
    698881,
    699105,
    699542,
    699979,
    700416,
    700854,
    701292,
    701730,
    702166,
    702423,
    702861,
    703299,
    703737,
    704175,
    704613,
    704869,
    705307,
    705745,
    706002,
    706440,
    706878,
    707316,
    707755,
    708127,
    708352,
    708577,
    715290,
    715516,
    715919,
    716884,
    717551,
    717742,
    718409,
    718634,
    719302,
    719525,
    719748,
    719971,
    720194,
    720417,
    720640,
    720863,
    721086,
    721309,
    721532,
    721755,
    721978,
    722201,
    722424,
    722647,
    722870,
    723093,
    723316,
    723539,
    723762,
    723985,
    724208,
    724431,
    724654,
    724877,
    725100,
    725323,
    725546,
    725769,
    725992,
    726215,
    726438,
    726661,
    726884,
    727107,
    727330,
    727553,
    727776,
    727999,
    728222,
    728445,
    728668,
    728891,
    729114,
    729337,
    729560,
    729783,
    730006,
    730229,
    730453,
    730677,
    730901,
    731125,
    731349,
    731573,
    731797,
    732021,
    732245,
    732468,
    732691,
    732915,
    733138,
    733361,
    733585,
    733809,
    734033,
    734256,
    734480,
    734704,
    734928,
    735152,
    735376,
    735600,
    735824,
    736048,
    736272,
    736496,
    736720,
    736944,
    737168,
    737392,
    737615,
    737839,
    738063,
    738287,
    738511,
    738735,
    738959,
    739183,
    739407,
    739631,
    739855,
    740079,
    740302,
    740526,
    740749,
    740973,
    741196,
    741419,
    741642,
    741865,
    742088,
    742312,
    742536,
    742760,
    742984,
    743208,
    743432,
    743656,
    743880,
    744104,
    744328,
    744552,
    744775,
    744999,
    745223,
    745447,
    745671,
    745895,
    746119,
    746344,
    746569,
    746794,
    747019,
    747244,
    747469,
    747694,
    747919,
    748144,
    748369,
    748594,
    748819,
    749044,
    749269,
    749494,
    749719,
    749909,
    750134,
    750359,
    750584,
    750809,
    751034,
    751259,
    751484,
    751709,
    751934,
    752159,
    752384,
    752609,
    752834,
    753059,
    753251,
    753443,
    753669,
    753894,
    754119,
    754344,
    754569,
    754794,
    755019,
    755244,
    755469,
    755694,
    755919,
    756144,
    756369,
    756594,
    756819,
    757044,
    757269,
    757494,
    757719,
    757944,
    758169,
    758394,
    758619,
    758844,
    759069,
    759294,
    759519,
    759744,
    759969,
    760194,
    760419,
    760644,
    760869,
    761094,
    761319,
    761544,
    761769,
    761994,
    762219,
    762444,
    762669,
    762894,
    763119,
    763344,
    763569,
    763794,
    764019,
    764244,
    764469,
    764694,
    764919,
    765144,
    765369,
    765594,
    765819,
    766044,
    766269,
    766494,
    766719,
    766944,
    767169,
    767394,
    767619,
    767844,
    768069,
    768294,
    768519,
    768744,
    768969,
    769194,
    769419,
    769644,
    770605,
    771566,
    771758,
    771984,
    772210,
    772436,
    772662,
    772888,
    773114,
    773340,
    773566,
    773792,
    774018,
    774244,
    774470,
    774696,
    774922,
    775148,
    775374,
    775600,
    775826,
    776052,
    776278,
    776504,
    776730,
    776956,
    777182,
    777408,
    777634,
    777860,
    778086,
    778312,
    778538,
    778764,
    778990,
    779216,
    779442,
    779668,
    779894,
    780120,
    780346,
    780572,
    780798,
    781024,
    781250,
    781476,
    781702,
    781928,
    782154,
    782380,
    782606,
    782832,
    783058,
    783284,
    783510,
    783736,
    783962,
    784218,
    784444,
    784670,
    784896,
    785122,
    785348,
    785574,
    785800,
    786026,
    786252,
    786478,
    786704,
    786930,
    787156,
    787382,
    787608,
    787800,
    788026,
    788252,
    788478,
    788704,
    788930,
    789156,
    789382,
    789608,
    789834,
    790060,
    790286,
    790512,
    790738,
    790964,
    791190,
    791416,
    791607,
    791833,
    792059,
    792285,
    792511,
    792737,
    792963,
    793189,
    793415,
    793641,
    793867,
    794093,
    794319,
    794545,
    794771,
    794997,
    795223,
    795449,
    795675,
    795901,
    796127,
    796353,
    796579,
    796805,
    797771,
    798108,
    799661,
    802214,
    806870,
    818713,
    819821,
    820745,
    821669,
    822593,
    823517,
    823979,
    824904,
    825829,
    826754,
    827679,
    828142,
    829069,
    829996,
    830923,
    831850,
    832777,
    833705,
    834633,
    835561,
    836489,
    837417,
    838345,
    838809,
    839737,
    840201,
    840665,
    841593,
    842568,
    843497,
    844426,
    845355,
    845792,
    846722,
    847652,
    848582,
    849512,
    850442,
    851373,
    852304,
    853235,
    854166,
    855097,
    856028,
    856960,
    857892,
    858824,
    859756,
    860688,
    862093,
    862562,
    862854,
    863079,
    863304,
    863529,
    864015,
    864240,
    864498,
    864969,
    865161,
    865632,
    865823,
    866295,
    866521,
    866747,
    867267,
    867602,
    868416,
    869084,
    870044,
    871006,
    871968,
    872930,
    873303,
    874265,
    875227,
    876189,
    893968,
    897847,
    898810,
    899773,
    900736,
    901699,
    902662,
    903036,
    903262,
    903635,
    903975,
    904315,
    904655,
    904995,
    905335,
    906299,
    907262,
    907782,
    908857,
    909342,
    909828,
    910314,
    910800,
    911286,
    911772,
    912258,
    912744,
    913230,
    913716,
    914202,
    914688,
    916536,
    916725,
    917698,
    918185,
    918672,
    919159,
    919646,
    920133,
    920620,
    921107,
    921481,
    921968,
    922455,
    922942,
    923429,
    923916,
    924403,
    925378,
    926353,
    927328,
    927816,
    928304,
    928530,
    929018,
    929506,
    929697,
    930192,
    930449,
    931245,
    931742,
    932112,
    932484,
    932856,
    933228,
    933600,
    933972,
    934344,
    935011,
    935234,
    935457,
    935680,
    935903,
    936128,
    936353,
    936578,
    936803,
    936994,
    937219,
    937444,
    937669,
    937894,
    938119,
    938344,
    938569,
    938794,
    939019,
    939244,
    939469,
    939694,
    939919,
    940144,
    940369,
    940594,
    940819,
    941317,
    941837,
    942650,
    943464,
    943753,
    944339,
    944955,
    945588,
    946226,
    947189,
    947514,
    947869,
    948226,
    948583,
    948955,
    949327,
    949699,
    950072,
    950445,
    950818,
    951191,
    951564,
    951937,
    952310,
    952697,
    953905,
    954324,
    954763,
    955249,
    955748,
    956254,
    956771,
    957291,
    957842,
    958951,
    960060,
    960712,
    961377,
    962044,
    962712,
    963381,
    964082,
    964897,
    965713,
    966658,
    967620,
    967809,
    968856,
    969672,
    972391,
    972731,
    972955,
    974640,
    974865,
    975090,
    975315,
    975540,
    976261,
    976634,
    976860,
    977086,
    977310,
    977536,
    977910,
    978282,
    978507,
    978732,
    978957,
    979330,
    979555,
    979927,
    980151,
    980819,
    981045,
    981270,
    982086,
    982459,
    982980,
    983301,
    984116,
    984476,
    984869,
    985243,
    985617,
    985843,
    986069,
    986295,
    986684,
    986910,
    987678,
    987904,
    988278,
    988503,
    988729,
    989315,
    989540,
    989899,
    990125,
    990351,
    990872,
    991245,
    991618,
    991810,
    992034,
    992258,
    992878,
    993104,
    993645,
    994018,
    994242,
    994468,
    994693,
    994919,
    995275,
    995794,
    996019,
    996492,
    996717,
    997090,
    997316,
    997837,
    998062,
    998435,
    998773,
    999110,
    999367,
]

print(TX_OFFSETS[635])
