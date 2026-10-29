# 공공 API 명세 확인 결과 (2026-10-29)

> [api-survey 계획](README.md) · 키 없이 볼 수 있는 공개 자료만 확인했다. 실제 응답은 아직 받지 않았다.
> 출처: 온통청년 OPEN API 소개 페이지, 각 data.go.kr 페이지에 들어 있는 Swagger 명세, LH 활용가이드(docx), data.go.kr 파일 데이터 페이지.

## 한눈에 보기

| API | 자격조건이 있는 곳 | 호출 패턴 | 사용자 조건으로 거를 수 있는 요청값 | 개발계정 한도 |
| --- | --- | --- | --- | --- |
| 온통청년 | 응답 필드(코드 + 서술형). 필드 설명표는 미확인 | 목록 하나 | 정책명, 지역(`zipCd`), 분류·키워드 | 기관 정책 |
| 잡알리오 | **목록 응답에 있음** (`aplyQlfcCn` 신청자격, `disqlfcRsn` 결격사유, `prefCondCn` 우대조건) | 목록 하나로 충분, 상세는 첨부파일·전형단계 | 학력(`acbgCondLst`), 근무지역(`workRgnLst`), 고용유형, 진행여부 | 1,000 |
| LH | **목록에 없음.** 상세에 일부 서술형(`ETC_CTS` 등), 대부분은 공고문 첨부파일(PDF·HWP) | 목록 → 별도 상세 API | 지역(`CNP_CD`), 공고유형, 공고상태, 게시일 기간 | 10,000 |
| 복지로 중앙부처 | **상세에만 있음** (`tgtrDtlCn` 지원대상, `slctCritCn` 선정기준) | 목록 → 상세 N회 | 나이(`age`), 생애주기, 가구유형, 관심주제, 검색어 | **100** |
| 복지로 지자체 | **상세에만 있음** (`sprtTrgtCn` 지원대상, `slctCritCn` 선정기준) | 목록 → 상세 N회 | 나이, 시도(`ctpvNm`), 시군구(`sggNm`), 생애주기, 가구상황 | 1,000 |

## 온통청년

- 현재 엔드포인트는 `https://www.youthcenter.go.kr/go/ythip/getPlcy`다. 예시 요청값은 `apiKeyNm`, `pageNum`, `pageSize`, `rtnType=json`이다.
- 키 없이 부르면 HTTP 400을 돌려준다. 옛 주소 `opi/youthPlcyList.do`(`openApiVlak`)는 홈페이지로 302 이동한다. 문서 페이지 하단의 예시는 옛 주소다.
- 응답 필드 설명표는 비로그인 요청에 401을 돌려준다. 키 발급(T2) 뒤 로그인 상태에서 확인한다.
- 코드표는 [API코드정보.xlsx](https://www.youthcenter.go.kr/downloadform/API코드정보.xlsx)에 있다. 아래 코드는 채팅의 선택지 후보다.
  - 학력(`schoolCd`): 고졸 미만 ~ 석·박사, 제한없음 (10개)
  - 취업상태(`jobCd`): 재직자, 자영업자, 미취업자, 프리랜서, 일용근로자, (예비)창업자 등 (10개)
  - 전공(`plcyMajorCd`) 9개, 특화대상(`sbizCd`) 10개, 결혼(`mrgSttsCd`) 3개
  - 소득조건 구분(`earnCndSeCd`): 무관, 연소득, 기타
  - 신청기간 구분(`aplyPrdSeCd`): 특정기간, 상시, 마감
  - 대분류 5개, 중분류 17개, 정책키워드 17개

## 잡알리오 (`apis.data.go.kr/1051000/recruitment`)

- `/list`, `/detail` 두 기능이 있다. 상세는 `sn`(채용공시 일련번호)으로 부른다.
- 목록에 이미 신청자격, 결격사유, 우대내용, 전형절차, 마감 D-day가 있다. 상세에만 있는 것은 첨부파일(`files[].url`)과 전형 단계별 경쟁률(`steps[]`)이다.
- 코드(학력, 고용유형, 근무지역, NCS)는 data.go.kr 첨부 코드정의서에 있다. 아직 받지 않았다.

## LH (`apis.data.go.kr/B552555/lhLeaseNoticeInfo1`)

- data.go.kr 15058530은 **분양임대공고문 목록 조회 하나**만 제공한다. Swagger가 비어 있어 활용가이드(2026-07-08판)로 확인했다.
- 응답의 `PAN_ID`, `SPL_INF_TP_CD`, `CCR_CNNT_SYS_DS_CD`, `UPP_AIS_TP_CD`, `AIS_TP_CD`는 상세 조회 API의 요청값이다. 상세는 **별도 API라 활용신청을 따로 해야 한다.**
  - 상세정보 조회 [15057999](https://www.data.go.kr/data/15057999/openapi.do) (`lhLeaseNoticeDtlInfo1/getLeaseNoticeDtlInfo1`): 접수처, 단지, 일정, 임대조건, 입주자격 기타(`ETC_CTS`) 같은 서술형과 공고문 첨부파일 목록(`dsAhflInfo`, PDF·HWP 다운로드 URL)이 있다. 활용가이드(2026-06-16판)로 확인했다.
  - 공급정보 조회 [15056765](https://www.data.go.kr/data/15056765/openapi.do): 주택형·필지·상가호 목록.
- 목록 응답 필드에는 자격조건이 없다. 공고유형, 공고명, 지역, 게시일, 마감일, 상태, 상세 URL만 있다. 자격조건 대부분은 상세 API가 주는 공고문 첨부파일에 있다.
- 게시일 기간(`PAN_ST_DT`, `PAN_ED_DT`)은 필수다. 기본값은 최근 2개월이다.

## 복지로 중앙부처 (`apis.data.go.kr/B554287/NationalWelfareInformationsV001`)

- 목록 `NationalWelfarelistV001`: `numOfRows` 최대 500, `pageNo` 최대 1000. 응답은 서비스명, 요약(`servDgst`), 생애주기, 가구유형, 관심주제, 소관부처, 상세 링크다. **선정기준은 없다.**
- 상세 `NationalWelfaredetailedV001`: `servId`로 부른다. `tgtrDtlCn`(지원대상), `slctCritCn`(선정기준), `alwServCn`(급여내용), 신청방법, 문의처, 근거법령, 서식이 있다.
- 파일 데이터 [15083323](https://www.data.go.kr/data/15083323/fileData.do)은 키 없이 받는 CSV다. 461행, 연 1회 갱신(2026-08-19 등록)이다. 열은 서비스ID, 서비스명, URL, 요약, 사이트, 대표문의, 소관부처·조직, 기준연도, 최종수정일이다. **선정기준 열은 없다.** 전체 서비스ID 목록을 얻는 데는 쓸 수 있다.

## 복지로 지자체 (`apis.data.go.kr/B554287/LocalGovernmentWelfareInformations`)

- 목록 `LcgvWelfarelist`: 시도·시군구, 나이, 생애주기, 가구상황, 관심주제로 거른다. 응답에 선정기준은 없다.
- 상세 `LcgvWelfaredetailed`: `sprtTrgtCn`(지원대상), `slctCritCn`(선정기준), `alwServCn`(급여내용), 신청방법이 있다.

## 확인하지 못한 것

- 온통청년 응답 필드 설명과 `pageSize` 최댓값.
- data.go.kr 트래픽 한도를 기능(목록·상세)별로 세는지, 키 전체로 세는지.
- 복지로 중앙부처 461건 중 청년 대상 건수.
- 잡알리오 코드정의서.
