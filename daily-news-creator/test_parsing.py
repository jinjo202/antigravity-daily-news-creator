import sys
import generate_report_us

text = "**-- 첫문단입니다.\n두번째문단입니다."
res = generate_report_us.parse_us_report(text)
print(res)
