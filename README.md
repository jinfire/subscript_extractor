# 대본 한 장 · YouTube 대본 추출

유튜브 링크를 입력하면 이미 제공되는 자막을 가져와 대본으로 복사하는 모바일 웹사이트입니다. 로그인, 데이터베이스, AI API 키 없이 사용합니다.

## 기능

- 일반 YouTube, youtu.be 공유, Shorts, live, embed 링크 지원
- **한국어 수동 → 한국어 자동생성 → 영어 수동 → 영어 자동생성** 순으로 자막 선택
- 해당 언어가 모두 없으면 사용 가능한 다른 언어 선택, 드롭다운에서 직접 변경 가능
- 시간 표시 켜기/끄기, 글자 수, 전체 복사
- 영상 출처와 한국어 요약·분석 요청문을 포함해 복사
- 긴 대본을 8,000자 단위로 나눠 복사 (모델별 토큰 한도와는 다릅니다)
- 모바일 화면, 하단 복사 버튼, 클립보드 실패 시 직접 복사 영역 제공
- 서버 메모리 캐시 10분/최대 16개, IP별 분당 12회, 동시 추출 4건 제한

## 실행

Python 3.10 이상이 필요합니다. 배포에는 Python 3.12를 권장합니다.

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

http://127.0.0.1:8000 에 접속합니다. 종료는 Ctrl+C입니다. 가상환경 활성화를 하지 않으므로 PowerShell 실행 정책 변경이 필요하지 않습니다.

Linux/macOS:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python app.py
```

`python app.py`는 로컬 개발 서버입니다. 공개 서비스에는 아래 Waitress 실행 명령을 사용하세요. 화면과 `/health`는 의존성 설치 전에도 열리지만 실제 추출에는 `youtube-transcript-api`가 반드시 필요합니다.

## GitHub와 배포

대상 저장소: https://github.com/jinfire/subscript_extractor

GitHub에 push하는 것과 공개 사이트 호스팅은 별개입니다. Python 서버가 필요하므로 GitHub Pages만으로 전체 서비스를 실행할 수 없습니다.

### Python 웹 서비스로 배포

호스팅에서 GitHub 저장소와 배포 브랜치를 연결합니다.

| 설정 | 값 |
| --- | --- |
| 빌드 명령 | `pip install -r requirements.txt` |
| 실행 명령 | `waitress-serve --host=0.0.0.0 --port=$PORT --threads=8 app:application` |
| 상태 확인 | `/health` |
| 런타임 | Python 3.12 |

`render.yaml`을 포함하여 Render Blueprint로도 설정할 수 있습니다. 호스팅 요금과 이용 가능 플랜은 생성 시 확인하세요. GitHub push 시 자동 배포하도록 설정하면 됩니다. 제공되는 HTTPS 주소를 사용하세요. 모바일 클립보드는 HTTPS 또는 localhost에서 동작합니다.

`/health`는 앱 프로세스가 응답하는지 확인하며 유튜브 추출 성공까지 확인하지 않습니다. **배포 서버에서 실제 영상을 넣어 추출되는지 확인해야 합니다.**

### Docker

```sh
docker build -t subscript-extractor .
docker run --rm -p 8000:8000 subscript-extractor
```

Docker 내부 서버는 Waitress를 사용합니다. 공개 배포에서는 호스팅의 HTTPS 프록시 뒤에 놓으세요.

## 자막을 가져오는 방식

[`youtube-transcript-api`](https://github.com/jdepoix/youtube-transcript-api)를 서버에서 실행합니다. 유튜브 내부 플레이어 정보에서 자막 주소를 얻고 해당 주소의 자막 본문을 요청합니다. 구글 공식 YouTube Data API가 아니며 별도 API 키는 필요하지 않습니다. 라이브러리 제작자의 서버를 경유하지 않습니다.

- 기존 수동·자동생성 자막만 가져옵니다. 자막이 전혀 없는 영상의 음성을 인식해 새로 대본을 만들지 않습니다.
- 자동 번역이나 AI 요약은 수행하지 않습니다. 요약 요청문과 대본을 복사하여 사용자가 ChatGPT에 붙여넣는 흐름입니다.
- 원문 순서와 내용을 유지하고 연속 공백만 정리합니다. 자동생성 자막에는 오타와 반복이 있을 수 있습니다.
- 클라우드 IP 차단, 봇 판정, 유튜브 내부 변경으로 추출이 실패할 수 있습니다. 로컬에서 성공해도 배포 환경에서 실패할 수 있습니다.
- 비공개·삭제·연령 제한 등 접근할 수 없는 영상은 실패할 수 있습니다.
- 차단을 자막 없음과 구분하여 표시합니다. 프록시나 로그인 쿠키를 통한 우회는 포함하지 않습니다.

## 데이터와 공개 운영

- 대본을 파일이나 DB에 영구 저장하지 않습니다. 서버 메모리 캐시는 재시작하면 사라집니다.
- 사용자 링크에서 영상 ID만 추출하며 임의의 사용자 입력 URL로 서버 요청을 보내지 않습니다.
- 자막은 HTML로 삽입하지 않고 텍스트 영역에 표시합니다.
- API 키·쿠키·토큰을 코드에 넣지 마세요. `.env`와 가상환경은 Git에서 제외합니다.
- 요청 제한과 캐시는 서버 프로세스별입니다. 여러 인스턴스에서는 공유되지 않습니다.
- 임의의 `X-Forwarded-For` 헤더는 신뢰하지 않습니다. 프록시 뒤에서는 여러 사용자가 같은 IP로 보일 수 있으므로 공개 운영 시 호스팅의 요청 제한과 신뢰 가능한 프록시 설정을 별도로 구성하세요.
- 사용자 계정 기능이 없고 사이트 접근은 공개입니다. 예기치 않은 대량 이용은 호스팅 요금을 발생시킬 수 있으므로 호스팅 사용량 한도를 설정하세요.

## API

`POST /api/transcript` · `Content-Type: application/json`

```json
{"url":"https://www.youtube.com/watch?v=dQw4w9WgXcQ","language":null}
```

`language` 생략/null은 자동 선택입니다. `"ko"`, `"en"` 등의 언어를 지정하면 해당 언어의 수동 자막을 우선합니다.

성공 응답에는 `video_id`, `url`, `language`, `is_generated`, `languages`, `segments`가 있습니다. 각 segment는 `text`와 초 단위 `start`를 포함합니다. 오류 응답에는 `error` 코드와 사용자용 `message`가 있습니다.

## 검증

외부 패키지 없이 로컬 서버·입력 검증·언어 선택·캐시·요청 제한·HTTP 계약을 테스트할 수 있습니다.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
node --test tests/text.test.mjs
node --check static/app.js
```

화면 동작 테스트에는 개발용 Node.js 22 이상과 jsdom이 필요합니다. 사이트 서버 자체에는 Node.js가 필요하지 않습니다.

```powershell
npm install
npm test
```

자동 테스트의 자막 공급자는 고정 테스트 데이터입니다. 실제 유튜브 통신 성공이나 모바일 브라우저 클립보드 동작을 보장하지 않습니다. 검증 결과와 환경 제약은 [검증 기록](docs/verification.md)에 남깁니다.

파일 구성:

```text
app.py              WSGI 서버, 추출 어댑터, 캐시, 요청 제한
static/             화면, 스타일, 복사·분할 로직
tests/              Python·JavaScript 테스트
requirements.txt    자막 라이브러리와 운영 서버
Dockerfile          Docker 배포
render.yaml         Render 배포 설정
```
