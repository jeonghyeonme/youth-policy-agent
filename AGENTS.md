# AI 코딩 도구 작업 규칙

이 저장소에서 작업하는 AI 코딩 도구(Claude Code, Codex, Cursor, Copilot, Gemini CLI 등)는 아래 규칙을 따른다.
청년 정책 안내 에이전트 — 사회 초년생의 채팅 질문을 LLM이 해석해 공공 API(온통청년 중심)를 호출하고 받을 수 있는 정책을 설명하는 웹 서비스. 팀 프로젝트, 현재 기획 단계.

## 무엇을 할 때 어디를 읽나

| 상황 | 읽을 것 |
| --- | --- |
| 작업 시작·이어하기 | [docs/STATUS.md](docs/STATUS.md) |
| 이 일이 왜 이렇게 정해졌나 | [docs/decisions/README.md](docs/decisions/README.md) → 해당 `D<번호>.md` |
| 원래 기획 | [docs/reference/proposal.md](docs/reference/proposal.md) |
| 작업 절차·브랜치·PR | [docs/process/workflow.md](docs/process/workflow.md) |
| 작업 마무리(기록) | [docs/process/wrap-up.md](docs/process/wrap-up.md) |

`docs/log/`는 "왜 그렇게 됐나"를 따라갈 때만 연다. 작업 시작 때 읽지 않는다.

## 결정

- STATUS "결정 대기"(Q 번호)에 있는 것을 AI가 정하지 않는다. 선택지와 장단점을 정리해 사람에게 묻는다.
- 구현 전에 근거(`D` 번호, 회의 날짜)를 밝힌다. 근거가 없으면 먼저 묻는다.
- 작업을 끝내면 [마무리 절차](docs/process/wrap-up.md)대로 `docs/log/NNN.md`를 남긴다.

## API 키

- `.env`와 `.env.*` 파일(단, `.env.example` 제외)을 읽거나, 출력하거나, 수정하지 않는다.
- 키 값을 코드, 테스트, 로그, 커밋 메시지, 문서에 적지 않는다. 환경변수 이름(`YOUTHCENTER_API_KEY` 등)으로만 참조한다.
- 공공 API를 실제로 호출해야 하면 사람에게 실행을 맡기고, 결과만 받는다.
- 새 환경변수가 필요하면 `.env.example`에 이름과 설명만 추가한다.

## 개인정보

- 사용자 대화나 선택값을 서버 로그, 파일, DB에 남기는 코드를 쓰지 않는다.
- 공공 API 검색어에 사용자 문장을 그대로 넣지 않는다. LLM이 뽑은 키워드만 보낸다.

## 트래픽

- 복지로 중앙부처 API는 개발계정 트래픽이 100이다. 반복 호출하는 코드나 테스트를 만들지 말고, 저장해 둔 응답 샘플을 쓴다.
