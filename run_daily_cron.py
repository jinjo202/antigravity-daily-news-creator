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

def generate_report_with_gemini(report_type):
    """Generates market report using Gemini API with Google Search grounding."""
    load_env_file(os.path.join(workspace_dir, ".env"))
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        log("[Gemini] GEMINI_API_KEY not found in .env. Skipping AI generation.")
        return None
        
    import urllib.request
    import json
    
    today_date = datetime.now().strftime("%Y-%m-%d")
    month_val = str(int(datetime.now().strftime("%m")))
    day_val = str(int(datetime.now().strftime("%d")))
    today_short_slash = f"{month_val}/{day_val}"
    
    if report_type == "asia":
        prompt = f"""
오늘 날짜는 {today_date} ({today_short_slash}) 입니다.
오늘 마감된 아시아 증시(한국, 일본, 중국, 대만 등) 시황 보고서를 한국어로 작성해주세요.
반드시 아래의 양식과 정보를 포함해야 합니다.

1. 제목 형식: **Title** : 아시아 시황({today_short_slash})
2. 첫 줄: "금일 아시아 증시 시황 보고 드립니다."
3. 둘째 줄: 아시아 증시 전체 요약 (한 줄 또는 두 줄)
4. 셋째 줄: 연초대비 등락 요약 라인
   형식: ※ {today_short_slash}(연초대비): 한국 등락률(연초대비등락률), 일본 등락률(연초대비등락률), 중국 등락률(연초대비등락률)
   예시: ※ 6.18(연초대비): 한국 +2.3%(+115.1), 일본 +1.7%(+41.1), 중국 △0.2%(+3.3)
   (등락률 기호: 상승은 +, 하락은 △ 기호를 사용하세요. 연초대비등락률도 동일하게 기호를 붙이세요.)
5. 본문 문단들:
   - 한국 증시 마감 상황 (코스피/코스닥 지수 및 등락률, 장중 특이사항)
   - 삼성전자, SK하이닉스 등 주요 대형주/반도체주 주가 및 뉴스 (예: SK하이닉스 HBM 관련 소식 등)
   - 일본 증시 마감 상황 (니케이225 지수 및 등락률, 특이사항)
   - 중국 증시 마감 상황 (상해종합지수 및 등락률, 홍콩 항셍지수 및 등락률, 특이사항)
   - 원/달러 환율 및 국채(10년) 금리 마감 수치
6. 마지막 줄: "감사합니다."

중요 규칙:
- 가짜 정보를 적지 말고, Google Search 결과를 사용하여 오늘({today_date}) 실제 마감된 지수와 뉴스를 정확하게 반영하세요.
- 만약 Google Finance 등 특정 금융 서비스에서 오늘 자 수치를 조회할 수 없거나 누락되어 있는 경우, Investing.com, Yahoo Finance 등 다른 공신력 있는 글로벌 금융 정보 사이트들의 최신 수치를 반드시 교차 참고하여 빈칸(공란)이나 누락 없이 모든 지수와 환율/금리 수치를 확실하게 기입하십시오.
- 각 본문 문장 사이에 불필요한 빈 줄을 남발하지 말고 콤팩트하게 작성하세요.
- 존댓말 서술형 본문으로 자연스럽게 작성하세요.
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
            return text_clean.strip()
    except Exception as e:
        log(f"[Gemini ERROR] Failed to call Gemini API: {e}")
        return None

def main():
    log("=== Daily Market Report Automation Start ===")
    
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
            # Check if it has today's content
            with open(today_report_path, "r", encoding="utf-8") as f:
                content = f.read()
            if today_short_slash in content or today_date in content:
                log("today_report.txt is already updated with today's content. Using it directly.")
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
            
            res = subprocess.run(
                [venv_python, v2_script],
                cwd=workspace_dir, capture_output=True, text=True
            )
            log("Execution Output:\n" + res.stdout)
            if res.returncode == 0:
                log("[SUCCESS] Daily Market Report generated and emailed successfully!")
            else:
                log(f"[ERROR] run_daily_v2.py failed with exit code {res.returncode}. Stderr: {res.stderr}")
        except Exception as ex:
            log(f"[ERROR] Failed to execute run_daily_v2.py: {ex}")
    else:
        log("[CRITICAL ERROR] No source report data found. Report generation aborted.")
        
    log("=== Daily Market Report Automation End ===\n")

if __name__ == '__main__':
    main()
