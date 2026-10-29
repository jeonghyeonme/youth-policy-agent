# 무료 LLM 후보 시험

Q5(LLM 업체)를 정하기 위한 실험이다. 업체 비교는 [comparison.md](comparison.md)에 있다.

## 실행

저장소 루트에서 실행한다. `.env`에 `GROQ_API_KEY`가 있어야 하고, `MISTRAL_API_KEY`가 없으면 Mistral은 건너뛴다.

```bash
python3 experiments/llm-providers/trial.py            # Windows: py experiments/llm-providers/trial.py
python3 experiments/llm-providers/trial.py --report   # 저장된 결과로 요약만 다시 본다
```

이미 저장된 사례는 다시 호출하지 않는다. 중간에 멈추면 다시 실행하면 된다.

## 무엇을 시험하나

D3의 두 호출을 그대로 흉내 낸다.

| 호출 | 입력 | 보는 것 |
| --- | --- | --- |
| 1회차 해석 (사례 `q01`~`q10`) | 직접 만든 질문 10개 | 분야·나이·지역·취업상태·학력을 정답과 비교해 맞힌 수 |
| 2회차 설명 (사례 `e01`~`e03`) | 사용자 유형 3개와 수집한 공개 정책 3건씩 | 사람이 읽고 판단한다. 자격조건을 지어내지 않는지, 해당 안 되는 정책을 해당 안 된다고 말하는지 |

모델마다 13회 호출한다. Groq 세 모델(`gpt-oss-120b`, `gpt-oss-20b`, `qwen3.8-27b`)이면 39회다. Groq의 세 모델은 엄격한 JSON 스키마 출력을 쓰고, 추론은 가장 낮게(`low`) 또는 끄고(`none`) 부른다. 추론 토큰도 하루 토큰 한도에서 빠지기 때문이다.

결과는 `results/<프롬프트 버전>/<모델>/<사례>.json`에 저장된다. 프롬프트를 고치면 `trial.py`의 `PROMPT_VERSION`을 올려서, 이전 결과를 덮지 않고 새로 시험한다. 지난 버전 요약은 `--report --version v1`로 본다. 요약에는 설명에 섞인 한자·라틴 문자 낱말도 나온다. 응답 원문과 토큰 사용량(`usage`)이 들어 있다. 입력은 직접 만든 문장과 공개 정책 텍스트뿐이고 키는 저장하지 않으므로, 커밋해서 공유한다.
