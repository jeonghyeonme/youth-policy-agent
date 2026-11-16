# api-survey — 공공 API 키 발급과 확인

> 키 발급 절차와 키 확인 스크립트만 있다. `claude/lucid-volta-qkj1pk`(커밋 `07a31e7`)의 같은 이름 폴더에서 옮겼다(log/033). 그 브랜치의 수집·변환 스크립트와 샘플은 옮기지 않았다(지금 `main`은 실시간 호출 + 캐시, D8·D9).

- [api-keys.md](api-keys.md): 온통청년·공공데이터포털·Groq 키 받는 법, `.env`에 넣는 법.
- `check_keys.py`: 넣은 키가 서비스마다 동작하는지 한 번씩 부른다. 사람이 로컬에서 실행한다(AGENTS.md "API 키"). 키와 요청 URL은 출력하지 않는다.

```bash
py experiments/api-survey/check_keys.py
```
