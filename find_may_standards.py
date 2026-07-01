import io
import sys
import os
import time
import re
import requests
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding != "utf-8":
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from config import AppConfig
from dart_api_client import DartApiClient, Disclosure
from email_sender import EmailSender
import watchlist_provider

def initialize_driver():
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=900,1200")
    options.add_argument("--disable-gpu")
    options.add_argument("--lang=ko-KR")
    return webdriver.Chrome(options=options)

def get_disclosure_text(driver, rcept_no: str) -> str:
    """DART 공시의 본문 텍스트를 추출합니다."""
    try:
        main_url = f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}"
        driver.get(main_url)
        time.sleep(2)
        
        iframe = driver.find_element(By.ID, "ifrm")
        viewer_url = iframe.get_attribute("src")
        
        driver.get(viewer_url)
        time.sleep(2)
        
        body_text = driver.find_element(By.TAG_NAME, "body").text
        return body_text
    except Exception as e:
        print(f"      ❌ 본문 텍스트 추출 실패 ({rcept_no}): {e}")
        return ""

def get_kind_etf_text(driver, acptno: str) -> str:
    """KIND ETF 공시의 본문 텍스트를 추출합니다."""
    try:
        url = f"https://kind.krx.co.kr/common/disclsviewer.do?method=search&acptno={acptno}"
        driver.get(url)
        time.sleep(3)
        
        # iframe 구조 고려 전체 텍스트 수집
        iframes = driver.find_elements(By.TAG_NAME, "iframe")
        full_text = ""
        for i, iframe in enumerate(iframes):
            try:
                driver.switch_to.frame(iframe)
                full_text += "\n" + driver.find_element(By.TAG_NAME, "body").text
                driver.switch_to.default_content()
            except:
                driver.switch_to.default_content()
        
        if not full_text:
            full_text = driver.find_element(By.TAG_NAME, "body").text
            
        return full_text
    except Exception as e:
        print(f"      ❌ KIND ETF 본문 텍스트 추출 실패 ({acptno}): {e}")
        return ""

def check_if_may_standard(text: str) -> bool:
    """본문 텍스트에서 5월 기준일 패턴이 발견되는지 확인합니다."""
    # 1) 기준일/폐쇄일 부근의 날짜 매칭
    # 예: 배당기준일 2026년 05월 15일, 2026.05.15, 2026-05-15, 2026/05/15
    # 혹은 "기준일" 근처에 5월 날짜가 있는 경우
    
    # 5월 날짜 패턴: 2026년 5월, 2026.5., 2026-05, 2026/05 등
    may_patterns = [
        r"2026\s*년\s*(?:05|5)\s*월",
        r"2026\.0?5\.",
        r"2026-0?5-",
        r"2026/0?5/"
    ]
    
    # 기준일 관련 단어 검색
    keywords = ["기준일", "폐쇄일", "분배락", "배당락"]
    
    # 먼저 5월 날짜가 아예 없는지 1차 필터링
    has_may_date = False
    for pat in may_patterns:
        if re.search(pat, text):
            has_may_date = True
            break
            
    if not has_may_date:
        return False
        
    # 날짜와 키워드의 인접성 판단 (동일 행 또는 50자 이내 존재 여부)
    lines = text.split("\n")
    for line in lines:
        if any(kw in line for kw in keywords):
            for pat in may_patterns:
                if re.search(pat, line):
                    print(f"      🎯 매칭 행 발견: {line.strip()[:100]}")
                    return True
                    
    # 행단위 매칭이 없더라도 텍스트 전체에서 키워드 근처에 매칭되는지 체크
    for match in re.finditer(r"(?:기준일|폐쇄일|분배락|배당락)", text):
        start = max(0, match.start() - 100)
        end = min(len(text), match.end() + 100)
        snippet = text[start:end]
        for pat in may_patterns:
            if re.search(pat, snippet):
                print(f"      🎯 근접 매칭 발견: ...{snippet.strip().replace('\n', ' ')[:120]}...")
                return True
                
    return False

