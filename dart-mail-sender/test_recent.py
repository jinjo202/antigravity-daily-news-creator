"""감시 종목별로 최근 배당 공시를 조회하고 이메일 발송 테스트를 합니다."""

import io
import sys
import time

if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding != "utf-8":
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import requests
from datetime import datetime, timedelta
from config import AppConfig
from dart_api_client import DartApiClient, Disclosure
from email_sender import EmailSender
import watchlist_provider

DIVIDEND_KEYWORDS = [
    "현금ㆍ현물배당", "현금·현물배당", "현금.현물배당",
    "배당결정", "배당 결정",
]

config = AppConfig()
dart_api = DartApiClient(api_key=config.dart_api_key)
dart_api.initialize()

stock_codes = watchlist_provider.get_stock_codes()

# 최근 90일
end_date = datetime.now().strftime("%Y%m%d")
begin_date = (datetime.now() - timedelta(days=90)).strftime("%Y%m%d")

print(f"\n🔍 감시 종목별 최근 배당 공시 조회 ({begin_date} ~ {end_date})")
print("=" * 60)

all_dividend_hits = []

for sc in stock_codes:
    name = watchlist_provider.get_stock_name(sc)
    cc = dart_api.get_corp_code(sc)
    if not cc:
        print(f"   ⚠️ {name} ({sc}) - DART 매핑 실패, 건너뜀")
        continue

    # corp_code별 개별 조회 (DART API는 corp_code 파라미터를 지원)
    params = {
        "crtfc_key": config.dart_api_key,
        "corp_code": cc,
        "bgn_de": begin_date,
        "end_de": end_date,
        "page_count": 100,
    }
    resp = requests.get("https://opendart.fss.or.kr/api/list.json", params=params)
    data = resp.json()

    if data.get("status") == "013":  # 데이터 없음
        print(f"   {name} ({sc}) - 공시 없음")
        time.sleep(0.1)
        continue

    if data.get("status") != "000":
        print(f"   ❌ {name} ({sc}) - API 오류: {data.get('message')}")
        time.sleep(0.1)
        continue

    disclosures = data.get("list", [])
    # 배당 관련만 필터링
    dividend_items = [
        d for d in disclosures
        if any(kw in d.get("report_nm", "") for kw in DIVIDEND_KEYWORDS)
    ]

    if dividend_items:
        print(f"   🔔 {name} ({sc}) - 배당 공시 {len(dividend_items)}건:")
        for item in dividend_items:
            print(f"      [{item['rcept_dt']}] {item['report_nm']}")
            disc = Disclosure.from_dict(item)
            all_dividend_hits.append(disc)
    else:
        total = len(disclosures)
        print(f"   {name} ({sc}) - 공시 {total}건 (배당 관련 없음)")

    time.sleep(0.1)  # rate limiting

print()
print("=" * 60)
print(f"총 감시 종목 배당 공시: {len(all_dividend_hits)}건")

if all_dividend_hits:
    print("\n📋 발견된 배당 공시:")
    for d in all_dividend_hits:
        print(f"   [{d.rcept_dt}] {d.corp_name} ({d.stock_code}) - {d.report_nm}")

    # 가장 최근 1건으로 이메일 테스트
    latest = all_dividend_hits[0]
    print(f"\n📧 이메일 발송 테스트: {latest.corp_name} - {latest.report_nm}")
    email_sender = EmailSender(
        recipient_emails=config.recipient_emails,
        headless=True,
    )
    success = email_sender.send_dividend_notification(latest)
    print(f"{'✅ 발송 성공!' if success else '❌ 발송 실패'}")
else:
    print("감시 종목의 최근 90일간 배당 공시가 없습니다.")

dart_api.close()
print("\n✅ 완료!")
