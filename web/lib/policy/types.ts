// 온통청년 정책을 서버 로직이 다루는 모양. API 응답(문자열 덩어리)은 sources/youthcenter.ts의 parsePolicy에서 한 번만 바꾼다.

/** 코드정의서(experiments/context-measurement/api-survey.md)의 값. "제한없음" 코드는 ANY에 모았다. */
export const ANY = {
  job: "0013010",
  school: "0049010",
  marital: "0055003",
  special: "0014010",
} as const;

export const UNEMPLOYED = "0013003";
const CLOSED = "0057003";

/** 나이 제한. null이면 제한 없음. sprtTrgtAgeLmtYn 표시값은 이름과 반대로 들어 있어 쓰지 않는다(log/017). */
export type AgeRange = { min: number; max: number } | null;

export type Policy = {
  id: string;
  name: string;
  keywords: string[];
  summary: string;
  support: string;
  operator: string;
  /** 대상 시군구 코드. 시군구 전용이면 몇 개, 전국이면 수백 개. */
  regionCodes: string[];
  age: AgeRange;
  jobCodes: string[];
  schoolCodes: string[];
  maritalCodes: string[];
  specialCodes: string[];
  /** 신청기간 구분이 "마감"이면 true */
  closed: boolean;
  /** 신청 종료일(로컬 날짜 0시). 상시·기간 없음이면 null */
  applyEnd: Date | null;
  views: number;
  /** LLM이 읽을 서술형 조건 */
  incomeNote: string;
  extraQualification: string;
  excluded: string;
  applyMethod: string;
  url: string;
};

export const isClosedCode = (code: string): boolean => code === CLOSED;

/** 사용자 조건. 선택지로만 받는다(D10). 모르는 값은 undefined. */
export type Profile = {
  age: number;
  /** 시군구 5자리 코드(API에 보내는 값) 또는 시도 앞자리. 대상 지역 코드의 앞부분과 비교한다. */
  region: string;
  job: string;
  school?: string;
  marital?: string;
  /** 사용자가 해당한다고 답한 특화 요건(여성, 수급자 등). 묻지 않았으면 undefined */
  special?: string[];
};

export type Verdict = "가능" | "불가" | "확인 필요";
