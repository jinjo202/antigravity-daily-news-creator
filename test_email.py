"""KT 배당 공시 - DART 원문 PDF 첨부 이메일 발송 테스트"""

import io
import sys

if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding != "utf-8":
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from dart_api_client import Disclosure
from email_sender import EmailSender

# KT 배당 공시 (실제 DART 데이터)
disc = Disclosure(
    corp_code="00190321",
    corp_name="케이티",
    stock_code="030200",
    corp_cls="Y",
    report_nm="현금ㆍ현물배당결정",
    rcept_no="20260512800359",
    flr_nm="케이티",
    rcept_dt="20260512",
    rm="",
)

print(f"📧 DART 원문 PDF 첨부 이메일 발송 테스트")
print(f"   종목: {disc.corp_name} ({disc.stock_code})")
print(f"   접수번호: {disc.rcept_no}")
print(f"   수신자: jin.jo202@gmail.com")
print()

email_sender = EmailSender(
    recipient_emails=["jin.jo202@gmail.com"],
    headless=True,
)
success = email_sender.send_dividend_notification(disc)
print(f"\n{'🎉 성공!' if success else '❌ 실패'}")
