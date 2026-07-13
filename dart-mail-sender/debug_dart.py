"""DART 공시 원문 viewer 페이지를 직접 열어 PDF로 저장합니다."""

import io
import sys
import time
import base64
import re

if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding != "utf-8":
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

RCEPT_NO = "20260512800359"  # KT 현금ㆍ현물배당결정
OUTPUT_PDF = r"c:\Users\infomax\OneDrive\dev\dart-mail-sender\test_kt_direct.pdf"
OUTPUT_PNG = r"c:\Users\infomax\OneDrive\dev\dart-mail-sender\test_kt_direct.png"

options = Options()
options.add_argument("--headless=new")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--window-size=900,1200")
options.add_argument("--disable-gpu")
options.add_argument("--lang=ko-KR")

driver = webdriver.Chrome(options=options)

# 1) 메인 페이지에서 iframe src 추출
main_url = f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={RCEPT_NO}"
print(f"1) 메인 페이지 로드: {main_url}")
driver.get(main_url)
time.sleep(3)

iframe = driver.find_element(By.ID, "ifrm")
viewer_url = iframe.get_attribute("src")
print(f"   viewer URL: {viewer_url}")

# 2) viewer 페이지 직접 접근
print(f"\n2) viewer 페이지 직접 접근")
driver.get(viewer_url)
time.sleep(3)

# 스크린샷
driver.save_screenshot(OUTPUT_PNG)
print(f"   스크린샷: {OUTPUT_PNG}")

# 페이지 전체 높이 확인
total_height = driver.execute_script("return document.body.scrollHeight")
print(f"   페이지 높이: {total_height}px")

# 3) 페이지 타이틀 추가를 위한 corp_name 추출
page_text = driver.find_element(By.TAG_NAME, "body").text[:200]
print(f"   본문 시작: {page_text[:100]}")

# 4) PDF로 저장 (Page.printToPDF)
print(f"\n3) PDF 생성 중...")
pdf_data = driver.execute_cdp_cmd("Page.printToPDF", {
    "printBackground": True,
    "preferCSSPageSize": False,
    "marginTop": 0.4,
    "marginBottom": 0.4,
    "marginLeft": 0.4,
    "marginRight": 0.4,
    "paperWidth": 8.27,   # A4
    "paperHeight": 11.69,  # A4
    "scale": 0.85,
})

pdf_bytes = base64.b64decode(pdf_data["data"])
with open(OUTPUT_PDF, "wb") as f:
    f.write(pdf_bytes)
print(f"   PDF 저장 완료: {OUTPUT_PDF} ({len(pdf_bytes):,} bytes)")

driver.quit()
print("\n완료!")
