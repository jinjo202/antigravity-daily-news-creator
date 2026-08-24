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

from send_email import send_via_gmail_smtp
from generate_report_us import parse_us_report, create_us_report_document

log_path = os.path.join(workspace_dir, "automation_log_financial.txt")

def log(msg):
    timestamp = datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")
    line = f"{timestamp} {msg}\n"
    print(line.strip())
    with open(log_path, "a", encoding="utf-8") as lf:
        lf.write(line)

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
                
        # Format the paragraphs with correct double/triple newlines
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
        log(f"[Warning] Failed to convert HTML to markdown: {e}")
        return None

def generate_email_body(text):
    """Clean up trailing spaces while preserving explicit single, double and triple newlines."""
    lines = [line.rstrip() for line in text.splitlines()]
    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines)

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
                html_body = payload.decode('utf-8', errors='ignore')
            elif part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                plain_body = payload.decode('utf-8', errors='ignore')
                
        if html_body:
            markdown = convert_html_to_markdown(html_body)
            if markdown:
                return markdown
        return plain_body
    except Exception as ex:
        log(f"[Error] Failed to parse EML file {os.path.basename(eml_path)}: {ex}")
        return None

def generate_report_with_gemini(report_type):
    """Generates market report using Gemini API with Google Search grounding and yfinance data."""
    load_env_file(os.path.join(workspace_dir, ".env"))
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        log("[Gemini] GEMINI_API_KEY not found in .env. Skipping AI generation.")
        return None
        
    import urllib.request
    import json
    
    # 1. Fetch real market data using yfinance to prevent hallucinations
    market_data_text = ""
    try:
        import yfinance as yf
        import pandas as pd
        
        log("[Gemini] Fetching actual market data via yfinance to prevent hallucination...")
        tickers = {
            "S&P 500": "^GSPC",
            "나스닥(Nasdaq)": "^IXIC",
            "다우존스(Dow)": "^DJI",
            "Euro Stoxx 50": "^STOXX50E",
            "미 국채 10년물 금리(%)": "^TNX",
            "원달러 환율(KRW/USD)": "KRW=X",
            "WTI 원유(USD/배럴)": "CL=F"
        }
        
        results = []
        for name, ticker in tickers.items():
            try:
                data = yf.Ticker(ticker).history(period="5d")
                if not data.empty:
                    closes = data['Close']
                    today_val = closes.iloc[-1]
                    if len(closes) > 1:
                        prev_val = closes.iloc[-2]
                        diff = today_val - prev_val
                        pct_diff = (diff / prev_val) * 100
                        results.append(f"- {name}: 오늘 마감 {today_val:.2f} (전일 종가 {prev_val:.2f}, 변동폭 {diff:+.2f}, {pct_diff:+.2f}%)")
                    else:
                        results.append(f"- {name}: 오늘 마감 {today_val:.2f}")
            except Exception as e:
                log(f"[Warning] Failed to fetch {name}: {e}")
                
        if results:
            market_data_text = "【실제 시장 데이터(가장 정확한 종가 기준)】\n" + "\n".join(results) + "\n\n(주의: 위 수치들은 실제 시장 마감 데이터입니다. 반드시 위 수치들을 보고서의 사실 기반으로 우선 사용하여 작성하세요.)"
    except Exception as e:
        log(f"[Warning] Failed to run yfinance fetching logic: {e}")
        market_data_text = "(yfinance 데이터를 불러오지 못했습니다. 구글 검색 결과에 의존하십시오.)"

    today_date = datetime.now().strftime("%Y-%m-%d")
    month_val = str(int(datetime.now().strftime("%m")))
    day_val = str(int(datetime.now().strftime("%d")))
    today_short_slash = f"{month_val}/{day_val}"
    
    # Yesterday's date string for index summary line (e.g. 6/23)
    yesterday = datetime.now() - timedelta(days=1)
    yes_month = str(int(yesterday.strftime("%m")))
    yes_day = str(int(yesterday.strftime("%d")))
    yes_short_slash = f"{yes_month}/{yes_day}"
    
    if report_type == "global":
        prompt = f"""
오늘 날짜는 {today_date} ({today_short_slash}) 입니다.
오늘 마감된(현지시간 전일 마감된) 뉴욕 증시 및 글로벌 금융시장 동향 보고서를 한국어로 작성해주세요.

{market_data_text}

반드시 아래의 양식과 정보, 상세한 문단 구조를 포함해야 합니다:

1. 제목 형식: **Title** : 일일 금융시장 동향({today_short_slash})(안티그래비티버전)

중요 양식 및 구조 규칙 (반드시 준수):
1. **절대로** "미국 증시 동향"이나 "**미국 증시 동향**" 과 같은 제목이나 섹션 헤더(**...**)를 넣지 마십시오.
2. 모든 본문 내용은 아래 샘플처럼 약 20~30자 내외의 짧은 행 단위로 자연스러운 조사의 유무나 문맥 흐름에 맞추어 직접 엔터(줄바꿈)를 쳐서 나누어야 합니다. 긴 단락(Paragraph)으로 길게 이어 쓰지 마십시오.
3. 주가/지수 숫자 요약 줄, 환율 및 금리 수치 줄은 **반드시 다른 서술형 문장과 한 줄에 섞어 쓰지 말고, 독립된 별개의 한 줄**로만 표기하십시오.
4. 아래 샘플처럼 단순한 요약이 아니라 **여러 세부 문단(주식시장 원인 분석, 채권 금리 움직임, 실물 경제 지표 발표 및 구체적 수치, 향후 증시 영향 전망 등)**을 상세하게 작성해야 합니다. 절대 내용을 짧게 축소하지 마십시오.
5. 아래의 샘플의 문단 구도와 세부 정보 밀도를 완벽히 복제하여 작성하십시오:

[샘플 문서의 문단 구조 및 템플릿]
안녕하십니까

{today_short_slash} 국내외 금융시장 동향입니다.

**__뉴욕 증시는 경제 지표 호조에도 불구,__**
**__FOMC 결과를 매파적 동결로 해석하며 장 후반 하락 전환__**했으며,
**__FOMC 전에 마감한 유럽 증시는 유가 하락 영향만 반영해 상승__**했습니다.
* {yes_short_slash}(연초대비): S&P500 등락률(연초대비등락률), 나스닥 등락률(연초대비등락률), Stoxx50 등락률(연초대비등락률)

**__연준이 기준금리를 예상대로 동결(3.50~3.75%)한 가운데,__**
**__점도표 상 올해 연말 기준금리를 기존 3.4%에서 3.8%로 올리며__**
**__연내 1회 인상을 예고__**했고,
올해 경제 성장률은 하향, 물가 상승률은 높였습니다.
(※ 26년 GDP : 3월 전망 2.4% → 6월 2.2%, Core PCE 3월 2.7% → 6월 3.3%)

시장은 이를 매파적 색채로 해석하면서,
**__미 국채 2년 단기물은 +13bp 상승했으며,__**
**__미 국채 10년은 +5bp 상승한 4.49%로 마감__**했습니다.

한편, 미 5월 소매판매는 전월대비 +0.9% 증가해
예상(+0.6%)을 웃돌면서 견조한 경제 상황을 나타냈습니다.
WTI 유가는 배럴당 75.5달러로 하락 마감했습니다.
원달러 환율은 전일 대비 15.0원 상승한 1,530.0원 수준으로 마감했습니다.

연준의 점도표 상향이 물가에 기인한 점이 크기 때문에,
현재 유가가 $75대로 안정된 점을 감안하면,
7월 FOMC에서는 덜 매파적인 모습을 나타낼 가능성이 있어
이번 FOMC 결과는 증시에는 아주 큰 부담은 아닐 것으로 판단합니다.

감사합니다.

중요 규칙 (필수 준수):
- 어떠한 상황에서도 "데이터가 없다", "확인되지 않는다", "제공하기 어렵다", "검색이 불가능하다", "정보 없음", "정보없음" 등의 거절 표현이나 사과 문구를 쓰지 마십시오.
- 만약 특정 수치를 바로 검색할 수 없다면, 위에 제공된 【실제 시장 데이터】를 최우선으로 참고하시고, 그래도 없다면 구글 검색을 활용하십시오.
- 제공된 원달러 환율, 미 국채 10년물 금리 등 숫자가 있다면 그 숫자를 **그대로 인용**하고 전일 대비 상승/하락 여부 코멘트도 그 수치 변동폭을 기준으로 정확하게 작성하십시오. (할루시네이션 절대 금지)
- 연초대비(YTD) 등락률은 뉴스 검색 결과에 직접 나오지 않더라도 아래의 2025년 말 종가 기준을 참고하여 오늘 수치와 직접 계산하여 반드시 소수점 첫째짜리까지 기입하십시오.
  * S&P 500 연초대비 기준값: 6845.50
  * 나스닥 연초대비 기준값: 23241.99
  * Euro Stoxx 50 연초대비 기준값: 4411.39
  * 계산법: ((오늘 종가 - 기준값) / 기준값) * 100
"""
    else:
        return None

    # Use gemini-1.5-pro model for reliability and reduced hallucination compared to flash
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-pro:generateContent?key={api_key}"
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
                # Remove '**--' from the beginning of the text if it exists
                if text_clean.startswith("**--"):
                    text_clean = text_clean[4:].strip()
                # Or replace all occurrences just in case
                text_clean = text_clean.replace("**--", "")
                return text_clean
        except Exception as e:
            log(f"[Gemini ERROR] Attempt {attempt+1}/5 failed to call Gemini API: {e}")
            if attempt < 4:
                # Exponential backoff tailored for heavily rate-limited IPs in GitHub Actions
                sleep_sec = 10 * (attempt + 1)
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
                                    # Ignore test runs sent before 7:30 AM when checking for global report duplicate
                                    if "[일일 금융시장 동향]" in subject_keyword and parsed_dt_kst.hour < 7:
                                        is_dup = False
                                    elif "[일일 금융시장 동향]" in subject_keyword and parsed_dt_kst.hour == 7 and parsed_dt_kst.minute < 30:
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
    log("=== US Daily Market Report Automation Start ===")
    
    # Check if weekend in KST (5=Saturday, 6=Sunday)
    kst_now = datetime.now(timezone(timedelta(hours=9)))
    is_forced = "--force" in sys.argv
    if not is_forced and kst_now.weekday() in [5, 6]:
        log(f"Today is {kst_now.strftime('%A')} (KST). Skipping weekend execution.")
        log("=== US Daily Market Report Automation End ===\n")
        return
        
    if not is_forced and check_already_sent("[일일 금융시장 동향]"):
        log("US Daily Market Report already sent today. Skipping.")
        log("=== US Daily Market Report Automation End ===\n")
        return
        
    today_date = datetime.now().strftime("%Y-%m-%d")
    month_val = str(int(datetime.now().strftime("%m")))
    day_val = str(int(datetime.now().strftime("%d")))
    today_short = f"{month_val}_{day_val}"
    today_short_slash = f"{month_val}/{day_val}"
    
    us_today_report_path = os.path.join(workspace_dir, "us_today_report.txt")
    
    report_updated = False
    
    # Check if a sample EML execution is requested or if we should run a sample run
    is_sample_run = len(sys.argv) > 1 and sys.argv[1] == "--sample"
    
    if is_sample_run:
        log("Sample run requested. Loading FW_ 일일 금융시장 동향(6_16).eml as sample...")
        sample_path = os.path.join(workspace_dir, "FW_ 일일 금융시장 동향(6_16).eml")
        if os.path.exists(sample_path):
            markdown = parse_eml_to_markdown(sample_path)
            if markdown:
                with open(us_today_report_path, 'w', encoding='utf-8') as f:
                    f.write(markdown)
                log("Successfully loaded sample EML body into us_today_report.txt.")
                report_updated = True
        else:
            log("[Error] Sample EML file not found.")

    if not report_updated and os.path.exists(us_today_report_path):
        mtime = datetime.fromtimestamp(os.path.getmtime(us_today_report_path))
        if mtime.strftime("%Y-%m-%d") == today_date:
            # Only reuse if generated in the last 30 minutes to prevent using stale files
            if datetime.now() - mtime < timedelta(minutes=30):
                with open(us_today_report_path, "r", encoding="utf-8") as f:
                    content = f.read()
                if today_short_slash in content or today_date in content:
                    log("us_today_report.txt was updated in the last 30 minutes. Using it directly.")
                    report_updated = True

    # Step 2: If not updated, search for today's .eml file
    if not report_updated:
        log("Searching for today's US market .eml file in workspace and Downloads...")
        found_eml = None
        # Check workspace directory first
        for filename in os.listdir(workspace_dir):
            if filename.endswith(".eml") and "금융시장 동향" in filename and today_short in filename:
                found_eml = os.path.join(workspace_dir, filename)
                break
                
        # If not found in workspace, check Downloads directory
        if not found_eml:
            downloads_dir = os.path.expanduser("~/Downloads")
            if os.path.exists(downloads_dir):
                for filename in os.listdir(downloads_dir):
                    if filename.endswith(".eml") and "금융시장 동향" in filename and today_short in filename:
                        download_path = os.path.join(downloads_dir, filename)
                        dest_path = os.path.join(workspace_dir, filename)
                        log(f"Found today's US EML file in Downloads: {filename}. Copying to workspace...")
                        try:
                            import shutil
                            shutil.copy2(download_path, dest_path)
                            found_eml = dest_path
                            break
                        except Exception as e:
                            log(f"[Error] Failed to copy US EML from Downloads: {e}")
                            
        if found_eml:
            log(f"Found today's EML file: {os.path.basename(found_eml)}. Extracting content...")
            markdown = parse_eml_to_markdown(found_eml)
            if markdown:
                with open(us_today_report_path, 'w', encoding='utf-8') as f:
                    f.write(markdown)
                log("Successfully extracted EML body to us_today_report.txt.")
                report_updated = True
            else:
                log("[Warning] EML file was found but parsing failed.")


    # Step 3: If still not updated, try Gmail IMAP
    if not report_updated:
        log("No updated report text or EML file found. Querying Gmail IMAP...")
        if retrieve_from_gmail_imap("금융시장 동향", us_today_report_path):
            report_updated = True

    # Step 3.5: If still not updated, try Gemini AI autogeneration
    if not report_updated:
        log("No updated report text or EML file found. Attempting autonomous generation via Gemini...")
        report_text = generate_report_with_gemini("global")
        if report_text:
            with open(us_today_report_path, "w", encoding="utf-8") as f:
                f.write(report_text)
            log("Successfully generated today's report autonomously via Gemini and updated us_today_report.txt.")
            report_updated = True

    # Step 4: Send the email
    if report_updated:
        log("Formatting email body...")
        with open(us_today_report_path, "r", encoding="utf-8") as f:
            raw_text = f.read().strip()
            
        if not raw_text:
            log("[CRITICAL ERROR] us_today_report.txt is empty. Aborting.")
            return
            
        email_body = generate_email_body(raw_text)
        
        # Extract title from raw_text or first line (robust against markdown bold/underline syntax)
        first_line = raw_text.split('\n')[0].strip()
        cleaned_first_line = first_line.replace('*', '').replace('_', '').strip()
        title_val = ""
        if cleaned_first_line.lower().startswith('title'):
            colon_idx = cleaned_first_line.find(':')
            if colon_idx != -1:
                title_val = cleaned_first_line[colon_idx + 1:].strip()
                
        if title_val:
            subject = f"[일일 금융시장 동향] {title_val} (안티그래비티버전)"
        else:
            subject = f"[일일 금융시장 동향] 미국시황동향 ({datetime.now().strftime('%m/%d')}) (안티그래비티버전)"
            
        # Determine document date string for the Word document
        today_str = datetime.now().strftime("%Y%m%d")
        doc_date_str = today_str
        if title_val:
            match = re.search(r'\((\d+)/(\d+)\)', title_val)
            if match:
                month = match.group(1).zfill(2)
                day = match.group(2).zfill(2)
                doc_date_str = f"{datetime.now().year}{month}{day}"
                
        output_filename = f"Daily_Market_Report_Official_US_{doc_date_str}.docx"
        output_file = os.path.join(workspace_dir, output_filename)
        
        log(f"Generating Word document: {output_file}...")
        attachment_path = None
        try:
            structured_data = parse_us_report(raw_text)
            create_us_report_document(structured_data, output_file)
            log(f"[SUCCESS] Word document generated at {output_file}")
            attachment_path = output_file
        except Exception as docx_ex:
            log(f"[ERROR] Failed to generate Word document: {docx_ex}")
            
        recipients = ["jin.jo202@gmail.com", "jinyoung22.jo@samsung.com", "jeonghwan.lim@samsung.com"]
        
        log(f"Sending email: '{subject}' to {recipients} with attachment {attachment_path}...")
        try:
            success = send_via_gmail_smtp(recipients, subject, email_body, attachment_path=attachment_path)
            if success:
                log("[SUCCESS] US Daily Market Report emailed successfully!")
            else:
                msg = "[ERROR] Email delivery failed."
                log(msg)
                try:
                    recipients = ["jin.jo202@gmail.com", "jinyoung22.jo@samsung.com", "jeonghwan.lim@samsung.com"]
                    send_via_gmail_smtp(recipients, "[오류 알림] 일일 금융시장 동향 이메일 전송 실패", f"에러 내용: {msg}\n\n최근 실행 로그를 점검해 주십시오.")
                except Exception as alert_ex:
                    log(f"Failed to send failure email alert: {alert_ex}")
        except Exception as ex:
            msg = f"[ERROR] Failed to send email: {ex}"
            log(msg)
            try:
                recipients = ["jin.jo202@gmail.com", "jinyoung22.jo@samsung.com", "jeonghwan.lim@samsung.com"]
                send_via_gmail_smtp(recipients, "[오류 알림] 일일 금융시장 동향 이메일 전송 예외 발생", f"에러 내용: {msg}\n\n최근 실행 로그를 점검해 주십시오.")
            except Exception as alert_ex:
                log(f"Failed to send failure email alert: {alert_ex}")
    else:
        msg = "[CRITICAL ERROR] No source report data found. Aborting."
        log(msg)
        try:
            recipients = ["jin.jo202@gmail.com", "jinyoung22.jo@samsung.com", "jeonghwan.lim@samsung.com"]
            send_via_gmail_smtp(recipients, "[오류 알림] 일일 금융시장 동향 자동 생성 실패 (소스 데이터 누락)", f"에러 내용: {msg}\n\n최근 실행 로그를 점검해 주십시오.")
        except Exception as alert_ex:
            log(f"Failed to send failure email alert: {alert_ex}")
        
    log("=== US Daily Market Report Automation End ===\n")

if __name__ == '__main__':
    main()
