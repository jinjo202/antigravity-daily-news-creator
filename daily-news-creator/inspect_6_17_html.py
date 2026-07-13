import email, re

path = 'C:/Users/infomax/OneDrive/dev/Daily news reporter creator/FW_ 일일 금융시장 동향(6_17).eml'
with open(path, 'rb') as f:
    msg = email.message_from_binary_file(f)

html = ''
for part in msg.walk():
    if part.get_content_type() == 'text/html':
        html = part.get_payload(decode=True).decode('utf-8', errors='ignore')
        break

with open('C:/Users/infomax/OneDrive/dev/Daily news reporter creator/inspect_6_17_html.html', 'w', encoding='utf-8') as f:
    f.write(html)
print("Saved HTML to inspect_6_17_html.html")
