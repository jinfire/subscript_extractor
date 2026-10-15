# 검증 기록

검증일: 2026-10-15 (Windows, Python 3.10.8, Node.js 24.14.0)

## 통과한 항목

- Python unittest 20개: 지원 링크와 외부 호스트 차단, 수동/자동 자막 언어 우선순위, 캐시 만료, 요청 제한, 동시 추출 제한, 오류 후 슬롯 반환, 요청 본문 검증, 정적 파일 경로 제한, HTTP 서버 통신
- JavaScript 테스트 9개: 타임스탬프, 원문 보존, 이모지 분할, 요약 요청문, 화면 제출, 언어 전환, 전체/요청문/부분 복사, 클립보드 실패 시 수동 복사, 추출 오류 후 재시도
- `node --check static/app.js` 문법 검사
- Python `py_compile` 문법 검사
- 실제 개발 서버에서 `/`, `/static/app.js`, `/static/style.css`, `/static/text.mjs`, `/health` HTTP 200 응답
- 실제 개발 서버에서 추출 모듈 미설치 시 503 `dependency_missing` 오류 안내

## 실행 방법

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
npm install
npm test
npm run check
```

이 환경에서는 npm 신규 설치 대신 인접 프로젝트의 기존 jsdom 설치를 `TEST_MODULE_ROOT`로 지정하여 화면 동작 테스트를 실행했습니다. 다른 프로젝트의 파일은 변경하지 않았습니다.

## 남아 있는 검증과 환경 제약

- GitHub TCP 443 연결 테스트 실패, `git ls-remote` 연결 실패
- `gh auth status`: 이 실행 환경에서 로그인된 GitHub 호스트 없음
- `git add`: `.git/index.lock` 생성 권한 거부. 세션의 `.git` 읽기 전용 제한으로 스테이징·커밋·push 미완료
- 재확인: PyPI 직접 HTTPS 요청이 `WinError 10013`(소켓 접근 권한 거부)으로 실패. 패키지 버전 부재로 판정할 수 없음
- 사용자 설치 후 `youtube-transcript-api 1.2.3`, `waitress 3.0.2`가 프로젝트 가상환경에 설치된 것을 확인
- 실제 영상 ID `dQw4w9WgXcQ`로 API와 라이브러리 직접 호출을 시도했으나 YouTube HTTPS 연결이 `WinError 10013`으로 실패. 실제 자막 추출 성공은 미확인
- 제약된 실행 도구에서 띄운 개발 서버는 종료함. 사용자 PowerShell에서 서버를 실행하여 네트워크 접근을 확인할 필요가 있음
- 자동 테스트는 테스트 공급자를 주입하여 수행했으며 실제 추출 성공을 뜻하지 않음
- Waitress 운영 서버 실행과 Docker 이미지는 검증하지 못함
- jsdom은 실제 브라우저가 아니므로 모바일 화면 배치·Safari/Chrome의 실제 클립보드 권한은 추가 확인 필요
- 공개 호스팅 배포와 배포 서버에서의 유튜브 IP 차단 여부는 미확인

위 제약을 해소한 후 `requirements.txt`를 설치하고 수동 자막/자동생성 자막/자막 없는 영상으로 실제 추출을 확인해야 합니다. 저장소 push와 공개 호스팅 배포는 구분하여 확인하세요.
