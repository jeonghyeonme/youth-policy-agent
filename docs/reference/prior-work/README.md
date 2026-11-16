# 다른 작업 브랜치에서 옮긴 기록

> [문서 지도](../../README.md) · 2026-11-16 정리(log/033)

2026-10-29~11-02에 다른 세션이 청년 정책을 따로 진행한 브랜치 두 개(`claude/exciting-goldberg-y71yhi`, `claude/lucid-volta-qkj1pk`)가 있었다. `main`에 병합되지 않았고, 결정·로그 번호가 지금 `main`과 겹쳐 통째로 합칠 수 없었다. 쓸모 있는 것만 골라 옮기고 브랜치는 지운다. 원래 내용은 커밋 `07a31e7`(lucid-volta, goldberg 포함)에 있었다.

| 문서 | 무엇 | 왜 옮겼나 |
| --- | --- | --- |
| [concept-scorecard.md](concept-scorecard.md) | 청년 정책·법률 정보·생필품 세 컨셉 점수표 | "왜 청년 정책인가"의 근거(D16) |
| [concept-comparison.md](concept-comparison.md) | 세 컨셉 비교 | 위와 같음 |
| [youth-vs-legal.md](youth-vs-legal.md) | 청년 정책 대 법률 정보 | 위와 같음 |
| [candidate-legal-agent.md](candidate-legal-agent.md) | 법률 정보 에이전트 제안서(채택 안 함) | 비교 문서가 가리키는 원문 |
| [youth-experiments.md](youth-experiments.md) | 그 브랜치의 청년 정책 실측 두 건 요약, 다른 설계(사전 수집) | 지금 구현과 비교할 숫자, 개선 후보 |

키 발급 절차와 키 확인 스크립트는 [experiments/api-survey](../../../experiments/api-survey/README.md)로 옮겼다.

**옮기지 않은 것**: 법률 정보안 토큰 측정, 무료 LLM 후보 시험(컨셉·모델이 정해짐, D16·D7), 공통 정책 형식과 수집·변환 스크립트·샘플(사전 수집 설계용, 아래 요약 참고).
