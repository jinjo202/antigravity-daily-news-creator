#!/usr/bin/env python3
"""통합 모니터링 & 이메일 알림 프로그램

1) DART 배당 공시 모니터링 (기존)
2) TrendForce 뉴스 모니터링 (신규)

사용법:
    python main.py                 # 배당 공시 모니터링 시작
    python main.py --setup         # Gmail 로그인 세션 설정 (최초 1회)
    python main.py --test          # DART API 연결 테스트
    python main.py --trendforce    # TrendForce 뉴스 모니터링 시작
    python main.py --trendforce-test  # TrendForce RSS 피드 테스트
"""

import argparse
import io
import sys

# Windows cp949 인코딩 문제 방지
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding != "utf-8":
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import os
class DualLogger:
    """터미널 출력과 파일 로그를 동시에 처리합니다."""
    def __init__(self, original_stream, log_file):
        self.original_stream = original_stream
        self.log_file = log_file
        self.encoding = getattr(original_stream, "encoding", "utf-8")
        
    def write(self, message):
        self.original_stream.write(message)
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(message)
        except Exception:
            pass
            
    def flush(self):
        self.original_stream.flush()

log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "monitor.log")
sys.stdout = DualLogger(sys.stdout, log_path)
sys.stderr = DualLogger(sys.stderr, log_path)

from config import AppConfig
from dart_api_client import DartApiClient
from disclosure_monitor import DisclosureMonitor
from email_sender import EmailSender
from browser_email_sender import BrowserEmailSender


BANNER = r"""

  ╔═══════════════════════════════════════════════════════╗
  ║                                                       ║
  ║   📊  통합 모니터링 시스템  📊                       ║
  ║                                                       ║
  ║   DART 배당 공시 + TrendForce 뉴스                    ║
  ║   v2.1.0  (Python + DART + TrendForce + Gmail)        ║
  ║                                                       ║
  ╚═══════════════════════════════════════════════════════╝

"""


def run_monitor(once: bool = False) -> None:
    """공시 모니터링을 시작합니다."""

    # 1. 설정 로드
    print("📂 설정을 로드합니다...")
    try:
        config = AppConfig()
    except SystemExit:
        raise
    except Exception as e:
        print(f"❌ 설정 로드 실패: {e}", file=sys.stderr)
        print("   .env.example 파일을 참고하여 .env 파일을 작성해주세요.", file=sys.stderr)
        sys.exit(1)

    print(config)

    # 2. DART API 클라이언트 초기화
    dart_api = DartApiClient(api_key=config.dart_api_key)
    try:
        dart_api.initialize()
    except Exception as e:
        print(f"❌ DART API 초기화 실패: {e}", file=sys.stderr)
        print("   API 키를 확인해주세요.", file=sys.stderr)
        dart_api.close()
        sys.exit(1)

    # 3. 이메일 발송기 초기화 (Selenium Gmail)
    email_sender = EmailSender(
        recipient_emails=config.recipient_emails,
        headless=True,
    )

    # 4. 공시 모니터 초기화 및 시작
    monitor = DisclosureMonitor(
        config=config,
        dart_api=dart_api,
        email_sender=email_sender,
    )
    monitor.initialize_watchlist_filter()

    try:
        if once:
            monitor.start_once()
        else:
            monitor.start()  # 블로킹 루프
    except KeyboardInterrupt:
        print()
        print("🛑 종료 신호를 받았습니다. 프로그램을 종료합니다...")
    finally:
        dart_api.close()
        print("⏹️  프로그램이 종료되었습니다.")


