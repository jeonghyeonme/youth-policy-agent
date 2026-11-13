# STATUS — 지금 상태와 다음 할 일

> **작업 시작점.** 이 파일은 "지금"만 담고 **덮어쓴다**(80줄 상한). 끝난 일은 지우고 경위는 [log/](log/README.md)로 보낸다.
> PM이 관리한다. 작업자는 자기 담당 줄의 "상태"만 고치고, 새 일·우선순위 변경은 PM에게 말한다.
> 마지막 갱신: 2026-11-08 · [log/023](log/023.md)

## 현재 단계

**기획 → API 검증** (실질 개발 4~5주, 주차별 계획 미정). 측정·실험 스크립트만 있음(`experiments/context-measurement/`). 스택은 Next.js + Vercel([D11](decisions/D11.md)), 코드는 `web/`([D12](decisions/D12.md)). PR마다 CI가 돈다([D3](decisions/D3.md)). 제안서: [reference/proposal.md](reference/proposal.md)

## 할 일

| # | 할 일 | 담당 | 상태 | 기한 | 근거 |
| --- | --- | --- | --- | --- | --- |
| T1 | 팀 인원·역할 확정 | PM | 대기 | - | Q5 |
| T4 | API별 컨텍스트 소모량 측정 — [결과](../experiments/context-measurement/results.md). 남은 것: Groq 무료 한도 확인(콘솔 Settings → Limits, 사람) | PM | 진행 중 | - | [측정 계획](../experiments/context-measurement/README.md) |
| T6 | 공공데이터포털 운영계정 신청(시연 전, 활용 사례 등록) | PM | 대기 (서비스가 동작한 뒤) | 시연 전 | [D8](decisions/D8.md) |
| T5 | GitHub 저장소 공개, 팀원 초대 | PM | 대기 | - | - |

상태 값: `대기` · `진행 중` · `막힘(이유)` · `검토 중` — 끝나면 줄을 지우고 `log/`에 남긴다.

## PM 승인 대기 (승인 전 착수 금지)

[AGENTS.md "PM 승인이 필요한 결정"](../AGENTS.md#pm-승인이-필요한-결정)에 해당하는 것. 누구든(AI 포함) 올릴 수 있고, **PM이 승인하기 전에는 그 결정에 기대는 작업을 진행하지 않는다.** 승인되면 `decisions/D<번호>.md`로 옮기고 여기서 지운다.

| # | 정할 것 | 선택지 / 추천안 | 올린 사람 | 막고 있는 일 |
| --- | --- | --- | --- | --- |
| Q5 | 팀 인원·역할 (LLM은 Groq `openai/gpt-oss-120b`로 정함, [D5](decisions/D5.md)·[D7](decisions/D7.md)) | - | PM | T1 |

## 열린 위험

- **Groq 무료 한도**: 분당 8,000토큰이면 서비스 전체가 분당 답변 1번 정도다(키 하나를 모든 사용자가 나눠 씀). 문서끼리 값이 달라 콘솔에서 확인해야 한다. [조사](../experiments/context-measurement/groq-models.md)
- **걸러도 큰 결과**: 온통청년은 `zipCd`(시군구 코드)로 거를 수 있다. 그래도 대표 질문 A는 지역·나이·취업으로 걸러 약 250건(약 13만 자)이 남는다. 상위 8건만 넘기는 3단계로 정했다([D9](decisions/D9.md)). [결과](../experiments/context-measurement/results.md#온통청년-지역-필터-2026-11-08-확인)
- **2단계 호출**: 복지로 두 API·잡알리오는 목록 → 상세라 정책 N건에 N+1번 호출. 복지로 중앙부처 한도 100이면 상세 수십 건으로 하루를 다 쓴다.
- **복지로 중앙부처 API 개발계정 트래픽 100**: 팀 개발에 빠듯하다. 응답을 저장해 두고 재사용한다(AGENTS.md).
- **API 키 공유 방식**: 저장소 밖에서 공유한다. 채팅 AI에 키나 `.env` 내용을 붙여넣지 않는다.
- **일정**: 주차별 계획이 없다. Q5(인원·역할)가 정해지면 세운다.
