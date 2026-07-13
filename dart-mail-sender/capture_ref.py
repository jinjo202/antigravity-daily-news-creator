"""모닝스타 배당 PDF를 Chrome으로 열어 스크린샷을 캡처합니다."""

import io
import sys
import time
import base64

if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

PDF_PATH = r"C:\Users\infomax\OneDrive\모닝스타\배당.pdf"
SCREENSHOT_PATH = r"C:\Users\infomax\OneDrive\dev\dart-mail-sender\morningstar_ref.png"

options = Options()
options.add_argument("--headless=new")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--window-size=1200,1600")
options.add_argument("--disable-gpu")

driver = webdriver.Chrome(options=options)

# PDF를 file:// 프로토콜로 열기
import os
file_url = "file:///" + os.path.abspath(PDF_PATH).replace("\\", "/")
print(f"Opening: {file_url}")
driver.get(file_url)
time.sleep(3)

# 스크린샷 저장
driver.save_screenshot(SCREENSHOT_PATH)
print(f"Screenshot saved: {SCREENSHOT_PATH}")

driver.quit()
print("Done!")
