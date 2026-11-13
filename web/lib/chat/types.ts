// api/chat 요청·응답 형식 — **초안. PM 승인 전(STATUS Q9).** 화면(T9) 코드가 이 형식에 기댄다.
// 사용자 값은 모두 선택지로 받는다(D10). 자유 입력은 질문 문장 하나뿐이다.
import type { Verdict } from "../policy/types.ts";

export const INCOME_BANDS = ["2천만 원 미만", "2천~3천만 원", "3천~4천만 원", "4천~5천만 원", "5천만 원 이상", "모름"] as const;
export const HOUSING = ["무주택", "주택 있음", "모름"] as const;

export type ChatRequest = {
  /** 사용자가 친 질문. LLM에만 보낸다. 공공 API 검색어에는 넣지 않는다(AGENTS.md). 300자 이하 */
  question: string;
  profile: {
    age: number;
    /** 시군구 5자리 법정동 코드 */
    sggCode: string;
    /** 취업 상태 코드(코드정의서 0013xxx) */
    job: string;
    /** 학력 코드(0049xxx). 묻지 않았으면 생략 */
    school?: string;
    /** 혼인 코드(0055xxx) */
    marital?: string;
    /** 해당한다고 답한 특화 요건 코드(0014xxx) */
    special?: string[];
    /** 연 소득 구간(본인) */
    incomeBand?: (typeof INCOME_BANDS)[number];
    housing?: (typeof HOUSING)[number];
    /** 가구원 수 1~6(6은 6인 이상) */
    householdSize?: number;
  };
};

export type Card = {
  id: string;
  name: string;
  operator: string;
  /** 지원 내용 앞부분 */
  support: string;
  verdict: Verdict;
  /** 판정 이유 한 문장 */
  reason: string;
  /** 확인 필요일 때 사용자에게 물을 질문 */
  askUser: string | null;
  /** 신청 종료일 YYYY-MM-DD. 상시면 null */
  applyEnd: string | null;
  url: string;
};

export type ChatResponse = {
  /** LLM이 질문에서 고른 분류(디버깅·화면 안내용) */
  query: { major: string; minor: string | null; keyword: string | null; terms: string[] };
  /** 필터를 통과한 정책 수. cards는 그중 상위 일부 */
  matched: number;
  cards: Card[];
  /** 카드로 보여 주지 않은 나머지 수 */
  more: number;
};
