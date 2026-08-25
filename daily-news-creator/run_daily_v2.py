import os
import sys
from datetime import datetime
from generate_report import parse_raw_text, create_report_document
from send_email import send_report_email

def read_today_report(file_path):
    """Reads today_report.txt as-is (존댓말 서술형 본문)."""
    if not os.path.exists(file_path):
        return None
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read().strip()
    return content if content else None

def generate_email_body(text):
    """Clean up text paragraphs to ensure double newlines between sections, and single newlines within sections."""
    import re
    # Split the input text into paragraphs by blank lines (handling potential multiple blank lines)
    paragraphs = re.split(r'\n\s*\n', text.strip())
    cleaned_paragraphs = []
    for p in paragraphs:
        # Strip each line inside the paragraph, remove empty lines
        lines = [line.strip() for line in p.splitlines() if line.strip()]
        if lines:
            cleaned_paragraphs.append(" ".join(lines))
    return "\n\n".join(cleaned_paragraphs)


def main():
    workspace_dir = os.path.dirname(os.path.abspath(__file__))
    input_file = os.path.join(workspace_dir, "today_report.txt")
    
    # 1. Read report text
    report_text = read_today_report(input_file)
    if not report_text:
        print("[오류] today_report.txt 파일을 읽을 수 없거나 비어 있습니다.")
        sys.exit(1)
        
    # 2. Extract date/title from report_text for subject and file name
    first_line = report_text.split('\n')[0].strip()
    # Strip markdown bold formatting and extra spaces
    first_line_clean = first_line.replace('*', '').strip()
    
    title_val = ""
    if first_line_clean.lower().startswith('title'):
        colon_idx = first_line_clean.find(':')
        if colon_idx != -1:
            title_val = first_line_clean[colon_idx + 1:].strip()
    else:
        # Fallback to the cleaned first line itself if it contains content
        title_val = first_line_clean
            
    today_str = datetime.now().strftime("%Y%m%d")
    # If title_val contains a date like 6/2 or 06/02, try to use it for doc name
    doc_date_str = today_str
    if title_val:
        import re
        match = re.search(r'\((\d+)/(\d+)\)', title_val)
        if match:
            month = match.group(1).zfill(2)
            day = match.group(2).zfill(2)
            doc_date_str = f"{datetime.now().year}{month}{day}"
            
    output_filename = f"Daily_Market_Report_Official_{doc_date_str}.docx"
    output_file = os.path.join(workspace_dir, output_filename)
    
    # 3. Build Word Document
    structured_data = parse_raw_text(report_text)
    create_report_document(structured_data, output_file)
    
    # 4. Build Email Body (clean up intra-paragraph newlines for justify alignment)
    email_body = generate_email_body(report_text)
    
    # Determine draft status (check arguments, fallback to KST hour)
    is_draft = "--draft" in sys.argv
    if not is_draft and "--final" not in sys.argv:
        # Get current KST hour (UTC+9)
        from datetime import timezone, timedelta
        kst_now = datetime.now(timezone(timedelta(hours=9)))
        is_draft = kst_now.hour < 15
        
    # Clean title_val to avoid duplicate prefixes
    title_clean = title_val.replace("[초안]", "").replace("[시황 보고서]", "").strip()
    if not title_clean:
        title_clean = f"아시아 및 국내 증시 시황 ({datetime.now().strftime('%m/%d')})"
        
    if is_draft:
        subject = f"[초안] {title_clean} (안티그래비티버전)"
    else:
        subject = f"[시황 보고서] {title_clean} (안티그래비티버전)"
    
    # 5. Send Email
    recipients = ["jin.jo202@gmail.com", "jinyoung22.jo@samsung.com", "jeonghwan.lim@samsung.com"]
    send_report_email(recipients, subject, email_body, output_file)

if __name__ == '__main__':
    main()
