import os
import sys
import smtplib
import re
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

# Gmail account settings
GMAIL_ADDRESS = "devbotsender8282@gmail.com"
GMAIL_PASSWORD = "lvjayqklnrkofjbj"  # Verified App Password

def wrap_line_by_words(text, max_len=40):
    """Wraps text on word boundaries (spaces) to not exceed max_len visual characters per line, protecting markdown tags."""
    words = text.split(" ")
    lines = []
    current_line = []
    current_len = 0
    
    for word in words:
        # Calculate visual length without markdown characters
        visible_word = word.replace("**", "").replace("__", "")
        word_len = len(visible_word)
        
        # Check if adding this word (and space) exceeds max_len
        if current_len + word_len + (1 if current_line else 0) > max_len:
            if current_line:
                lines.append(" ".join(current_line))
                current_line = [word]
                current_len = word_len
            else:
                current_line = [word]
                current_len = word_len
        else:
            current_line.append(word)
            current_len += word_len + (1 if len(current_line) > 1 else 0)
            
    if current_line:
        lines.append(" ".join(current_line))
    return lines


def convert_text_to_html(body_text):
    """Converts the plain text body to HTML matching the original TrendForce Gmail styling exactly,
    preserving line lengths and formatting them as justified rectangular text blocks."""
    
    def get_line_type(line):
        cleaned = line.strip()
        if not cleaned:
            return 'empty'
        cleaned_lower = cleaned.lower()
        if cleaned_lower.startswith("title") or cleaned_lower.startswith("**title**"):
            return 'title'
        # Check list item starting with * followed by space or non-breaking space
        if cleaned.startswith("* ") or cleaned.startswith("*\xa0") or cleaned.startswith("*\t"):
            return 'list_item'
        if cleaned.startswith("※") or "※" in cleaned:
            return 'footnote'
        return 'normal'

    # Group lines by empty lines or structural type changes
    lines = body_text.splitlines()
    groups = []
    current_group = []
    current_type = None
    
    for line in lines:
        ltype = get_line_type(line)
        if ltype == 'empty':
            if current_group:
                groups.append((current_type, current_group))
                current_group = []
            groups.append(('empty', ['']))
            current_type = None
        elif ltype in ('title', 'list_item', 'footnote'):
            if current_group:
                groups.append((current_type, current_group))
            groups.append((ltype, [line]))
            current_group = []
            current_type = None
        else:  # normal
            if current_type == 'normal':
                current_group.append(line)
            else:
                if current_group:
                    groups.append((current_type, current_group))
                current_group = [line]
                current_type = 'normal'
                
    if current_group:
        groups.append((current_type, current_group))

    html_parts = []
    
    for gtype, glines in groups:
        if gtype == 'empty':
            # Empty paragraph (no alignment needed, default left)
            html_parts.append('<p style="box-sizing:content-box;font-family:굴림,sans-serif;color:rgb(0,0,0);font-size:12pt;vertical-align:top;display:block;line-height:1.5;font-weight:400;margin:5px 0px 10.66px;padding:0px;background-color:rgb(255,255,255);text-align:left;"><span style="font-family:바탕체,serif;color:black"><br></span></p>')
        else:
            # Preserve leading spaces of the first line
            first_line = glines[0]
            m = re.match(r'^(\s*)', first_line)
            leading_spaces = m.group(1) if m else ""
            nbsp = leading_spaces.replace(" ", "&nbsp;")
            
            if gtype == 'title':
                content = glines[0].strip()
                # Markdown bold/underline styling
                content = re.sub(r'\*\*__(.*?)__\*\*', r'<strong style="font-weight:bold"><u style="text-decoration:underline">\1</u></strong>', content)
                content = re.sub(r'__\*\*(.*?)\*\*__', r'<strong style="font-weight:bold"><u style="text-decoration:underline">\1</u></strong>', content)
                content = re.sub(r'\*\*(.*?)\*\*', r'<strong style="font-weight:bold">\1</strong>', content)
                content = re.sub(r'__(.*?)__', r'<u style="text-decoration:underline">\1</u>', content)
                
                if content.lower().startswith("title") or content.lower().startswith("**title**"):
                    cleaned_title = content.replace("**", "")
                    colon_idx = cleaned_title.find(":")
                    if colon_idx != -1:
                        title_label = cleaned_title[:colon_idx + 1]
                        title_val = cleaned_title[colon_idx + 1:]
                    else:
                        title_label = cleaned_title
                        title_val = ""
                else:
                    title_label = content
                    title_val = ""
                    
                title_label = re.sub(r'\*\*__(.*?)__\*\*', r'<strong style="font-weight:bold"><u style="text-decoration:underline">\1</u></strong>', title_label)
                title_label = re.sub(r'__\*\*(.*?)\*\*__', r'<strong style="font-weight:bold"><u style="text-decoration:underline">\1</u></strong>', title_label)
                title_label = re.sub(r'\*\*(.*?)\*\*', r'<strong style="font-weight:bold">\1</strong>', title_label)
                title_label = re.sub(r'__(.*?)__', r'<u style="text-decoration:underline">\1</u>', title_label)
                
                title_val = re.sub(r'\*\*__(.*?)__\*\*', r'<strong style="font-weight:bold"><u style="text-decoration:underline">\1</u></strong>', title_val)
                title_val = re.sub(r'__\*\*(.*?)\*\*__', r'<strong style="font-weight:bold"><u style="text-decoration:underline">\1</u></strong>', title_val)
                title_val = re.sub(r'\*\*(.*?)\*\*', r'<strong style="font-weight:bold">\1</strong>', title_val)
                title_val = re.sub(r'__(.*?)__', r'<u style="text-decoration:underline">\1</u>', title_val)
                
                html_parts.append(f'<p style="margin:0px 0px 10.66px 0px;text-align:left;"><span style="font-weight:bold;font-family:\'Malgun Gothic\', \'맑은 고딕\', sans-serif;font-size:13.3333px">{nbsp}{title_label}</span><span style="font-family:\'Malgun Gothic\', \'맑은 고딕\', sans-serif;font-size:13.3333px">{title_val}</span></p>')
                
            elif gtype == 'list_item':
                # Format each list line individually (left aligned)
                for line in glines:
                    content = line.strip()
                    content = re.sub(r'\*\*__(.*?)__\*\*', r'<strong style="font-weight:bold"><u style="text-decoration:underline">\1</u></strong>', content)
                    content = re.sub(r'__\*\*(.*?)\*\*__', r'<strong style="font-weight:bold"><u style="text-decoration:underline">\1</u></strong>', content)
                    content = re.sub(r'\*\*(.*?)\*\*', r'<strong style="font-weight:bold">\1</strong>', content)
                    content = re.sub(r'__(.*?)__', r'<u style="text-decoration:underline">\1</u>', content)
                    html_parts.append(f'<p align="left" style="box-sizing:content-box;font-family:굴림,sans-serif;color:rgb(0,0,0);font-size:12pt;vertical-align:top;display:block;font-weight:400;margin:0px;padding:0px;background-color:rgb(255,255,255);line-height:1.5;text-align:left;"><span style="box-sizing:content-box;font-family:바탕체,serif;color:blue;letter-spacing:-0.4pt;margin-left:0px;margin-bottom:0px;margin-right:0px;margin-top:0px;padding-left:0px;padding-bottom:0px;padding-right:0px;padding-top:0px;font-size:11pt;line-height:145%;background:transparent;">{nbsp}{content}</span></p>')
                    
            elif gtype == 'footnote':
                # Format footnote lines
                for line in glines:
                    content = line.strip()
                    content = re.sub(r'\*\*__(.*?)__\*\*', r'<strong style="font-weight:bold"><u style="text-decoration:underline">\1</u></strong>', content)
                    content = re.sub(r'__\*\*(.*?)\*\*__', r'<strong style="font-weight:bold"><u style="text-decoration:underline">\1</u></strong>', content)
                    content = re.sub(r'\*\*(.*?)\*\*', r'<strong style="font-weight:bold">\1</strong>', content)
                    content = re.sub(r'__(.*?)__', r'<u style="text-decoration:underline">\1</u>', content)
                    html_parts.append(f'<p align="left" style="box-sizing:content-box;font-family:굴림,sans-serif;color:rgb(0,0,0);font-size:12pt;vertical-align:top;display:block;line-height:1.5;font-weight:400;margin:5px 0px 10.66px;padding:0px;background-color:rgb(255,255,255);text-align:left;"><span style="background:transparent;font-size:11pt;line-height:145%;font-family:바탕체,serif;color:blue">{nbsp}{content}</span></p>')
                    
            else:  # normal
                # Decide if we wrap or keep original lines
                # If original lines are already formatted (i.e. multiple short lines), we preserve them.
                # If it's a long continuous text block, we wrap it to match the sample email line length (~40 chars).
                use_original = len(glines) > 1 and all(len(l.strip()) < 42 for l in glines)
                
                if use_original:
                    final_lines = [l.strip() for l in glines]
                else:
                    combined = " ".join([l.strip() for l in glines])
                    final_lines = wrap_line_by_words(combined, max_len=40)
                
                # Render the lines inside a single paragraph using <br> for line breaks
                # so that they form a clean justified block
                rendered_lines = []
                for fl in final_lines:
                    content = fl
                    content = re.sub(r'\*\*__(.*?)__\*\*', r'<strong style="font-weight:bold"><u style="text-decoration:underline">\1</u></strong>', content)
                    content = re.sub(r'__\*\*(.*?)\*\*__', r'<strong style="font-weight:bold"><u style="text-decoration:underline">\1</u></strong>', content)
                    content = re.sub(r'\*\*(.*?)\*\*', r'<strong style="font-weight:bold">\1</strong>', content)
                    content = re.sub(r'__(.*?)__', r'<u style="text-decoration:underline">\1</u>', content)
                    rendered_lines.append(content)
                
                joined_content = "<br>".join(rendered_lines)
                
                # Check if it is a greeting, sign-off, or very short paragraph overall
                total_text_len = sum(len(l) for l in final_lines)
                is_short = total_text_len < 28 or any(kw in joined_content for kw in ["안녕하십니까", "감사합니다", "보고 드립니다", "동향입니다", "올림", "드림"])
                
                if is_short:
                    html_parts.append(f'<p align="left" style="box-sizing:content-box;font-family:굴림,sans-serif;color:rgb(0,0,0);font-size:12pt;vertical-align:top;display:block;line-height:1.5;font-weight:400;margin:5px 0px 10.66px;padding:0px;background-color:rgb(255,255,255);text-align:left;"><span style="background-color:transparent;color:black;font-family:바탕체,serif;font-size:12pt">{nbsp}{joined_content}</span></p>')
                else:
                    html_parts.append(f'<p align="justify" style="box-sizing:content-box;font-family:굴림,sans-serif;color:rgb(0,0,0);font-size:12pt;vertical-align:top;display:block;line-height:1.5;font-weight:400;margin:5px 0px 10.66px;padding:0px;background-color:rgb(255,255,255);text-align:justify;text-justify:inter-character;word-break:break-all;"><span style="background-color:transparent;color:black;font-family:바탕체,serif;font-size:12pt">{nbsp}{joined_content}</span></p>')
                
    return "".join(html_parts)


