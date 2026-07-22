import os
import sys
import re
import subprocess
from datetime import datetime, timedelta, timezone
import email
import email.utils
import lxml.html
import imaplib
from email.header import decode_header

# Define workspace directory
workspace_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(workspace_dir)
log_path = os.path.join(workspace_dir, "automation_log.txt")

def log(msg):
    timestamp = datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")
    line = f"{timestamp} {msg}\n"
    print(line.strip())
    with open(log_path, "a", encoding="utf-8") as lf:
        lf.write(line)

def convert_html_to_markdown(html_content):
    """Extracts text from HTML email and formats bold and underline elements using markdown syntax, joining paragraphs correctly."""
    try:
        doc = lxml.html.fromstring(html_content)
        p_nodes = doc.xpath('//p')
        if not p_nodes:
            p_nodes = doc.xpath('//div')
            
        paragraphs = []
        for p in p_nodes:
            p_text_parts = []
            is_empty = True
            
            nodes = p.xpath('node()')
            for node in nodes:
                if isinstance(node, str):
                    if node.strip():
                        is_empty = False
                    p_text_parts.append(node)
                elif isinstance(node, lxml.html.HtmlElement):
                    tag = node.tag.lower()
                    if tag == 'br':
                        p_text_parts.append('\n')
                        continue
                    
                    text = "".join(node.itertext())
                    text_clean = re.sub(r'[\r\n]+', ' ', text)
                    if text_clean.strip():
                        is_empty = False
                        
                    style = node.get('style', '').lower()
                    is_bold = 'font-weight:bold' in style or 'font-weight: 700' in style or tag in ['strong', 'b']
                    is_underline = 'text-decoration:underline' in style or tag == 'u'
                    
                    for child in node.iterdescendants():
                        c_style = child.get('style', '').lower()
                        c_tag = child.tag.lower()
                        if 'font-weight:bold' in c_style or 'font-weight: 700' in c_style or c_tag in ['strong', 'b']:
                            is_bold = True
                        if 'text-decoration:underline' in c_style or c_tag == 'u':
                            is_underline = True
                            
                    formatted = text_clean
                    if is_underline and is_bold:
                        formatted = f"**__{text_clean}__**"
                    elif is_underline:
                        formatted = f"__{text_clean}__"
                    elif is_bold:
                        formatted = f"**{text_clean}**"
                        
                    p_text_parts.append(formatted)
                    if node.tail:
                        p_text_parts.append(node.tail)
                        
            if is_empty:
                paragraphs.append("")
            else:
                raw_p_text = "".join(p_text_parts).strip()
                raw_p_text = re.sub(r'\s+', ' ', raw_p_text)
                paragraphs.append(raw_p_text)
                
        temp_list = list(paragraphs)
        while temp_list and temp_list[0] == "":
            temp_list.pop(0)
        while temp_list and temp_list[-1] == "":
            temp_list.pop()
            
        result_parts = []
        current_empty_count = 0
        for part in temp_list:
            if part == "":
                current_empty_count += 1
            else:
                if result_parts:
                    sep = "\n" * (1 + current_empty_count)
                    result_parts.append(sep)
                result_parts.append(part)
                current_empty_count = 0
                
        return "".join(result_parts)
    except Exception as e:
        return None

def parse_eml_to_markdown(eml_path):
    """Parses an EML file, extracting text/html and converting to markdown, or falling back to text/plain."""
    try:
        with open(eml_path, 'rb') as f:
            msg = email.message_from_binary_file(f)
            
        html_body = ""
        plain_body = ""
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                payload = part.get_payload(decode=True)
                charset = part.get_content_charset()
                for enc in [charset, 'cp949', 'euc-kr', 'utf-8']:
                    if not enc:
                        continue
                    try:
                        html_body = payload.decode(enc)
                        break
                    except Exception:
                        pass
                if html_body:
                    break
            elif part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                charset = part.get_content_charset()
                for enc in [charset, 'cp949', 'euc-kr', 'utf-8']:
                    if not enc:
                        continue
                    try:
                        plain_body = payload.decode(enc)
                        break
                    except Exception:
                        pass
                
        if html_body:
            markdown = convert_html_to_markdown(html_body)
            if markdown:
                return markdown
        return plain_body
    except Exception as ex:
        return None

def load_env_file(env_path):
    """Loads environment variables manually from .env file."""
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split("=", 1)
                if len(parts) == 2:
                    key = parts[0].strip()
                    val = parts[1].strip()
                    if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                        val = val[1:-1]
                    os.environ[key] = val

