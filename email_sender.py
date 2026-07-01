import os
import tempfile

from dart_api_client import Disclosure
from browser_email_sender import BrowserEmailSender
from pdf_generator import PdfGenerator


# Gmail 계정 설정
GMAIL_ADDRESS = "devbotsender8282@gmail.com"
GMAIL_PASSWORD = "lvjayqklnrkofjbj"


class EmailSender:
    """배당 공시 알림 이메일 발송 클래스

    Selenium + Chrome 브라우저를 사용하여 Gmail에서 직접 이메일을 발송합니다.
    DART 공시 원문 페이지를 그대로 PDF로 변환하여 첨부합니다.
    """

    def __init__(self, recipient_emails: list[str], headless: bool = True):
        self.recipient_emails = recipient_emails
        self.headless = headless

    def send_dividend_notification(self, disclosure: Disclosure) -> bool:
        """배당 공시 알림 이메일을 발송합니다 (DART 원문 PDF 첨부)."""
        subject = f"[배당공시] {disclosure.corp_name} - 현금ㆍ현물배당 결정"
        html_body = self._build_html_body(disclosure)

        # DART 공시 원문 페이지를 그대로 PDF로 저장
        pdf_path = None
        try:
            date_str = disclosure.rcept_dt
            pdf_filename = f"{disclosure.corp_name}_현금현물배당결정_{date_str}.pdf"
            pdf_path = os.path.join(tempfile.gettempdir(), pdf_filename)

            print(f"   📋 DART 공시 원문 PDF 생성 중...")
            if not PdfGenerator.generate_from_dart(
                rcept_no=disclosure.rcept_no,
                output_path=pdf_path,
                corp_name=disclosure.corp_name,
            ):
                print(f"   ⚠️ PDF 생성 실패, 이메일만 발송합니다")
                pdf_path = None

        except Exception as e:
            print(f"   ⚠️ PDF 생성 중 오류: {e}")
            pdf_path = None

        # 이메일 발송
        sender = BrowserEmailSender(
            gmail_address=GMAIL_ADDRESS,
            gmail_password=GMAIL_PASSWORD,
            headless=self.headless,
        )
        success = sender.send_email(
            self.recipient_emails, subject, html_body,
            attachment_path=pdf_path,
        )

        # 임시 PDF 파일 정리
        if pdf_path and os.path.exists(pdf_path):
            try:
                os.remove(pdf_path)
            except OSError:
                pass

        return success

    # ── HTML 이메일 본문 ──────────────────────────────────────

    @staticmethod
    def _build_html_body(d: Disclosure) -> str:
        formatted_date = EmailSender._format_date(d.rcept_dt)
        rm_display = d.rm if d.rm else "-"
        return f"""\
<div style="font-family:'Apple SD Gothic Neo','Malgun Gothic',sans-serif;max-width:600px;margin:0 auto;background:#fff;border-radius:12px;box-shadow:0 2px 8px rgba(0,0,0,0.1);overflow:hidden">
  <div style="background:linear-gradient(135deg,#1a237e,#283593);color:#fff;padding:24px 32px">
    <h1 style="margin:0;font-size:20px;font-weight:600">📢 현금ㆍ현물배당 결정 공시</h1>
    <div style="display:inline-block;background:rgba(255,255,255,0.2);padding:4px 12px;border-radius:20px;font-size:12px;margin-top:8px">배당 공시 알림</div>
  </div>
  <div style="padding:32px">
    <p style="color:#495057;font-size:15px">
      감시 대상 종목에서 새로운 배당 결정 공시가 접수되었습니다.
    </p>
    <table style="width:100%;border-collapse:collapse;margin:16px 0">
      <tr><th style="text-align:left;padding:12px 16px;background:#f8f9fa;color:#495057;font-weight:600;font-size:13px;border-bottom:1px solid #e9ecef;width:120px">기업명</th><td style="padding:12px 16px;color:#212529;font-size:14px;border-bottom:1px solid #e9ecef"><strong>{d.corp_name}</strong></td></tr>
      <tr><th style="text-align:left;padding:12px 16px;background:#f8f9fa;color:#495057;font-weight:600;font-size:13px;border-bottom:1px solid #e9ecef;width:120px">종목코드</th><td style="padding:12px 16px;color:#212529;font-size:14px;border-bottom:1px solid #e9ecef">{d.stock_code}</td></tr>
      <tr><th style="text-align:left;padding:12px 16px;background:#f8f9fa;color:#495057;font-weight:600;font-size:13px;border-bottom:1px solid #e9ecef;width:120px">보고서명</th><td style="padding:12px 16px;color:#212529;font-size:14px;border-bottom:1px solid #e9ecef">{d.report_nm}</td></tr>
      <tr><th style="text-align:left;padding:12px 16px;background:#f8f9fa;color:#495057;font-weight:600;font-size:13px;border-bottom:1px solid #e9ecef;width:120px">접수일자</th><td style="padding:12px 16px;color:#212529;font-size:14px;border-bottom:1px solid #e9ecef">{formatted_date}</td></tr>
      <tr><th style="text-align:left;padding:12px 16px;background:#f8f9fa;color:#495057;font-weight:600;font-size:13px;border-bottom:1px solid #e9ecef;width:120px">비고</th><td style="padding:12px 16px;color:#212529;font-size:14px;border-bottom:1px solid #e9ecef">{rm_display}</td></tr>
    </table>
    <a href="{d.dart_url}" style="display:inline-block;background:#1a237e;color:#fff!important;text-decoration:none;padding:12px 24px;border-radius:8px;font-size:14px;font-weight:600;margin-top:16px">
      📄 DART에서 공시 원문 보기
    </a>
    <p style="color:#868e96;font-size:12px;margin-top:16px">
      📎 상세 배당 결정 내용은 첨부된 PDF 파일을 참고해주세요.
    </p>
  </div>
  <div style="padding:16px 32px;background:#f8f9fa;font-size:12px;color:#868e96;text-align:center">
    이 메일은 배당 공시 모니터링 시스템에서 자동 발송되었습니다.
  </div>
</div>"""

    @staticmethod
    def _format_date(date: str) -> str:
        """날짜 포맷팅 (YYYYMMDD → YYYY-MM-DD)"""
        if len(date) == 8:
            return f"{date[:4]}-{date[4:6]}-{date[6:8]}"
        return date

    def send_etf_notification(self, etf_name: str, stock_code: str, report_nm: str, date_str: str, acptno: str) -> bool:
        """KIND ETF 공시 알림 이메일을 발송합니다 (KIND 원문 PDF 첨부)."""
        subject = f"[ETF분배금] {etf_name} - {report_nm}"
        html_body = self._build_etf_html_body(etf_name, stock_code, report_nm, date_str, acptno)

        pdf_path = None
        try:
            # 파일명에 한글/특수문자 매핑 고려
            cleaned_date = date_str.split()[0].replace("-", "") # "2026-05-22 13:20" -> "20260522"
            pdf_filename = f"{etf_name}_이익분배금신고_{cleaned_date}.pdf"
            pdf_filename = pdf_filename.replace("/", "_").replace("\\", "_")
            pdf_path = os.path.join(tempfile.gettempdir(), pdf_filename)

            print(f"   📋 KIND 공시 원문 PDF 생성 중...")
            if not PdfGenerator.generate_from_kind(
                acptno=acptno,
                output_path=pdf_path,
                corp_name=etf_name,
            ):
                print(f"   ⚠️ PDF 생성 실패, 이메일만 발송합니다")
                pdf_path = None

        except Exception as e:
            print(f"   ⚠️ PDF 생성 중 오류: {e}")
            pdf_path = None

        # 이메일 발송
        sender = BrowserEmailSender(
            gmail_address=GMAIL_ADDRESS,
            gmail_password=GMAIL_PASSWORD,
            headless=self.headless,
        )
        success = sender.send_email(
            self.recipient_emails, subject, html_body,
            attachment_path=pdf_path,
        )

        # 임시 PDF 파일 정리
        if pdf_path and os.path.exists(pdf_path):
            try:
                os.remove(pdf_path)
            except OSError:
                pass

        return success

    @staticmethod
    def _build_etf_html_body(etf_name: str, stock_code: str, report_nm: str, date_str: str, acptno: str) -> str:
        kind_url = f"https://kind.krx.co.kr/common/disclsviewer.do?method=search&acptno={acptno}"
        return f"""\
<div style="font-family:'Apple SD Gothic Neo','Malgun Gothic',sans-serif;max-width:600px;margin:0 auto;background:#fff;border-radius:12px;box-shadow:0 2px 8px rgba(0,0,0,0.1);overflow:hidden">
  <div style="background:linear-gradient(135deg,#006064,#00838f);color:#fff;padding:24px 32px">
    <h1 style="margin:0;font-size:20px;font-weight:600">📢 ETF 이익분배금신고 공시</h1>
    <div style="display:inline-block;background:rgba(255,255,255,0.2);padding:4px 12px;border-radius:20px;font-size:12px;margin-top:8px">ETF 분배금 알림</div>
  </div>
  <div style="padding:32px">
    <p style="color:#495057;font-size:15px">
      감시 대상 ETF 종목에서 새로운 이익분배금신고 공시가 접수되었습니다.
    </p>
    <table style="width:100%;border-collapse:collapse;margin:16px 0">
      <tr><th style="text-align:left;padding:12px 16px;background:#f8f9fa;color:#495057;font-weight:600;font-size:13px;border-bottom:1px solid #e9ecef;width:120px">종목명</th><td style="padding:12px 16px;color:#212529;font-size:14px;border-bottom:1px solid #e9ecef"><strong>{etf_name}</strong></td></tr>
      <tr><th style="text-align:left;padding:12px 16px;background:#f8f9fa;color:#495057;font-weight:600;font-size:13px;border-bottom:1px solid #e9ecef;width:120px">종목코드</th><td style="padding:12px 16px;color:#212529;font-size:14px;border-bottom:1px solid #e9ecef">{stock_code}</td></tr>
      <tr><th style="text-align:left;padding:12px 16px;background:#f8f9fa;color:#495057;font-weight:600;font-size:13px;border-bottom:1px solid #e9ecef;width:120px">보고서명</th><td style="padding:12px 16px;color:#212529;font-size:14px;border-bottom:1px solid #e9ecef">{report_nm}</td></tr>
      <tr><th style="text-align:left;padding:12px 16px;background:#f8f9fa;color:#495057;font-weight:600;font-size:13px;border-bottom:1px solid #e9ecef;width:120px">공시시간</th><td style="padding:12px 16px;color:#212529;font-size:14px;border-bottom:1px solid #e9ecef">{date_str}</td></tr>
    </table>
    <a href="{kind_url}" style="display:inline-block;background:#006064;color:#fff!important;text-decoration:none;padding:12px 24px;border-radius:8px;font-size:14px;font-weight:600;margin-top:16px">
      📄 KIND에서 공시 원문 보기
    </a>
    <p style="color:#868e96;font-size:12px;margin-top:16px">
      📎 상세 분배금 지급 내용은 첨부된 PDF 파일을 참고해주세요.
    </p>
  </div>
  <div style="padding:16px 32px;background:#f8f9fa;font-size:12px;color:#868e96;text-align:center">
    이 메일은 배당 공시 모니터링 시스템에서 자동 발송되었습니다.
  </div>
</div>"""

    def send_dividend_reminder(self, disclosure: Disclosure, standard_date: str) -> bool:
        """배당기준일 당일 리마인드 알림 메일을 발송합니다."""
        subject = f"[배당기준일 리마인드] 오늘은 {disclosure.corp_name}의 배당/주주명부폐쇄 기준일입니다."
        html_body = self._build_dividend_reminder_html(disclosure, standard_date)

        pdf_path = None
        try:
            date_str = disclosure.rcept_dt
            pdf_filename = f"[리마인드]{disclosure.corp_name}_현금현물배당결정_{date_str}.pdf"
            pdf_path = os.path.join(tempfile.gettempdir(), pdf_filename)

            print(f"   📋 [리마인드] DART 공시 원문 PDF 생성 중...")
            if not PdfGenerator.generate_from_dart(
                rcept_no=disclosure.rcept_no,
                output_path=pdf_path,
                corp_name=disclosure.corp_name,
            ):
                pdf_path = None
        except Exception as e:
            print(f"   ⚠️ [리마인드] PDF 생성 중 오류: {e}")
            pdf_path = None

        sender = BrowserEmailSender(
            gmail_address=GMAIL_ADDRESS,
            gmail_password=GMAIL_PASSWORD,
            headless=self.headless,
        )
        success = sender.send_email(
            self.recipient_emails, subject, html_body,
            attachment_path=pdf_path,
        )

        if pdf_path and os.path.exists(pdf_path):
            try:
                os.remove(pdf_path)
            except OSError:
                pass
        return success

    @staticmethod
    def _build_dividend_reminder_html(d: Disclosure, standard_date: str) -> str:
        formatted_date = EmailSender._format_date(d.rcept_dt)
        rm_display = d.rm if d.rm else "-"
        return f"""\
<div style="font-family:'Apple SD Gothic Neo','Malgun Gothic',sans-serif;max-width:600px;margin:0 auto;background:#fff;border-radius:12px;box-shadow:0 2px 8px rgba(0,0,0,0.1);overflow:hidden">
  <div style="background:linear-gradient(135deg,#e65100,#f57c00);color:#fff;padding:24px 32px">
    <h1 style="margin:0;font-size:20px;font-weight:600">⏰ 오늘은 배당기준일(주주명부폐쇄일)입니다</h1>
    <div style="display:inline-block;background:rgba(255,255,255,0.2);padding:4px 12px;border-radius:20px;font-size:12px;margin-top:8px">2차 리마인드 알림</div>
  </div>
  <div style="padding:32px">
    <div style="background:#fff3e0;border-left:4px solid #e65100;padding:16px;border-radius:4px;margin-bottom:24px">
      <p style="margin:0;color:#e65100;font-size:14px;font-weight:600;line-height:1.6">
        ⚠️ [필독] 오늘은 해당 종목의 배당을 받기 위한 주주명부폐쇄(기준일) 당일입니다.<br/>
        배당 권리 확정 여부를 다시 한번 점검하시기 바랍니다.
      </p>
    </div>
    <table style="width:100%;border-collapse:collapse;margin:16px 0">
      <tr><th style="text-align:left;padding:12px 16px;background:#f8f9fa;color:#495057;font-weight:600;font-size:13px;border-bottom:1px solid #e9ecef;width:120px">기업명</th><td style="padding:12px 16px;color:#212529;font-size:14px;border-bottom:1px solid #e9ecef"><strong>{d.corp_name}</strong></td></tr>
      <tr><th style="text-align:left;padding:12px 16px;background:#f8f9fa;color:#495057;font-weight:600;font-size:13px;border-bottom:1px solid #e9ecef;width:120px">배당기준일</th><td style="padding:12px 16px;color:#d84315;font-size:14px;font-weight:600;border-bottom:1px solid #e9ecef">{standard_date} (오늘)</td></tr>
      <tr><th style="text-align:left;padding:12px 16px;background:#f8f9fa;color:#495057;font-weight:600;font-size:13px;border-bottom:1px solid #e9ecef;width:120px">보고서명</th><td style="padding:12px 16px;color:#212529;font-size:14px;border-bottom:1px solid #e9ecef">{d.report_nm}</td></tr>
      <tr><th style="text-align:left;padding:12px 16px;background:#f8f9fa;color:#495057;font-weight:600;font-size:13px;border-bottom:1px solid #e9ecef;width:120px">최초공시일</th><td style="padding:12px 16px;color:#212529;font-size:14px;border-bottom:1px solid #e9ecef">{formatted_date}</td></tr>
      <tr><th style="text-align:left;padding:12px 16px;background:#f8f9fa;color:#495057;font-weight:600;font-size:13px;border-bottom:1px solid #e9ecef;width:120px">비고</th><td style="padding:12px 16px;color:#212529;font-size:14px;border-bottom:1px solid #e9ecef">{rm_display}</td></tr>
    </table>
    <a href="{d.dart_url}" style="display:inline-block;background:#e65100;color:#fff!important;text-decoration:none;padding:12px 24px;border-radius:8px;font-size:14px;font-weight:600;margin-top:16px">
      📄 DART에서 공시 원문 보기
    </a>
  </div>
  <div style="padding:16px 32px;background:#f8f9fa;font-size:12px;color:#868e96;text-align:center">
    이 메일은 배당 공시 모니터링 시스템에서 자동 발송되었습니다.
  </div>
</div>"""

    def send_etf_reminder(self, etf_name: str, stock_code: str, report_nm: str, date_str: str, acptno: str, standard_date: str) -> bool:
        """KIND ETF 이익분배락/기준일 당일 리마인드 알림 메일을 발송합니다."""
        subject = f"[ETF분배일 리마인드] 오늘은 {etf_name}의 분배락/이익분배 기준일입니다."
        html_body = self._build_etf_reminder_html(etf_name, stock_code, report_nm, date_str, acptno, standard_date)

        pdf_path = None
        try:
            cleaned_date = date_str.split()[0].replace("-", "")
            pdf_filename = f"[리마인드]{etf_name}_이익분배금신고_{cleaned_date}.pdf"
            pdf_filename = pdf_filename.replace("/", "_").replace("\\", "_")
            pdf_path = os.path.join(tempfile.gettempdir(), pdf_filename)

            print(f"   📋 [리마인드] KIND 공시 원문 PDF 생성 중...")
            if not PdfGenerator.generate_from_kind(
                acptno=acptno,
                output_path=pdf_path,
                corp_name=etf_name,
            ):
                pdf_path = None
        except Exception as e:
            print(f"   ⚠️ [리마인드] PDF 생성 중 오류: {e}")
            pdf_path = None

        sender = BrowserEmailSender(
            gmail_address=GMAIL_ADDRESS,
            gmail_password=GMAIL_PASSWORD,
            headless=self.headless,
        )
        success = sender.send_email(
            self.recipient_emails, subject, html_body,
            attachment_path=pdf_path,
        )

        if pdf_path and os.path.exists(pdf_path):
            try:
                os.remove(pdf_path)
            except OSError:
                pass
        return success

    @staticmethod
    def _build_etf_reminder_html(etf_name: str, stock_code: str, report_nm: str, date_str: str, acptno: str, standard_date: str) -> str:
        kind_url = f"https://kind.krx.co.kr/common/disclsviewer.do?method=search&acptno={acptno}"
        return f"""\
<div style="font-family:'Apple SD Gothic Neo','Malgun Gothic',sans-serif;max-width:600px;margin:0 auto;background:#fff;border-radius:12px;box-shadow:0 2px 8px rgba(0,0,0,0.1);overflow:hidden">
  <div style="background:linear-gradient(135deg,#311b92,#673ab7);color:#fff;padding:24px 32px">
    <h1 style="margin:0;font-size:20px;font-weight:600">⏰ 오늘은 ETF 이익분배 기준일(분배락일)입니다</h1>
    <div style="display:inline-block;background:rgba(255,255,255,0.2);padding:4px 12px;border-radius:20px;font-size:12px;margin-top:8px">2차 리마인드 알림</div>
  </div>
  <div style="padding:32px">
    <div style="background:#ede7f6;border-left:4px solid #311b92;padding:16px;border-radius:4px;margin-bottom:24px">
      <p style="margin:0;color:#311b92;font-size:14px;font-weight:600;line-height:1.6">
        ⚠️ [필독] 오늘은 해당 ETF의 분배금을 받기 위한 이익분배 기준일(분배락일) 당일입니다.<br/>
        분배 권리 확정 여부를 다시 한번 확인하시기 바랍니다.
      </p>
    </div>
    <table style="width:100%;border-collapse:collapse;margin:16px 0">
      <tr><th style="text-align:left;padding:12px 16px;background:#f8f9fa;color:#495057;font-weight:600;font-size:13px;border-bottom:1px solid #e9ecef;width:120px">종목명</th><td style="padding:12px 16px;color:#212529;font-size:14px;border-bottom:1px solid #e9ecef"><strong>{etf_name}</strong></td></tr>
      <tr><th style="text-align:left;padding:12px 16px;background:#f8f9fa;color:#495057;font-weight:600;font-size:13px;border-bottom:1px solid #e9ecef;width:120px">분배기준일</th><td style="padding:12px 16px;color:#311b92;font-size:14px;font-weight:600;border-bottom:1px solid #e9ecef">{standard_date} (오늘)</td></tr>
      <tr><th style="text-align:left;padding:12px 16px;background:#f8f9fa;color:#495057;font-weight:600;font-size:13px;border-bottom:1px solid #e9ecef;width:120px">보고서명</th><td style="padding:12px 16px;color:#212529;font-size:14px;border-bottom:1px solid #e9ecef">{report_nm}</td></tr>
      <tr><th style="text-align:left;padding:12px 16px;background:#f8f9fa;color:#495057;font-weight:600;font-size:13px;border-bottom:1px solid #e9ecef;width:120px">최초공시일</th><td style="padding:12px 16px;color:#212529;font-size:14px;border-bottom:1px solid #e9ecef">{date_str}</td></tr>
    </table>
    <a href="{kind_url}" style="display:inline-block;background:#311b92;color:#fff!important;text-decoration:none;padding:12px 24px;border-radius:8px;font-size:14px;font-weight:600;margin-top:16px">
      📄 KIND에서 공시 원문 보기
    </a>
  </div>
  <div style="padding:16px 32px;background:#f8f9fa;font-size:12px;color:#868e96;text-align:center">
    이 메일은 배당 공시 모니터링 시스템에서 자동 발송되었습니다.
  </div>
</div>"""