def send_via_gmail_smtp(recipients, subject, body, attachment_path=None):
    """Sends the report email via Gmail SMTP using the secure App Password."""
    print("=" * 60)
    print("[SMTP] starting email delivery...")
    print("=" * 60)
    
    # Parse recipients
    if isinstance(recipients, str):
        recipient_list = [r.strip() for r in recipients.split(",") if r.strip()]
    else:
        recipient_list = recipients
        
    if not recipient_list:
        print("[SMTP ERROR] Recipient list is empty.")
        return False
        
    try:
        # Create MIMEMultipart email message
        msg = MIMEMultipart()
        msg['From'] = GMAIL_ADDRESS
        msg['To'] = ", ".join(recipient_list)
        msg['Subject'] = subject
        
        # Convert plain text body to structured HTML with strict document wrapping and justification overrides
        raw_html = convert_text_to_html(body)
        html_body = f"""<!DOCTYPE html>
<html xmlns:w="urn:schemas-microsoft-com:office:word" lang="ko">
<head>
<meta charset="utf-8">
<!--[if gte mso 9]>
<xml>
  <w:WordDocument>
    <w:DontUseAdvancedTypographyReadingMail/>
  </w:WordDocument>
</xml>
<![endif]-->
<style type="text/css">
  /* Global paragraph overrides removed to respect inline styling */
</style>
</head>
<body style="margin:0;padding:0;">
{raw_html}
</body>
</html>"""
        
        # Attach the HTML body
        msg.attach(MIMEText(html_body, 'html', 'utf-8'))
        
        # Attach Word document
        if attachment_path and os.path.exists(attachment_path):
            filename = os.path.basename(attachment_path)
            print(f"[SMTP] Attaching file: {filename}")
            try:
                with open(attachment_path, "rb") as f:
                    part = MIMEBase("application", "octet-stream")
                    part.set_payload(f.read())
                encoders.encode_base64(part)
                part.add_header(
                    "Content-Disposition",
                    f"attachment; filename={filename}",
                )
                msg.attach(part)
                print("[SMTP] Attachment added successfully!")
            except Exception as file_err:
                print(f"[SMTP WARNING] Failed to attach file (will still attempt to send email): {file_err}")
                
        # Connect to Gmail SMTP server
        print("[SMTP] Connecting to smtp.gmail.com:465...")
        server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
        print("[SMTP] Logging in...")
        server.login(GMAIL_ADDRESS, GMAIL_PASSWORD)
        print("[SMTP] Sending mail...")
        server.sendmail(GMAIL_ADDRESS, recipient_list, msg.as_string())
        server.quit()
        
        print(f"[SMTP SUCCESS] Email sent to {len(recipient_list)} recipients!")
        return True
    except Exception as e:
        print(f"[SMTP ERROR] Failed to send email: {e}")
        return False

def send_report_email(recipients, subject, body, attachment_path=None):
    """Orchestrator to send daily stock report via SMTP."""
    return send_via_gmail_smtp(recipients, subject, body, attachment_path)

if __name__ == '__main__':
    # Test execution
    recipients = ["jin.jo202@gmail.com"]
    subject = "[SMTP Test] Daily Asia Market Report"
    body = "Title : 아시아 시황 테스트\n\n이것은 SMTP 기반 전송 테스트 본문입니다.\n※ 테스트 항목 1\n감사합니다."
    send_report_email(recipients, subject, body)