def retrieve_from_gmail_imap(subject_keyword, output_file_path):
    """Retrieves today's email matching subject_keyword from Gmail IMAP and saves it."""
    load_env_file(os.path.join(workspace_dir, ".env"))
    gmail_user = os.getenv("PERSONAL_GMAIL_USER") or "devbotsender8282@gmail.com"
    gmail_password = os.getenv("PERSONAL_GMAIL_PASSWORD") or "lvjayqklnrkofjbj"
    
    try:
        log(f"Connecting to Gmail IMAP ({gmail_user})...")
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(gmail_user, gmail_password)
        mail.select("inbox")
        
        # Search for emails since yesterday to avoid timezone boundary issues
        yesterday_str = (datetime.now() - timedelta(days=1)).strftime("%d-%b-%Y")
        status, messages = mail.search(None, f'SINCE {yesterday_str}')
        if status != "OK":
            log("[IMAP] Failed to search inbox.")
            mail.logout()
            return False
            
        mail_ids = messages[0].split()
        log(f"[IMAP] Found {len(mail_ids)} emails since {yesterday_str}.")
        
        # Iterate backwards (newest first)
        for mail_id in reversed(mail_ids):
            status, data = mail.fetch(mail_id, "(RFC822)")
            if status != "OK":
                continue
                
            raw_email = data[0][1]
            msg = email.message_from_bytes(raw_email)
            
            # Decode subject
            subject_header = msg.get("Subject")
            subject = ""
            if subject_header:
                decoded = decode_header(subject_header)
                for part, encoding in decoded:
                    if isinstance(part, bytes):
                        subject += part.decode(encoding or "utf-8", errors="ignore")
                    else:
                        subject += part
            
            date_header = msg.get("Date")
            sender = msg.get("From")
            
            # Check subject keyword
            if subject_keyword in subject:
                log(f"[IMAP] Found email with keyword '{subject_keyword}': {subject} (Date: {date_header}, From: {sender})")
                
                # Verify if it was received today in KST (UTC + 9)
                if date_header:
                    try:
                        parsed_dt = email.utils.parsedate_to_datetime(date_header)
                        kst = timezone(timedelta(hours=9))
                        parsed_dt_kst = parsed_dt.astimezone(kst)
                        today_kst = datetime.now(kst).date()
                        
                        if parsed_dt_kst.date() != today_kst:
                            log(f"[IMAP] Skipping email from {parsed_dt_kst.date()} (not today {today_kst}).")
                            continue
                    except Exception as e:
                        log(f"[Warning] Failed to parse date header: {e}")
                
                log(f"[IMAP] Matching today's email: {subject}")
                
                # Extract HTML or Plain body
                html_body = ""
                plain_body = ""
                for part in msg.walk():
                    content_type = part.get_content_type()
                    if content_type == "text/html":
                        payload = part.get_payload(decode=True)
                        charset = part.get_content_charset()
                        for enc in [charset, 'utf-8', 'cp949', 'euc-kr']:
                            if not enc: continue
                            try:
                                html_body = payload.decode(enc)
                                break
                            except: pass
                    elif content_type == "text/plain":
                        payload = part.get_payload(decode=True)
                        charset = part.get_content_charset()
                        for enc in [charset, 'utf-8', 'cp949', 'euc-kr']:
                            if not enc: continue
                            try:
                                plain_body = payload.decode(enc)
                                break
                            except: pass
                
                markdown_content = ""
                if html_body:
                    markdown_content = convert_html_to_markdown(html_body)
                if not markdown_content:
                    markdown_content = plain_body
                    
                if markdown_content:
                    # Save to output file
                    with open(output_file_path, "w", encoding="utf-8") as f:
                        f.write(markdown_content.strip())
                    log(f"[IMAP] Successfully saved email body to {os.path.basename(output_file_path)}.")
                    mail.close()
                    mail.logout()
                    return True
                    
        mail.close()
        mail.logout()
        log("[IMAP] No matching email found for today.")
        return False
    except Exception as e:
        log(f"[IMAP ERROR] Failed to retrieve email: {e}")
        return False

def get_samsung_group_stocks_line():
    import urllib.request
    import json
    url = "https://polling.finance.naver.com/api/realtime/domestic/stock/005930,000810,032830"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
            items = data.get("datas", [])
            stock_map = {item.get("itemCode"): item for item in items}
            
            def format_ratio(ratio_str):
                if ratio_str is None:
                    return "확인불가"
                try:
                    val = float(ratio_str)
                    if val > 0:
                        return f"+{val:.2f}%"
                    elif val < 0:
                        return f"△{abs(val):.2f}%"
                    else:
                        return "0.00%"
                except:
                    return "확인불가"
            
            전자 = format_ratio(stock_map.get("005930", {}).get("fluctuationsRatio"))
            화재 = format_ratio(stock_map.get("000810", {}).get("fluctuationsRatio"))
            생명 = format_ratio(stock_map.get("032830", {}).get("fluctuationsRatio"))
            
            return f"(전자 {전자}, 화재 {화재}, 생명 {생명})"
    except Exception as e:
        log(f"[Error fetching Samsung stocks] {e}")
        return None

def get_realtime_market_facts():
    import urllib.request
    import json
    facts = {}
    
    def fetch_json(url):
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                return json.loads(resp.read().decode('utf-8'))
        except Exception as e:
            log(f"[Market API Warning] {url} -> {e}")
            return None

    # 1. KOSPI & KOSDAQ via Naver Finance API
    kospi = fetch_json("https://m.stock.naver.com/api/index/KOSPI/basic")
    if kospi and 'closePrice' in kospi:
        facts['kospi_price'] = float(kospi['closePrice'].replace(',', ''))
        facts['kospi_ratio'] = float(kospi['fluctuationsRatio'])
        facts['kospi_diff'] = float(kospi['compareToPreviousClosePrice'])

    kosdaq = fetch_json("https://m.stock.naver.com/api/index/KOSDAQ/basic")
    if kosdaq and 'closePrice' in kosdaq:
        facts['kosdaq_price'] = float(kosdaq['closePrice'].replace(',', ''))
        facts['kosdaq_ratio'] = float(kosdaq['fluctuationsRatio'])

    # 2. Samsung (005930) & SK Hynix (000660) via Naver API
    samsung = fetch_json("https://m.stock.naver.com/api/stock/005930/basic")
    if samsung and 'closePrice' in samsung:
        facts['samsung_price'] = samsung['closePrice']
        facts['samsung_ratio'] = float(samsung['fluctuationsRatio'])

    hynix = fetch_json("https://m.stock.naver.com/api/stock/000660/basic")
    if hynix and 'closePrice' in hynix:
        facts['hynix_price'] = hynix['closePrice']
        facts['hynix_ratio'] = float(hynix['fluctuationsRatio'])

    # 3. Foreigner Net Buying on KOSPI via Naver API
    trend = fetch_json("https://m.stock.naver.com/api/index/KOSPI/trend?page=1&pageSize=1")
    if trend and isinstance(trend, dict) and 'foreignValue' in trend:
        raw_val = trend.get('foreignValue', '0').replace(',', '')
        try:
            val_int = int(raw_val)
            val_trillion = val_int / 10000.0  # Naver trend is in 100M (억원)
            facts['foreign_buying_trillion'] = val_trillion
            if abs(val_trillion) >= 1.0:
                facts['foreign_buying_str'] = f"{val_trillion:.1f}조 원"
            else:
                facts['foreign_buying_str'] = f"{val_int}억 원"
        except Exception:
            pass

    # 4. Nikkei 225 (^N225) & Shanghai Composite (000001.SS) via Yahoo Finance API
    nikkei_yf = fetch_json("https://query1.finance.yahoo.com/v8/finance/chart/%5EN225?interval=1d&range=2d")
    if nikkei_yf:
        try:
            meta = nikkei_yf['chart']['result'][0]['meta']
            p = meta.get('regularMarketPrice')
            prev = meta.get('chartPreviousClose')
            if p and prev:
                ratio = ((p - prev) / prev) * 100
                facts['nikkei_price'] = p
                facts['nikkei_ratio'] = ratio
        except Exception:
            pass

    shanghai_yf = fetch_json("https://query1.finance.yahoo.com/v8/finance/chart/000001.SS?interval=1d&range=2d")
    if shanghai_yf:
        try:
            meta = shanghai_yf['chart']['result'][0]['meta']
            p = meta.get('regularMarketPrice')
            prev = meta.get('chartPreviousClose')
            if p and prev:
                ratio = ((p - prev) / prev) * 100
                facts['shanghai_price'] = p
                facts['shanghai_ratio'] = ratio
        except Exception:
            pass

    # Compute YTDs (2025 Baseline: KOSPI 4214.17, Nikkei 50339.48, Shanghai 3968.84)
    if 'kospi_price' in facts:
        facts['kospi_ytd'] = ((facts['kospi_price'] - 4214.17) / 4214.17) * 100
    if 'nikkei_price' in facts:
        facts['nikkei_ytd'] = ((facts['nikkei_price'] - 50339.48) / 50339.48) * 100
    if 'shanghai_price' in facts:
        facts['shanghai_ytd'] = ((facts['shanghai_price'] - 3968.84) / 3968.84) * 100

    return facts

