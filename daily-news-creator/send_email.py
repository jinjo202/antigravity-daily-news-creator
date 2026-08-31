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

def convert_text_to_html(body_text, report_type="asia"):
    """Converts the plain text body to HTML matching the clean style exactly,
    processing paragraph-by-paragraph, using <br> for line breaks within paragraphs
    to ensure Outlook does not add extra spacing between lines."""
    import re
    # Split the input text into paragraphs by blank lines
    paragraphs = re.split(r'\n\s*\n', body_text.strip())
    html_parts = []
    
    if report_type == "global":
        font_size = "12pt"
    else:
        font_size = "11pt"
        
    line_height_css = "line-height:1.0; mso-line-height-rule:exactly;"
    # margin-top 3.75pt (5px) creates the gap between paragraphs.
    margin_style = "margin:3.75pt 0 0 0; mso-margin-top-alt:3.75pt; margin-bottom:0; mso-margin-bottom-alt:0;"
        
    font_family_style = "font-family:'바탕체', Batang, serif; mso-ascii-font-family:'바탕체'; mso-fareast-font-family:'바탕체'; mso-hansi-font-family:'바탕체';"
    
    for p in paragraphs:
        if not p.strip():
            continue
            
        lines = p.splitlines()
        p_html_lines = []
        
        is_samsung_line = False
        is_align_left = False
        p_color = 'black'
        align_str = 'justify'
        
        for line in lines:
            line_stripped = line.strip()
            if not line_stripped:
                continue
                
            content = line_stripped
            
            # Parse markdown bold (**...**) and underline (__...__)
            content = re.sub(r'\*\*__(.*?)__\*\*', r'<strong style="font-weight:bold"><u style="text-decoration:underline">\1</u></strong>', content)
            content = re.sub(r'__\*\*(.*?)\*\*__', r'<strong style="font-weight:bold"><u style="text-decoration:underline">\1</u></strong>', content)
            content = re.sub(r'\*\*(.*?)\*\*', r'<strong style="font-weight:bold">\1</strong>', content)
            content = re.sub(r'__(.*?)__', r'<u style="text-decoration:underline">\1</u>', content)
            
            _is_samsung = '(' in line_stripped and '전자' in line_stripped and '화재' in line_stripped and '생명' in line_stripped
            
            # Check if YTD line or Samsung stocks line
            _is_blue = line_stripped.startswith('※') or (line_stripped.startswith('*') and '연초대비' in line_stripped) or _is_samsung
            line_color = 'blue' if _is_blue else 'black'
            
            # Determine alignment
            _is_align_left = any(kw in content for kw in ["안녕하십니까", "감사합니다", "보고 드립니다", "동향입니다", "올림", "드림"]) or content.lower().startswith('title') or (content.startswith('(') and not _is_samsung)
            
            if _is_samsung: is_samsung_line = True
            if _is_blue: p_color = 'blue'
            if _is_align_left: is_align_left = True
            
            m = re.match(r'^(\s+)', line)
            leading_space = m.group(1) if m else ""
            nbsp = leading_space.replace(" ", "&nbsp;")
            
            p_html_lines.append(f'<span style="{font_family_style} font-size:{font_size}; color:{line_color};">{nbsp}{content}</span>')
            
        if is_samsung_line:
            align_str = 'center'
        elif is_align_left:
            align_str = 'left'
            
        # Join lines within the paragraph with <br>
        joined_lines = "<br>\n".join(p_html_lines)
        
        html_parts.append(
            f'<p align="{align_str}" style="{margin_style} {line_height_css} text-align:{align_str}; {font_family_style} font-size:{font_size}; color:{p_color}; word-break:keep-all; word-wrap:break-word;">\n'
            f'{joined_lines}\n'
            f'</p>'
        )
        
    return "\n".join(html_parts)


def send_via_gmail_smtp(recipients, subject, body, attachment_path=None, report_type="asia"):
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
        raw_html = convert_text_to_html(body, report_type=report_type)
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

def send_report_email(recipients, subject, body, attachment_path=None, report_type="asia"):
    """Orchestrator to send daily stock report via SMTP."""
    return send_via_gmail_smtp(recipients, subject, body, attachment_path, report_type)

if __name__ == '__main__':
    # Test execution
    recipients = ["jin.jo202@gmail.com"]
    subject = "[SMTP Test] Daily Asia Market Report"
    body = "Title : 아시아 시황 테스트\n\n이것은 SMTP 기반 전송 테스트 본문입니다.\n※ 테스트 항목 1\n감사합니다."
    send_report_email(recipients, subject, body)
