"""TrendForce 뉴스 모니터링 & 이메일 알림 모듈

TrendForce WordPress REST API에서 새로운 기사를 수집하여,
매일 아침 다이제스트(요약) 이메일로 일괄 발송합니다.

- 이 노트북에서는 휴일(주말/공휴일)에만 실행됩니다.
- 다른 PC에서는 워킹데이에 실행됩니다.
"""

import io
import os
import sys
import time
import json
import re as _re
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import requests

# Windows cp949 인코딩 문제 방지
if getattr(sys.stdout, "encoding", None) != "utf-8" and hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if getattr(sys.stderr, "encoding", None) != "utf-8" and hasattr(sys.stderr, "buffer"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from browser_email_sender import BrowserEmailSender

# Gmail 계정 정보 (기존 email_sender.py와 동일)
GMAIL_ADDRESS = "devbotsender8282@gmail.com"
GMAIL_PASSWORD = "lvjayqklnrkofjbj"

# TrendForce WordPress REST API URL
WP_API_URL = "https://www.trendforce.com/news/wp-json/wp/v2/posts"
WP_CATEGORIES_URL = "https://www.trendforce.com/news/wp-json/wp/v2/categories"
WP_TAGS_URL = "https://www.trendforce.com/news/wp-json/wp/v2/tags"

# 처리된 기사 URL 저장 파일
PROCESSED_FILE = os.path.join(os.path.dirname(__file__), "processed_trendforce.txt")

# HTTP 요청 헤더
HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
    "Accept": "application/json",
}

# 2026년 한국 법정 공휴일 (대체공휴일 포함) — disclosure_monitor.py와 동일
KOREAN_HOLIDAYS_2026 = {
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
    "2026-12-25",  # 성탄절
}


@dataclass
class TrendForceArticle:
    """TrendForce 뉴스 기사 정보"""

    title: str
    link: str
    pub_date: str
    description: str
    categories: list[str] = field(default_factory=list)
    content_html: str = ""
    author: str = ""
    views: int = 0  # 조회수
    title_ko: str = ""  # 한국어 번역 제목
    description_ko: str = ""  # 한국어 번역 요약

    def __str__(self) -> str:
        cats = ", ".join(self.categories) if self.categories else "N/A"
        return f"[{self.pub_date}] {self.title} ({cats})"


def is_holiday(date: datetime | None = None) -> bool:
    """주말 또는 한국 공휴일인지 확인합니다."""
    if date is None:
        date = datetime.now()
    # 주말 체크 (5=토, 6=일)
    if date.weekday() in (5, 6):
        return True
    return date.strftime("%Y-%m-%d") in KOREAN_HOLIDAYS_2026


def is_workday(date: datetime | None = None) -> bool:
    """평일(워킹데이)인지 확인합니다."""
    return not is_holiday(date)


