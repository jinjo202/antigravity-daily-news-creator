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

def wrap_korean_text(text, max_len=30):
    """Wraps Korean text strictly by spaces, ensuring no line exceeds max_len characters.
    Words are never split across lines."""
    is_bold_header = text.startswith('**') and text.endswith('**')
    if is_bold_header:
        text = text[2:-2].strip()
        
    words = text.split()
    lines = []
    current_line = []
    current_len = 0
    
    for word in words:
        visible_word = word.replace("**", "").replace("__", "")
        word_len = len(visible_word)
        
        extra = 1 if current_line else 0
        if current_len + word_len + extra > max_len:
            if current_line:
                lines.append(" ".join(current_line))
                current_line = [word]
                current_len = word_len
            else:
                current_line = [word]
                current_len = word_len
        else:
            current_line.append(word)
            current_len += word_len + extra
            
    if current_line:
        lines.append(" ".join(current_line))
        
    result = [l for l in lines if l]
    if is_bold_header:
        result = [f"**{l}**" for l in result]
    return result


def convert_text_to_html(body_text):
    """Converts the plain text body to HTML matching the clean style exactly,
    processing line-by-line, wrapping to max 25 characters,
    and keeping font family as 바탕체 11pt."""
    import re
    lines = body_text.splitlines()
    html_parts = []
    
    for line in lines:
        line_stripped = line.strip()
        
        if not line_stripped:
            # Empty paragraph
            html_parts.append('<p style="margin:0px 0px 8px 0px;line-height:1.15;text-align:left;font-family:바탕체,serif;font-size:11pt;color:black;"><br></p>')
            continue
            
        # Wrap the line to max 30 characters
        wrapped_lines = wrap_korean_text(line_stripped, max_len=30)
        for w_line in wrapped_lines:
            # Parse markdown bold (**...**) and underline (__...__)
            content = w_line
            content = re.sub(r'\*\*__(.*?)__\*\*', r'<strong style="font-weight:bold"><u style="text-decoration:underline">\1</u></strong>', content)
            content = re.sub(r'__\*\*(.*?)\*\*__', r'<strong style="font-weight:bold"><u style="text-decoration:underline">\1</u></strong>', content)
            content = re.sub(r'\*\*(.*?)\*\*', r'<strong style="font-weight:bold">\1</strong>', content)
            content = re.sub(r'__(.*?)__', r'<u style="text-decoration:underline">\1</u>', content)
            
            # Check if YTD line (starts with ※ or starts with * and contains 연초대비)
            is_ytd = w_line.startswith('※') or (w_line.startswith('*') and '연초대비' in w_line)
            color = 'blue' if is_ytd else 'black'
            
            # We align left for greeting, title, sign-offs, or headers
            is_align_left = any(kw in w_line for kw in ["안녕하십니까", "감사합니다", "보고 드립니다", "동향입니다", "올림", "드림"]) or w_line.startswith('**') or w_line.lower().startswith('title')
            align_str = 'left' if is_align_left else 'justify'
            
            # Keep leading whitespace using non-breaking spaces if any
            m = re.match(r'^(\s+)', w_line)
            leading_space = m.group(1) if m else ""
            nbsp = leading_space.replace(" ", "&nbsp;")
            
            html_parts.append(
                f'<p align="{align_str}" style="margin:0px 0px 8px 0px;line-height:1.15;text-align:{align_str};font-family:바탕체,serif;font-size:11pt;color:{color};word-break:break-all;">'
                f'<span style="font-family:바탕체,serif;font-size:11pt;color:{color};">{nbsp}{content}</span>'
                f'</p>'
            )
        
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
