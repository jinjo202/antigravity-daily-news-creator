import email

path = 'C:/Users/infomax/OneDrive/dev/Daily news reporter creator/FW_ 아시아 시황(6_18).eml'
with open(path, 'rb') as f:
    msg = email.message_from_binary_file(f)

for part in msg.walk():
    if part.get_content_type() == 'text/html':
        print("charset:", part.get_content_charset())
        payload = part.get_payload(decode=True)
        # print first 100 bytes
        print("bytes:", payload[:100])
        # try decoding with cp949/euc-kr explicitly (without ignore)
        try:
            print("CP949:", payload.decode('cp949')[:200])
        except Exception as e:
            print("CP949 failed:", e)
        try:
            print("UTF-8:", payload.decode('utf-8')[:200])
        except Exception as e:
            print("UTF-8 failed:", e)
        break
