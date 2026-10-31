# 법률 정보 에이전트 토큰 측정

Q7(컨셉 확정)의 조건을 확인하는 실험이다. [3안 비교](../../docs/reference/concept-comparison.md) 2.1에서 법률 정보안은 질문당 15K~40K 토큰, 하루 5~13개 질문으로 **추정**했다. 이 스크립트는 그 값을 실제로 잰다. 확정 기준은 무료 Groq 하루 200K 토큰으로 **하루 30개 질문 이상**이다.

## 무엇을 하나

제안서 5.1의 흐름을 작게 재현한다. LLM이 도구 두 개를 골라 부르는 루프를 돌리고, 호출마다 Groq가 돌려준 `usage`를 더한다.

| 도구 | 하는 일 | 국가법령정보 API |
| --- | --- | --- |
| `search_law` | 목록 검색, 최대 5건 | `lawSearch.do` |
| `get_law` | 본문 조회. 법령은 조문 하나만 지정할 수 있다 | `lawService.do` |

자료 종류(target)는 `lstrm`(법령용어), `law`(현행 법령), `school`(학칙·학교규정), `admrul`(행정규칙), `moelCgmExpc`(고용노동부 해석), `expc`(법령해석례), `prec`(판례)다. 질문은 제안서 7.1 사례에서 6개를 골랐다(용어 1, 학사 1, 노동 2, 주거 1, 교통 1).

조절값:
- `--max-steps` (기본 6): 질문당 LLM 호출 상한. 마지막 호출에서는 도구를 끄고 답을 강제한다. 결과에 `forced`로 남는다.
- `--max-chars` (기본 3000): 도구 결과 하나를 LLM에 넘길 최대 글자 수. 토큰을 가장 크게 좌우할 값이다.

이 두 값을 바꿔 돌리면 결과가 `results/steps<N>-chars<M>/`에 따로 쌓여 비교할 수 있다.

## 실행

준비:
1. `.env`에 `GROQ_API_KEY`와 `LAW_API_OC`를 넣는다. 이름은 `.env.example`에 있다. Groq 키 발급은 청년 정책 브랜치(`claude/exciting-goldberg-y71yhi`)의 `experiments/api-survey/api-keys.md` "2-1"과 같다.
2. 국가법령정보 공동활용(open.law.go.kr)에서 `법령`, `법령용어`, `학칙·공단·공공기관`, `행정규칙`, `고용노동부 법령해석`, `법령해석례`, `판례`의 OPEN API 활용을 신청한다. 신청할 때 호출할 PC의 IP나 도메인을 등록해야 할 수 있다(확인하지 않음). 승인되지 않은 자료는 `[API 오류]`로 LLM에 전달되고, 그 사례의 토큰은 실제보다 적게 나온다.

저장소 루트에서:

```bash
python3 experiments/legal-tokens/trial.py --fake
```

키 없이 흐름만 확인한다. 결과는 임시 폴더에 쓰고 저장소는 건드리지 않는다.

```bash
python3 experiments/legal-tokens/trial.py
```

기본 모델(`gpt-oss-120b`)로 6개 사례를 돌린다. Windows는 `py experiments/legal-tokens/trial.py`.

```bash
python3 experiments/legal-tokens/trial.py --models gpt-oss-20b,qwen3.8-27b --max-chars 1500
```

모델과 조절값을 바꿔 돌린다.

```bash
python3 experiments/legal-tokens/trial.py --report
```

저장된 결과로 요약만 다시 본다.

## 한도와 호출 수

- Groq 무료 한도는 분당 8K 토큰, 하루 200K 토큰이다(청년 정책 브랜치 `comparison.md`, 공식 표). 도구 결과가 쌓이면 호출 하나가 수천 토큰이라 429가 자주 난다. 스크립트가 `retry-after`만큼 기다리므로 6개 사례에 수십 분 걸릴 수 있다.
- `--budget`(기본 150,000)을 넘으면 그 모델은 멈춘다. 하루 한도를 다 쓰지 않게 하려는 값이다. 다음 날 다시 실행하면 저장되지 않은 사례부터 이어서 한다.
- 법령 API 응답은 `cache/`에 저장하고 같은 요청은 다시 보내지 않는다. 모델이나 조절값을 바꿔 다시 돌려도 법령 API 호출은 거의 늘지 않는다.

## 결과와 커밋

- `results/`에는 질문, 호출마다의 `usage`, 도구 인자와 결과 글자 수, 최종 답이 있다. `cache/`에는 공개 법령 원문이 있다. 키는 저장하지 않는다.
- 법령 API 응답의 링크에는 OC 값이 들어 있다. 스크립트가 저장 전과 LLM에 넘기기 전에 `OC={LAW_API_OC}`로 바꾼다. 커밋 전에 OC 값으로 한 번 검색해 확인한다.
- 둘 다 커밋해서 공유한다. 다음 사람이 `--report`로 같은 숫자를 볼 수 있다.

## 읽는 법

`--report`는 모델·조절값마다 질문당 평균·중앙값·최대 토큰과 하루 질문 수를 보여 준다. 판단할 때는 다음도 함께 본다.

- `forced` 사례가 많으면 단계 상한이 낮아 토큰이 실제보다 적게 나온 것이다.
- `[API 오류]`나 `검색 결과 0건`이 많으면 답의 품질과 토큰이 모두 실제와 다르다. 결과 파일의 도구 기록에서 확인한다.
- 답의 품질은 이 스크립트가 채점하지 않는다. 결과 파일의 `answer`를 사람이 읽는다.
