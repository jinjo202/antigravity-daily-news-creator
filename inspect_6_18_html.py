import email

path = 'C:/Users/infomax/OneDrive/dev/Daily news reporter creator/FW_ 아시아 시황(6_18).eml'
with open(path, 'rb') as f:
    msg = email.message_from_binary_file(f)

html = ''
for part in msg.walk():
    if part.get_content_type() == 'text/html':
        html = part.get_payload(decode=True).decode('utf-8', errors='ignore')
        break

p_tags = []
if html:
    import re
    p_tags = re.findall(r'<p.*?>.*?</p>', html, re.DOTALL)

for i, p in enumerate(p_tags[:40]):
    clean_p = p.replace('&nbsp;', ' ')
    text = re.sub(r'<.*?>', '', clean_p).strip()
    style_match = re.search(r'style="([^"]*)"', p)
    style = style_match.group(1) if style_match else 'None'
    print(f"P{i}: style={style} | text={repr(text)}")