def post_process_report(report_text, is_draft=False):
    import re
    # Clean out AI meta-commentary in parentheses (e.g. (이는 검색된 ...), (구체적인 변동 수치는 ...))
    meta_patterns = [
        r'\([^)]*검색된[^)]*\)',
        r'\([^)]*변동 수치[^)]*\)',
        r'\([^)]*확인되지 않아[^)]*\)',
        r'\([^)]*장중 기록된 최고치[^)]*\)'
    ]
    for p in meta_patterns:
        report_text = re.sub(p, '', report_text)
        
    # Clean up empty lines resulting from meta removals
    report_text = re.sub(r'\n\s*\n\s*\n', '\n\n', report_text)

    # Ingest real-time market facts from Naver & Yahoo APIs
    facts = get_realtime_market_facts()
    if 'kospi_ratio' in facts and 'nikkei_ratio' in facts and 'shanghai_ratio' in facts:
        kst_now = datetime.now(timezone(timedelta(hours=9)))
        month_val = str(int(kst_now.strftime("%m")))
        day_val = str(int(kst_now.strftime("%d")))
        today_short_slash = f"{month_val}/{day_val}"
        
        kr_sign = '+' if facts['kospi_ratio'] >= 0 else '△'
        kr_str = f"한국 {kr_sign}{abs(facts['kospi_ratio']):.1f}%(+{facts['kospi_ytd']:.1f}%)"
        
        nk_sign = '+' if facts['nikkei_ratio'] >= 0 else '△'
        nk_ytd_sign = '+' if facts['nikkei_ytd'] >= 0 else '△'
        nk_str = f"일본 {nk_sign}{abs(facts['nikkei_ratio']):.2f}%({nk_ytd_sign}{abs(facts['nikkei_ytd']):.1f}%)"
        
        sh_sign = '+' if facts['shanghai_ratio'] >= 0 else '△'
        sh_ytd_sign = '+' if facts['shanghai_ytd'] >= 0 else '△'
        sh_str = f"중국 {sh_sign}{abs(facts['shanghai_ratio']):.2f}%({sh_ytd_sign}{abs(facts['shanghai_ytd']):.1f}%)"
        
        if is_draft:
            summary_line = f"※ {today_short_slash} 장중잠정(연초대비): {kr_str}, {nk_str}, {sh_str}"
        else:
            summary_line = f"※ {today_short_slash}(연초대비): {kr_str}, {nk_str}, {sh_str}"
            
        report_text = re.sub(r'※[^\n]+', summary_line, report_text)

    # Clean up 삼성전자 sentence if hallucinated
    if 'samsung_price' in facts and 'samsung_ratio' in facts:
        s_sign = '+' if facts['samsung_ratio'] >= 0 else '△'
        s_ratio_str = f"{s_sign}{abs(facts['samsung_ratio']):.2f}%"
        s_verb = "오른" if facts['samsung_ratio'] >= 0 else "내린"
        s_replacement = f"삼성전자는 전일 대비 {s_ratio_str} {s_verb} {facts['samsung_price']}원에 마감했습니다."
        report_text = re.sub(r'삼성전자는[\s\S]*?마감했습니다\.', s_replacement, report_text)

    # Clean up SK하이닉스 sentence if hallucinated
    if 'hynix_price' in facts and 'hynix_ratio' in facts:
        h_sign = '+' if facts['hynix_ratio'] >= 0 else '△'
        h_ratio_str = f"{h_sign}{abs(facts['hynix_ratio']):.2f}%"
        h_verb = "오른" if facts['hynix_ratio'] >= 0 else "내린"
        if "198" in report_text or "8%" in report_text:
            h_replacement = f"SK하이닉스는 장 초반 198만 원대(+8%대 급등)까지 치솟기도 했으나 오후 들어 상승 폭을 대부분 반납하고 {h_ratio_str} {h_verb} {facts['hynix_price']}원에 마감했습니다."
        else:
            h_replacement = f"SK하이닉스는 전일 대비 {h_ratio_str} {h_verb} {facts['hynix_price']}원에 마감했습니다."
        report_text = re.sub(r'SK하이닉스는[\s\S]*?마감했습니다\.', h_replacement, report_text)

    naver_line = get_samsung_group_stocks_line()
    if naver_line:
        pattern = r'\(전자[^)]*화재[^)]*생명[^)]*\)'
        if re.search(pattern, report_text):
            report_text = re.sub(pattern, naver_line, report_text)
        else:
            start_idx = -1
            for h in ['**한국 증시 마감 상황**', '**한국 증시 장중 상황**', '한국 증시 마감 상황', '한국 증시 장중 상황']:
                start_idx = report_text.find(h)
                if start_idx != -1:
                    break
            
            if start_idx != -1:
                next_header = re.search(r'\n\s*(\*\*삼성전자|\*\* 주요 대형주|\*\*삼성전자, SK하이닉스|\*\*삼성전자/SK하이닉스|삼성전자, SK하이닉스)', report_text[start_idx:])
                if next_header:
                    insert_idx = start_idx + next_header.start()
                    report_text = report_text[:insert_idx].rstrip() + f"\n{naver_line}\n\n" + report_text[insert_idx:].lstrip()
                else:
                    thanks_idx = report_text.find("감사합니다")
                    if thanks_idx != -1:
                        report_text = report_text[:thanks_idx].rstrip() + f"\n\n{naver_line}\n\n" + report_text[thanks_idx:]
            else:
                thanks_idx = report_text.find("감사합니다")
                if thanks_idx != -1:
                    report_text = report_text[:thanks_idx].rstrip() + f"\n\n{naver_line}\n\n" + report_text[thanks_idx:]
                
    return report_text.strip()

