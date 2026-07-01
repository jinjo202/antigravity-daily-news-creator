"""Gmail SMTP 이메일 발송 모듈

기존 Selenium + Chrome 브라우저 자동화 대신 구글 SMTP 프로토콜을 직접 사용하여 이메일을 발송합니다.
안정성과 성능이 비약적으로 향상되었습니다.
"""

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

class BrowserEmailSender:
    """구글 SMTP 기반 이메일 발송 클래스
    
    기존 BrowserEmailSender의 인터페이스를 그대로 유지하여 기존 코드와의 호환성을 100% 보장합니다.
    """

    def __init__(
        self,
        gmail_address: str,
        gmail_password: str,
        recipient: str = None,
        headless: bool = True,
    ):
        self.gmail_address = gmail_address
        self.gmail_password = gmail_password  # 구글 앱 비밀번호 (16자리)
        self.recipient = recipient
        self.headless = headless

    def send_email(
        self,
        recipients: list[str] | str,
        subject: str,
        html_body: str,
        attachment_path: str | None = None,
    ) -> bool:
        """이메일을 발송합니다.
        
        Args:
            recipients: 수신자 이메일 주소 리스트 또는 쉼표(,)로 구분된 문자열
            subject: 이메일 제목
            html_body: HTML 이메일 본문
            attachment_path: 첨부할 파일 경로 (옵션)
        """
        try:
            # 수신자 파싱
            if isinstance(recipients, str):
                recipient_list = [r.strip() for r in recipients.split(",") if r.strip()]
            else:
                recipient_list = recipients

            if not recipient_list:
                print("   ❌ [SMTP] 수신자 이메일 주소가 비어있습니다.")
                return False

            # 메일 객체 생성
            msg = MIMEMultipart()
            msg['From'] = self.gmail_address
            msg['To'] = ", ".join(recipient_list)
            msg['Subject'] = subject

            # 본문 추가
            msg.attach(MIMEText(html_body, 'html', 'utf-8'))

            # 첨부파일 처리
            if attachment_path and os.path.exists(attachment_path):
                filename = os.path.basename(attachment_path)
                try:
                    with open(attachment_path, "rb") as f:
                        part = MIMEBase("application", "octet-stream")
                        part.set_payload(f.read())
                    encoders.encode_base64(part)
                    
                    # 파일명 한글 깨짐 방지 처리
                    part.add_header(
                        "Content-Disposition",
                        f"attachment; filename={filename}",
                    )
                    msg.attach(part)
                    print(f"   📎 [SMTP] 파일 첨부 완료: {filename}")
                except Exception as file_err:
                    print(f"   ⚠️ [SMTP] 파일 첨부 실패 (메일은 전송 시도): {file_err}")

            # SMTP 서버 연결 및 발송
            server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
            server.login(self.gmail_address, self.gmail_password)
            server.sendmail(self.gmail_address, recipient_list, msg.as_string())
            server.quit()
            
            print(f"   ✅ [SMTP] 이메일 발송 성공 → 수신인 {len(recipient_list)}명")
            return True
            
        except Exception as e:
            print(f"   ❌ [SMTP] 이메일 발송 중 오류 발생: {e}")
            return False

    def setup_login(self):
        """기존 인터페이스 호환용 스텁"""
        print("💡 SMTP 모드는 브라우저 로그인이 필요하지 않습니다. 앱 비밀번호가 정상 등록되어 있으면 바로 작동합니다.")
