# 🚀 Railway 클라우드 배포 가이드
## (어디서나 접속 — WiFi 무관, 직원 공유 가능)

---

## 1단계 — GitHub에 올리기

1. https://github.com 가입 (없으면)
2. "New repository" → 이름: `nike-rack-monitor` → Create
3. 아래 명령어 실행 (cmd에서):

```bash
cd "C:\Users\vulca\OneDrive\바탕 화면\nike-rack-monitor"
git init
git add .
git commit -m "first commit"
git branch -M main
git remote add origin https://github.com/본인아이디/nike-rack-monitor.git
git push -u origin main
```

---

## 2단계 — Railway 배포

1. https://railway.app 접속 → GitHub으로 로그인
2. **"New Project"** 클릭
3. **"Deploy from GitHub repo"** 선택
4. `nike-rack-monitor` 레포 선택
5. 자동 배포 시작됨 (2~3분)

---

## 3단계 — API 키 환경변수 설정

Railway 대시보드에서:
1. 프로젝트 클릭 → **Variables** 탭
2. **"+ New Variable"** 클릭
3. 입력:
   - KEY: `OPENAI_API_KEY`
   - VALUE: `sk-proj-...` (본인 키)
4. **Add** 클릭 → 자동 재배포

---

## 4단계 — 고정 주소 설정

1. Railway 대시보드 → **Settings** 탭
2. **"Generate Domain"** 클릭
3. 예: `nike-monitor-production.up.railway.app` 생성됨
4. 이 주소를 직원들에게 공유!

---

## 5단계 — 폰 홈화면에 앱 아이콘 추가

**아이폰:**
1. Safari에서 주소 접속
2. 하단 공유버튼(□↑) → "홈 화면에 추가"
3. 이름: `랙모니터` → 추가

**안드로이드:**
1. Chrome에서 주소 접속
2. 우상단 메뉴(⋮) → "홈 화면에 추가"

→ 앱처럼 아이콘으로 바로 실행 가능!

---

## 접속 주소 정리

| 화면 | 주소 |
|---|---|
| 스캔 (사진 업로드) | `https://your-app.railway.app/` |
| 대시보드 (현황+변동) | `https://your-app.railway.app/dashboard` |

---

## ⚠️ Railway 무료 플랜 주의

- 월 500시간 무료 (한 서버 24시간 기준 약 20일)
- DB(SQLite)는 재배포 시 초기화될 수 있음
- 장기 운영 시 **Railway 유료 플랜($5/월)** 권장

---

## 로컬 PC 계속 쓰는 경우 (Railway 없이)

서버 켤 때마다 cmd에서:
```bash
cd "C:\Users\vulca\OneDrive\바탕 화면\nike-rack-monitor"
set OPENAI_API_KEY=sk-proj-...
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

모바일 접속: `http://192.168.123.103:8000`
대시보드: `http://192.168.123.103:8000/dashboard`
