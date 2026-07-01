#!/usr/bin/env python3
"""SK텔레콤, 현대자동차 배당 공시를 DART에서 직접 조회합니다."""

import os, sys, time, re, json

os.chdir(os.path.dirname(os.path.abspath(__file__)))

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

options = Options()
options.add_argument("--headless=new")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--disable-gpu")
options.add_argument("--window-size=1920,1080")

driver = webdriver.Chrome(options=options)
driver.set_page_load_timeout(30)

results = {}

# 조회할 종목들 (종목코드 기반으로 DART 검색)
targets = {
    "SK텔레콤": "017670",
    "현대자동차": "005380",
}

for name, stock_code in targets.items():
    print(f"\n{'='*60}")
    print(f"🔍 {name} ({stock_code}) 배당 공시 검색 중...")
    print(f"{'='*60}")
    
    try:
        # DART 기업별 공시 검색
        url = f"https://dart.fss.or.kr/dsab002/search.ax?totalCnt=&currentPage=1&maxResults=15&maxLinks=10&sort=date&series=desc&textCrpNm={name}&startDate=20260101&endDate=20260601"
        driver.get(url)
        time.sleep(3)
        
        page_text = driver.find_element(By.TAG_NAME, "body").text
        print(f"   페이지 텍스트 길이: {len(page_text)}")
        
        # 테이블 행 찾기
        rows = driver.find_elements(By.CSS_SELECTOR, "tr")
        print(f"   테이블 행: {len(rows)}개")
        
        dividend_rows = []
        for row in rows:
            row_text = row.text
            if "배당" in row_text:
                print(f"   📋 배당 관련 행 발견: {row_text[:150]}")
                
                # 링크에서 접수번호 추출
                links = row.find_elements(By.TAG_NAME, "a")
                for link in links:
                    href = link.get_attribute("href") or ""
                    onclick = link.get_attribute("onclick") or ""
                    combined = href + onclick
                    
                    m = re.search(r"rcpNo=(\d+)", combined)
                    if not m:
                        m = re.search(r"'(\d{14})'", combined)
                    
                    if m:
                        rcept_no = m.group(1)
                        link_text = link.text.strip()
                        print(f"      접수번호: {rcept_no}, 제목: {link_text}")
                        dividend_rows.append({
                            "rcept_no": rcept_no,
                            "title": link_text,
                            "row_text": row_text[:200]
                        })
        
        if not dividend_rows:
            # 직접 페이지에서 검색 - 다른 방법 시도
            print("   ⚠️ 기업별 검색에서 결과 없음. 다른 방식 시도...")
            
            # DART 통합검색 - 기업명 + 주요사항보고
            url2 = f"https://dart.fss.or.kr/dsab007/detailSearch.ax"
            
            import requests
            session = requests.Session()
            session.headers.update({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": "https://dart.fss.or.kr/dsab007/main.do"
            })
            
            payload = {
                "currentPage": "1",
                "maxResults": "50",
                "maxLinks": "10",
                "sort": "date",
                "series": "desc",
                "textCrpNm": name,
                "startDate": "20260101",
                "endDate": "20260601",
                "publicType": "",
            }
            
            resp = session.post(url2, data=payload, timeout=15)
            print(f"   HTTP POST 응답: {resp.status_code}, 크기: {len(resp.text)}")
            
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(resp.text, "html.parser")
            
            for a_tag in soup.find_all("a"):
                text = a_tag.get_text(strip=True)
                if "배당" in text:
                    onclick = a_tag.get("onclick", "")
                    href = a_tag.get("href", "")
                    m = re.search(r"rcpNo=(\d+)", onclick + href)
                    if not m:
                        m = re.search(r"'(\d{14})'", onclick)
                    if m:
                        rcept_no = m.group(1)
                        print(f"   📋 발견: {text} (접수번호: {rcept_no})")
                        dividend_rows.append({
                            "rcept_no": rcept_no,
                            "title": text,
                        })
        
        # 배당 공시 상세 조회 - 배당기준일 파싱
        for item in dividend_rows:
            rcept_no = item["rcept_no"]
            print(f"\n   📄 공시 상세 조회: {item['title']} (접수: {rcept_no})")
            
            try:
                driver.get(f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}")
                time.sleep(3)
                
                iframe = driver.find_element(By.ID, "ifrm")
                viewer_url = iframe.get_attribute("src")
                print(f"      viewer URL: {viewer_url[:100]}...")
                
                driver.get(viewer_url)
                time.sleep(3)
                
                text = driver.find_element(By.TAG_NAME, "body").text
                print(f"      본문 길이: {len(text)}")
                
                # 기준일/폐쇄일 관련 줄 출력
                for line in text.split("\n"):
                    if any(kw in line for kw in ["기준일", "폐쇄일", "배당금", "1주당"]):
                        print(f"      → {line.strip()[:120]}")
                
                # 날짜 추출
                date_patterns = [
                    r"2026\s*년\s*(?:0?[1-9]|1[0-2])\s*월\s*\d+\s*일",
                    r"2026\.(?:0?[1-9]|1[0-2])\.\d+",
                    r"2026-(?:0?[1-9]|1[0-2])-\d+",
                ]
                
                std_date = None
                for line in text.split("\n"):
                    if any(kw in line for kw in ["기준일", "폐쇄일"]):
                        for pat in date_patterns:
                            match = re.search(pat, line)
                            if match:
                                raw = match.group(0).replace(" ", "")
                                m2 = re.search(r"(\d{4})년(\d{1,2})월(\d{1,2})일", raw) or re.search(r"(\d{4})[\./-](\d{1,2})[\./-](\d{1,2})", raw)
                                if m2:
                                    std_date = f"{m2.group(1)}-{int(m2.group(2)):02d}-{int(m2.group(3)):02d}"
                                    break
                    if std_date:
                        break
                
                if not std_date:
                    for m in re.finditer(r"(?:기준일|폐쇄일)", text):
                        snippet = text[max(0, m.start()-150):min(len(text), m.end()+150)]
                        for pat in date_patterns:
                            m2 = re.search(pat, snippet)
                            if m2:
                                raw = m2.group(0).replace(" ", "")
                                m3 = re.search(r"(\d{4})년(\d{1,2})월(\d{1,2})일", raw) or re.search(r"(\d{4})[\./-](\d{1,2})[\./-](\d{1,2})", raw)
                                if m3:
                                    std_date = f"{m3.group(1)}-{int(m3.group(2)):02d}-{int(m3.group(3)):02d}"
                                    break
                        if std_date:
                            break
                
                if std_date:
                    print(f"      ✅ 배당기준일: {std_date}")
                    item["standard_date"] = std_date
                else:
                    print(f"      ⚠️ 기준일 파싱 실패")
                    # 전체 텍스트에서 "기준" 근처 출력
                    for m in re.finditer(r"기준", text):
                        snippet = text[max(0, m.start()-50):min(len(text), m.end()+80)]
                        print(f"      [기준 근처]: {snippet.strip()}")
                    
            except Exception as e:
                print(f"      ❌ 오류: {e}")
        
        results[name] = dividend_rows
        
    except Exception as e:
        print(f"   ❌ 오류: {e}")
        import traceback
        traceback.print_exc()

driver.quit()

print(f"\n{'='*60}")
print(f"📊 최종 결과")
print(f"{'='*60}")
for name, rows in results.items():
    print(f"\n{name}:")
    if rows:
        for r in rows:
            std = r.get("standard_date", "파싱실패")
            print(f"  📄 {r['title']} → 기준일: {std}")
    else:
        print(f"  배당 공시 없음")

with open("skt_hyundai_result.json", "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

print(f"\n✅ 완료!")
