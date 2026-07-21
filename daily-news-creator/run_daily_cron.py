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

def post_process_report(report_text):
    import re
    naver_line = get_samsung_group_stocks_line()
    if not naver_line:
        return report_text
    
    # Check if (전자 ...) line already exists
    pattern = r'\(전자[^)]*화재[^)]*생명[^)]*\)'
    if re.search(pattern, report_text):
        report_text = re.sub(pattern, naver_line, report_text)
    else:
        # Look for the start of the next section
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
                
    return report_text

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
    is_draft = (kst_now.hour < 15) or ("--draft" in sys.argv)
    today_date = kst_now.strftime("%Y-%m-%d")
    month_val = str(int(kst_now.strftime("%m")))
    day_val = str(int(kst_now.strftime("%d")))
    today_short_slash = f"{month_val}/{day_val}"
    
    if report_type == "asia":
        if is_draft:
            prompt = f"""
오늘 날짜는 {today_date} ({today_short_slash}) 이고, 현재 한국 표준시(KST)는 장중인 {current_time_str} 입니다.
금일(오늘) 한국 시간 오후 2시 20분 기준의 한국 증시(코스피, 코스닥) 및 아시아 증시(일본, 중국 등)의 실시간 장중 지수와 주요 기업(삼성전자, SK하이닉스 등)의 실시간 장중 주가를 검색하여 장중 잠정 시황 보고서를 한국어로 작성해주세요.
반드시 오늘({today_date})의 실시간 장중 데이터를 검색하여 반영해야 하며, 이전 영업일(예: 7/17 금요일 등)의 수치나 내용을 오늘 수치처럼 적지 마십시오.
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

아시아 증시는 반도체 업종에 대한 우려감 및
이란 사태 여파로 대부분 하락세를 기록했으며,
홍콩 증시는 딥시크의 자체 AI 칩 개발 소식에
+3%대 상승 중입니다.
※ {today_short_slash} 장중잠정(연초대비): 한국 등락률(연초대비등락률), 일본 등락률(연초대비등락률), 중국 등락률(연초대비등락률)

한국 증시는 오전장에서 플러스를 보이기도 했으나,
오후 들어 하락하면서 5월 저점(7,209pt)에 근접,
△5.4% 하락, 7,247pt를 기록했습니다.

반도체에서 비반도체로 로테이션이 나오는 미국과 달리
주식 전반에서 매도세가 일어났으며,
상승종목 비율이 13%에 그쳤습니다.
(전자 등락률, 화재 등락률, 생명 등락률)

원달러는 SK하이닉스 ADR 상장을 앞두고
원화 강세가 지속되면서 △12원(1,504원) 하락했고,
국채금리는 미, 이란 우려 재점화에 따른
미 국채금리 급등 영향에 10년물이 +3bp(4.24%) 상승했으나,
5년, 3년 중단기물은 각각 △2bp, △1bp하락했습니다.

일본 역시 기술주 전반 매도 분위기에 하락했고,
중국은 그나마 홍콩 상승 영향에 소폭 하락했습니다.

이제 코스피 주가수익비율은 6.2배 수준까지 하락,
금융위기 당시를 밑돌면서 과매도 구간에 진입한 것으로 보이나
여전히 수급이 불안하여 고변동성은 지속될 수 있습니다.

감사합니다.

중요 규칙 (필수 준수):
- 어떠한 상황에서도 "데이터가 없다", "확인되지 않는다", "제공하기 어렵다", "검색이 불가능하다" 등의 거절 표현이나 사과 문구를 쓰지 마십시오.
- 연초대비(YTD) 등락률은 뉴스 검색 결과에 직접 나오지 않더라도 아래의 2025년 말 종가 기준을 참고하여 오늘 실시간 수치와 직접 계산하여 반드시 소수점 첫째짜리까지 기입하십시오.
  * 한국(코스피) 연초대비 기준값: 4214.17
  * 일본(니케이225) 연초대비 기준값: 50339.48
  * 중국(상해종합) 연초대비 기준값: 3968.84
  * 계산법: ((오늘 실시간 가격 - 기준값) / 기준값) * 100
- 만약 Google Finance 등 특정 금융 서비스에서 오늘 자 수치를 조회할 수 없거나 누락되어 있는 경우, Investing.com, Yahoo Finance 등 다른 공신력 있는 글로벌 금융 정보 사이트들의 최신 수치를 반드시 교차 참고하여 빈칸(공란)이나 누락 없이 모든 지수와 환율/금리 수치를 확실하게 기입하십시오.
- 매일 검색 시, 한국 주식시장(코스피, 코스닥)에 대해 주요 글로벌 투자은행(IB, 예: 골드만삭스, 모건스탠리, JP모건, UBS 등)이 언급한 최근 보고서 내용이나 한국 증시 전망에 대한 코멘트가 있는지 함께 검색하여 본문에 1~2줄 내외로 자연스럽게 추가하십시오.
- 매월 1일, 11일, 21일(혹은 그 직후 영업일)에는 당일 또는 전일 관세청에서 발표한 '수출입 현황' 또는 '수출 데이터'(예: 1~10일, 1~20일, 월간 수출 데이터 등)를 반드시 검색하여 반도체 수출 변동률 및 전체 수출 내 반도체 비중(%) 등의 핵심 데이터를 본문에 한 줄 독립된 라인이나 서술형 코멘트로 확실하게 포함시키십시오. (예: 오늘이 7/21인 경우, 오늘 오전 발표된 7월 1~20일 수출 데이터 및 반도체 비중 40.3% 등을 본문에 반드시 포함시킬 것)
- 일본과 중국 시황 내용이 반드시 포함되어야 합니다.
"""
        else:
            prompt = f"""
오늘 날짜는 {today_date} ({today_short_slash}) 이며, 현재 한국 표준시(KST)는 {current_time_str} (마감 후) 입니다.
오늘 최종 마감된 아시아 증시(한국, 일본, 중국, 대만 등) 시황 보고서를 한국어로 작성해주세요.
반드시 오늘({today_date})의 실제 최종 마감 데이터를 검색하여 반영해야 하며, 이전 영업일(예: 7/17 금요일 등)의 수치나 내용을 오늘 수치처럼 적지 마십시오.
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

아시아 증시는 반도체 업종에 대한 우려감 및
이란 사태 여파로 대부분 하락세를 기록했으며,
홍콩 증시는 딥시크의 자체 AI 칩 개발 소식에
+3%대 상승 중입니다.
※ {today_short_slash}(연초대비): 한국 등락률(연초대비등락률), 일본 등락률(연초대비등락률), 중국 등락률(연초대비등락률)

한국 증시는 오전장에서 플러스를 보이기도 했으나,
오후 들어 하락하면서 5월 저점(7,209pt)에 근접,
△5.4% 하락, 7,247pt를 기록했습니다.

반도체에서 비반도체로 로테이션이 나오는 미국과 달리
주식 전반에서 매도세가 일어났으며,
상승종목 비율이 13%에 그쳤습니다.
(전자 등락률, 화재 등락률, 생명 등락률)

원달러는 SK하이닉스 ADR 상장을 앞두고
원화 강세가 지속되면서 △12원(1,504원) 하락했고,
국채금리는 미, 이란 우려 재점화에 따른
미 국채금리 급등 영향에 10년물이 +3bp(4.24%) 상승했으나,
5년, 3년 중단기물은 각각 △2bp, △1bp하락했습니다.

일본 역시 기술주 전반 매도 분위기에 하락했고,
중국은 그나마 홍콩 상승 영향에 소폭 하락했습니다.

이제 코스피 주가수익비율은 6.2배 수준까지 하락,
금융위기 당시를 밑돌면서 과매도 구간에 진입한 것으로 보이나
여전히 수급이 불안하여 고변동성은 지속될 수 있습니다.

감사합니다.

중요 규칙 (필수 준수):
- 어떠한 상황에서도 "데이터가 없다", "확인되지 않는다", "제공하기 어렵다", "검색이 불가능하다" 등의 거절 표현이나 사과 문구를 쓰지 마십시오.
- 연초대비(YTD) 등락률은 뉴스 검색 결과에 직접 나오지 않더라도 아래의 2025년 말 종가 기준을 참고하여 오늘 마감 수치와 직접 계산하여 반드시 소수점 첫째짜리까지 기입하십시오.
  * 한국(코스피) 연초대비 기준값: 4214.17
  * 일본(니케이225) 연초대비 기준값: 50339.48
  * 중국(상해종합) 연초대비 기준값: 3968.84
  * 계산법: ((오늘 종가 - 기준값) / 기준값) * 100
- 만약 Google Finance 등 특정 금융 서비스에서 오늘 자 수치를 조회할 수 없거나 누락되어 있는 경우, Investing.com, Yahoo Finance 등 다른 공신력 있는 글로벌 금융 정보 사이트들의 최신 수치를 반드시 교차 참고하여 빈칸(공란)이나 누락 없이 모든 지수와 환율/금리 수치를 확실하게 기입하십시오.
- 매일 검색 시, 한국 주식시장(코스피, 코스닥)에 대해 주요 글로벌 투자은행(IB, 예: 골드만삭스, 모건스탠리, JP모건, UBS 등)이 언급한 최근 보고서 내용이나 한국 증시 전망에 대한 코멘트가 있는지 함께 검색하여 본문에 1~2줄 내외로 자연스럽게 추가하십시오.
- 매월 1일, 11일, 21일(혹은 그 직후 영업일)에는 당일 또는 전일 관세청에서 발표한 '수출입 현황' 또는 '수출 데이터'(예: 1~10일, 1~20일, 월간 수출 데이터 등)를 반드시 검색하여 반도체 수출 변동률 및 전체 수출 내 반도체 비중(%) 등의 핵심 데이터를 본문에 한 줄 독립된 라인이나 서술형 코멘트로 확실하게 포함시키십시오. (예: 오늘이 7/21인 경우, 오늘 오전 발표된 7월 1~20일 수출 데이터 및 반도체 비중 40.3% 등을 본문에 반드시 포함시킬 것)
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
                    text_clean = post_process_report(text_clean)
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
                                    # Ignore test runs sent before 3:30 PM (15:30) when checking for final report duplicate
                                    elif "[시황 보고서]" in subject_keyword and (parsed_dt_kst.hour < 15 or (parsed_dt_kst.hour == 15 and parsed_dt_kst.minute < 30)):
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
                log(f"[ERROR] run_daily_v2.py failed with exit code {res.returncode}. Stderr: {res.stderr or ''}")
        except Exception as ex:
            log(f"[ERROR] Failed to execute run_daily_v2.py: {ex}")
    else:
        log("[CRITICAL ERROR] No source report data found. Report generation aborted.")
        
    log("=== Daily Market Report Automation End ===\n")

if __name__ == '__main__':
    main()
