"""DART 공시 원문에서 배당 결정 상세 데이터를 스크래핑합니다."""

import io
import sys
import time
from dataclasses import dataclass, field

import requests
from bs4 import BeautifulSoup


@dataclass
class DividendDetail:
    """배당 결정 상세 정보"""

    corp_name: str = ""
    rcept_dt: str = ""
    report_nm: str = ""

    # 1. 배당구분
    dividend_type: str = ""  # 분기배당, 결산배당 등
    # 2. 배당종류
    dividend_kind: str = ""  # 현금배당, 현물배당 등
    # - 현물자산의 상세내역
    asset_detail: str = ""
    # 3. 1주당 배당금(원)
    dividend_per_share_common: str = ""  # 보통주
    dividend_per_share_preferred: str = ""  # 종류주식
    # - 차등배당 여부
    differential_dividend: str = ""
    # 4. 시가배당률(%)
    dividend_yield_common: str = ""  # 보통주
    dividend_yield_preferred: str = ""  # 종류주식
    # 5. 배당금총액(원)
    total_dividend_amount: str = ""
    # 6. 배당기준일
    record_date: str = ""
    # 7. 배당금지급 예정일자
    payment_date: str = ""
    # 8. 주주총회 개최여부
    shareholder_meeting: str = ""
    # 9. 주주총회 예정일자
    shareholder_meeting_date: str = ""
    # 10. 이사회결의일(결정일)
    board_decision_date: str = ""
    # - 사외이사 참석여부
    outside_director_present: str = ""  # 참석(명)
    outside_director_absent: str = ""  # 불참(명)
    # - 감사 참석여부
    auditor_attendance: str = ""
    # 11. 기타 투자판단과 관련한 중요사항
    other_important_matters: str = ""
    # * 관련공시
    related_disclosure: str = ""


class DartDisclosureScraper:
    """DART 공시 원문 페이지에서 배당 결정 상세 정보를 스크래핑합니다."""

    @staticmethod
    def fetch_dividend_detail(rcept_no: str, corp_name: str = "", rcept_dt: str = "") -> DividendDetail | None:
        """접수번호로 DART 공시 원문에서 배당 상세 정보를 가져옵니다."""
        detail = DividendDetail(corp_name=corp_name, rcept_dt=rcept_dt)

        try:
            # DART 공시 상세 페이지 URL
            url = f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}"
            print(f"   🌐 DART 공시 원문 조회 중: {url}")

            session = requests.Session()
            session.headers.update({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            })

            # 메인 페이지에서 문서 viewer URL 추출
            resp = session.get(url, timeout=10)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            # iframe의 dcmNo를 찾아 실제 문서 URL 구성
            # DART는 iframe으로 실제 문서를 로드함
            # 문서 뷰어 URL 패턴: /report/viewer.do?rcpNo=...&dcmNo=...&eleId=...
            iframes = soup.select("iframe")
            viewer_url = None
            for iframe in iframes:
                src = iframe.get("src", "")
                if "viewer.do" in src or "main.do" in src:
                    if src.startswith("/"):
                        viewer_url = f"https://dart.fss.or.kr{src}"
                    elif src.startswith("http"):
                        viewer_url = src
                    break

            if not viewer_url:
                # JavaScript에서 URL 추출 시도
                scripts = soup.find_all("script")
                for script in scripts:
                    text = script.string or ""
                    if "dcmNo" in text:
                        import re
                        match = re.search(r"dcmNo['\"]?\s*[:=]\s*['\"]?(\d+)", text)
                        if match:
                            dcm_no = match.group(1)
                            viewer_url = (
                                f"https://dart.fss.or.kr/report/viewer.do?"
                                f"rcpNo={rcept_no}&dcmNo={dcm_no}&eleId=0&offset=0&length=0&dtd=dart3.xsd"
                            )
                            break

            if not viewer_url:
                print("   ⚠️ 문서 뷰어 URL을 찾을 수 없습니다. 기본 형식으로 시도합니다.")
                # 직접 API 시도
                viewer_url = (
                    f"https://dart.fss.or.kr/report/viewer.do?"
                    f"rcpNo={rcept_no}&dcmNo={rcept_no}&eleId=0&offset=0&length=0&dtd=dart3.xsd"
                )

            # 문서 내용 가져오기
            resp2 = session.get(viewer_url, timeout=10)
            resp2.raise_for_status()
            doc_soup = BeautifulSoup(resp2.text, "html.parser")

            # 테이블에서 데이터 추출
            tables = doc_soup.find_all("table")
            detail.report_nm = "현금ㆍ현물배당 결정"

            for table in tables:
                rows = table.find_all("tr")
                for row in rows:
                    cells = row.find_all(["td", "th"])
                    if len(cells) < 2:
                        continue

                    label = cells[0].get_text(strip=True)
                    value = cells[-1].get_text(strip=True)

                    # 중간 셀이 있는 경우 (보통주/종류주식 구분)
                    mid = cells[1].get_text(strip=True) if len(cells) > 2 else ""

                    if "배당구분" in label:
                        detail.dividend_type = value
                    elif "배당종류" in label:
                        detail.dividend_kind = value
                    elif "현물자산" in label:
                        detail.asset_detail = value
                    elif "1주당" in label and "배당금" in label:
                        if "보통" in mid:
                            detail.dividend_per_share_common = value
                        elif "종류" in mid:
                            detail.dividend_per_share_preferred = value
                        else:
                            detail.dividend_per_share_common = value
                    elif "차등배당" in label:
                        detail.differential_dividend = value
                    elif "시가배당" in label:
                        if "보통" in mid:
                            detail.dividend_yield_common = value
                        elif "종류" in mid:
                            detail.dividend_yield_preferred = value
                        else:
                            detail.dividend_yield_common = value
                    elif "배당금총액" in label:
                        detail.total_dividend_amount = value
                    elif "배당기준일" in label:
                        detail.record_date = value
                    elif "배당금지급" in label:
                        detail.payment_date = value
                    elif "주주총회" in label and "개최" in label:
                        detail.shareholder_meeting = value
                    elif "주주총회" in label and "예정" in label:
                        detail.shareholder_meeting_date = value
                    elif "이사회" in label and ("결의" in label or "결정" in label):
                        detail.board_decision_date = value
                    elif "참석" in label and "명" in mid:
                        detail.outside_director_present = value
                    elif "불참" in label or ("참석" in label and "불" in mid):
                        detail.outside_director_absent = value
                    elif "감사" in label and "참석" in label:
                        detail.auditor_attendance = value
                    elif "기타" in label and "투자" in label:
                        # 기타 중요사항은 여러 줄일 수 있음
                        detail.other_important_matters = value
                    elif "관련공시" in label:
                        detail.related_disclosure = value

            session.close()
            print("   ✅ 공시 상세 데이터 추출 완료")
            return detail

        except Exception as e:
            print(f"   ❌ 공시 원문 스크래핑 실패: {e}")
            return None
