# 공통 정책 형식 (초안)

> [api-survey 계획](README.md) W3 · 상태: **초안, PM 확정 전**(Q10) · 온통청년은 키 승인 전이라 아직 매핑하지 않았다
> 출처 다섯 개의 정책·공고를 한 형식으로 옮긴다. 서버 필터, 결과 카드, LLM 설명이 모두 이 형식만 읽는다.
> 변환 코드: [normalize.py](normalize.py). 채움률은 이 스크립트로 다시 낼 수 있다.

## 형식

레코드 하나가 정책 또는 공고 하나다.

| 필드 | 형태 | 뜻 | 쓰는 곳 |
| --- | --- | --- | --- |
| `id` | 문자열 | `<출처>:<원본 ID>` (예: `welfare-central:WLF00000781`) | 전부 |
| `source` | `youthcenter`, `jobalio`, `lh`, `welfare-central`, `welfare-local` | 출처 | 카드 |
| `title`, `summary` | 문자열 | 정책명, 한 줄 요약 | 카드, LLM |
| `categories` | 목록 | 온통청년 대분류(일자리, 주거, 교육, 복지문화, 참여권리) 중 하나 이상 | 서버 필터 |
| `regions` | 목록 | 짧은 시도명(서울, 경기, …) 또는 `["전국"]` | 서버 필터 |
| `period` | `{start, end, status}` | 날짜는 `YYYY-MM-DD`. `status`는 `open`, `closed`, `always`, `unknown` | 서버 필터, 카드 |
| `url` | 문자열 | 원문 링크 | 카드 |
| `eligibility.age` | `{min, max}` | 나이 조건 | 서버 필터 |
| `eligibility.income` | `{type, min, max}` | 소득 조건 | 서버 필터 |
| `eligibility.education`, `eligibility.job_status` | 목록 | 학력, 취업상태 조건 | 서버 필터 |
| `eligibility.life_stages`, `eligibility.households` | 목록 | 생애주기(청년 등), 가구상황(저소득 등) | 서버 필터 |
| `eligibility.texts` | `[{label, text}]` | 서술형 자격조건 (지원대상, 선정기준, 신청자격 등) | **LLM 설명** |
| `eligibility.in_attachment_only` | 참·거짓 | 자격조건이 첨부 공고문에만 있다 (LH, D2) | 카드 |
| `benefit`, `how_to_apply` | 문자열 | 지원 내용, 신청 방법 | 카드, LLM |

### 코드 조건은 세 가지 상태를 구분한다

`eligibility`의 코드 조건(`age`부터 `households`까지)은 값이 셋 중 하나다.

| 값 | 뜻 | 서버 필터 |
| --- | --- | --- |
| `null` | 원본에 정보가 없다 | 걸러내지 않는다. 서술형이 있으면 LLM이 설명한다 |
| `[]` | 제한 없음 (예: 잡알리오 "학력무관") | 걸러내지 않는다 |
| 값이 있음 | 조건이 있다 | 사용자 값이 맞지 않으면 걸러낸다 |

정보가 없는 정책을 걸러내면, 받을 수 있는 정책을 놓친다. 그래서 확실히 안 맞는 것만 뺀다.

### LLM에는 무엇이 가나 (D3)

서버가 걸러 낸 상위 몇 건의 `title`, `summary`, `eligibility.texts`, `benefit`만 넘긴다. 나머지 필드는 카드로 보여 준다. LH(`in_attachment_only`)는 LLM에 넘기지 않는다.

## 출처별 매핑

