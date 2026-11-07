# API별 컨텍스트 소모량 측정

후보 공공 API를 하나씩 호출해, LLM에 넘길 때 드는 컨텍스트 양을 재고 온통청년과 묶을 API를 추립니다. 방향만 정했고 세부 설계는 미정입니다.

## 무엇을 재나

컨텍스트는 세 곳에서 늘어납니다.

| 출처 | 규모 | 비고 |
| --- | --- | --- |
| 도구 정의 | API당 수백 토큰 수준 | 함수 이름·설명·파라미터 스키마 |
| API 응답 | 가장 큼 | 서버 필터링 전후를 따로 잴 것 |
| 대화 기록 | 턴이 늘수록 증가 | 대표 질문으로 시뮬레이션 |

## 준비된 것

- [API 조사](api-survey.md): 후보 API 다섯 개의 요청값·응답 형식·키 파라미터·2단계 호출 여부 (공개 문서 기준)
- [대표 질문](question-candidates.md): A·B로 확정([D2](../../docs/decisions/D2.md))
- `measure.py`: 저장한 응답 파일(JSON/XML)의 크기를 잰다. API를 호출하지 않는다. 표준 라이브러리만 쓴다

  ```bash
  python3 experiments/context-measurement/measure.py samples/youthcenter/*.xml
  python3 experiments/context-measurement/measure.py samples/youthcenter/*.xml --keep fields/youthcenter.txt
  ```

  원본, 빈 값을 뺀 JSON, `--keep`에 적은 필드만 남긴 JSON의 크기를 건수·건당 글자와 함께 표로 낸다. 토큰 기준(Q5)이 정해지기 전이라 바이트·글자 수로 잰다. 파일에 `serviceKey`·`openApiVlak` 같은 키 파라미터 이름이 보이면 재지 않고 멈춘다.
- 테스트: `python3 -m unittest experiments/context-measurement/test_measure.py` (손으로 만든 작은 샘플 사용)

## 측정 전에 정할 것

- [ ] API 키 발급: 온통청년 마이페이지, 공공데이터포털 서비스별 활용신청
- [ ] 토큰 계산 기준 (같은 한국어도 LLM마다 토큰 수가 다름)
- [x] 호출 조건: 대표 질문 A·B ([D2](../../docs/decisions/D2.md))
- [ ] 온통청년 API가 옛 형식(`youthPlcyList.do`)인지 개편 형식인지 확인 ([조사](api-survey.md#온통청년-문서끼리-맞지-않는다))
- [ ] 추리는 기준: 소모량 상한, 쓸모와의 균형

## 주의

- 복지로 중앙부처 API는 개발계정 트래픽이 **100**입니다. 응답을 한 번 받아 로컬에 저장해 두고 재사용하세요. 복지로·잡알리오는 목록 → 상세 2단계라 정책 N건에 호출이 N+1번 듭니다.
- 저장한 응답 샘플은 공개 데이터이지만, 키가 들어간 요청 URL은 저장하지 마세요.

결과는 이 디렉토리에 `results.md`로 정리합니다.
