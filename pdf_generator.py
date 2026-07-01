"""DART 공시 원문 페이지를 그대로 PDF로 저장합니다.

Selenium으로 DART viewer 페이지를 열어
Chrome DevTools Protocol의 Page.printToPDF로 그대로 PDF 인쇄합니다.
"""

import base64
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By


class PdfGenerator:
    """DART 공시 원문 → PDF 직접 저장"""

    @staticmethod
    def generate_from_dart(rcept_no: str, output_path: str, corp_name: str = "") -> bool:
        """DART 공시 원문 페이지를 그대로 PDF로 저장합니다.

        Args:
            rcept_no: DART 접수번호
            output_path: PDF 저장 경로
            corp_name: 기업명 (로그용)
        """
        options = Options()
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=900,1200")
        options.add_argument("--disable-gpu")
        options.add_argument("--lang=ko-KR")

        driver = None
        try:
            driver = webdriver.Chrome(options=options)

            # 1) DART 메인 페이지에서 viewer iframe URL 추출
            main_url = f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}"
            print(f"   🌐 DART 공시 페이지 접속 중...")
            driver.get(main_url)
            time.sleep(3)

            # iframe#ifrm의 src에서 viewer URL 추출
            try:
                iframe = driver.find_element(By.ID, "ifrm")
                viewer_url = iframe.get_attribute("src")
            except Exception:
                # fallback: 직접 viewer URL 구성
                viewer_url = (
                    f"https://dart.fss.or.kr/report/viewer.do?"
                    f"rcpNo={rcept_no}&dcmNo={rcept_no}&eleId=0&offset=0&length=0&dtd=HTML"
                )

            # 2) viewer 페이지 직접 접근 (iframe 밖에서)
            driver.get(viewer_url)
            time.sleep(3)

            # 3) 상단에 기업명/날짜 헤더 추가 (모닝스타 참고 PDF처럼)
            if corp_name:
                driver.execute_script(f"""
                    var header = document.createElement('div');
                    header.style.cssText = 'padding:0 0 8px 0;margin-bottom:8px;border-bottom:1px solid #ccc;font-family:Malgun Gothic,sans-serif;font-size:11px;color:#666';
                    header.textContent = '{corp_name} / 현금ㆍ현물배당결정';
                    document.body.insertBefore(header, document.body.firstChild);
                """)
                time.sleep(0.5)

            # 4) Chrome CDP로 PDF 인쇄
            print(f"   📄 PDF 생성 중...")
            pdf_data = driver.execute_cdp_cmd("Page.printToPDF", {
                "printBackground": True,
                "preferCSSPageSize": False,
                "marginTop": 0.5,
                "marginBottom": 0.5,
                "marginLeft": 0.6,
                "marginRight": 0.6,
                "paperWidth": 8.27,   # A4
                "paperHeight": 11.69,  # A4
                "scale": 0.9,
            })

            pdf_bytes = base64.b64decode(pdf_data["data"])
            with open(output_path, "wb") as f:
                f.write(pdf_bytes)

            print(f"   📄 PDF 생성 완료: {output_path} ({len(pdf_bytes):,} bytes)")
            return True

        except Exception as e:
            print(f"   ❌ PDF 생성 실패: {e}")
            return False
        finally:
            if driver:
                driver.quit()

    @staticmethod
    def generate_from_kind(acptno: str, output_path: str, corp_name: str = "") -> bool:
        """KIND 공시 상세 페이지를 그대로 PDF로 저장합니다.

        Args:
            acptno: KIND 접수번호
            output_path: PDF 저장 경로
            corp_name: 기업명/ETF명 (로그 및 헤더용)
        """
        import base64
        options = Options()
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=900,1200")
        options.add_argument("--disable-gpu")
        options.add_argument("--lang=ko-KR")

        driver = None
        try:
            driver = webdriver.Chrome(options=options)

            url = f"https://kind.krx.co.kr/common/disclsviewer.do?method=search&acptno={acptno}"
            print(f"   🌐 KIND 공시 페이지 접속 중...")
            driver.get(url)
            time.sleep(5)

            # 상단에 기업명/날짜 헤더 추가
            if corp_name:
                driver.execute_script(f"""
                    var header = document.createElement('div');
                    header.style.cssText = 'padding:0 0 8px 0;margin-bottom:8px;border-bottom:1px solid #ccc;font-family:Malgun Gothic,sans-serif;font-size:11px;color:#666';
                    header.textContent = '{corp_name} / ETF이익분배금신고';
                    document.body.insertBefore(header, document.body.firstChild);
                """)
                time.sleep(0.5)

            # Chrome CDP로 PDF 인쇄
            print(f"   📄 PDF 생성 중...")
            pdf_data = driver.execute_cdp_cmd("Page.printToPDF", {
                "printBackground": True,
                "preferCSSPageSize": False,
                "marginTop": 0.5,
                "marginBottom": 0.5,
                "marginLeft": 0.6,
                "marginRight": 0.6,
                "paperWidth": 8.27,   # A4
                "paperHeight": 11.69,  # A4
                "scale": 0.9,
            })

            pdf_bytes = base64.b64decode(pdf_data["data"])
            with open(output_path, "wb") as f:
                f.write(pdf_bytes)

            print(f"   📄 PDF 생성 완료: {output_path} ({len(pdf_bytes):,} bytes)")
            return True

        except Exception as e:
            print(f"   ❌ PDF 생성 실패: {e}")
            return False
        finally:
            if driver:
                driver.quit()

