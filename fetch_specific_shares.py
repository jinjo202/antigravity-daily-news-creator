import os
import sys
import requests
import re
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("DART_API_KEY")

targets = {
    "SK텔레콤": "00159023",
    "현대자동차": "00164742"
}

for name, corp_code in targets.items():
    print(f"\n🔍 Querying DART API for {name} ({corp_code})...")
    url = "https://opendart.fss.or.kr/api/list.json"
    params = {
        "crtfc_key": api_key,
        "corp_code": corp_code,
        "bgn_de": "20260101",
        "end_de": "20260601",
        "page_count": 100
    }
    
    resp = requests.get(url, params=params)
    data = resp.json()
    if data.get("status") == "000":
        found = False
        for item in data.get("list", []):
            report_nm = item.get("report_nm", "")
            if any(kw in report_nm for kw in ["배당", "주주명부", "폐쇄", "기준일"]):
                print(f"[{item.get('rcept_dt')}] {item.get('corp_name')} - {report_nm} (rcpNo: {item.get('rcept_no')})")
                found = True
        if not found:
            print("❌ No dividend or record date related disclosures found since 2026-01-01.")
    else:
        print(f"Error ({data.get('status')}): {data.get('message')}")
