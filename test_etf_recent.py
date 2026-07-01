"""KIND ETF 공시 최근 데이터를 조회하고 이메일 발송 및 PDF 생성을 테스트합니다."""

import io
import sys
import time
import requests
import re
from datetime import datetime, timedelta
from bs4 import BeautifulSoup

# Windows cp949 인코딩 문제 방지
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding != "utf-8":
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from config import AppConfig
from email_sender import EmailSender
import watchlist_provider

def test_etf_flow():
    config = AppConfig()
    
    # 1. 180일 전부터 오늘까지 조회
    today_str = datetime.now().strftime("%Y-%m-%d")
    thirty_days_ago = (datetime.now() - timedelta(days=180)).strftime("%Y-%m-%d")
    
    print(f"\n🔍 KIND ETF 공시 조회 ({thirty_days_ago} ~ {today_str})")
    print("=" * 60)
    
    url = "https://kind.krx.co.kr/disclosure/disclosurebystocktype.do"
    payload = {
        "method": "searchDisclosureByStockTypeEtfSub",
        "forward": "disclosurebystocktype_etf_sub",
        "currentPageSize": "100", # 최근 100건 조회
        "pageIndex": "1",
        "orderMode": "1",
        "orderStat": "D",
        "etfIsuSrtCd": "",
        "reportCd": "",
        "reportTmp": "",
        "etfIsuSrtNm": "",
        "reportNm": "분배",
        "fromDate": thirty_days_ago,
        "toDate": today_str
    }
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://kind.krx.co.kr/disclosure/disclosurebystocktype.do?method=searchDisclosureByStockTypeEtf",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    
    try:
        res = requests.post(url, data=payload, headers=headers)
        if res.status_code != 200:
            print(f"❌ KIND ETF 공시 요청 실패 (HTTP {res.status_code})")
            return
            
        soup = BeautifulSoup(res.text, "html.parser")
        table = soup.find("table", class_="tbl-type")
        if not table:
            table = soup.find("table")
            
        if not table:
            print("❌ KIND ETF 공시 테이블을 찾을 수 없습니다.")
            return
            
        rows = table.find_all("tr")
        print(f"총 조회된 공시 행 개수: {len(rows) - 1}개")
        
        all_dividend_hits = []
        fallback_hits = [] # 감시 대상은 아니지만 이익분배금 관련 공시인 것들
        
        for row in rows[1:]:
            cells = row.find_all(["td", "th"])
            if len(cells) < 5:
                continue
                
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
                
            # 이익분배금 관련 키워드 검출
            is_dividend_related = any(kw in report_title for kw in ["이익분배", "이익금분배", "분배금"])
            
            if is_dividend_related:
                item_info = {
                    "acptno": acptno,
                    "date": date_cell,
                    "stock_name": stock_name,
                    "report_title": report_title
                }
                
                matched_stock_code = watchlist_provider.find_matched_etf(stock_name)
                if matched_stock_code:
                    item_info["matched_code"] = matched_stock_code
                    item_info["etf_name"] = watchlist_provider.get_etf_name(matched_stock_code)
                    all_dividend_hits.append(item_info)
                else:
                    fallback_hits.append(item_info)
                    
        print(f"🎯 매칭된 감시 대상 ETF 공시: {len(all_dividend_hits)}건")
        print(f"💡 매칭되지 않았지만 발견된 기타 ETF 분배금 공시: {len(fallback_hits)}건")
        print("=" * 60)
        
        target_item = None
        if all_dividend_hits:
            print("\n📋 발견된 감시 대상 ETF 분배금 공시:")
            for d in all_dividend_hits:
                print(f"   [{d['date']}] {d['etf_name']} (원공시명: {d['stock_name']}) - {d['report_title']} (접수번호: {d['acptno']})")
            target_item = all_dividend_hits[0]
        elif fallback_hits:
            print("\n📋 감시 대상은 아니지만 테스트 가능한 ETF 분배금 공시 목록:")
            for d in fallback_hits[:5]: # 최대 5개 출력
                print(f"   [{d['date']}] {d['stock_name']} - {d['report_title']} (접수번호: {d['acptno']})")
            print("   👉 감시 대상 공시가 없어 위 목록 중 가장 최근 공시로 발송 테스트를 진행합니다.")
            target_item = fallback_hits[0]
            # fallback_item의 경우 etf_name을 stock_name으로 설정하고 matched_code는 '000000' 등으로 처리
            target_item["etf_name"] = target_item["stock_name"]
            target_item["matched_code"] = "000000"
        else:
            print("\n❌ 최근 30일간 ETF 이익분배금 관련 공시가 아예 존재하지 않습니다.")
            print("   테스트를 종료합니다.")
            return
            
        if target_item:
            print()
            print(f"📧 이메일 및 PDF 인쇄 테스트 시작:")
            print(f"   - 대상 ETF : {target_item['etf_name']}")
            print(f"   - 공시 제목: {target_item['report_title']}")
            print(f"   - 공시 시간: {target_item['date']}")
            print(f"   - 접수 번호: {target_item['acptno']}")
            print()
            
            email_sender = EmailSender(
                recipient_emails=config.recipient_emails,
                headless=False,
            )
            success = email_sender.send_etf_notification(
                etf_name=target_item["etf_name"],
                stock_code=target_item["matched_code"],
                report_nm=target_item["report_title"],
                date_str=target_item["date"],
                acptno=target_item["acptno"]
            )
            
            if success:
                print("\n✅ 이메일 및 PDF 테스트 발송 성공!")
            else:
                print("\n❌ 테스트 발송 실패")
                
    except Exception as e:
        print(f"❌ 실행 중 오류 발생: {e}")
        
    print("\n🏁 테스트 완료!")

if __name__ == "__main__":
    test_etf_flow()