| 공통 필드 | 잡알리오 | LH (임대주택만) | 복지로 중앙부처 | 복지로 지자체 |
| --- | --- | --- | --- | --- |
| `title` | `[instNm] recrutPbancTtl` | `PAN_NM` | `servNm` | `servNm` |
| `summary` | `hireTypeNmLst · recrutSeNm · ncsCdNmLst` | `AIS_TP_CD_NM` | `servDgst` | `servDgst` |
| `categories` | 일자리 | 주거 | 관심주제(`intrsThemaArray`) + 제목 낱말 | 관심주제(`intrsThemaNmArray`) + 제목 낱말 |
| `regions` | 근무지역(`workRgnNmLst`) | `CNP_CD_NM` | 전국 | `ctpvNm` |
| `period` | `pbancBgngYmd`~`pbancEndYmd`, `ongoingYn` | `PAN_NT_ST_DT`~`CLSG_DT`, `PAN_SS` | 상시 | 상세의 `enfcBgngYmd`~`enfcEndYmd` (`99991231`은 상시) |
| `url` | `srcUrl` | `DTL_URL` | `servDtlLink` | `servDtlLink` |
| `education` | `acbgCondNmLst` (학력무관은 `[]`) | - | - | - |
| `life_stages` | - | - | `lifeArray` | `lifeNmArray` |
| `households` | - | - | `trgterIndvdlArray` | `trgterIndvdlNmArray` |
| `texts` | 신청자격, 결격사유, 우대조건 | - (첨부파일) | 상세의 지원대상, 선정기준 | 상세의 지원대상, 선정기준 |
| `benefit` | - | - | 상세의 `alwServCn` | 상세의 `alwServCn` |

## 샘플로 확인한 채움률

`normalize.py` 실행 결과다(2026-10-29 샘플, 934건). 필수 필드(`title`, `url`)가 빠진 레코드는 없다.

| 출처 | 건수 | categories | regions | period.end | education | life_stages | households | texts |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 잡알리오 | 200 | 100% | 100% | 100% | 26% | 0% | 0% | 100% |
| LH | 73 | 100% | 100% | 100% | 0% | 0% | 0% | 0% |
| 복지로 중앙부처 | 461 | 98% | 100% | 0% (상시) | 0% | 64% | 60% | 4% |
| 복지로 지자체 | 200 | 74% | 100% | 0% | 0% | 62% | 41% | 5% |

복지로의 `texts`가 낮은 것은 상세를 일부만 받았기 때문이다(중앙부처 20건, 지자체 10건). 전체 수집에서는 청년 대상 상세를 모두 받는다.

## 샘플에서 드러난 점

- **나이는 어느 출처에도 코드로 없다.** 공공데이터포털 4개 출처 모두 `eligibility.age`가 0%다. 복지로는 나이를 요청값(`age`)으로만 받고 응답에는 주지 않는다. D1로 미리 수집하면 이 요청값 필터도 쓸 수 없다. 나이는 온통청년의 나이 필드(키 승인 후 확인), 복지로의 생애주기 "청년", 그리고 서술형(예: 잡알리오 "만 20세 이상")에 기대야 한다. Q4(서술형 판단 주체)의 근거다.
- **소득도 코드로 없다.** 온통청년 소득조건 코드(`earnCndSeCd`)가 유일한 후보다.
- **지역 이름이 출처마다 다르다.** LH와 복지로는 "전남광주통합특별시", 잡알리오는 "전남광주"로 쓴다. 둘 다 `["광주", "전남"]`으로 옮긴다.
- **분류는 관심주제만으로는 부족하다.** "청년 주택임차보증금 이자 지원"은 관심주제가 서민금융뿐이라 주거로 잡히지 않는다. 제목 낱말(주택, 월세, 전세 등)로 분류를 보탰다. 낱말 목록은 임시다.
- **생애주기가 빈 복지 서비스가 많다.** 중앙부처 461건 중 165건이 비어 있다. "제한 없음"인지 "정보 없음"인지 알 수 없어 `null`(걸러내지 않음)로 둔다.

## 남은 일

- 온통청년 매핑. 코드표로 확인한 필드는 `lclsfNm`, `mclsfNm`, `plcyKywdNm`, `schoolCd`, `jobCd`, `plcyMajorCd`, `sbizCd`, `mrgSttsCd`, `earnCndSeCd`, `aplyPrdSeCd`다. 나이(`sprtTrgtMinAge`, `sprtTrgtMaxAge`), 소득 금액, 지역(`zipCd`), 서술형(`addAplyQlfcCndCn`, `ptcpPrpTrgtCn`, `earnEtcCn`)은 추정한 이름이라 실제 응답으로 확인한다.
- 시군구 단위 지역(복지로 지자체 `sggNm`, 온통청년 `zipCd`)을 쓸지 정한다.
- 출처 사이 중복 정책 묶기(W4 겹침 분석 뒤).
