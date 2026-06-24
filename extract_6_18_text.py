import email, re
from html import unescape

path = 'C:/Users/infomax/OneDrive/dev/Daily news reporter creator/FW_ 아시아 시황(6_18).eml'
with open(path, 'rb') as f:
    msg = email.message_from_binary_file(f)

html = ''
for part in msg.walk():
    if part.get_content_type() == 'text/html':
        html = part.get_payload(decode=True).decode('utf-8', errors='ignore')
        break

# Clean up HTML and extract paragraph texts
def clean_html(html_str):
    # Find paragraphs
    paras = re.findall(r'<p.*?>(.*?)</p>', html_str, re.DOTALL)
    out = []
    for p in paras:
        text = re.sub(r'<.*?>', '', p, flags=re.DOTALL)
        text = unescape(text).strip()
        text = text.replace('\xa0', ' ').replace('\u200b', '')
        out.append(text)
    return out

lines = clean_html(html)
with open('extracted_6_18.txt', 'w', encoding='utf-8') as f:
    for i, line in enumerate(lines):
        f.write(f"Line {i}: {line}\n")
print("Saved to extracted_6_18.txt")
