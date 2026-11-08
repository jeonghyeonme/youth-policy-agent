# 샘플 수집 기록 (2026-11-08 15:48)

> fetch_samples.py가 썼다. 키 값은 지웠다.

| 호출 | 결과 | 크기 | 비고(실패 시 응답 앞부분) |
| --- | --- | --- | --- |
| youthcenter/old_list | 실패 HTTP 0 | - | 연결 실패: <urlopen error timed out> 문서의 요청 예시(옛 형식) |
| youthcenter/A_list | 저장 HTTP 200 | 229,961 B | 개편 형식 주소·파라미터는 추정 |
| youthcenter/B_list | 저장 HTTP 200 | 234,424 B | 개편 형식 주소·파라미터는 추정 |
| jobalio/A_list | 저장 HTTP 200 | 249,040 B | 오퍼레이션 경로(/list, /detail)는 추정 |
| lh/B_list | 저장 HTTP 200 | 1,671 B | 오퍼레이션 경로는 추정 |
| welfare_national/A_list | 저장 HTTP 200 | 81,589 B | 오퍼레이션 경로는 추정 |
| welfare_national/A_detail_1 | 저장 HTTP 200 | 9,019 B | |
| welfare_national/A_detail_2 | 저장 HTTP 200 | 6,298 B | |
| welfare_national/A_detail_3 | 저장 HTTP 200 | 5,484 B | |
| welfare_national/A_detail_4 | 저장 HTTP 200 | 6,003 B | |
| welfare_national/A_detail_5 | 저장 HTTP 200 | 8,830 B | |
| welfare_national/B_list | 저장 HTTP 200 | 3,538 B | 오퍼레이션 경로는 추정 |
| welfare_national/B_detail_1 | 저장 HTTP 200 | 9,128 B | |
| welfare_national/B_detail_2 | 저장 HTTP 200 | 10,575 B | |
| welfare_national/B_detail_3 | 저장 HTTP 200 | 8,071 B | |
| welfare_national/B_detail_4 | 저장 HTTP 200 | 4,226 B | |
| welfare_local/A_list | 실패 HTTP 200 | - | <?xml version="1.0" encoding="UTF-8" standalone="yes"?><wantedList><totalCount>0</totalCount><pageNo>1</pageNo><numOfRows>100</numOfRows><resultCode>40</resultCode><resultMessage>NO DATA FOUND</result 오퍼레이션 경로는 추정 |
| welfare_local/B_list | 실패 HTTP 200 | - | <?xml version="1.0" encoding="UTF-8" standalone="yes"?><wantedList><totalCount>0</totalCount><pageNo>1</pageNo><numOfRows>100</numOfRows><resultCode>40</resultCode><resultMessage>NO DATA FOUND</result 오퍼레이션 경로는 추정 |
