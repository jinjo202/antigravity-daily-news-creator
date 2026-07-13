import os
import sys
from dotenv import load_dotenv


class AppConfig:
    """애플리케이션 설정을 관리하는 클래스"""

    def __init__(self):
        load_dotenv()

        self.dart_api_key = self._require("DART_API_KEY", "your_dart_api_key_here")
        self.poll_interval_minutes = int(os.getenv("POLL_INTERVAL_MINUTES", "5"))

        raw = os.getenv(
            "RECIPIENT_EMAILS",
            # 배당공시 중복 방지(2026-07-01): jinyoung22.jo/jin.jo202 는
            # dividends/kind_dividend_watch 가 전담하므로 폴백 기본값에서도 제외.
            "meejin.an@samsung.com,songyee.lee@samsung.com,"
            "eg222.ko@samsung.com,jiwon99.kwon@samsung.com,bokyu.kim@samsung.com,jeonghwan.lim@samsung.com",
        )
        self.recipient_emails = [e.strip() for e in raw.split(",") if e.strip()]

    @staticmethod
    def _require(key: str, placeholder: str | None = None) -> str:
        """필수 설정값을 로드하고, 누락 시 에러를 출력합니다."""
        value = os.getenv(key)
        if not value or (placeholder and value == placeholder):
            print(f"❌ 설정 오류: {key}가 설정되지 않았습니다.", file=sys.stderr)
            print("   .env.example 파일을 참고하여 .env 파일을 작성해주세요.", file=sys.stderr)
            sys.exit(1)
        return value

    def __str__(self) -> str:
        masked_key = self.dart_api_key[:4] + "********"
        recipients_str = ", ".join(self.recipient_emails)
        return (
            "\n"
            "╔══════════════════════════════════════════════╗\n"
            "║          📋 애플리케이션 설정 정보           ║\n"
            "╠══════════════════════════════════════════════╣\n"
            f"║ DART API Key : {masked_key}\n"
            f"║ 이메일 발송  : Selenium Gmail 자동화\n"
            f"║ 수신자       : {recipients_str}\n"
            f"║ 폴링 간격    : {self.poll_interval_minutes}분\n"
            "╚══════════════════════════════════════════════╝"
        )