class TrendForceMonitor:
    """TrendForce 뉴스 모니터링 클래스 (휴일 전용, 매일 아침 다이제스트)

    - 매일 아침 지정 시각에 WordPress REST API로 최신 기사를 확인
    - 새로운 기사를 모아 하나의 다이제스트 이메일로 발송
    - holiday_only=True인 경우, 휴일(주말/공휴일)에만 발송
    """

    def __init__(
        self,
        recipient_emails: list[str],
        send_hour: int = 8,
        send_minute: int = 0,
        headless: bool = True,
        holiday_only: bool = True,
    ):
        self.recipient_emails = recipient_emails
        self.send_hour = send_hour
        self.send_minute = send_minute
        self.headless = headless
        self.holiday_only = holiday_only
        self._processed: set[str] = set()
        self._last_sent_date: str | None = None
        self._category_cache: dict[int, str] = {}
        self._tag_cache: dict[int, str] = {}
        self._load_processed()

    # ── 영속성 ────────────────────────────────────────────

    def _load_processed(self) -> None:
        """처리된 기사 URL 목록을 파일에서 로드합니다."""
        if os.path.exists(PROCESSED_FILE):
            with open(PROCESSED_FILE, "r", encoding="utf-8") as f:
                self._processed = {line.strip() for line in f if line.strip()}
        print(f"📂 처리된 TrendForce 기사 {len(self._processed)}건 로드됨")

    def _save_processed(self, url: str) -> None:
        """처리된 기사 URL을 파일에 추가 저장합니다."""
        if url not in self._processed:
            self._processed.add(url)
            with open(PROCESSED_FILE, "a", encoding="utf-8") as f:
                f.write(url + "\n")

    # ── WP REST API ───────────────────────────────────────

    def _resolve_names(self, ids: list[int], cache: dict, url: str) -> list[str]:
        """카테고리/태그 ID를 이름으로 변환합니다."""
        missing = [i for i in ids if i not in cache]
        if missing:
            try:
                resp = requests.get(
                    url,
                    params={"include": ",".join(str(i) for i in missing), "per_page": 100},
                    headers=HTTP_HEADERS, timeout=15,
                )
                if resp.ok:
                    for item in resp.json():
                        cache[item["id"]] = item["name"]
            except Exception:
                pass
        return [cache[i] for i in ids if i in cache]

    def _fetch_articles(self, per_page: int = 30) -> list[TrendForceArticle]:
        """TrendForce WordPress REST API에서 최신 기사를 가져옵니다."""
        resp = requests.get(
            WP_API_URL,
            params={"per_page": per_page, "orderby": "date", "order": "desc"},
            headers=HTTP_HEADERS,
            timeout=30,
        )
        resp.raise_for_status()
        posts = resp.json()

        articles: list[TrendForceArticle] = []
        for post in posts:
            title = _re.sub(r"<[^>]+>", "", post.get("title", {}).get("rendered", "")).strip()
            link = post.get("link", "").strip()
            pub_date = post.get("date", "").strip()  # ISO 8601 형식

            # excerpt에서 HTML 태그 제거
            excerpt_raw = post.get("excerpt", {}).get("rendered", "")
            description = _re.sub(r"<[^>]+>", "", excerpt_raw).strip()
            description = (
                description.replace("&hellip;", "…")
                .replace("&rarr;", "→")
                .replace("&amp;", "&")
                .replace("Continue reading →", "")
                .strip()
            )

            content_html = post.get("content", {}).get("rendered", "")

            # 카테고리/태그 이름 조회
            cat_ids = post.get("categories", [])
            tag_ids = post.get("tags", [])
            categories = self._resolve_names(cat_ids, self._category_cache, WP_CATEGORIES_URL)
            tags = self._resolve_names(tag_ids, self._tag_cache, WP_TAGS_URL)
            all_labels = categories + tags

            if title and link:
                articles.append(
                    TrendForceArticle(
                        title=title,
                        link=link,
                        pub_date=pub_date,
                        description=description,
                        categories=all_labels,
                        content_html=content_html,
                        views=post.get("views", 0) or 0,
                    )
                )

        return articles

    # ── 번역 ──────────────────────────────────────────────

    @staticmethod
    def _translate_articles(articles: list[TrendForceArticle]) -> None:
        """기사 제목과 요약을 한국어로 번역합니다."""
        try:
            from deep_translator import GoogleTranslator
            translator = GoogleTranslator(source='en', target='ko')

            print(f"   🌐 {len(articles)}건 한국어 번역 중...")
            for i, a in enumerate(articles):
                try:
                    a.title_ko = translator.translate(a.title) or a.title
                    if a.description:
                        # deep-translator는 5000자 제한
                        desc_short = a.description[:3000]
                        a.description_ko = translator.translate(desc_short) or a.description
                    else:
                        a.description_ko = a.description
                    time.sleep(0.3)  # Rate limit 방지
                except Exception as e:
                    print(f"   ⚠️ 번역 실패 ({i+1}번 기사): {e}")
                    a.title_ko = a.title
                    a.description_ko = a.description
            print(f"   ✅ 번역 완료")

        except ImportError:
            print("   ⚠️ deep-translator 미설치 — 영문 그대로 발송")
            for a in articles:
                a.title_ko = a.title
                a.description_ko = a.description

    # ── 다이제스트 이메일 ─────────────────────────────────

    def _send_digest(self, articles: list[TrendForceArticle]) -> bool:
        """새 기사들을 모아 하나의 다이제스트 이메일로 발송합니다."""
        # 번역
        self._translate_articles(articles)

        today = datetime.now().strftime("%Y-%m-%d")
        subject = f"[TrendForce Daily] {today} — {len(articles)}건의 새로운 기사"
        html_body = self._build_digest_html(articles, today)

        sender = BrowserEmailSender(
            gmail_address=GMAIL_ADDRESS,
            gmail_password=GMAIL_PASSWORD,
            headless=self.headless,
        )

        return sender.send_email(
            recipients=self.recipient_emails,
            subject=subject,
            html_body=html_body,
        )

    @staticmethod
    def _build_digest_html(articles: list[TrendForceArticle], date_str: str) -> str:
        """다이제스트 이메일의 HTML 본문을 생성합니다."""

        # ── 핵심 요약 (Top 3 조회수 기준) ─────────────────
        top_articles = sorted(articles, key=lambda a: a.views, reverse=True)[:3]
        summary_items = ""
        for a in top_articles:
            t = a.title_ko or a.title
            summary_items += f"""\
      <li style="margin-bottom:6px;line-height:1.5;">
        <a href="{a.link}" style="color:#0f172a;text-decoration:none;font-weight:500;">{t}</a>
      </li>
"""

        summary_section = f"""\
    <!-- Summary -->
    <div style="background:#f0fdf4;border-left:4px solid #22c55e;padding:16px 24px;margin:20px 32px 0;border-radius:6px;">
      <div style="font-size:13px;font-weight:700;color:#15803d;margin-bottom:8px;">📌 오늘의 핵심 요약</div>
      <ul style="margin:0;padding-left:18px;font-size:13px;color:#1e293b;">
{summary_items}
      </ul>
    </div>
"""

        # ── 기사별 카드 ─────────────────────────────────
        article_cards = ""
        for i, a in enumerate(articles, 1):
            cat_badges = " ".join(
                f'<span style="display:inline-block;background:#e0f2fe;color:#0369a1;'
                f'padding:2px 8px;border-radius:10px;font-size:11px;margin:2px 3px 2px 0;">'
                f'{cat}</span>'
                for cat in a.categories[:5]
            )

            # 한국어 제목/요약 (없으면 영문 사용)
            title_display = a.title_ko or a.title
            desc_display = a.description_ko or a.description

            article_cards += f"""\
    <div style="border-bottom:1px solid #e2e8f0;padding:16px 0;">
      <div style="font-size:10px;color:#94a3b8;margin-bottom:4px;">📅 {a.pub_date}</div>
      <a href="{a.link}" style="color:#0f172a;font-size:15px;font-weight:600;
                text-decoration:none;line-height:1.4;">{i}. {title_display}</a>
      <div style="font-size:11px;color:#94a3b8;margin-top:2px;">{a.title}</div>
      <div style="margin-top:6px;">{cat_badges}</div>
      <p style="color:#475569;font-size:13px;line-height:1.6;margin:8px 0 0;">
        {desc_display[:300]}{'…' if len(desc_display) > 300 else ''}
      </p>
    </div>
"""

        return f"""\
<div style="font-family:'Segoe UI',Arial,sans-serif;background:#f0f4f8;padding:20px;">
  <div style="max-width:680px;margin:0 auto;background:#fff;border-radius:12px;
              box-shadow:0 2px 12px rgba(0,0,0,0.08);overflow:hidden;">

    <!-- Header -->
    <div style="background:linear-gradient(135deg,#0d9488,#06b6d4);color:#fff;padding:28px 32px;">
      <div style="font-size:11px;letter-spacing:1.5px;text-transform:uppercase;opacity:0.8;">
        Daily News Digest
      </div>
      <h1 style="margin:8px 0 6px;font-size:22px;font-weight:700;">
        📰 TrendForce News — {date_str}
      </h1>
      <div style="font-size:14px;opacity:0.9;">
        {len(articles)}건의 새로운 기사가 있습니다
      </div>
    </div>

{summary_section}

    <!-- Articles -->
    <div style="padding:12px 32px 24px;">
{article_cards}
    </div>

    <!-- Footer -->
    <div style="padding:16px 32px;background:#f8fafc;font-size:11px;color:#94a3b8;text-align:center;">
      TrendForce News Monitor — 매일 아침 자동 발송
    </div>
  </div>
</div>"""

    # ── 모니터링 루프 ─────────────────────────────────────

    def start(self) -> None:
        """모니터링을 시작합니다 (블로킹 루프)."""
        mode = "휴일만 (노트북)" if self.holiday_only else "워킹데이만 (데스크탑)"

        print()
        print("🚀 TrendForce 뉴스 모니터링을 시작합니다.")
        print(f"   데이터 소스 : WordPress REST API")
        print(f"   발송 시각  : 매일 {self.send_hour:02d}:{self.send_minute:02d}")
        print(f"   실행 모드  : {mode}")
        print(f"   수신자     : {', '.join(self.recipient_emails)}")
        print()

        today = datetime.now()
        if self.holiday_only:
            if is_holiday(today):
                print(f"   📅 오늘은 휴일입니다 — 모니터링 활성화 ✅")
            else:
                print(f"   📅 오늘은 워킹데이입니다 — 다음 휴일까지 대기 💤")
        else:
            if is_workday(today):
                print(f"   📅 오늘은 워킹데이입니다 — 모니터링 활성화 ✅")
            else:
                print(f"   📅 오늘은 휴일입니다 — 다음 워킹데이까지 대기 💤")

        print()
        print("💡 종료하려면 Ctrl+C를 누르세요.")
        print()

        while True:
            now = datetime.now()
            ts = now.strftime("%H:%M:%S")

            # 매 분마다 체크
            if self._should_send_now(now):
                print(f"[{ts}] ⏰ 아침 다이제스트 발송 시각입니다!")
                self._run_daily_digest()
                self._last_sent_date = now.strftime("%Y-%m-%d")

            # 1분 간격 루프 (가벼운 체크)
            time.sleep(60)

    def _should_send_now(self, now: datetime) -> bool:
        """지금이 발송 시각인지 확인합니다."""
        today_str = now.strftime("%Y-%m-%d")

        # 오늘 이미 발송했으면 스킵
        if self._last_sent_date == today_str:
            return False

        # 지정 시각 체크 (±5분 오차 허용)
        if now.hour != self.send_hour:
            return False
        if now.minute < self.send_minute or now.minute > self.send_minute + 5:
            return False

        # 실행 모드 체크
        if self.holiday_only and not is_holiday(now):
            # 노트북: 휴일에만 발송
            return False
        if not self.holiday_only and is_holiday(now):
            # 데스크탑: 워킹데이에만 발송
            return False

        return True

    def _run_daily_digest(self) -> None:
        """RSS 피드를 확인하고 새 기사를 다이제스트 이메일로 발송합니다."""
        now = datetime.now()
        ts = now.strftime("%H:%M:%S")

        print(f"[{ts}] 🔍 TrendForce 최신 기사 확인 중...")

        try:
            articles = self._fetch_articles()
            print(f"[{ts}]    API에서 {len(articles)}건의 기사 조회됨")

            new_articles = [a for a in articles if a.link not in self._processed]

            if not new_articles:
                print(f"[{ts}]    새로운 기사 없음 — 이메일 발송 건너뜀")
                return

            print(f"[{ts}]    📋 새로운 기사 {len(new_articles)}건 발견!")
            for i, a in enumerate(new_articles, 1):
                print(f"[{ts}]       {i}. {a.title}")

            # 다이제스트 이메일 발송
            print(f"[{ts}]    📧 다이제스트 이메일 발송 중...")
            success = self._send_digest(new_articles)

            if success:
                print(f"[{ts}]    ✅ 다이제스트 발송 성공 ({len(new_articles)}건)")
                # 발송 성공 후 처리 완료 기록
                for a in new_articles:
                    self._save_processed(a.link)
            else:
                print(f"[{ts}]    ❌ 다이제스트 발송 실패")

        except Exception as e:
            print(f"[{ts}]    ❌ 뉴스 확인 중 오류: {e}", file=sys.stderr)

    # ── 테스트 ────────────────────────────────────────────

    def test_fetch(self) -> None:
        """WP REST API에서 최신 기사를 가져와 출력합니다 (이메일 발송 없음)."""
        print("🧪 TrendForce 기사 테스트 (WordPress REST API)")
        print(f"   API: {WP_API_URL}")
        print()

        today = datetime.now()
        print(f"   📅 오늘: {today.strftime('%Y-%m-%d (%A)')}")
        print(f"   📅 휴일 여부: {'✅ 휴일' if is_holiday(today) else '❌ 워킹데이'}")
        print()

        articles = self._fetch_articles()
        print(f"   총 {len(articles)}건의 기사 조회됨")
        print()

        for i, a in enumerate(articles[:10], 1):
            already = "✅ 발송됨" if a.link in self._processed else "🆕 미발송"
            cats = ", ".join(a.categories) if a.categories else "N/A"
            print(f"   {i:2d}. [{already}] {a.title}")
            print(f"       📅 {a.pub_date}")
            print(f"       🏷️  {cats}")
            print(f"       🔗 {a.link}")
            print()

        new_count = sum(1 for a in articles if a.link not in self._processed)
        print(f"   📊 새로운 기사: {new_count}건 / 전체: {len(articles)}건")
        print()
        print("✅ 테스트 완료!")
