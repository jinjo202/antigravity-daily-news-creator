#!/usr/bin/env python3
"""Selenium으로 DART 검색하여 감시 종목 배당 공시를 조회합니다."""

import os, sys, json, time, re

os.chdir(os.path.dirname(os.path.abspath(__file__)))
LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "check_output.txt")
logf = open(LOG, "w", encoding="utf-8")

def log(msg):
    logf.write(msg + "\n")
    logf.flush()
    print(msg)

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    import watchlist_provider

    stock_codes = watchlist_provider.get_stock_codes()
    stock_names = {sc: watchlist_provider.get_stock_name(sc) for sc in stock_codes}
    log(f"감시 종목: {len(stock_codes)}개")

    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")

    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(30)

    # ─── 방법: DART 공시검색 페이지를 Selenium으로 접근 ───
    log("\n🔍 DART 공시검색 페이지 접근 중...")
    driver.get("https://dart.fss.or.kr/dsab007/main.do")
    time.sleep(3)

    # 검색 조건 설정
    # 1) 시작일 설정
    start_input = driver.find_element(By.ID, "startDate")
    driver.execute_script("arguments[0].value = '20260501'", start_input)
    
    # 2) 종료일 설정
    end_input = driver.find_element(By.ID, "endDate")
    driver.execute_script("arguments[0].value = '20260601'", end_input)
    
    # 3) 보고서명에 "현금" 입력
    try:
        report_name_input = driver.find_element(By.ID, "reportName")
        report_name_input.clear()
        report_name_input.send_keys("현금ㆍ현물배당")
        log("   보고서명 검색어 입력 완료")
    except Exception as e:
        log(f"   보고서명 입력 실패: {e}")
        # 대안: textCrpNm 등 다른 필드 시도
    
    # 4) 검색 버튼 클릭
    try:
        search_btn = driver.find_element(By.CSS_SELECTOR, "input[type='submit'], button[type='submit'], .btnSearch, #searchBtn")
        search_btn.click()
        log("   검색 버튼 클릭")
    except:
        try:
            search_btn = driver.find_element(By.XPATH, "//a[contains(text(),'검색')]")
            search_btn.click()
            log("   검색 링크 클릭")
        except:
            # JavaScript로 검색 실행
            driver.execute_script("fnSearch(1)")
            log("   JavaScript로 검색 실행")
    
    time.sleep(5)
    
    # 결과 페이지 분석
    page_text = driver.find_element(By.TAG_NAME, "body").text
    log(f"\n   페이지 텍스트 길이: {len(page_text)}")
    
    # 스크린샷 저장
    driver.save_screenshot(os.path.join(os.path.dirname(os.path.abspath(__file__)), "dart_search.png"))
    log("   스크린샷 저장: dart_search.png")
    
    # 테이블에서 결과 추출
    results = []
    rows = driver.find_elements(By.CSS_SELECTOR, "table.tbList tbody tr, table.tbl-type tbody tr, .tbWideList tbody tr, #listContents tr")
    
    if not rows:
        rows = driver.find_elements(By.CSS_SELECTOR, "table tbody tr")
    
    log(f"   테이블 행: {len(rows)}개")
    
    for row in rows:
        try:
            cells = row.find_elements(By.TAG_NAME, "td")
            if len(cells) < 3:
                continue
            
            row_text = row.text
            if "배당" not in row_text:
                continue
            
            # 각 셀 텍스트
            cell_texts = [c.text.strip() for c in cells]
            log(f"   행: {' | '.join(cell_texts[:6])}")
            
            # 링크에서 접수번호 추출
            links = row.find_elements(By.TAG_NAME, "a")
            rcept_no = ""
            report_nm = ""
            corp_name = ""
            
            for link in links:
                href = link.get_attribute("href") or ""
                onclick = link.get_attribute("onclick") or ""
                text = link.text.strip()
                
                m = re.search(r"rcpNo=(\d+)", href + onclick)
                if m:
                    rcept_no = m.group(1)
                    report_nm = text
                
                m = re.search(r"crpNm=([^&]+)", href + onclick)
                if not m:
                    m = re.search(r"'(\d{8})'", onclick)
            
            # 기업명은 보통 두번째 셀
            if len(cell_texts) > 1:
                corp_name = cell_texts[1]
            
            date_str = ""
            if len(cell_texts) > 4:
                date_str = cell_texts[4]
            
            if rcept_no:
                results.append({
                    "corp_name": corp_name,
                    "report_nm": report_nm or cell_texts[2] if len(cell_texts) > 2 else "",
                    "rcept_no": rcept_no,
                    "rcept_dt": date_str,
                    "row_text": row_text[:200],
                })
                
        except Exception as e:
            log(f"   행 파싱 오류: {e}")
    
    log(f"\n📋 배당 공시 {len(results)}건 추출됨")
    for r in results:
        log(f"   {r['corp_name']} - {r['report_nm']} [{r['rcept_dt']}]")
    
    # 감시 종목 매칭
    watchlist_names = set(stock_names.values())
    matched = []
    for r in results:
        for name in watchlist_names:
            if name in r.get("corp_name", "") or name in r.get("row_text", ""):
                r["matched_name"] = name
                matched.append(r)
                log(f"   🎯 감시 종목: {name}")
                break
    
    log(f"\n감시 종목 배당 공시: {len(matched)}건")
    
    # 배당기준일 파싱
    target_dates = {"2026-05-30", "2026-05-31", "2026-06-01", "2026-06-02"}
    found_targets = []
    
    for r in matched:
        log(f"\n🔍 {r['corp_name']} 기준일 파싱 중... (접수: {r['rcept_no']})")
        try:
            driver.get(f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={r['rcept_no']}")
            time.sleep(3)
            
            iframe = driver.find_element(By.ID, "ifrm")
            viewer_url = iframe.get_attribute("src")
            driver.get(viewer_url)
            time.sleep(3)
            
            text = driver.find_element(By.TAG_NAME, "body").text
            
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
                    snippet = text[max(0, m.start()-100):min(len(text), m.end()+100)]
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
                log(f"   📅 배당기준일: {std_date}")
                r["standard_date"] = std_date
                if std_date in target_dates:
                    log(f"   🔔 ★ 주말/오늘 해당!")
                    found_targets.append(r)
            else:
                log(f"   ⚠️ 파싱 실패")
        except Exception as e:
            log(f"   ❌ 오류: {e}")
    
    driver.quit()
    
    log(f"\n{'='*60}")
    log(f"📊 최종 결과")
    log(f"{'='*60}")
    log(f"전체 배당 공시: {len(results)}건")
    log(f"감시 종목 배당: {len(matched)}건")
    log(f"주말/오늘 기준일: {len(found_targets)}건")
    
    if found_targets:
        for r in found_targets:
            log(f"  🔔 {r['corp_name']} 기준일: {r.get('standard_date','?')} (접수: {r['rcept_no']})")
    else:
        log("  → 해당 없음")
    log(f"{'='*60}")
    
    with open("weekend_check_result.json", "w", encoding="utf-8") as f:
        json.dump({
            "found": len(found_targets),
            "targets": found_targets,
            "all_matched": matched,
            "all_results": results,
        }, f, ensure_ascii=False, indent=2, default=str)
    
    log("\n✅ 완료!")

except Exception as e:
    log(f"❌ 오류: {e}")
    import traceback
    log(traceback.format_exc())
finally:
    logf.close()
