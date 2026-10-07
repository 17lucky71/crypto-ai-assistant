# 비트코인 AI 비서 (crypto-ai-assistant)

업비트 비트코인(KRW-BTC) 일별 종가 데이터를 저장·요약하고, **그 요약을 근거로 대화로 답하는 AI 비서** 웹 서비스입니다.

## 1. 서비스 소개

### 왜 만들었나
- ChatGPT에 "요즘 비트코인 어때?"라고 물으면 내 데이터를 모르기 때문에 일반적인 이야기만 하거나 숫자를 지어낼 수 있다.
- 업비트 차트는 숫자는 정확하지만 "지난달보다 올랐어?", "제일 많이 떨어진 날은?" 같은 질문에는 답해 주지 않는다. 직접 표를 보고 계산해야 한다.
- 그래서 **저장된 실제 시세 데이터만 근거로, 쉬운 말로 답하는 비서**를 만들었다.

### 무엇이 좋은가
| 대상 | 이로운 점 |
|---|---|
| 코인 초보자 | 차트를 읽지 못해도 "요즘 오르는 중이야?"라고 물으면 쉬운 말로 답을 듣는다 |
| 바쁜 직장인·학생 | 매일 차트를 보지 않아도 질문 한 번으로 흐름을 파악한다 |
| 급락에 불안한 사람 | "이 정도 하락이 자주 있었어?"에 과거 급락 기록으로 답해, 감정이 아닌 데이터로 판단하게 돕는다 |

- **정확성**: AI는 시스템 프롬프트에 넣은 데이터 요약 안에서만 답하고, 없는 정보는 "데이터에 없다"고 말한다.
- **최신성**: 화면에서 데이터를 추가·수정·삭제하면 요약이 즉시 다시 계산되고 AI 답변에도 반영된다.
- **안전성**: 미래 가격 예측이나 매수·매도 권유는 하지 않도록 규칙을 넣었다.

## 2. 주요 기능
1. **데이터 기반 AI 채팅**: 질문 → 데이터 요약을 시스템 프롬프트에 주입 → GPT 답변 (로딩 표시)
2. **데이터 관리(CRUD)**: 날짜·종가·메모 추가, 목록, 수정, 삭제
3. **대화 기록**: 채팅 자동 저장, 목록 조회, 이전 대화 불러오기, 삭제
4. **데이터 요약 표시**: 기간, 개수, 최근 종가, 30일 변화, 추세
5. **(보너스) 인사이트·UX 고도화**: 가격 그래프(30일/90일/180일/전체 선택), 추가 통계 3종, CSV·JSON 내보내기, 다크 모드

## 3. 기술 스택
| 구분 | 사용 기술 |
|---|---|
| 백엔드 | Python 3.11, FastAPI, Pydantic, Uvicorn |
| DB | Firebase Firestore (`firebase-admin`) |
| AI | OpenAI GPT (`gpt-4o-mini`, `max_tokens=500`) |
| 프론트엔드 | HTML / CSS / JavaScript (프레임워크 없음) |
| 배포 | Render (백엔드), Vercel (프론트엔드) |
| 데이터 | 업비트 시세 API (KRW-BTC 일봉, 400일) |

## 4. 배포 URL
| 구분 | 주소 |
|---|---|
| 프론트엔드 (Vercel) | https://YOUR-APP.vercel.app |
| 백엔드 API (Render) | https://YOUR-API.onrender.com |
| Swagger UI | https://YOUR-API.onrender.com/docs |

> Render 무료 티어는 15분간 요청이 없으면 잠들어, 첫 접속에 30초~1분이 걸릴 수 있습니다. 화면 상단에 "서버 깨우는 중" 안내가 뜨고, 서버가 깨면 자동으로 데이터를 불러옵니다.

## 5. 프로젝트 구조
```
crypto-ai-assistant/
├── backend/
│   ├── main.py                    # FastAPI 앱, CORS, 라우터 등록
│   ├── app/
│   │   ├── config.py              # 환경 변수 읽기
│   │   ├── db.py                  # Firestore 연결 (키 없으면 메모리 저장소)
│   │   ├── schemas.py             # Pydantic 요청/응답 모델 (입력 검증)
│   │   ├── routers/               # URL 과 HTTP 처리만 담당
│   │   │   ├── data.py            #   /api/data (CRUD + summary)
│   │   │   ├── conversations.py   #   /api/conversations
│   │   │   └── chat.py            #   /api/chat
│   │   └── services/              # 실제 로직
│   │       ├── data_service.py    #   CRUD, 요약 통계 계산
│   │       ├── conversation_service.py
│   │       └── chat_service.py    #   시스템 프롬프트 구성, GPT 호출, 자동 저장
│   ├── scripts/seed_upbit.py      # 업비트 데이터 수집·분석·Firestore 업로드
│   ├── data/btc_daily.csv         # 수집한 원본 데이터
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── index.html / style.css / app.js
│   ├── config.js                  # 로컬용 API 주소
│   ├── build.js                   # Vercel 빌드 시 API_BASE_URL 로 config.js 생성
│   └── vercel.json
├── docs/
│   ├── GLOSSARY.md                # 과제 용어 정리
│   └── screenshots/
└── render.yaml
```