def main():
    print("🚀 5월 기준일 배당 공시 수집 및 발송기 작동 개시")
    print("=" * 60)
    
    config = AppConfig()
    dart_api = DartApiClient(api_key=config.dart_api_key)
    dart_api.initialize()
    
    email_sender = EmailSender(
        recipient_emails=config.recipient_emails,
        headless=True,
    )
    
    driver = initialize_driver()
    stock_codes = watchlist_provider.get_stock_codes()
    corp_codes = dart_api.get_corp_codes_for_stocks(stock_codes)
    
    # DART 최근 75일 공시 목록 조회
    end_date = datetime.now().strftime("%Y%m%d")
    begin_date = (datetime.now() - timedelta(days=75)).strftime("%Y%m%d")
    
    print(f"\n1. DART 배당 관련 공시 수집 및 분석 ({begin_date} ~ {end_date})")
    disclosures = []
    for sc in stock_codes:
        name = watchlist_provider.get_stock_name(sc)
        cc = dart_api.get_corp_code(sc)
        if not cc:
            continue
        params = {
            "crtfc_key": config.dart_api_key,
            "corp_code": cc,
            "bgn_de": begin_date,
            "end_de": end_date,
            "page_count": 100,
        }
        try:
            resp = requests.get("https://opendart.fss.or.kr/api/list.json", params=params)
            data = resp.json()
            if data.get("status") == "000":
                for item in data.get("list", []):
                    disc = Disclosure.from_dict(item)
                    disclosures.append(disc)
            time.sleep(0.1)
        except Exception as ex:
            print(f"      ⚠️ {name} ({sc}) 공시 로드 중 오류: {ex}")
    
    # 배당/기준일 관련 키워드 공시 필터링
    DIVIDEND_KEYWORDS = ["현금ㆍ현물배당", "현금·현물배당", "배당결정", "주주명부폐쇄", "기준일"]
    filtered_disclosures = [
        d for d in disclosures
        if d.corp_code in corp_codes and any(kw in d.report_nm for kw in DIVIDEND_KEYWORDS)
    ]
    
    print(f"   감시 종목 배당 관련 공시 후보: {len(filtered_disclosures)}건")
    
    may_dart_disclosures = []
    for d in filtered_disclosures:
        print(f"   🔍 분석 중: {d.corp_name} ({d.rcept_dt}) - {d.report_nm}")
        text = get_disclosure_text(driver, d.rcept_no)
        if check_if_may_standard(text):
            print(f"      ✅ 5월 기준일 확정!")
            may_dart_disclosures.append(d)
        time.sleep(1)
        
    # 2. KIND ETF 최근 75일 공시 수집 및 분석
    print(f"\n2. KIND ETF 공시 수집 및 분석")
    url = "https://kind.krx.co.kr/disclosure/disclosurebystocktype.do"
    today_str = datetime.now().strftime("%Y-%m-%d")
    ago_str = (datetime.now() - timedelta(days=75)).strftime("%Y-%m-%d")
    
    payload = {
        "method": "searchDisclosureByStockTypeEtfSub",
        "forward": "disclosurebystocktype_etf_sub",
        "currentPageSize": "100",
        "pageIndex": "1",
        "orderMode": "1",
        "orderStat": "D",
        "etfIsuSrtCd": "",
        "reportCd": "",
        "reportTmp": "",
        "etfIsuSrtNm": "",
        "reportNm": "",
        "fromDate": ago_str,
        "toDate": today_str
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://kind.krx.co.kr/disclosure/disclosurebystocktype.do?method=searchDisclosureByStockTypeEtf",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    
    may_etf_disclosures = []
    try:
        res = requests.post(url, data=payload, headers=headers, timeout=15)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            table = soup.find("table")
            if table:
                rows = table.find_all("tr")[1:]
                for row in rows:
                    cells = row.find_all(["td", "th"])
                    if len(cells) < 5:
                        continue
                    date_cell = cells[1].get_text().strip()
                    stock_name = cells[2].get_text().strip()
                    report_title = cells[3].get_text().strip()
                    
                    acptno = ""
                    for link in row.find_all("a"):
                        onclick = link.get("onclick") or ""
                        if "openDisclsViewer" in onclick:
                            m = re.search(r"openDisclsViewer\('(\d+)',''\)", onclick)
                            if m:
                                acptno = m.group(1)
                                break
                    if not acptno:
                        continue
                        
                    # ETF 필터
                    matched_code = watchlist_provider.find_matched_etf(stock_name)
                    if not matched_code:
                        continue
                        
                    etf_name = watchlist_provider.get_etf_name(matched_code)
                    print(f"   🔍 ETF 분석 중: {etf_name} ({date_cell}) - {report_title}")
                    
                    text = get_kind_etf_text(driver, acptno)
                    if check_if_may_standard(text):
                        print(f"      ✅ 5월 기준일 확정!")
                        may_etf_disclosures.append({
                            "etf_name": etf_name,
                            "stock_code": matched_code,
                            "report_nm": report_title,
                            "date_str": date_cell,
                            "acptno": acptno
                        })
                    time.sleep(1)
    except Exception as e:
        print(f"   ❌ KIND ETF 로드 중 오류: {e}")

    # 3. 5월 기준일 공시 메일 재전송 실행
    print("\n" + "=" * 60)
    print(f"🎯 최종 5월 기준일 배당 공시 목록 (주식 {len(may_dart_disclosures)}건, ETF {len(may_etf_disclosures)}건)")
    print("=" * 60)
    
    # 이력 저장을 회피하여 무조건 전송하게 만듦 (테스트 발송이므로)
    sent_count = 0
    for d in may_dart_disclosures:
        print(f"📧 주식 메일 전송 중: {d.corp_name} - {d.report_nm}")
        success = email_sender.send_dividend_notification(d)
        print(f"   결과: {'성공' if success else '실패'}")
        if success:
            sent_count += 1
        time.sleep(2)
        
    for d in may_etf_disclosures:
        print(f"📧 ETF 메일 전송 중: {d['etf_name']} - {d['report_nm']}")
        success = email_sender.send_etf_notification(
            etf_name=d['etf_name'],
            stock_code=d['stock_code'],
            report_nm=d['report_nm'],
            date_str=d['date_str'],
            acptno=d['acptno']
        )
        print(f"   결과: {'성공' if success else '실패'}")
        if success:
            sent_count += 1
        time.sleep(2)
        
    driver.quit()
    dart_api.close()
    
    print("\n" + "=" * 60)
    print(f"🎉 5월 기준일 배당 공시 수동 재발송 완료! (총 {sent_count}건 발송 성공)")
    print("=" * 60)

if __name__ == "__main__":
    main()
