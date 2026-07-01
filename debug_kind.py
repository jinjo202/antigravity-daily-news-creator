"""KIND ETF 공시 페이지 구조를 Selenium으로 분석합니다."""

import io
import sys
import time
import json

if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding != "utf-8":
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

options = Options()
options.add_argument("--headless=new")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--window-size=1400,900")
options.add_argument("--disable-gpu")
options.add_argument("--lang=ko-KR")
# 네트워크 로그 캡처
options.set_capability("goog:loggingPrefs", {"performance": "ALL"})

driver = webdriver.Chrome(options=options)

# 1) ETF 공시 페이지 로드
url = "https://kind.krx.co.kr/disclosure/disclosurebystocktype.do?method=searchDisclosureByStockTypeEtf"
print(f"1) KIND ETF 공시 페이지: {url}")
driver.get(url)
time.sleep(5)

driver.save_screenshot(r"c:\Users\infomax\OneDrive\dev\dart-mail-sender\debug_kind_etf.png")
print("   스크린샷: debug_kind_etf.png")

# 2) 페이지 구조 분석
print("\n2) 페이지 구조")

# 공시 목록 테이블 찾기
tables = driver.find_elements(By.TAG_NAME, "table")
print(f"   테이블 개수: {len(tables)}")

for i, table in enumerate(tables):
    rows = table.find_elements(By.TAG_NAME, "tr")
    if len(rows) > 1:
        print(f"\n   테이블[{i}] ({len(rows)}행):")
        for row in rows[:5]:
            cells = row.find_elements(By.CSS_SELECTOR, "td, th")
            texts = [c.text.strip()[:25] for c in cells]
            # 링크도 확인
            links = row.find_elements(By.TAG_NAME, "a")
            link_info = ""
            for link in links:
                href = link.get_attribute("href") or ""
                onclick = link.get_attribute("onclick") or ""
                if href or onclick:
                    link_info += f" [href={href[:60]}] [onclick={onclick[:60]}]"
            print(f"     {' | '.join(texts)}{link_info}")

# 3) '이익분배금신고' 키워드 확인
print("\n3) '이익분배금' 관련 항목 검색")
all_links = driver.find_elements(By.TAG_NAME, "a")
for link in all_links:
    text = link.text.strip()
    if "이익" in text or "분배" in text or "배당" in text:
        href = link.get_attribute("href") or ""
        onclick = link.get_attribute("onclick") or ""
        print(f"   {text} | href={href[:80]} | onclick={onclick[:80]}")

# 4) 네트워크 요청 분석 (XHR)
print("\n4) 네트워크 요청 분석")
logs = driver.get_log("performance")
for log_entry in logs:
    try:
        msg = json.loads(log_entry["message"])
        method = msg.get("message", {}).get("method", "")
        if method == "Network.requestWillBeSent":
            params = msg["message"]["params"]
            req_url = params.get("request", {}).get("url", "")
            req_method = params.get("request", {}).get("method", "")
            if "kind" in req_url and ("disclosure" in req_url or "etf" in req_url.lower()):
                post_data = params.get("request", {}).get("postData", "")
                print(f"   {req_method} {req_url[:100]}")
                if post_data:
                    print(f"   POST data: {post_data[:200]}")
    except Exception:
        pass

# 5) JavaScript로 검색 함수 분석
print("\n5) JavaScript 함수 분석")
try:
    result = driver.execute_script("""
        var scripts = document.querySelectorAll('script');
        var funcs = [];
        scripts.forEach(function(s) {
            var text = s.textContent || '';
            if (text.indexOf('search') >= 0 || text.indexOf('disclosure') >= 0) {
                // 함수 정의 부분만 추출
                var matches = text.match(/function\\s+\\w+\\s*\\([^)]*\\)[^{]*\\{[^}]{0,200}/g);
                if (matches) {
                    matches.forEach(function(m) { funcs.push(m.substring(0, 150)); });
                }
            }
        });
        return funcs;
    """)
    for f in result[:10]:
        print(f"   {f}")
except Exception as e:
    print(f"   오류: {e}")

driver.quit()
print("\n완료!")
