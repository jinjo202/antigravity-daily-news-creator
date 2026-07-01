"""감시 대상 종목 리스트를 관리합니다.

배당 공시를 모니터링할 특정 종목들의 종목코드와 이름을 정의합니다.
종목을 추가/제거하려면 아래 WATCHLIST 딕셔너리를 수정하세요.
"""


# ──────────────────────────────────────────────────────────────
# 감시 대상 종목 (종목코드 → 종목명)
# 총 14개 종목
# ──────────────────────────────────────────────────────────────

WATCHLIST: dict[str, str] = {
    # ── 통신 ──
    "032640": "LG유플러스",
    "017670": "SK텔레콤",
    "030200": "KT",
    # ── 금융 ──
    "105560": "KB금융",
    "055550": "신한지주",
    "086790": "하나금융지주",
    "024110": "기업은행",
    "316140": "우리금융지주",
    # ── 자동차 ──
    "005380": "현대자동차",
    "000270": "기아",
    # ── 인프라 ──
    "088980": "맥쿼리인프라",
    # ── 삼성 그룹 ──
    "005930": "삼성전자",
    "028050": "삼성E&A",
    "012750": "에스원",
}


# ──────────────────────────────────────────────────────────────
# 감시 대상 ETF (종목코드 → 상세 정보)
# 사용자가 지정한 6개 ETF (KODEX 200, KODEX 코스닥150, KODEX AI전력핵심, PLUS K방산, HANARO 원자력, KoAct 바이오)
# ──────────────────────────────────────────────────────────────

ETF_WATCHLIST: dict[str, dict] = {
    "069500": {
        "name": "KODEX 200",
        "keywords": ["kodex 200", "kodex200"]
    },
    "229200": {
        "name": "KODEX 코스닥150",
        "keywords": ["kodex 코스닥 150", "kodex 코스닥150", "kodex코스닥150"]
    },
    "487240": {
        "name": "KODEX AI전력핵심설비",
        "keywords": ["kodex ai전력핵심", "kodex ai 전력핵심", "kodexai전력핵심"]
    },
    "449450": {
        "name": "PLUS K방산",
        "keywords": ["plus k방산", "plusk방산", "plus k 방산"]
    },
    "434730": {
        "name": "HANARO 원자력iSelect",
        "keywords": ["hanaro 원자력", "hanaro원자력", "hanaro 원자력iselect"]
    },
    "462900": {
        "name": "KoAct 바이오헬스케어액티브",
        "keywords": ["koact 바이오헬스케어", "koact 바이오", "koact바이오"]
    }
}


def get_stock_codes() -> list[str]:
    """감시 대상 종목코드 리스트를 반환합니다."""
    return list(WATCHLIST.keys())


def get_stock_name(stock_code: str) -> str:
    """종목코드로 종목명을 조회합니다."""
    return WATCHLIST.get(stock_code, "알 수 없음")


def contains(stock_code: str) -> bool:
    """종목코드가 감시 대상에 포함되는지 확인합니다."""
    return stock_code in WATCHLIST


def find_matched_etf(disclosure_stock_name: str) -> str | None:
    """공시 종목명이 감시 대상 ETF 중 하나와 매칭되는지 확인하고 해당 종목코드를 반환합니다.
    
    대소문자와 공백을 무시하여 유연하게 매칭하며, 인덱스형 상품은 엄격히 매치합니다.
    """
    cleaned_disclosure_name = disclosure_stock_name.replace(" ", "").lower()
    if cleaned_disclosure_name.endswith("etf"):
        cleaned_disclosure_name = cleaned_disclosure_name[:-3]
        
    for stock_code, info in ETF_WATCHLIST.items():
        is_exact_match_target = info["name"] in ["KODEX 200", "KODEX 코스닥150"]
        for kw in info["keywords"]:
            cleaned_kw = kw.replace(" ", "").lower()
            if cleaned_kw.endswith("etf"):
                cleaned_kw = cleaned_kw[:-3]
                
            if is_exact_match_target:
                if cleaned_disclosure_name == cleaned_kw:
                    return stock_code
            else:
                if cleaned_kw in cleaned_disclosure_name:
                    return stock_code
    return None


def get_etf_name(stock_code: str) -> str:
    """ETF 종목코드로 종목명을 반환합니다."""
    if stock_code in ETF_WATCHLIST:
        return ETF_WATCHLIST[stock_code]["name"]
    return "알 수 없음"

