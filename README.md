# 📦 Nike Rack Monitor

나이키 매장 진열 랙 실시간 모니터링 시스템

## 폴더 구조

```
nike-rack-monitor/
├── main.py           # FastAPI 서버
├── database.py       # SQLite 데이터 저장/조회/비교
├── analyzer.py       # GPT-4o 병렬 이미지 분석
├── requirements.txt  # 필요 패키지
├── railway.toml      # Railway 클라우드 배포 설정
└── static/
    └── index.html    # 웹/모바일 UI
```

---

## ✅ 로컬 테스트 방법 (PC에서)

1. Python 설치 확인 (3.10 이상)
2. 터미널에서:

```bash
cd nike-rack-monitor
pip install -r requirements.txt
```

3. OpenAI API 키 환경변수 설정:

**Windows:**
```
set OPENAI_API_KEY=sk-xxxxxxxxxxxxx
```

**Mac/Linux:**
```
export OPENAI_API_KEY=sk-xxxxxxxxxxxxx
```

4. 서버 실행:
```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

5. 브라우저: `http://localhost:8000`
6. 같은 WiFi 모바일: `http://[PC의 IP]:8000` (예: http://192.168.0.10:8000)

---

## ☁️ Railway 클라우드 배포 (어디서나 접속)

1. https://railway.app 가입 (GitHub 로그인)
2. "New Project" → "Deploy from GitHub repo"
3. 이 폴더를 GitHub에 올린 후 연결
4. Railway 대시보드 → Variables → 추가:
   ```
   OPENAI_API_KEY = sk-xxxxxxxxxxxxx
   ```
5. 배포 완료 후 제공되는 URL로 접속 (모바일, PC 모두 가능)

---

## 📸 사용법

1. 상단에서 **김해 / 정관** 매장 선택
2. 랙 사진을 찍을 때:
   - 한 랙 끝에서 끝까지 찍기 (여러장)
   - **랙이 바뀔 때마다 검은 암전 사진 1장 삽입**
   - 1번 랙 → 암전 → 2번 랙 → 암전 → 3번 랙 ...
3. 사진 모두 선택 후 **"AI 분석 시작"** 클릭
4. 수십장도 동시 병렬 처리 → 빠름
5. 결과:
   - **변동 내역**: 이전 스캔과 비교 (신규/제거/가격변동)
   - **전체 랙 현황**: 랙별 품번/가격/할인율 테이블
6. **스캔 기록**에서 이전 회차 언제든 다시 조회 가능

---

## 🔧 GPT-4o vs GPT-4o-mini 차이

| | gpt-4o-mini | gpt-4o |
|---|---|---|
| 신발 태그 인식 | 작은 글씨 오인식 많음 | 높은 정확도 |
| 비용 (사진 1장) | ~$0.001 | ~$0.01 |
| 500장 기준 | ~$0.5 | ~$5 |

→ 정확도를 위해 **gpt-4o 풀버전** 권장

---

## ⚠️ 주의사항

- SQLite DB 파일(`nike_monitor.db`)이 서버와 같은 폴더에 생성됨
- Railway 무료 플랜은 DB 파일이 재배포 시 초기화될 수 있음
  → 중요 데이터는 Railway 유료 플랜 or Supabase 연동 권장
- 로컬 실행 시에는 PC 꺼지면 모바일 접속 불가