def run_test() -> None:
    """DART API 연결 및 감시 종목 매핑을 테스트합니다."""
    print("🧪 DART API 연결 테스트")
    print()

    config = AppConfig()
    print(config)

    dart_api = DartApiClient(api_key=config.dart_api_key)
    try:
        dart_api.initialize()
    except Exception as e:
        print(f"❌ DART API 초기화 실패: {e}", file=sys.stderr)
        dart_api.close()
        sys.exit(1)

    import watchlist_provider

    stock_codes = watchlist_provider.get_stock_codes()
    corp_codes = dart_api.get_corp_codes_for_stocks(stock_codes)
    print(f"\n🎯 감시 종목 매핑 결과: {len(corp_codes)}/{len(stock_codes)}개 성공")
    for sc in stock_codes:
        name = watchlist_provider.get_stock_name(sc)
        cc = dart_api.get_corp_code(sc)
        status = "✅" if cc else "⚠️"
        print(f"   {status} {name} ({sc}) → {cc or '매핑 실패'}")

    # 오늘의 주요사항보고 조회 테스트
    from datetime import datetime

    today = datetime.now().strftime("%Y%m%d")
    print(f"\n🔍 오늘({today}) 거래소공시(I) 조회 중...")  # 배당결정은 I (B 아님)
    disclosures = dart_api.fetch_all_disclosures(
        begin_date=today, end_date=today, pblntf_ty="I"
    )
    print(f"   총 {len(disclosures)}건 조회됨")

    # 배당 결정 공시 필터링
    dividend_keywords = [
        "현금ㆍ현물배당 결정", "현금·현물배당 결정",
        "현금ㆍ현물배당결정", "현금·현물배당결정",
    ]
    dividend_disclosures = [
        d for d in disclosures
        if any(kw in d.report_nm for kw in dividend_keywords)
    ]
    if dividend_disclosures:
        print(f"   📋 배당 결정 공시 {len(dividend_disclosures)}건 발견:")
        for d in dividend_disclosures:
            in_watchlist = d.corp_code in corp_codes
            mark = "🔔" if in_watchlist else "  "
            print(f"   {mark} {d.corp_name} ({d.stock_code}) - {d.report_nm}")
    else:
        print("   배당 결정 공시 없음")

    dart_api.close()
    print("\n✅ 테스트 완료!")


def run_trendforce(once: bool = False) -> None:
    """TrendForce 및 SemiAnalysis 뉴스 모니터링을 시작합니다."""
    import os
    from dotenv import load_dotenv
    from trendforce_monitor import TrendForceMonitor
    from semianalysis_monitor import SemiAnalysisMonitor

    load_dotenv()

    raw = os.getenv("TRENDFORCE_RECIPIENT_EMAILS", "")
    if raw.strip():
        recipients = [e.strip() for e in raw.split(",") if e.strip()]
    else:
        # 기본 수신자가 없으면 사용자에게 안내
        print("⚠️  TRENDFORCE_RECIPIENT_EMAILS 환경변수가 설정되지 않았습니다.")
        print("   .env 파일에 다음을 추가해주세요:")
        print('   TRENDFORCE_RECIPIENT_EMAILS=email1@example.com,email2@example.com')
        sys.exit(1)

    poll_interval = int(os.getenv("TRENDFORCE_POLL_MINUTES", "30"))
    send_hour = int(os.getenv("TRENDFORCE_SEND_HOUR", "8"))
    send_minute = int(os.getenv("TRENDFORCE_SEND_MINUTE", "0"))

    # PC 사용자명으로 실행 모드 자동 판별
    # ocarr (이 노트북) → 휴일만 / infomax (다른 PC) → 워킹데이만
    username = os.getenv("USERNAME", "").lower()
    if username == "ocarr":
        holiday_only = True
        print(f"🖥️  PC 감지: {username} (노트북) → 휴일 전용 모드")
    elif username == "infomax":
        holiday_only = False
        print(f"🖥️  PC 감지: {username} (데스크탑) → 워킹데이 전용 모드")
    else:
        holiday_only = os.getenv("TRENDFORCE_HOLIDAY_ONLY", "true").lower() in ("true", "1", "yes")
        print(f"🖥️  PC 감지: {username} (알 수 없음) → .env 설정 사용 (holiday_only={holiday_only})")

    tf_monitor = TrendForceMonitor(
        recipient_emails=recipients,
        send_hour=send_hour,
        send_minute=send_minute,
        headless=True,
        holiday_only=holiday_only,
    )
    
    sa_monitor = SemiAnalysisMonitor(
        recipient_emails=recipients,
        send_hour=send_hour,
        send_minute=send_minute,
        headless=True,
        holiday_only=holiday_only,
    )

    try:
        if once:
            # 1회 다이제스트 체크 및 발송
            tf_monitor._run_daily_digest()
            sa_monitor._run_daily_digest()
        else:
            import threading
            t_tf = threading.Thread(target=tf_monitor.start, daemon=True, name="TrendForce")
            t_sa = threading.Thread(target=sa_monitor.start, daemon=True, name="SemiAnalysis")
            t_tf.start()
            t_sa.start()
            
            while True:
                import time
                time.sleep(1)
    except KeyboardInterrupt:
        print()
        print("🛑 종료 신호를 받았습니다. 프로그램을 종료합니다...")
    if not once:
        print("⏹️  프로그램이 종료되었습니다.")