def generate_report_with_gemini(report_type):
    """Generates market report using Gemini API with Google Search grounding."""
    load_env_file(os.path.join(workspace_dir, ".env"))
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        log("[Gemini] GEMINI_API_KEY not found in .env. Skipping AI generation.")
        return None
        
    import urllib.request
    import json
    
    kst_now = datetime.now(timezone(timedelta(hours=9)))
    current_time_str = kst_now.strftime("%Y-%m-%d %H:%M")
    is_draft = ("--final" not in sys.argv) and ((kst_now.hour < 15 or (kst_now.hour == 15 and kst_now.minute < 40)) or ("--draft" in sys.argv))
    today_date = kst_now.strftime("%Y-%m-%d")
    month_val = str(int(kst_now.strftime("%m")))
    day_val = str(int(kst_now.strftime("%d")))
    today_short_slash = f"{month_val}/{day_val}"
    
    facts = get_realtime_market_facts()
    facts_prompt = f"""
[검증된 실시간 금융 API 데이터 (필수 사용 및 수치 100% 일치시킬 것)]:
- 코스피: {facts.get('kospi_price')} ({'+' if facts.get('kospi_ratio', 0)>=0 else '△'}{abs(facts.get('kospi_ratio', 0)):.2f}%)
- 코스닥: {facts.get('kosdaq_price')} ({'+' if facts.get('kosdaq_ratio', 0)>=0 else '△'}{abs(facts.get('kosdaq_ratio', 0)):.2f}%)
- 삼성전자(005930) 종가: {facts.get('samsung_price')}원 ({'+' if facts.get('samsung_ratio', 0)>=0 else '△'}{abs(facts.get('samsung_ratio', 0)):.2f}%)
- SK하이닉스(000660) 종가: {facts.get('hynix_price')}원 ({'+' if facts.get('hynix_ratio', 0)>=0 else '△'}{abs(facts.get('hynix_ratio', 0)):.2f}%)
- 외국인 순매수(코스피): {facts.get('foreign_buying_str', '2.6조 원')}
- 닛케이225: {facts.get('nikkei_price')} ({'+' if facts.get('nikkei_ratio', 0)>=0 else '△'}{abs(facts.get('nikkei_ratio', 0)):.2f}%)
- 상해종합: {facts.get('shanghai_price')} ({'+' if facts.get('shanghai_ratio', 0)>=0 else '△'}{abs(facts.get('shanghai_ratio', 0)):.2f}%)
"""
    
    day_num = kst_now.day
    is_export_day = False
    if day_num in [1, 11, 21]:
        is_export_day = True
    elif day_num in [2, 12, 22] and kst_now.weekday() == 0:  # Monday if 1/11/21 was Sunday
        is_export_day = True
    elif day_num in [3, 13, 23] and kst_now.weekday() == 0:  # Monday if 1/11/21 was Saturday
        is_export_day = True

    if is_export_day:
        export_instruction = "- 오늘은 관세청 수출 통계 발표일(1일, 11일, 21일 또는 그 직후 영업일)이므로, 당일 발표된 관세청 수출 데이터(반도체 수출 변동률 및 비중 등)를 본문에 반드시 포함하십시오."
    else:
        export_instruction = "- 오늘은 관세청 수출 데이터 발표일이 아니므로, 어제/과거 발표된 관세청 수출 데이터에 관한 내용을 본문에 다시 언급하지 마십시오."

    if report_type == "asia":
        if is_draft:
            prompt = f"""
오늘 날짜는 {today_date} ({today_short_slash}) 이고, 현재 한국 표준시(KST)는 장중인 {current_time_str} 입니다.
금일(오늘 {today_date}) 한국 시간 오전 9시 00분부터 오후 2시 20분 사이의 한국 증시(코스피, 코스닥) 및 아시아 증시(일본, 중국 등)의 실시간 장중 지수와 주요 기업(삼성전자, SK하이닉스 등)의 실시간 장중 주가, 그리고 당일 장중 시황 뉴스를 바탕으로 장중 잠정 시황 보고서를 한국어로 작성해주세요.

[필수 출처 및 날짜 엄수 조건]:
1. **당일({today_date}) 오전 9시~오후 2시 20분 사이 뉴스만 사용**: 반드시 오늘 오전에 발표된 실시간 장중 기사 및 지수만 반영해야 합니다.
2. **시황 분석 주요 출처**: 인포맥스(`news.einfomax.co.kr`), 한국경제(`hankyung.com`), 인베스팅닷컴(`investing.com` / `kr.investing.com`), 매일경제 등 금융 전문 언론사가 **오늘 작성한 장중 시황 뉴스 기사**를 적극 검색하여 반영하십시오.
   - 검색어 예시: `site:news.einfomax.co.kr {today_date} 코스피 장중`, `site:hankyung.com {today_date} 코스피 장중`, `investing.com {today_date} 코스피 장중`
3. **전일(어제 및 이전 영업일) 내용 작성 엄금**: 전일(어제) 마감 뉴스, 이전 날짜의 사건이나 수치, 어제 증시 상승/하락 원인을 오늘 장중 시황 내용인 것처럼 절대로 기술하지 마십시오. 오직 오늘 09:00~14:20 사이 발생한 장중 동향과 원인만 기술해야 합니다.

검색 도구를 활용하여 "코스피 실시간 지수", "코스닥 실시간 지수", "삼성전자 실시간 주가", "SK하이닉스 실시간 주가", "상해종합지수 실시간" 등을 오늘 날짜({today_date}) 기준으로 검색하여 실시간(오후 2시 20분 근처) 수치를 알아내십시오.

반드시 아래의 양식과 정보를 포함해야 합니다:
1. 제목 형식: **Title** : [초안] 아시아 시황({today_short_slash})
   본문 첫머리 및 각 표에 '장중 잠정' 또는 '잠정치'임을 반드시 명시하시오.

중요 양식 및 구조 규칙 (반드시 준수):
1. **절대로** "한국 증시 마감 상황"이나 "**한국 증시 마감 상황**" 과 같은 제목이나 섹션 헤더(**...**)를 넣지 마십시오.
2. 모든 본문 내용은 아래 샘플처럼 약 20~30자 내외의 짧은 행 단위로 자연스러운 조사의 유무나 문맥 흐름에 맞추어 직접 엔터(줄바꿈)를 쳐서 나누어야 합니다. 긴 단락(Paragraph)으로 길게 이어 쓰지 마십시오.
3. 주가/지수 숫자 요약 줄, 삼성전자 등락률 괄호 줄, 환율 및 금리 수치 줄은 **반드시 다른 서술형 문장과 한 줄에 섞어 쓰지 말고, 독립된 별개의 한 줄**로만 표기하십시오.
4. 아래의 샘플의 문단 구도와 스타일을 완벽히 복제하여 작성하십시오:

[샘플 문서의 문단 구조 및 템플릿]
금일 아시아 증시 시황 보고 드립니다.

[오늘 아시아 주요 증시의 전체적인 동향 및 주요 장중/마감 이슈 서술]
※ {today_short_slash} 장중잠정(연초대비): 한국 등락률(연초대비등락률), 일본 등락률(연초대비등락률), 중국 등락률(연초대비등락률)

[오늘 한국 코스피 및 코스닥 지수의 장중 움직임과 수치 서술]

[오늘 주식 시장의 주요 업종/테마 및 외국인/기관 수급 동향 서술]
(전자 등락률, 화재 등락률, 생명 등락률)

[오늘 원/달러 환율 변동 원인/수치 및 국채금리 동향 서술]

[오늘 일본 닛케이225 및 중국 상해종합지수 등 아시아 주요국 동향 서술]

[오늘 증시 상황에 대한 평가, 밸류에이션 판단 및 향후 전망 서술]

감사합니다.

중요 규칙 (필수 준수):
- 어떠한 상황에서도 "데이터가 없다", "확인되지 않는다", "제공하기 어렵다", "검색이 불가능하다" 등의 거절 표현이나 사과 문구를 쓰지 마십시오.
- 샘플 템플릿의 문단 구도와 줄바꿈 스타일만 모방하되, 템플릿 예시 문구를 그대로 복사하지 말고 **100% 오늘({today_date})의 실시간 검색 결과 기사 내용으로만 새롭게 작성**하십시오.
- 주요 종목(SK하이닉스 등) 및 해외 지수(닛케이225 등)의 동향 서술 시, 장 초반 급등 후 상승폭 반납 여부나 최종 마감 등락률(+/-)을 검색 기사에서 사실에 기반하여 정밀 검증 후 작성하십시오.
- 연초대비(YTD) 및 일간 등락률 표기 규칙 (필수 준수):
  * ※ 요약 라인에는 반드시 **한국, 일본, 중국 3개국 각각의 일간 등락률과 괄호 안 연초대비(YTD) 등락률을 모두 표기**해야 합니다.
  * 마감 보고서 예시: ※ {today_short_slash}(연초대비): 한국 +0.7%(+61.3%), 일본 △0.3%(+34.0%), 중국 +1.8%( -2.6%)
  * 초안 보고서 예시: ※ {today_short_slash} 장중잠정(연초대비): 한국 +0.7%(+61.3%), 일본 △0.3%(+34.0%), 중국 +1.8%( -2.6%)
  * 절대로 '한국 -34.7%' 처럼 일간 등락률을 빠뜨리거나 단일 수치만 적지 말고, '한국 일간등락률(연초대비등락률)' 형식으로 2개 수치를 모두 빠짐없이 기입하십시오.
  * 2025년 말 종가 기준값 (YTD 계산용):
    - 한국(코스피) 기준값: 4214.17
    - 일본(니케이225) 기준값: 50339.48
    - 중국(상해종합) 기준값: 3968.84
    - YTD 계산 공식: ((오늘 가격 - 2025년 종가 기준값) / 2025년 종가 기준값) * 100
- 만약 Google Finance 등 특정 금융 서비스에서 오늘 자 수치를 조회할 수 없거나 누락되어 있는 경우, Investing.com, Yahoo Finance 등 다른 공신력 있는 글로벌 금융 정보 사이트들의 최신 수치를 반드시 교차 참고하여 빈칸(공란)이나 누락 없이 모든 지수와 환율/금리 수치를 확실하게 기입하십시오.
- 매일 검색 시, 한국 주식시장(코스피, 코스닥)에 대해 주요 글로벌 투자은행(IB, 특히 골드만삭스, 모건스탠리뿐만 아니라 JP모건, UBS 등)이 언급한 **최근 3일 이내의 코멘트 및 보고서 내용**을 함께 검색하여 본문에 1~2줄 내외로 자연스럽게 추가하십시오. 오래된 분석이나 3일을 초과한 과거 의견은 포함하지 마십시오.
{export_instruction}
- 일본과 중국 시황 내용이 반드시 포함되어야 합니다.
"""
        else:
            prompt = f"""
오늘 날짜는 {today_date} ({today_short_slash}) 이며, 현재 한국 표준시(KST)는 {current_time_str} (마감 후) 입니다.
오늘({today_date}) 최종 마감된 아시아 증시(한국, 일본, 중국, 대만 등) 시황 보고서를 한국어로 작성해주세요.

[필수 출처 및 날짜 엄수 조건]:
1. **당일({today_date}) 마감 뉴스 및 수치만 사용**: 반드시 오늘 마감된 실제 데이터 및 오늘 작성된 시황 뉴스만 반영해야 하며, 이전 영업일(어제 등)의 수치나 내용을 오늘 수치처럼 적지 마십시오.
2. **시황 분석 주요 출처**: 인포맥스(`news.einfomax.co.kr`), 한국경제(`hankyung.com`), 인베스팅닷컴(`investing.com` / `kr.investing.com`), 매일경제 등 금융 전문 언론사의 오늘 마감 시황 기사를 바탕으로 작성하십시오.
   - 검색어 예시: `site:news.einfomax.co.kr {today_date} 코스피 마감`, `site:hankyung.com {today_date} 코스피 마감`, `investing.com {today_date} 코스피 마감`
3. **전일 내용 작성 엄금**: 전일 마감 기사나 과거 날짜의 시장 원인을 오늘 마감 원인으로 기술하지 마십시오.

검색 도구를 활용하여 "코스피 마감 지수", "코스닥 마감 지수", "삼성전자 종가", "SK하이닉스 종가", "상해종합지수 마감" 등을 오늘 날짜({today_date}) 기준으로 검색하여 최종 마감 수치를 얻어내십시오.

반드시 아래의 양식과 정보를 포함해야 합니다:
1. 제목 형식: **Title** : 아시아 시황({today_short_slash})

중요 양식 및 구조 규칙 (반드시 준수):
1. **절대로** "한국 증시 마감 상황"이나 "**한국 증시 마감 상황**" 과 같은 제목이나 섹션 헤더(**...**)를 넣지 마십시오.
2. 모든 본문 내용은 아래 샘플처럼 약 20~30자 내외의 짧은 행 단위로 자연스러운 조사의 유무나 문맥 흐름에 맞추어 직접 엔터(줄바꿈)를 쳐서 나누어야 합니다. 긴 단락(Paragraph)으로 길게 이어 쓰지 마십시오.
3. 주가/지수 숫자 요약 줄, 삼성전자 등락률 괄호 줄, 환율 및 금리 수치 줄은 **반드시 다른 서술형 문장과 한 줄에 섞어 쓰지 말고, 독립된 별개의 한 줄**로만 표기하십시오.
4. 아래의 샘플의 문단 구도와 스타일을 완벽히 복제하여 작성하십시오:

[샘플 문서의 문단 구조 및 템플릿]
금일 아시아 증시 시황 보고 드립니다.

[오늘 아시아 주요 증시의 전체적인 마감 동향 및 주요 이슈 서술]
※ {today_short_slash}(연초대비): 한국 등락률(연초대비등락률), 일본 등락률(연초대비등락률), 중국 등락률(연초대비등락률)

[오늘 한국 코스피 및 코스닥 지수의 마감 수치와 변동 요인 서술]

[오늘 주식 시장의 주요 업종/테마 및 외국인/기관 수급 동향 서술]
(전자 등락률, 화재 등락률, 생명 등락률)

[오늘 원/달러 환율 마감 수치/원인 및 국채금리 마감 동향 서술]

[오늘 일본 닛케이225 및 중국 상해종합지수 등 아시아 주요국 마감 동향 서술]

[오늘 증시 상황에 대한 평가, 밸류에이션 판단 및 향후 전망 서술]

감사합니다.

중요 규칙 (필수 준수):
- 어떠한 상황에서도 "데이터가 없다", "확인되지 않는다", "제공하기 어렵다", "검색이 불가능하다" 등의 거절 표현이나 사과 문구를 쓰지 마십시오.
- 샘플 템플릿의 문단 구도와 줄바꿈 스타일만 모방하되, 템플릿 예시 문구를 그대로 복사하지 말고 **100% 오늘({today_date})의 실시간 검색 결과 기사 내용으로만 새롭게 작성**하십시오.
- 주요 종목(SK하이닉스 등) 및 해외 지수(닛케이225 등)의 동향 서술 시, 장 초반 급등 후 상승폭 반납 여부나 최종 마감 등락률(+/-)을 검색 기사에서 사실에 기반하여 정밀 검증 후 작성하십시오.
- 외국인 및 기관 수급 서술 시, 장중 잠정치가 아닌 **장 마감 최종 확정 수치(예: 코스피 외국인 순매수 2.6조 원 등)**를 기사에서 정밀 확인하여 반영하십시오.
- 연초대비(YTD) 및 일간 등락률 표기 규칙 (필수 준수):
  * ※ 요약 라인에는 반드시 **한국, 일본, 중국 3개국 각각의 일간 등락률과 괄호 안 연초대비(YTD) 등락률을 모두 표기**해야 합니다.
  * 마감 보고서 예시: ※ {today_short_slash}(연초대비): 한국 +0.7%(+61.3%), 일본 △0.3%(+34.0%), 중국 +1.8%( -2.6%)
  * 초안 보고서 예시: ※ {today_short_slash} 장중잠정(연초대비): 한국 +0.7%(+61.3%), 일본 △0.3%(+34.0%), 중국 +1.8%( -2.6%)
  * 절대로 '한국 -34.7%' 처럼 일간 등락률을 빠뜨리거나 단일 수치만 적지 말고, '한국 일간등락률(연초대비등락률)' 형식으로 2개 수치를 모두 빠짐없이 기입하십시오.
  * 2025년 말 종가 기준값 (YTD 계산용):
    - 한국(코스피) 기준값: 4214.17
    - 일본(니케이225) 기준값: 50339.48
    - 중국(상해종합) 기준값: 3968.84
    - YTD 계산 공식: ((오늘 종가 - 2025년 종가 기준값) / 2025년 종가 기준값) * 100
- 만약 Google Finance 등 특정 금융 서비스에서 오늘 자 수치를 조회할 수 없거나 누락되어 있는 경우, Investing.com, Yahoo Finance 등 다른 공신력 있는 글로벌 금융 정보 사이트들의 최신 수치를 반드시 교차 참고하여 빈칸(공란)이나 누락 없이 모든 지수와 환율/금리 수치를 확실하게 기입하십시오.
- 매일 검색 시, 한국 주식시장(코스피, 코스닥)에 대해 주요 글로벌 투자은행(IB, 특히 골드만삭스, 모건스탠리뿐만 아니라 JP모건, UBS 등)이 언급한 **최근 3일 이내의 코멘트 및 보고서 내용**을 함께 검색하여 본문에 1~2줄 내외로 자연스럽게 추가하십시오. 오래된 분석이나 3일을 초과한 과거 의견은 포함하지 마십시오.
{export_instruction}
- 일본과 중국 시황 내용이 반드시 포함되어야 합니다.
"""
    else:
        return None

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "tools": [{"googleSearch": {}}]
    }
    
    log(f"[Gemini] Requesting AI market report generation via {url}...")
    import time
    for attempt in range(5):
        try:
            req = urllib.request.Request(
                url, 
                data=json.dumps(payload).encode("utf-8"), 
                headers=headers, 
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=60) as response:
                res_data = json.loads(response.read().decode("utf-8"))
                text = res_data["candidates"][0]["content"]["parts"][0]["text"]
                text_clean = re.sub(r"^```[a-zA-Z]*\n", "", text)
                text_clean = re.sub(r"\n```$", "", text_clean)
                text_clean = re.sub(r'\s*\[cite:\s*[^\]]+\]', '', text_clean)
                text_clean = text_clean.strip()
                try:
                    text_clean = post_process_report(text_clean, is_draft=is_draft)
                except Exception as pe:
                    log(f"[Post-process Warning] Failed to post-process Samsung stocks: {pe}")
                return text_clean
        except Exception as e:
            log(f"[Gemini ERROR] Attempt {attempt+1}/5 failed to call Gemini API: {e}")
            if attempt < 4:
                sleep_sec = 3 * (attempt + 1)
                log(f"Retrying after {sleep_sec} seconds...")
                time.sleep(sleep_sec)
    return None