**라우터와 서비스를 나눈 기준**: 라우터는 "어떤 URL로 무엇을 받고 어떤 상태 코드를 돌려줄지"만, 서비스는 "데이터를 어떻게 계산·저장할지"만 맡는다. 그래서 `/api/chat` 이 `/api/data/summary` 와 같은 요약 함수(`build_summary`)를 그대로 재사용할 수 있다.

## 6. API
| 메서드 | 경로 | 설명 |
|---|---|---|
| POST | `/api/data` | 새 데이터 추가 (같은 날짜가 있으면 409) |
| GET | `/api/data` | 목록 조회 (`?order=desc&limit=30`) |
| PUT | `/api/data/{id}` | 수정 (바꿀 항목만 전송) |
| DELETE | `/api/data/{id}` | 삭제 |
| GET | `/api/data/summary` | 요약 (프롬프트 주입용) |
| GET | `/api/data/statistics` | (보너스) 추가 통계 + 그래프용 시계열 |
| GET | `/api/data/export?format=csv` | (보너스) CSV 또는 JSON 파일 다운로드 |
| POST | `/api/conversations` | 대화 저장 |
| GET | `/api/conversations` | 대화 목록 (**messages 미포함**, 개수만) |
| GET | `/api/conversations/{id}` | 특정 대화 불러오기 (**messages 포함**) |
| DELETE | `/api/conversations/{id}` | 대화 삭제 |
| POST | `/api/chat` | AI 대화 (요약 주입 + 자동 저장) |

### 요약 응답 예시 (`GET /api/data/summary`)
```json
{
  "name": "비트코인 일별 종가 (업비트 KRW-BTC)",
  "period": "2025-09-03 ~ 2026-10-07",
  "count": 400,
  "metrics": {
    "latest": {"date": "2026-10-07", "value": 165000000},
    "average": 140000000,
    "max": {"date": "...", "value": 0},
    "min": {"date": "...", "value": 0},
    "change_30d_pct": 4.2,
    "daily_volatility_pct": 2.4
  },
  "trend": "상승 (최근 30일 평균이 직전 30일 대비 +4.2%)"
}
```

### 컨텍스트 주입 흐름 (`POST /api/chat`)
```
사용자 질문
  → ① data_service.build_summary()  : 요약 계산 (/api/data/summary 와 같은 함수)
  → ② 요약을 시스템 프롬프트에 삽입   : "당신은 데이터 분석 비서입니다. [사용자 데이터 요약] ..."
  → ③ 이전 대화 최대 10개 + 질문과 함께 GPT 호출 (max_tokens 500)
  → ④ 질문·답변을 conversations 에 자동 저장
  → 답변 + conversation_id 반환
```

## 7. 보너스: 인사이트·UX 고도화
| 요구 사항 | 구현 |
|---|---|
| 추가 지표 1개 이상 | `/api/data/statistics` 신설 + `/api/data/summary` 보강. **상승일 비율**(오른 날 ÷ 전체), **최대 낙폭 MDD**(고점 대비 가장 크게 떨어진 비율과 날짜), **월별 수익률**(월초 대비 월말), **7일·30일 이동평균** |
| 그래프 1개 | 라이브러리 없이 SVG 로 직접 그린 종가 + 30일 이동평균 선 그래프. 마우스를 올리면 그날 가격 표시 |
| 선택 UI | 그래프 기간 30일 / 90일 / 180일 / 전체 전환 |
| 데이터 내보내기 | 데이터 관리의 **CSV / JSON** 버튼 → `/api/data/export` (CSV 는 엑셀에서 한글이 깨지지 않게 BOM 포함) |
| 다크 모드 | 상단 🌙 버튼. 선택은 브라우저에 기억되고, 처음 방문 시 OS 설정을 따른다 |

상승일 비율과 최대 낙폭은 요약에도 넣어, AI 가 "가장 크게 떨어졌을 때가 언제야?" 같은 질문에도 답할 수 있게 했다.

