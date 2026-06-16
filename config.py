# Trading Bot Configuration

STARTING_CAPITAL = 10000
MAX_POSITION_PCT = 0.10
MIN_POSITION_PCT = 0.02
ENTRY_THRESHOLD_BULL = 7.0
ENTRY_THRESHOLD_NEUTRAL = 8.0
ENTRY_THRESHOLD_BEAR = 9.0
PROFIT_TARGET = 0.09
STOP_LOSS = 0.07
MAX_HOLD_DAYS = 20
MAX_POSITIONS = 10
MAX_SECTOR_POSITIONS = 2
MAX_CORRELATION = 0.7
DATA_PROVIDER = "yfinance"
NOTIFICATION_METHOD = "email"
NOTIFICATION_EMAIL = "mrrjw3408@gmail.com"
GMAIL_APP_PASSWORD = "ahsf xuyv juvj gnmv"
WEIGHT_TECHNICAL = 2.0
WEIGHT_SECTOR_STRENGTH = 2.0
WEIGHT_TREND = 2.0
WEIGHT_INSTITUTIONAL = 2.5
WEIGHT_VOLUME = 0.5
WEIGHT_BONUS = 0.5
VIX_LOW = 15
VIX_HIGH = 25
BREADTH_BULL = 70
BREADTH_BEAR = 50
YIELD_CURVE_FLAT = 0.1

SECTORS = {
    "Energy": "XLE",
    "Infrastructure": "PAVE",
    "Finance": "XLF",
    "Health": "XLV",
    "Semiconductors": "SOXX",
    "Backdoor Tech": "XLK",
    "Consumer Discretionary": "XLY",
    "Industrials": "XLI",
    "Materials": "XLB"
}

TICKERS = {
    "Energy": ["XOM","CVX","COP","EOG","SLB","MPC","PSX","VLO","OXY","HAL","BKR","DVN","WMB","OKE","KMI","LNG","ET","EPD","PAA","TRGP","MPLX","ENB","TRP","NRG","AES","EXC","NEE","DUK","SO","ED","PCG","ETR","XEL","WEC","ES","CMS","NI","ATO"],
    "Infrastructure": ["UNP","CSX","NSC","CP","CNI","WAB","GWW","PWR","MTZ","EME","ACM","FLR","KBR","TTEK","VMC","MLM","EXP","AWK","AMT","CCI","SBAC","DLR","EQIX","PLD","PSA","EXR","CUBE","REXR","FR","EGP","STAG","LXP","TRNO","MSEX","CWT","SJW","YORW","ARTNA"],
    "Finance": ["JPM","BAC","WFC","GS","MS","C","BLK","SCHW","AXP","COF","USB","PNC","TFC","BK","STT","MTB","CFG","HBAN","RF","KEY","FITB","ZION","CMA","V","MA","PYPL","FIS","FISV","GPN","DFS","BOKF","FFIN","WBS","UMBF","IBOC","CVBF","WAFD","TCBI"],
    "Health": ["JNJ","UNH","PFE","ABT","TMO","MRK","DHR","BMY","AMGN","GILD","CVS","CI","HUM","CNC","MOH","ELV","HCA","THC","UHS","ISRG","SYK","BSX","MDT","ZBH","EW","HOLX","DXCM","LLY","BIIB","REGN","VRTX","IQV","CRL","MEDP","ICLR","EVH","MMSI","NVCR","FATE"],
    "Semiconductors": ["NVDA","AMD","INTC","QCOM","AVGO","TXN","MU","AMAT","LRCX","KLAC","ASML","TSM","ARM","MRVL","ADI","NXPI","ON","SWKS","QRVO","MPWR","WOLF","SITM","AMBA","ALGM","DIOD","FORM","ACLS","ONTO","UCTT","COHU","ICHR","MTSI","AXTI","PDFS","CEVA","SLAB","TSEM","UMC"],
    "Backdoor Tech": ["CSCO","FFIV","NTAP","PSTG","HPE","DELL","STX","WDC","T","VZ","TMUS","LUMN","CRWD","PANW","FTNT","ZS","OKTA","S","TENB","RPD","VRNS","QLYS","ETN","CARR","TT","JCI","GTLS","VICR","CTS","LFUS","NOVT","CABO","SHEN","ITRN","AWR","OTIS"],
    "Consumer Discretionary": ["AMZN","TSLA","HD","MCD","NKE","SBUX","TGT","LOW","BKNG","CMG","ABNB","RCL","CCL","MGM","LVS","WYNN","DRI","YUM","QSR","WING","ROST","TJX","BBWI","PVH","RL","TPR","VFC","HBI","UAA","LULU","NVR","PHM","DHI","LEN","TOL","MHO","GRBK","SKY","CCS","MTH","F","GM","RIVN","LCID","HOG","LEA","BWA","ALV","MGA","AZO"],
    "Industrials": ["GE","HON","MMM","CAT","DE","BA","RTX","LMT","NOC","GD","LHX","HII","TDG","HWM","TXT","WWD","AXON","LDOS","SAIC","CACI","BAH","KTOS","PLTR","ACN","IR","AME","PH","ROK","EMR","FTV","GNRC","XYL","WAT","MIDD","SPXC","GGG","ITT","RXO","CHRW","EXPD","JBHT","ODFL","SAIA","XPO","TFII","DSGR","HEI","TDY","CW","DRS"],
    "Materials": ["LIN","APD","SHW","ECL","DD","DOW","LYB","EMN","FCX","NEM","GOLD","AEM","WPM","PAAS","HL","AA","CMC","NUE","STLD","RS","MLI","CF","MOS","NTR","RPM","PPG","OLN","ASH","HUN","TROX","ALB","FMC","CTVA","SMG","ATI","WOR","KWR","VNTR","HWKN","IOSP","BCPC","GCP","CENX","KALU","CDE","AG","AMR","MP","USAC","CTRA"]
}