def run_trendforce_test() -> None:
    """TrendForce RSS 피드를 테스트합니다."""
    from trendforce_monitor import TrendForceMonitor

    monitor = TrendForceMonitor(
        recipient_emails=["test@test.com"],
    )
    monitor.test_fetch()


def run_all(once: bool = False) -> None:
    """DART 배당 공시와 TrendForce 뉴스를 동시에 모니터링합니다."""
    import threading
    import time
    from datetime import datetime

    if once:
        print("🚀 [System] 단회 통합 모니터링(DART + TrendForce)을 시작합니다...")
        try:
            run_monitor(once=True)
        except Exception as e:
            print(f"❌ DART 단회 실행 중 오류: {e}", file=sys.stderr)
        
        try:
            now = datetime.now()
            # GitHub Actions에서 돌 때는, 실행 시간대가 오전 8:00 ~ 8:59 사이일 때만 뉴스 발송
            if now.hour == 8:
                run_trendforce(once=True)
            else:
                print(f"   [News] 현재 시각({now.strftime('%H:%M')})은 뉴스 발송 시간(08:00~08:59)이 아니므로 뉴스는 스킵합니다.")
        except Exception as e:
            print(f"❌ TrendForce 단회 실행 중 오류: {e}", file=sys.stderr)
        return

    print("🚀 [System] 통합 모니터링(DART + TrendForce) 초기화를 시작합니다...")
    
    t_dart = threading.Thread(target=run_monitor, args=(False,), daemon=True, name="DART")
    t_tf = threading.Thread(target=run_trendforce, args=(False,), daemon=True, name="TrendForce")

    t_dart.start()
    # 두 모니터의 콘솔 출력이 섞이는 것을 방지하기 위해 2초 대기
    time.sleep(2)
    t_tf.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n🛑 [System] 종료 신호를 받았습니다. 프로그램을 종료합니다...")
        sys.exit(0)


def setup_gmail_login() -> None:
    """Gmail 로그인 세션을 설정합니다 (최초 1회)."""
    from email_sender import GMAIL_ADDRESS, GMAIL_PASSWORD

    sender = BrowserEmailSender(
        gmail_address=GMAIL_ADDRESS,
        gmail_password=GMAIL_PASSWORD,
        headless=False,
    )
    sender.setup_login()


def setup_stdout_logging(filename="app.log") -> None:
    import sys
    from datetime import datetime

    class Logger(object):
        def __init__(self, fn):
            self.terminal = sys.stdout
            self.log = open(fn, "a", encoding="utf-8", buffering=1)

        def write(self, message):
            self.terminal.write(message)
            self.log.write(message)

        def flush(self):
            self.terminal.flush()
            self.log.flush()

    class ErrorLogger(object):
        def __init__(self, fn):
            self.terminal = sys.stderr
            self.log = open(fn, "a", encoding="utf-8", buffering=1)

        def write(self, message):
            self.terminal.write(message)
            self.log.write(message)

        def flush(self):
            self.terminal.flush()
            self.log.flush()

    try:
        with open(filename, "a", encoding="utf-8") as f:
            f.write(f"\n\n=================== STARTUP: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===================\n")
    except Exception:
        pass

    sys.stdout = Logger(filename)
    sys.stderr = ErrorLogger(filename)


def main() -> None:
    setup_stdout_logging()
    parser = argparse.ArgumentParser(
        description="통합 모니터링 시스템 (DART 배당 공시 + TrendForce 뉴스)"
    )
    parser.add_argument(
        "--setup",
        action="store_true",
        help="Gmail 로그인 세션 설정 (최초 1회)",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="공시 모니터링 1회만 실행 후 종료 (GitHub Actions용)",
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="DART API 연결 테스트만 수행",
    )
    parser.add_argument(
        "--trendforce",
        action="store_true",
        help="TrendForce 뉴스 모니터링 시작",
    )
    parser.add_argument(
        "--trendforce-test",
        action="store_true",
        help="TrendForce RSS 피드 테스트 (이메일 발송 없음)",
    )
    args = parser.parse_args()

    print(BANNER)

    if args.setup:
        setup_gmail_login()
        return

    if args.test:
        run_test()
        return

    if args.trendforce:
        run_trendforce()
        return

    if args.trendforce_test:
        run_trendforce_test()
        return

    # 두 모니터링 동시 실행
    run_all(once=args.once)


if __name__ == "__main__":
    main()
