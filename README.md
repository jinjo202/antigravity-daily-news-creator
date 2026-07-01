# 📊 배당 공시 모니터링 시스템

DART(전자공시시스템) OpenAPI를 활용하여 **감시 대상 종목**의 **"현금ㆍ현물배당 결정"** 공시가 접수되면 자동으로 이메일을 발송하는 Python 프로그램입니다.

## 감시 대상 종목 (14개)

| 분류 | 종목명 | 종목코드 |
|------|--------|---------|
| 통신 | LG유플러스 | 032640 |
| 통신 | SK텔레콤 | 017670 |
| 통신 | KT | 030200 |
| 금융 | KB금융 | 105560 |
| 금융 | 신한지주 | 055550 |
| 금융 | 하나금융지주 | 086790 |
| 금융 | 기업은행 | 024110 |
| 금융 | 우리금융지주 | 316140 |
| 자동차 | 현대자동차 | 005380 |
| 자동차 | 기아 | 000270 |
| 인프라 | 맥쿼리인프라 | 088980 |
| 삼성 | 삼성전자 | 005930 |
| 삼성 | 삼성E&A | 028050 |
| 삼성 | 에스원 | 012750 |

> 종목을 추가/제거하려면 `watchlist_provider.py`의 `WATCHLIST` 딕셔너리를 수정하세요.

## 주요 기능

- ✅ DART OpenAPI를 통한 실시간 공시 모니터링
- ✅ 특정 종목 자동 필터링
- ✅ "현금ㆍ현물배당 결정" 키워드 감지
- ✅ HTML 형식의 알림 이메일 자동 발송
- ✅ 다중 수신자 지원
- ✅ 중복 알림 방지
- ✅ 설정 가능한 폴링 주기

## 사전 준비

### 1. DART OpenAPI 인증키 발급

1. [Open DART](https://opendart.fss.or.kr/) 접속
2. 회원가입 후 로그인
3. **인증키 신청/관리** 메뉴에서 API 인증키 발급

### 2. SMTP 설정 (Gmail 예시)

1. Google 계정 → 보안 → **2단계 인증** 활성화
2. **앱 비밀번호** 생성 (메일 용도)
3. 생성된 16자리 비밀번호를 `.env` 파일에 입력

## 설치 및 설정

```bash
# 1. 의존성 설치
pip install -r requirements.txt

# 2. 환경 설정 파일 복사
cp .env.example .env

# 3. .env 파일 수정 (API 키, SMTP 정보 입력)
notepad .env
```

### `.env` 파일 설정 항목

| 항목 | 설명 | 예시 |
|---|---|---|
| `DART_API_KEY` | DART OpenAPI 인증키 | `abc123...` |
| `SMTP_HOST` | SMTP 서버 | `smtp.gmail.com` |
| `SMTP_PORT` | SMTP 포트 | `587` (TLS) 또는 `465` (SSL) |
| `SMTP_USERNAME` | SMTP 사용자명 | `your-email@gmail.com` |
| `SMTP_PASSWORD` | SMTP 비밀번호 | Gmail 앱 비밀번호 |
| `SENDER_EMAIL` | 발신자 이메일 | `your-email@gmail.com` |
| `RECIPIENT_EMAILS` | 수신자 이메일 (쉼표 구분) | `a@ex.com,b@ex.com` |
| `POLL_INTERVAL_MINUTES` | 폴링 간격 (분) | `5` |

## 실행

```bash
python main.py
```

종료하려면 `Ctrl+C`를 누르세요.

## 프로젝트 구조

```
dart-mail-sender/
├── main.py                  # 프로그램 진입점
├── config.py                # 설정 로드 (.env)
├── dart_api_client.py       # DART OpenAPI 클라이언트
├── watchlist_provider.py    # 감시 대상 종목 리스트
├── disclosure_monitor.py    # 공시 모니터링 로직
├── email_sender.py          # 이메일 발송
├── requirements.txt         # Python 의존성
├── .env.example             # 환경변수 템플릿
└── README.md                # 이 문서
```

## 동작 원리

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   DART API   │────▶│  필터링 로직  │────▶│  이메일 발송  │
│  (공시 조회)  │     │ 감시 종목 +  │     │   (SMTP)     │
│              │     │ 배당 키워드   │     │              │
└──────────────┘     └──────────────┘     └──────────────┘
       ▲                                         │
       │              5분 간격                     │
       └──────────── 반복 실행 ◀──────────────────┘
```
