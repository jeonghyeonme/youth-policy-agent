# web — 서비스 코드

Next.js(TypeScript) 앱이다. Vercel에 배포하며 Root Directory는 `web`이다([D11](../docs/decisions/D11.md), [D12](../docs/decisions/D12.md)). 계획은 [docs/plan.md](../docs/plan.md).

## 실행

```bash
npm ci
```

```bash
npm run dev
```

## 검사 (CI와 같다)

```bash
npm run lint && npm run typecheck && npm test && npm run build
```

- 테스트는 Node.js 내장 테스트 도구(`node --test`)로 TypeScript를 바로 실행한다. Node 22 이상이 필요하다.
- 테스트는 공공 API·Groq를 부르지 않는다. `experiments/context-measurement/samples/`의 저장 응답을 읽는다(AGENTS.md "트래픽").
- `lib/` 안의 파일은 서로 `.ts` 확장자를 붙여 불러온다(Node가 그대로 실행하기 위해).

## 구조

| 위치 | 하는 일 | 근거 |
| --- | --- | --- |
| `lib/policy/types.ts` | 정책·사용자 조건 타입. 나이는 숫자로만 판단(0~0은 제한 없음) | log/017 |
| `lib/policy/filter.ts` | 지역·나이·취업·신청 가능 필터 | D9 2단계 |
| `lib/policy/rank.ts` | 키워드 일치 → 맞춤도 → 지역 전용 순위, 상위 8건 | D9 3단계 |
| `lib/policy/codeVerdict.ts` | 코드 요건 판정, LLM 판정과 합치기 | D10 |
| `lib/sources/youthcenter.ts` | 온통청년 API 요청·응답 해석 | D6, log/011·016 |
| `lib/sources/cache.ts` | 공공 API 응답 메모리 캐시 | D8 |
| `lib/policy/medianIncome.ts` | 2026년 기준 중위소득 표(보건복지부) | D10 개선 |
| `lib/llm/vocab.ts` | LLM이 고를 수 있는 분류 값(코드정의서). 목록 밖 값은 API로 보내지 않는다 | AGENTS.md "개인정보" |
| `lib/llm/understand.ts` | 질문 → 대분류·중분류·정책 키워드·순위용 단어 | D9 1단계 |
| `lib/llm/judge.ts` | 서술형 자격 판정 프롬프트와 결과 해석 | D10 2단계 |
| `lib/llm/groq.ts` | Groq 호출(fetch, JSON 모드), 한도 오류 | D5, D7 |
| `lib/chat/types.ts` | `api/chat` 요청·응답 형식 — **초안, PM 승인 전(Q9)** | AGENTS.md "구조" |
| `lib/chat/validate.ts` | 요청 본문 검증 | |
| `lib/chat/answer.ts` | 질문 한 턴: 이해 → 온통청년 → 필터·순위 → 코드 판정 + 서술형 판정 → 카드 | D9, D10 |
| `app/api/chat/route.ts` | `POST /api/chat`. 키는 여기서만 읽고, 요청 내용은 로그에 남기지 않는다 | D11 |

## 실제 키로 한 번 돌려 보기 (사람이 로컬에서)

```bash
node --env-file=../.env scripts/try-question.ts A
```

`A` 또는 `B`(대표 질문, D2). 질문 하나에 온통청년 최대 2회, Groq 2회를 부른다. AI 도구는 실행하지 않는다(AGENTS.md "API 키").

## 환경변수

`.env.example`(저장소 루트)의 이름을 쓴다. 서버가 쓰는 것은 `YOUTHCENTER_API_KEY`, `GROQ_API_KEY`. 로컬 `npm run dev`는 `web/.env.local`, 스크립트는 루트 `.env`, 배포는 Vercel 환경변수. 키 값은 커밋하지 않는다.