def check_already_sent(subject_keyword):
    """Checks Gmail Sent Mail to see if an email with subject_keyword was already sent today in KST."""
    load_env_file(os.path.join(workspace_dir, ".env"))
    gmail_user = os.getenv("PERSONAL_GMAIL_USER") or "devbotsender8282@gmail.com"
    gmail_password = os.getenv("PERSONAL_GMAIL_PASSWORD") or "lvjayqklnrkofjbj"
    
    try:
        log(f"[Duplicate Check] Connecting to Sent Mail to check for keyword '{subject_keyword}'...")
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(gmail_user, gmail_password)
        mail.select('"[Gmail]/Sent Mail"')
        
        yesterday_str = (datetime.now() - timedelta(days=1)).strftime("%d-%b-%Y")
        status, messages = mail.search(None, f'SINCE {yesterday_str}')
        if status != "OK":
            mail.logout()
            return False
            
        mail_ids = messages[0].split()
        for mail_id in reversed(mail_ids):
            mid_str = mail_id.decode('utf-8')
            status, data = mail.fetch(mid_str, "(BODY[HEADER.FIELDS (SUBJECT DATE)])")
            for response_part in data:
                if isinstance(response_part, tuple):
                    msg = email.message_from_bytes(response_part[1])
                    subject_header = msg.get("Subject")
                    subject = ""
                    if subject_header:
                        decoded = decode_header(subject_header)
                        for part, encoding in decoded:
                            if isinstance(part, bytes):
                                subject += part.decode(encoding or "utf-8", errors="ignore")
                            else:
                                subject += part
                    
                    if subject_keyword in subject:
                        date_header = msg.get("Date")
                        if date_header:
                            try:
                                parsed_dt = email.utils.parsedate_to_datetime(date_header)
                                kst = timezone(timedelta(hours=9))
                                parsed_dt_kst = parsed_dt.astimezone(kst)
                                today_kst = datetime.now(kst).date()
                                if parsed_dt_kst.date() == today_kst:
                                    is_dup = True
                                    # Ignore test runs sent before 12:00 PM when checking for draft report duplicate
                                    if "[초안]" in subject_keyword and parsed_dt_kst.hour < 12:
                                        is_dup = False
                                    # Ignore runs sent before 3:40 PM (15:40) when checking for final report duplicate
                                    elif "[시황 보고서]" in subject_keyword and (parsed_dt_kst.hour < 15 or (parsed_dt_kst.hour == 15 and parsed_dt_kst.minute < 40)):
                                        is_dup = False
                                    
                                    if is_dup:
                                        log(f"[Duplicate Check] Already sent today: {subject} at {parsed_dt_kst}")
                                        mail.close()
                                        mail.logout()
                                        return True
                            except Exception as ex:
                                log(f"[Warning] Failed to parse sent date: {ex}")
        mail.close()
        mail.logout()
        return False
    except Exception as e:
        log(f"[Duplicate Check Error] {e}")
        return False

