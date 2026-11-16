// LLM이 고를 수 있는 온통청년 분류 값. 코드정의서(API코드정보.xlsx, experiments/context-measurement/api-survey.md)에 있는 것만.
// 이 목록 밖의 값은 API에 보내지 않는다. 사용자 문장이 공공 API 검색어로 새지 않게 하는 장치다(AGENTS.md "개인정보").

export const MAJOR = ["일자리", "주거", "교육", "복지문화", "참여권리"] as const;

export const MINOR = [
  "취업",
  "재직자",
  "창업",
  "주택 및 거주지",
  "기숙사",
  "전월세 및 주거급여 지원",
  "미래역량강화",
  "교육비지원",
  "온라인교육",
  "취약계층 및 금융지원",
  "건강",
  "예술인지원",
  "문화활동",
  "청년참여",
  "정책인프라구축",
  "청년국제교류",
  "권익보호",
] as const;

export const KEYWORD = [
  "대출",
  "보조금",
  "바우처",
  "금리혜택",
  "교육지원",
  "맞춤형상담서비스",
  "인턴",
  "벤처",
  "중소기업",
  "청년가장",
  "장기미취업청년",
  "공공임대주택",
  "신용회복",
  "육아",
  "출산",
  "해외진출",
  "주거지원",
] as const;

export type Major = (typeof MAJOR)[number];
export type Minor = (typeof MINOR)[number];
export type Keyword = (typeof KEYWORD)[number];

export const pick = <T extends string>(allowed: readonly T[], value: unknown): T | null =>
  typeof value === "string" && (allowed as readonly string[]).includes(value) ? (value as T) : null;
