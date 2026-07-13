import os
import sys
from datetime import datetime
from generate_report import parse_raw_text, create_report_document

def main():
    # Define file paths
    workspace_dir = os.path.dirname(os.path.abspath(__file__))
    input_file = os.path.join(workspace_dir, "today_report.txt")
    
    # Check if input file exists
    if not os.path.exists(input_file):
        # Create a helpful template for the user if it's missing
        template_text = """금일 아시아 증시 시황 보고 드립니다.

아시아 증시는 미국 증시가 5월 마지막 거래일 종전 합의 기대,
유가 약세와 AI 낙관론 유지로 사상 최고치로 마감한 영향에
6월 첫 거래일 상승을 이어 갔습니다.
다만, 중국은 5월 제조업 PMI지수 둔화로 소폭 하락했습니다.
※ 6.2(연초대비): 한국 +3.7%(+108.5), 일본 +0.9%(+33.0), 중국 △0.2%(+2.3)

코스피는 대형 주도주 중심 상승이(상승종목 비율 19%)이
6월 들어서도 지속되면서 8,800pt에 근접했습니다.
젠슨 황 CEO 방한과 협력 기대에 LG전자와 두산로보틱스가
상한가를 기록하는 등 자금이 소수 업종에 몰리는 모습을 보였습니다.

삼성전자와 SK하이닉스도 
HBM4가 탑재된 엔비디아의 베라루빈 양산 발표에 상승을 이어갔고,
삼성전자는 시총 2,000조를 돌파했습니다.
(전자 +10.1%, 화재 +6.2%, 생명 +5.5%)

원달러는 외국인의 코스피 17거래일 연속 순매도 속에
+1원(1,506원) 상승했고,
국채금리(10년)는 BOK 국제콘퍼런스에서 신현송 총재가
다시 한번 매파적 발언을 하며 +10bp(4.17%) 급등했습니다.
(※ 신현송 총재, "단기적인 문제 인플레이션이 이미 높고,
    이에 대응하기 위한 운신의 폭이 커졌다.")

금주는 엔비디아 GTC 대만 행사(1~4일), 대만 컴퓨텍스 2026(2~5일),
젠슨 황 CEO 방한(8일 유력) 등 AI 관련 이벤트로 
관련주 쏠림이 더 심화될 수도 있고
단기 변동성이 확대될 수도 있어 유의할 필요가 있어 보입니다."""
        
        with open(input_file, 'w', encoding='utf-8') as f:
            f.write(template_text)
        print(f"[알림] '{input_file}' 템플릿 파일이 생성되었습니다. 시황 텍스트를 이곳에 복사해 넣으세요.")
        return

    # Read today's report text
    with open(input_file, 'r', encoding='utf-8') as f:
        raw_text = f.read().strip()
        
    if not raw_text:
        print("[경고] 'today_report.txt' 파일이 비어 있습니다. 시황 내용을 채워 넣어 주세요.")
        return

    # Generate filename based on today's date
    today_str = datetime.now().strftime("%Y%m%d")
    output_filename = f"Daily_Market_Report_{today_str}.docx"
    output_file = os.path.join(workspace_dir, output_filename)

    print(f"[시작] {today_str} 시황 보고서 워드 변환 작업을 시작합니다...")
    
    try:
        # Parse and create document
        structured_data = parse_raw_text(raw_text)
        create_report_document(structured_data, output_file)
        
        print(f"[완료] 리포트 파일 생성 성공: {output_file}")
        
        # Open the generated Word document automatically on Windows!
        if sys.platform == 'win32':
            print("[알림] 생성된 워드 문서를 자동으로 실행합니다...")
            os.startfile(output_file)
            
    except Exception as e:
        print(f"[에러] 시황 생성 중 오류가 발생하였습니다: {str(e)}")

if __name__ == '__main__':
    main()