## 8. Firestore 컬렉션 구조
```
data/{자동ID}
  date: "2026-10-07"   value: 165000000   memo: "일간 +6.3% 급등"
  created_at, updated_at

conversations/{자동ID}
  title: "최근 한 달 흐름 어때?"
  messages: [{role: "user", content: "..."}, {role: "assistant", content: "..."}]
  created_at, updated_at
```

## 9. 환경 변수
| 이름 | 위치 | 설명 |
|---|---|---|
| `OPENAI_API_KEY` | 백엔드 | OpenAI API 키 |
| `OPENAI_MODEL` | 백엔드 | 기본 `gpt-4o-mini` |
| `OPENAI_MAX_TOKENS` | 백엔드 | 답변 최대 토큰, 기본 500 (비용 제한) |
| `FIREBASE_SERVICE_ACCOUNT_JSON` | 백엔드(배포) | 서비스 계정 키 JSON 전체 |
| `FIREBASE_SERVICE_ACCOUNT_PATH` | 백엔드(로컬) | 서비스 계정 키 파일 경로 |
| `ALLOWED_ORIGINS` | 백엔드 | CORS 허용 도메인 (쉼표 구분) |
| `API_BASE_URL` | 프론트(Vercel) | 백엔드 주소 |

키 파일과 `.env` 는 `.gitignore` 에 등록해 GitHub 에 올라가지 않는다.

## 10. 로컬 실행 방법 (Windows)

### 백엔드
```bash
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env          # 값 채우기
python scripts/seed_upbit.py --upload   # 업비트 400일 수집 → CSV 저장 → Firestore 업로드
uvicorn main:app --reload
```
- API: http://localhost:8000 , Swagger: http://localhost:8000/docs
- Firebase 키 없이 실행하면 메모리 저장소로 동작한다 (서버를 끄면 사라짐, 개발용).

### 프론트엔드
```bash
cd frontend
python -m http.server 5500
```
- http://localhost:5500 접속. API 주소는 `config.js` 에서 바꾼다.

## 11. 데이터 선정과 분석
- **데이터**: 업비트 KRW-BTC 일봉 종가 400일 (최소 100개 조건 충족)
- **선정 이유**: 변동이 커서 "추세·급등락" 질문거리가 많고, 키 없이 받을 수 있는 공개 API 라 재현이 쉽다.
- **점검**: 빠진 날짜, 0 이하 값 확인 (`seed_upbit.py` 실행 시 출력)
- **요약 정보**: 기간, 개수, 평균, 최고·최저(날짜 포함), 기간 변화율, 30일 변화율, 일간 변동성(일간 수익률 표준편차), 최대 상승·하락일, 월별 평균·최고·최저
- **추세 판단**: 최근 30일 평균이 직전 30일 평균보다 +3% 이상이면 상승, -3% 이하면 하락, 그 사이는 보합
- **메모 자동 생성**: 하루 ±5% 이상 움직인 날에 "일간 +6.3% 급등" 메모를 붙여, AI 가 급등락일을 설명할 수 있게 했다.

## 12. 보안·운영
- API 키, 서비스 계정 키는 모두 환경 변수로 관리하고 코드에 넣지 않았다.
- **입력 검증(Pydantic)**: 잘못된 날짜, 0 이하 가격, 200자 넘는 메모, 빈 메시지는 422 로 거절한다.
- **예외 처리**: 없는 id 404, 중복 날짜 409, AI 호출 실패 503, 그 외 500 을 JSON 으로 돌려주고 프론트가 문구로 표시한다.
- **CORS**: `ALLOWED_ORIGINS` 에 등록한 프론트 주소만 호출할 수 있다.
- **비용 제한**: 작은 모델(`gpt-4o-mini`), `max_tokens=500`, 이전 대화는 최근 10개만 전송.

## 13. 제출 스크린샷
| 화면 | 이미지 |
|---|---|
| 데이터 요약이 보이는 채팅 (질문+답변) | ![채팅](docs/screenshots/01_chat.png) |
| 데이터 관리 (추가/수정/삭제) | ![데이터 관리](docs/screenshots/02_data.png) |
| 대화 기록 불러오기 | ![대화 기록](docs/screenshots/03_history.png) |
| Swagger UI | ![Swagger](docs/screenshots/04_swagger.png) |
| (보너스) 그래프·다크 모드 | ![그래프](docs/screenshots/05_chart_dark.png) |

## 14. 데이터 출처
- 업비트 Open API (시세 조회, 인증 불필요): https://docs.upbit.com
- AI 답변은 저장된 과거 데이터 요약만 근거로 하며 투자 조언이 아닙니다.
