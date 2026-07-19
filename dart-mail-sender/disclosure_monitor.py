import sys
import time
from datetime import datetime, timedelta
import re
import requests
from bs4 import BeautifulSoup

from config import AppConfig
from dart_api_client import DartApiClient, Disclosure
from email_sender import EmailSender
import watchlist_provider


class DisclosureMonitor:
    """공시 모니터링을 담당하는 클래스

    주기적으로 DART API를 호출하여 감시 대상 종목의
    "현금ㆍ현물배당 결정" 공시를 감지하고 이메일을 발송합니다.
    """

    # 배당 관련 키워드 (다양한 유니코드 중점 표기 대응)
    DIVIDEND_KEYWORDS: list[str] = [
        "현금ㆍ현물배당 결정",
        "현금·현물배당 결정",
        "현금ㆍ현물배당결정",
        "현금·현물배당결정",
        "현금.현물배당 결정",
        "현금.현물배당결정",
        "주주명부폐쇄",
    ]

    def __init__(
        self,
        config: AppConfig,
        dart_api: DartApiClient,
        email_sender: EmailSender,
    ):
        self.config = config
        self.dart_api = dart_api
        self.email_sender = email_sender

        # 이미 처리한 공시 접수번호 (중복 알림 방지)
        import os
        current_dir = os.path.dirname(os.path.abspath(__file__))
        self.history_file = os.path.join(current_dir, "processed_disclosures.txt")
        self._processed: set[str] = set()
        self._load_processed()

        # 예약 리마인드 목록 설정
        self.reminders_file = os.path.join(current_dir, "pending_reminders.json")
        self._reminders = {}
        self._load_reminders()
        self._last_reminder_run_date = None

        # 감시 대상 종목의 corp_code 세트
        self._watchlist_corp_codes: set[str] = set()

    def _load_processed(self) -> None:
        """파일에서 이미 처리된 공시 접수번호 목록을 로드합니다."""
        import os
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            self._processed.add(line)
                print(f"💾 공시 처리 이력 로드 완료: {len(self._processed)}개 로드됨 ({self.history_file})")
            except Exception as e:
                print(f"⚠️ 공시 처리 이력을 읽는 중 오류 발생: {e}", file=sys.stderr)
        else:
            print("💾 기존 공시 처리 이력 파일이 없습니다. 새로 생성합니다.")

    def _save_processed(self, rcept_no: str) -> None:
        """공시 접수번호를 이력 세트에 추가하고 파일에 저장합니다."""
        self._processed.add(rcept_no)
        try:
            with open(self.history_file, "a", encoding="utf-8") as f:
                f.write(f"{rcept_no}\n")
        except Exception as e:
            print(f"⚠️ 공시 처리 이력을 저장하는 중 오류 발생: {e}", file=sys.stderr)

    def _load_reminders(self) -> None:
        """파일에서 예약 리마인드 목록을 로드합니다."""
        import json
        import os
        if os.path.exists(self.reminders_file):
            try:
                with open(self.reminders_file, "r", encoding="utf-8") as f:
                    self._reminders = json.load(f)
                print(f"💾 예약 리마인드 로드 완료: {len(self._reminders)}개 로드됨 ({self.reminders_file})")
            except Exception as e:
                print(f"⚠️ 예약 리마인드 목록을 읽는 중 오류 발생: {e}", file=sys.stderr)
        else:
            self._reminders = {}

    def _save_reminders(self) -> None:
        """예약 리마인드 목록을 파일에 저장합니다."""
        import json
        try:
            with open(self.reminders_file, "w", encoding="utf-8") as f:
                json.dump(self._reminders, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"⚠️ 예약 리마인드 목록을 저장하는 중 오류 발생: {e}", file=sys.stderr)

    def initialize_watchlist_filter(self) -> None:
        """감시 대상 종목의 corp_code 세트를 초기화합니다."""
        stock_codes = watchlist_provider.get_stock_codes()
        self._watchlist_corp_codes = self.dart_api.get_corp_codes_for_stocks(stock_codes)

        print(f"🎯 감시 종목 필터 설정 완료: {len(self._watchlist_corp_codes)}개 종목 매핑됨")
        print("   감시 대상 종목:")
        for sc in stock_codes:
            name = watchlist_provider.get_stock_name(sc)
            cc = self.dart_api.get_corp_code(sc)
            status = "✅" if cc else "⚠️ 매핑 실패"
            print(f"     {status} {name} ({sc})")

        unmapped = len(stock_codes) - len(self._watchlist_corp_codes)
        if unmapped > 0:
            print(f"   ⚠️  {unmapped}개 종목코드의 DART 고유번호를 찾을 수 없습니다.")

    def start(self) -> None:
        """모니터링을 시작합니다 (블로킹 루프)."""
        interval = self.config.poll_interval_minutes * 60

        print()
        print("🚀 공시 모니터링을 시작합니다.")
        print(f"   폴링 간격: {self.config.poll_interval_minutes}분")
        print(f"   수신자: {self.config.recipient_emails}")
        print('   감시 키워드: "현금ㆍ현물배당 결정"')
        print()
        print("💡 종료하려면 Ctrl+C를 누르세요.")
        print()

        # 시작 즉시 한 번 실행
        self._check_disclosures()
        self._check_and_send_reminders()

        while True:
            time.sleep(interval)
            self._check_disclosures()
            self._check_and_send_reminders()

    def start_once(self) -> None:
        """모니터링을 딱 1회만 실행하고 종료합니다 (GitHub Actions 크론용)."""
        print()
        print("🚀 단회 공시 모니터링을 시작합니다.")
        print(f"   수신자: {self.config.recipient_emails}")
        print('   감시 키워드: "현금ㆍ현물배당 결정"')
        print()
        
        self._check_disclosures()
        self._check_and_send_reminders()
        print("🏁 단회 공시 모니터링 완료.")

    def _check_disclosures(self) -> None:
        """공시를 확인하고 새로운 배당 공시를 처리합니다."""
        now = datetime.now()
        today = now.strftime("%Y%m%d")
        yesterday = (now - timedelta(days=1)).strftime("%Y%m%d")
        time_str = now.strftime("%H:%M:%S")

        print(f"[{time_str}] 🔍 DART 공시 확인 중... (조회기간: {yesterday} ~ {today})")

        try:
            # ⚠️ 현금ㆍ현물배당결정은 '거래소공시(I)'다. 과거 pblntf_ty="B"(주요사항보고)는
            #    배당공시를 한 건도 못 잡았다(실증). 반드시 "I"로 조회한다.
            disclosures = self.dart_api.fetch_all_disclosures(
                begin_date=yesterday,
                end_date=today,
                pblntf_ty="I",
            )
            print(f"[{time_str}]    총 {len(disclosures)}건의 거래소공시(I) 조회됨")

            # "현금ㆍ현물배당 결정" 필터링
            dividend_disclosures = [
                d for d in disclosures if self._is_dividend_decision(d.report_nm)
            ]

            if not dividend_disclosures:
                print(f"[{time_str}]    배당 결정 공시 없음")
            else:
                print(
                    f"[{time_str}]    📋 배당 결정 공시 {len(dividend_disclosures)}건 발견"
                )

                # 감시 대상 종목 필터링 및 신규 공시 처리
                new_count = 0
                for d in dividend_disclosures:
                    if d.rcept_no in self._processed:
                        continue

                    if d.corp_code not in self._watchlist_corp_codes:
                        self._save_processed(d.rcept_no)
                        continue

                    # 새로운 감시 대상 배당 공시
                    new_count += 1
                    print()
                    print(f"[{time_str}]    🔔 ═══════════════════════════════════════")
                    print(f"[{time_str}]    🔔 새로운 배당 공시 발견!")
                    print(f"[{time_str}]    🔔 기업명  : {d.corp_name}")
                    print(f"[{time_str}]    🔔 종목코드: {d.stock_code}")
                    print(f"[{time_str}]    🔔 보고서  : {d.report_nm}")
                    print(f"[{time_str}]    🔔 접수일  : {d.rcept_dt}")
                    print(f"[{time_str}]    🔔 ═══════════════════════════════════════")
                    print()

                    # 이메일 발송
                    print(f"[{time_str}]    📧 이메일 발송 중...")
                    success = self.email_sender.send_dividend_notification(d)

                    if success:
                        print(
                            f"[{time_str}]    ✅ 이메일 발송 성공 → "
                            f"{self.config.recipient_emails}"
                        )
                        # 2차 리마인드 알림 예약 등록 (배당기준일 파싱)
                        print(f"[{time_str}]    ⏰ 배당기준일 파싱 중...")
                        std_date = self._parse_dart_standard_date(d.rcept_no)
                        if std_date:
                            print(f"[{time_str}]    ⏰ 파싱 완료! 배당기준일: {std_date} (예약 등록 완료)")
                            self._reminders[d.rcept_no] = {
                                "type": "dart",
                                "corp_name": d.corp_name,
                                "report_nm": d.report_nm,
                                "standard_date": std_date,
                                "data": d.to_dict()
                            }
                            self._save_reminders()
                        else:
                            print(f"[{time_str}]    ⚠️ 배당기준일 파싱 실패 (예약 보류)")
                    else:
                        print(f"[{time_str}]    ❌ 이메일 발송 실패")

                    self._save_processed(d.rcept_no)
                    time.sleep(1)  # 이메일 발송 간격

                if new_count == 0:
                    print(f"[{time_str}]    새로운 감시 종목 배당 공시 없음")
                else:
                    print(f"[{time_str}]    🏁 {new_count}건의 공시 처리 완료")

        except Exception as e:
            print(f"[{time_str}]    ❌ DART 공시 확인 중 오류 발생: {e}", file=sys.stderr)

        # ────────────────────────────────────────────────────────
        # KIND ETF 공시 모니터링 추가
        # ────────────────────────────────────────────────────────
        try:
            self._check_etf_disclosures()
        except Exception as e:
            print(f"[{time_str}]    ❌ ETF 공시 확인 중 오류 발생: {e}", file=sys.stderr)

    def _check_etf_disclosures(self) -> None:
        """KIND에서 ETF 공시를 확인하고 새로운 이익분배금 관련 공시를 처리합니다."""
        now = datetime.now()
        time_str = now.strftime("%H:%M:%S")

        # 어제와 오늘 날짜 구하기 (안정성을 위해 2일 범위 조회)
        today_str = now.strftime("%Y-%m-%d")
        yesterday_str = (now - timedelta(days=1)).strftime("%Y-%m-%d")

        print(f"[{time_str}] 🔍 KIND ETF 공시 확인 중... (조회기간: {yesterday_str} ~ {today_str})")

        url = "https://kind.krx.co.kr/disclosure/disclosurebystocktype.do"
        payload = {
            "method": "searchDisclosureByStockTypeEtfSub",
            "forward": "disclosurebystocktype_etf_sub",
            "currentPageSize": "30",
            "pageIndex": "1",
            "orderMode": "1",
            "orderStat": "D",
            "etfIsuSrtCd": "",
            "reportCd": "",
            "reportTmp": "",
            "etfIsuSrtNm": "",
            "reportNm": "",
            "fromDate": yesterday_str,
            "toDate": today_str
        }

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://kind.krx.co.kr/disclosure/disclosurebystocktype.do?method=searchDisclosureByStockTypeEtf",
            "Content-Type": "application/x-www-form-urlencoded"
        }

        try:
            res = requests.post(url, data=payload, headers=headers, timeout=10)
            if res.status_code != 200:
                print(f"[{time_str}]    ❌ KIND ETF 공시 요청 실패 (HTTP {res.status_code})")
                return

            soup = BeautifulSoup(res.text, "html.parser")
            table = soup.find("table", class_="tbl-type")
            if not table:
                table = soup.find("table")

            if not table:
                print(f"[{time_str}]    ⚠️ KIND ETF 공시 테이블을 찾을 수 없습니다.")
                return

            rows = table.find_all("tr")
            if len(rows) <= 1:
                print(f"[{time_str}]    KIND ETF 공시 내역 없음")
                return

            new_count = 0
            for row in rows[1:]:
                cells = row.find_all(["td", "th"])
                if len(cells) < 5:
                    continue

                # 컬럼 구조: 번호 | 시간 | 종목명 | 공시제목 | 제출인
                date_cell = cells[1].get_text().strip()
                stock_name = cells[2].get_text().strip()
                report_title = cells[3].get_text().strip()

                # 접수번호(acptno) 추출
                acptno = ""
                links = row.find_all("a")
                for link in links:
                    onclick = link.get("onclick") or ""
                    if "openDisclsViewer" in onclick:
                        match = re.search(r"openDisclsViewer\('(\d+)',''\)", onclick)
                        if match:
                            acptno = match.group(1)
                            break

                if not acptno:
                    continue

                # 1) 이익분배금 관련 공시 여부 체크 (이익분배, 이익금분배, 분배금)
                is_dividend_related = any(kw in report_title for kw in ["이익분배", "이익금분배", "분배금"])
                if not is_dividend_related:
                    continue

                # 2) 감시 대상 ETF인지 매칭 확인
                matched_stock_code = watchlist_provider.find_matched_etf(stock_name)
                if not matched_stock_code:
                    # 감시 대상이 아니면 중복 필터용으로 자동 등록 후 무시
                    self._save_processed(acptno)
                    continue

                # 3) 중복 공시 확인
                if acptno in self._processed:
                    continue

                # 신규 ETF 이익분배금 공시!
                new_count += 1
                etf_name = watchlist_provider.get_etf_name(matched_stock_code)

                print()
                print(f"[{time_str}]    🔔 ═══════════════════════════════════════")
                print(f"[{time_str}]    🔔 새로운 ETF 이익분배금 공시 발견!")
                print(f"[{time_str}]    🔔 종목명  : {etf_name} (공시명: {stock_name})")
                print(f"[{time_str}]    🔔 종목코드: {matched_stock_code}")
                print(f"[{time_str}]    🔔 보고서  : {report_title}")
                print(f"[{time_str}]    🔔 공시시간: {date_cell}")
                print(f"[{time_str}]    🔔 ═══════════════════════════════════════")
                print()

                # 이메일 발송
                print(f"[{time_str}]    📧 이메일 발송 중...")
                success = self.email_sender.send_etf_notification(
                    etf_name=etf_name,
                    stock_code=matched_stock_code,
                    report_nm=report_title,
                    date_str=date_cell,
                    acptno=acptno
                )

                if success:
                    print(f"[{time_str}]    ✅ ETF 이메일 발송 성공 → {self.config.recipient_emails}")
                    # 2차 리마인드 알림 예약 등록 (분배기준일 파싱)
                    print(f"[{time_str}]    ⏰ 분배기준일 파싱 중...")
                    std_date = self._parse_kind_standard_date(acptno)
                    if std_date:
                        print(f"[{time_str}]    ⏰ 파싱 완료! 분배기준일: {std_date} (예약 등록 완료)")
                        self._reminders[acptno] = {
                            "type": "etf",
                            "corp_name": etf_name,
                            "report_nm": report_title,
                            "standard_date": std_date,
                            "data": {
                                "etf_name": etf_name,
                                "stock_code": matched_stock_code,
                                "report_nm": report_title,
                                "date_str": date_cell,
                                "acptno": acptno
                            }
                        }
                        self._save_reminders()
                    else:
                        print(f"[{time_str}]    ⚠️ 분배기준일 파싱 실패 (예약 보류)")
                else:
                    print(f"[{time_str}]    ❌ ETF 이메일 발송 실패")

                self._save_processed(acptno)
                time.sleep(1)

            if new_count == 0:
                print(f"[{time_str}]    새로운 감시 ETF 이익분배금 공시 없음")
            else:
                print(f"[{time_str}]    🏁 {new_count}건의 ETF 공시 처리 완료")

        except Exception as e:
            print(f"[{time_str}]    ❌ ETF 공시 조회 중 오류: {e}", file=sys.stderr)

    def _is_dividend_decision(self, report_name: str) -> bool:
        """보고서명이 배당 결정 관련인지 확인합니다."""
        return any(kw in report_name for kw in self.DIVIDEND_KEYWORDS)

    def _check_and_send_reminders(self) -> None:
        """매일 아침 배당기준일 당일인 공시가 있는지 예약 목록을 뒤져서 리마인드 알림 메일을 전송합니다.
        
        알림 전송 규칙:
        1. 배당 기준일 당일에 발송
        2. 배당 기준일이 주말/휴일인 경우, 그 다음 영업일에도 한번 더 발송
        """
        now = datetime.now()
        today_str = now.strftime("%Y-%m-%d")
        time_str = now.strftime("%H:%M:%S")

        # 오전 08:00 ~ 09:30 사이에 작동
        # 그리고 하루에 단 한 번만 기동되게 제한
        current_hour = now.hour
        current_minute = now.minute

        is_target_time = (current_hour == 8) or (current_hour == 9 and current_minute <= 30)
        if not is_target_time:
            return

        if self._last_reminder_run_date == today_str:
            return

        print(f"[{time_str}] ⏰ 아침 배당기준일 리마인드 스케줄러 기동 중...")

        targets_to_delete = []
        reminders_updated = False

        for key, item in list(self._reminders.items()):
            standard_date = item.get("standard_date")
            prev_bday = self.get_previous_business_day(standard_date)
            next_bday = self.get_next_business_day(standard_date)

            is_t1_day = (today_str == prev_bday) and not item.get("sent_t1", False)
            is_same_day = (today_str == standard_date) or (today_str == next_bday and next_bday != standard_date)

            should_send = is_t1_day or is_same_day
            rem_type_label = "[T-1일 전날 알림]" if is_t1_day else "[당일 알림]"

            if should_send:
                print(f"[{time_str}]    🔔 {rem_type_label} 리마인드 발송 대상 포착 (기준일: {standard_date}, 오늘: {today_str})")
                success = False
                if item["type"] == "dart":
                    disc = Disclosure.from_dict(item["data"])
                    success = self.email_sender.send_dividend_reminder(disc, standard_date)
                elif item["type"] == "etf":
                    d = item["data"]
                    success = self.email_sender.send_etf_reminder(
                        etf_name=d["etf_name"],
                        stock_code=d["stock_code"],
                        report_nm=d["report_nm"],
                        date_str=d["date_str"],
                        acptno=d["acptno"],
                        standard_date=standard_date
                    )

                if success:
                    print(f"[{time_str}]    ✅ {rem_type_label} 이메일 발송 성공!")
                    if is_t1_day:
                        item["sent_t1"] = True
                        reminders_updated = True
                    if is_same_day:
                        targets_to_delete.append(key)
                else:
                    print(f"[{time_str}]    ❌ {rem_type_label} 이메일 발송 실패")

        if targets_to_delete:
            for key in targets_to_delete:
                del self._reminders[key]
            reminders_updated = True

        if reminders_updated:
            self._save_reminders()

        self._last_reminder_run_date = today_str
        print(f"[{time_str}] ⏰ 리마인드 스케줄러 점검 완료.")

    def _parse_dart_standard_date(self, rcept_no: str) -> str | None:
        """DART 공시 상세 뷰어에서 배당기준일을 추출합니다."""
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
            time.sleep(2)

            iframe = driver.find_element(By.ID, "ifrm")
            viewer_url = iframe.get_attribute("src")

            driver.get(viewer_url)
            time.sleep(2)

            text = driver.find_element(By.TAG_NAME, "body").text

            # 배당기준일 파싱 정규식
            may_patterns = [
                r"2026\s*년\s*(?:05|5|06|6|04|4)\s*월\s*\d+\s*일",
                r"2026\.0?[456]\.\d+",
                r"2026-0?[456]-\d+",
                r"2026/0?[456]/\d+"
            ]

            keywords = ["기준일", "폐쇄일"]
            lines = text.split("\n")
            for line in lines:
                if any(kw in line for kw in keywords):
                    for pat in may_patterns:
                        match = re.search(pat, line)
                        if match:
                            return self._normalize_date_string(match.group(0))

            for match in re.finditer(r"(?:기준일|폐쇄일)", text):
                start = max(0, match.start() - 100)
                end = min(len(text), match.end() + 100)
                snippet = text[start:end]
                for pat in may_patterns:
                    m = re.search(pat, snippet)
                    if m:
                        return self._normalize_date_string(m.group(0))

        except Exception as e:
            print(f"      ⚠️ DART 배당기준일 파싱 중 오류: {e}")
        finally:
            if driver:
                driver.quit()
        return None

    def _parse_kind_standard_date(self, acptno: str) -> str | None:
        """KIND ETF 공시 상세 뷰어에서 분배기준일을 추출합니다."""
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
            url = f"https://kind.krx.co.kr/common/disclsviewer.do?method=search&acptno={acptno}"
            driver.get(url)
            time.sleep(3)

            iframes = driver.find_elements(By.TAG_NAME, "iframe")
            text = ""
            for iframe in iframes:
                try:
                    driver.switch_to.frame(iframe)
                    text += "\n" + driver.find_element(By.TAG_NAME, "body").text
                    driver.switch_to.default_content()
                except:
                    driver.switch_to.default_content()

            if not text:
                text = driver.find_element(By.TAG_NAME, "body").text

            may_patterns = [
                r"2026\s*년\s*(?:05|5|06|6|04|4)\s*월\s*\d+\s*일",
                r"2026\.0?[456]\.\d+",
                r"2026-0?[456]-\d+",
                r"2026/0?[456]/\d+"
            ]

            keywords = ["기준일", "폐쇄일", "분배락"]
            lines = text.split("\n")
            for line in lines:
                if any(kw in line for kw in keywords):
                    for pat in may_patterns:
                        match = re.search(pat, line)
                        if match:
                            return self._normalize_date_string(match.group(0))

            for match in re.finditer(r"(?:기준일|폐쇄일|분배락)", text):
                start = max(0, match.start() - 100)
                end = min(len(text), match.end() + 100)
                snippet = text[start:end]
                for pat in may_patterns:
                    m = re.search(pat, snippet)
                    if m:
                        return self._normalize_date_string(m.group(0))

        except Exception as e:
            print(f"      ⚠️ KIND ETF 배당기준일 파싱 중 오류: {e}")
        finally:
            if driver:
                driver.quit()
        return None

    def _normalize_date_string(self, raw_date: str) -> str:
        """날짜 문자열을 YYYY-MM-DD 형태로 정규화합니다."""
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

    def get_next_business_day(self, start_date_str: str) -> str:
        """주어진 날짜가 주말/휴일인 경우 그 다음 비즈니스 데이(평일)를 계산하여 반환합니다.
        평일인 경우 원래 날짜를 그대로 반환합니다.
        """
        from datetime import datetime, timedelta
        try:
            date_obj = datetime.strptime(start_date_str, "%Y-%m-%d")
        except ValueError:
            # 예외 처리: 포맷이 맞지 않는 경우 원래 문자열 반환
            return start_date_str

        # 2026년 한국 법정 공휴일 (대체공휴일 포함)
        holidays = {
            "2026-01-01",  # 신정
            "2026-02-16", "2026-02-17", "2026-02-18",  # 설날 연휴
            "2026-03-01", "2026-03-02",  # 삼일절 및 대체공휴일
            "2026-05-05",  # 어린이날
            "2026-05-24", "2026-05-25",  # 부처님오신날 및 대체공휴일
            "2026-06-06",  # 현충일
            "2026-08-15", "2026-08-17",  # 광복절 및 대체공휴일
            "2026-09-24", "2026-09-25", "2026-09-26",  # 추석 연휴
            "2026-10-03",  # 개천절
            "2026-10-09",  # 한글날
            "2026-12-25"   # 성탄절
        }

        while True:
            # 주말(토, 일) 체크 (5=토, 6=일)
            is_weekend = date_obj.weekday() in [5, 6]
            current_str = date_obj.strftime("%Y-%m-%d")
            is_holiday = current_str in holidays

            if not is_weekend and not is_holiday:
                return current_str

            # 휴일이면 하루 뒤로 전진
            date_obj += timedelta(days=1)

    def get_previous_business_day(self, start_date_str: str) -> str:
        """주어진 날짜의 직전 비즈니스 데이(평일)를 계산하여 반환합니다.
        예컨대 월요일인 경우 직전 금요일을 반환하고, 공휴일인 경우 그 전 영업일을 반환합니다.
        """
        from datetime import datetime, timedelta
        try:
            date_obj = datetime.strptime(start_date_str, "%Y-%m-%d")
        except ValueError:
            return start_date_str

        # 2026년 한국 법정 공휴일 (대체공휴일 포함)
        holidays = {
            "2026-01-01",  # 신정
            "2026-02-16", "2026-02-17", "2026-02-18",  # 설날 연휴
            "2026-03-01", "2026-03-02",  # 삼일절 및 대체공휴일
            "2026-05-05",  # 어린이날
            "2026-05-24", "2026-05-25",  # 부처님오신날 및 대체공휴일
            "2026-06-06",  # 현충일
            "2026-08-15", "2026-08-17",  # 광복절 및 대체공휴일
            "2026-09-24", "2026-09-25", "2026-09-26",  # 추석 연휴
            "2026-10-03",  # 개천절
            "2026-10-09",  # 한글날
            "2026-12-25"   # 성탄절
        }

        while True:
            # 하루 앞으로 후퇴
            date_obj -= timedelta(days=1)
            is_weekend = date_obj.weekday() in [5, 6]
            current_str = date_obj.strftime("%Y-%m-%d")
            is_holiday = current_str in holidays

            if not is_weekend and not is_holiday:
                return current_str