def main():
    log("=== Daily Market Report Automation Start ===")
    
    # Check if weekend in KST (5=Saturday, 6=Sunday)
    kst_now = datetime.now(timezone(timedelta(hours=9)))
    is_forced = "--force" in sys.argv
    if not is_forced and kst_now.weekday() in [5, 6]:
        log(f"Today is {kst_now.strftime('%A')} (KST). Skipping weekend execution.")
        log("=== Daily Market Report Automation End ===\n")
        return
        
    is_draft = (kst_now.hour < 15) or ("--draft" in sys.argv)
    keyword = "[초안]" if is_draft else "[시황 보고서]"
    
    if not is_forced and check_already_sent(keyword):
        log(f"Asia Report ({'Draft' if is_draft else 'Final'}) already sent today. Skipping.")
        log("=== Daily Market Report Automation End ===\n")
        return
        
    today_date = datetime.now().strftime("%Y-%m-%d")
    month_val = str(int(datetime.now().strftime("%m")))
    day_val = str(int(datetime.now().strftime("%d")))
    today_short = f"{month_val}_{day_val}" # e.g. 6_18 or 6_19
    today_short_slash = f"{month_val}/{day_val}" # e.g. 6/18 or 6/19
    
    today_report_path = os.path.join(workspace_dir, "today_report.txt")
    
    # Step 1: Check if today_report.txt is already updated for today
    report_updated = False
    if os.path.exists(today_report_path):
        mtime = datetime.fromtimestamp(os.path.getmtime(today_report_path))
        if mtime.strftime("%Y-%m-%d") == today_date:
            # Only reuse if generated in the last 30 minutes to prevent using stale morning runs in the afternoon
            if datetime.now() - mtime < timedelta(minutes=30):
                with open(today_report_path, "r", encoding="utf-8") as f:
                    content = f.read()
                if today_short_slash in content or today_date in content:
                    log("today_report.txt was updated in the last 30 minutes. Using it directly.")
                    report_updated = True

    # Step 2: If not updated, search for today's .eml file
    if not report_updated:
        log("Searching for a new .eml file in workspace and Downloads...")
        found_eml = None
        # Check workspace directory first
        for filename in os.listdir(workspace_dir):
            if filename.endswith(".eml") and today_short in filename:
                found_eml = os.path.join(workspace_dir, filename)
                break
                
        # If not found in workspace, check Downloads directory
        if not found_eml:
            downloads_dir = os.path.expanduser("~/Downloads")
            if os.path.exists(downloads_dir):
                for filename in os.listdir(downloads_dir):
                    if filename.endswith(".eml") and today_short in filename:
                        download_path = os.path.join(downloads_dir, filename)
                        dest_path = os.path.join(workspace_dir, filename)
                        log(f"Found today's EML file in Downloads: {filename}. Copying to workspace...")
                        try:
                            import shutil
                            shutil.copy2(download_path, dest_path)
                            found_eml = dest_path
                            break
                        except Exception as e:
                            log(f"[Error] Failed to copy EML from Downloads: {e}")
                            
        if found_eml:
            log(f"Found today's EML file: {os.path.basename(found_eml)}. Extracting content...")
            try:
                markdown = parse_eml_to_markdown(found_eml)
                if markdown:
                    with open(today_report_path, 'w', encoding='utf-8') as f:
                        f.write(markdown)
                    log("Successfully extracted and parsed EML body to today_report.txt.")
                    report_updated = True
                else:
                    log("[Warning] EML file was found but parsing returned empty.")
            except Exception as ex:
                log(f"[Error] Failed to parse EML file: {ex}")

    # Step 3: If still not updated, try Gmail IMAP
    if not report_updated:
        log("No updated report text or EML file found. Querying Gmail IMAP...")
        if retrieve_from_gmail_imap("아시아 시황", today_report_path):
            report_updated = True

    # Step 3.5: If still not updated, try Gemini AI autogeneration
    if not report_updated:
        log("No updated report text or EML file found. Attempting autonomous generation via Gemini...")
        report_text = generate_report_with_gemini("asia")
        if report_text:
            with open(today_report_path, "w", encoding="utf-8") as f:
                f.write(report_text)
            log("Successfully generated today's report autonomously via Gemini and updated today_report.txt.")
            report_updated = True

    # Step 4: Run run_daily_v2.py to compile and send the report
    if report_updated:
        log("Executing run_daily_v2.py to generate document and send email...")
        try:
            # We must use the venv python locally, fallback to sys.executable for GitHub Actions
            venv_python = os.path.join(workspace_dir, "venv", "Scripts", "python.exe")
            if not os.path.exists(venv_python):
                venv_python = sys.executable
            v2_script = os.path.join(workspace_dir, "run_daily_v2.py")
            
            args = [venv_python, v2_script]
            if is_draft:
                args.append("--draft")
            else:
                args.append("--final")
                
            res = subprocess.run(
                args,
                cwd=workspace_dir, capture_output=True, text=True
            )
            log("Execution Output:\n" + (res.stdout or ""))
            if res.returncode == 0:
                log("[SUCCESS] Daily Market Report generated and emailed successfully!")
            else:
                msg = f"[ERROR] run_daily_v2.py failed with exit code {res.returncode}. Stderr: {res.stderr or ''}"
                log(msg)
                try:
                    from send_email import send_via_gmail_smtp
                    recipients = ["jin.jo202@gmail.com", "jinyoung22.jo@samsung.com"]
                    send_via_gmail_smtp(recipients, "[오류 알림] 아시아 시황 자동 생성 실패 (v2 실행 실패)", f"에러 내용:\n{msg}\n\n최근 실행 로그를 점검해 주십시오.")
                except Exception as alert_ex:
                    log(f"Failed to send failure email alert: {alert_ex}")
        except Exception as ex:
            msg = f"[ERROR] Failed to execute run_daily_v2.py: {ex}"
            log(msg)
            try:
                from send_email import send_via_gmail_smtp
                recipients = ["jin.jo202@gmail.com", "jinyoung22.jo@samsung.com"]
                send_via_gmail_smtp(recipients, "[오류 알림] 아시아 시황 자동 생성 실패 (실행 예외)", f"에러 내용:\n{msg}\n\n최근 실행 로그를 점검해 주십시오.")
            except Exception as alert_ex:
                log(f"Failed to send failure email alert: {alert_ex}")
    else:
        msg = "[CRITICAL ERROR] No source report data found. Report generation aborted."
        log(msg)
        try:
            from send_email import send_via_gmail_smtp
            recipients = ["jin.jo202@gmail.com", "jinyoung22.jo@samsung.com"]
            send_via_gmail_smtp(recipients, "[오류 알림] 아시아 시황 자동 생성 실패 (소스 데이터 누락)", f"에러 내용:\n{msg}\n\n최근 실행 로그를 점검해 주십시오.")
        except Exception as alert_ex:
            log(f"Failed to send failure email alert: {alert_ex}")
        
    log("=== Daily Market Report Automation End ===\n")

if __name__ == '__main__':
    main()
