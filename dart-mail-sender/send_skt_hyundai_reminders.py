import io
import sys
import os
import time
import re
from datetime import datetime

# Enforce UTF-8 output encoding for Windows CP949 compatibility
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding != "utf-8":
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from config import AppConfig
from dart_api_client import DartApiClient, Disclosure
from email_sender import EmailSender

def parse_standard_date(rcept_no: str) -> str | None:
    """Selenium으로 DART 공시 원문을 읽어 배당기준일을 추출합니다."""
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By

    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")

    driver = None
    try:
        driver = webdriver.Chrome(options=options)
        main_url = f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}"
        driver.get(main_url)
        time.sleep(3)

        iframe = driver.find_element(By.ID, "ifrm")
        viewer_url = iframe.get_attribute("src")

        driver.get(viewer_url)
        time.sleep(3)

        text = driver.find_element(By.TAG_NAME, "body").text

        # 배당기준일 파싱 정규식
        date_patterns = [
            r"2026\s*년\s*(?:05|5|06|6|04|4)\s*월\s*\d+\s*일",
            r"2026\.0?[456]\.\d+",
            r"2026-0?[456]-\d+",
            r"2026/0?[456]/\d+"
        ]

        def normalize_date(raw_date: str) -> str:
            raw_date = raw_date.replace(" ", "")
            m = re.search(r"(\d{4})년(\d{1,2})월(\d{1,2})일", raw_date)
            if m:
                return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
            m = re.search(r"(\d{4})\.(\d{1,2})\.(\d{1,2})", raw_date)
            if m:
                return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
            m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", raw_date)
            if m:
                return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
            m = re.search(r"(\d{4})/(\d{1,2})/(\d{1,2})", raw_date)
            if m:
                return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
            return raw_date

        keywords = ["기준일", "폐쇄일"]
        lines = text.split("\n")
        for line in lines:
            if any(kw in line for kw in keywords):
                for pat in date_patterns:
                    match = re.search(pat, line)
                    if match:
                        return normalize_date(match.group(0))

        for match in re.finditer(r"(?:기준일|폐쇄일)", text):
            start = max(0, match.start() - 100)
            end = min(len(text), match.end() + 100)
            snippet = text[start:end]
            for pat in date_patterns:
                m = re.search(pat, snippet)
                if m:
                    return normalize_date(m.group(0))

    except Exception as e:
        print(f"      ⚠️ 배당기준일 파싱 중 오류: {e}")
    finally:
        if driver:
            driver.quit()
    return None

def main():
    print("=" * 60)
    print("📢 SK텔레콤 및 현대자동차 누락 배당기준일 리마인드 메일 발송")
    print("=" * 60)

    config = AppConfig()
    dart_api = DartApiClient(api_key=config.dart_api_key)
    dart_api.initialize()

    # 이메일 발송기 초기화
    email_sender = EmailSender(
        recipient_emails=config.recipient_emails,
        headless=True,
    )

    # 1. SK텔레콤 (017670) 배당결정공시 rcpNo = 20260427801018
    # 2. 현대자동차 (005380) 배당결정공시 rcpNo = 20260423800359
    targets = [
        {"name": "SK텔레콤", "rcpNo": "20260427801018"},
        {"name": "현대자동차", "rcpNo": "20260423800359"}
    ]

    for target in targets:
        name = target["name"]
        rcp_no = target["rcpNo"]
        print(f"\n🔍 {name} ({rcp_no}) 조회 및 기준일 분석 중...")

        # DART API를 통해 공시 정보 상세 획득
        url = "https://opendart.fss.or.kr/api/list.json"
        params = {
            "crtfc_key": config.dart_api_key,
            "corp_code": dart_api.get_corp_code("017670" if name == "SK텔레콤" else "005380"),
            "bgn_de": "20260401",
            "end_de": "20260501",
            "page_count": 100
        }
        
        import requests
        resp = requests.get(url, params=params)
        data = resp.json()
        
        target_disc = None
        if data.get("status") == "000":
            for item in data.get("list", []):
                if item.get("rcept_no") == rcp_no:
                    target_disc = Disclosure.from_dict(item)
                    break
        
        if not target_disc:
            print(f"❌ DART API에서 {name} 공시({rcp_no}) 조회 실패!")
            continue

        print(f"✅ 공시 발견: {target_disc.report_nm} (접수일자: {target_disc.rcept_dt})")
        
        # 기준일 파싱
        print("⏰ 배당기준일 파싱 중...")
        std_date = parse_standard_date(rcp_no)
        
        if not std_date:
            print("⚠️ 파싱 실패로 기본값 '2026-05-31' 사용")
            std_date = "2026-05-31"
        else:
            print(f"🎯 파싱 완료! 배당기준일: {std_date}")

        # 이메일 발송 실행!
        print(f"📧 {name} 배당기준일 리마인드 2차 이메일 발송 중...")
        success = email_sender.send_dividend_reminder(target_disc, std_date)
        if success:
            print(f"✅ {name} 이메일 발송 성공!")
        else:
            print(f"❌ {name} 이메일 발송 실패!")

    dart_api.close()
    print("\n🏁 모든 리마인드 발송 작업 완료!")

if __name__ == "__main__":
    main()
