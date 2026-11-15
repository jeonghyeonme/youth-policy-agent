// D10 1단계: 코드 요건은 서버가 기계적으로 판정한다. LLM은 이 코드를 잘못 읽었다(log/019: 특화 요건 무시, "대졸 예정"을 "대졸"로).
// 서버가 LLM 판정을 바꾸면 이유와 확인 질문도 서버가 쓴다(log/029: LLM 이유가 "부합"인데 판정만 "확인 필요"였다).
import type { Policy, Profile, Verdict } from "./types.ts";
import { ANY } from "./types.ts";

/** 코드정의서 이름(api-survey.md). 이유·질문 문장에 쓴다. */
const NAMES: Record<string, string> = {
  "0049001": "고졸 미만", "0049002": "고교 재학", "0049003": "고졸 예정", "0049004": "고교 졸업",
  "0049005": "대학 재학", "0049006": "대졸 예정", "0049007": "대학 졸업", "0049008": "석·박사", "0049009": "기타",
  "0055001": "기혼", "0055002": "미혼",
  "0013001": "재직자", "0013002": "자영업자", "0013003": "미취업자", "0013004": "프리랜서", "0013005": "일용근로자",
  "0013006": "(예비)창업자", "0013007": "단기근로자", "0013008": "영농종사자", "0013009": "기타",
  "0014001": "중소기업", "0014002": "여성", "0014003": "기초생활수급자", "0014004": "한부모가정", "0014005": "장애인",
  "0014006": "농업인", "0014007": "군인", "0014008": "지역인재", "0014009": "기타",
};
const names = (codes: string[]): string => codes.map((c) => NAMES[c] ?? c).join(", ");

export type Finding = { verdict: Verdict; reason: string; askUser: string | null };

const LISTS = [
  { field: "schoolCodes", any: ANY.school, key: "school", label: "학력" },
  { field: "maritalCodes", any: ANY.marital, key: "marital", label: "혼인" },
  { field: "jobCodes", any: ANY.job, key: "job", label: "취업 상태" },
] as const;

/**
 * 코드로 결론이 나면 판정·이유·질문을, 아니면 null을 돌려준다.
 * 학력·혼인·취업: 목록에 사용자 값이 없으면 "불가", 사용자 값을 모르면 "확인 필요".
 * 특화 요건(여성·수급자 등): 사용자가 해당한다고 답하지 않았으면 "확인 필요".
 */
export const codeCheck = (p: Policy, profile: Profile): Finding | null => {
  let unknown: Finding | null = null;
  for (const { field, any, key, label } of LISTS) {
    const codes = p[field];
    if (codes.length === 0 || codes.includes(any)) continue;
    const value = profile[key];
    if (value === undefined) {
      unknown ??= { verdict: "확인 필요", reason: `${label} 요건이 있다: ${names(codes)}`, askUser: `${label}이(가) ${names(codes)} 중 하나에 해당하나요?` };
    } else if (!codes.includes(value)) {
      return { verdict: "불가", reason: `${label} 요건(${names(codes)})에 해당하지 않는다`, askUser: null };
    }
  }
  const special = p.specialCodes.filter((c) => c !== ANY.special);
  if (special.length > 0 && !special.some((c) => profile.special?.includes(c))) {
    return { verdict: "확인 필요", reason: `대상 요건이 있다: ${names(special)}`, askUser: `${names(special)} 중 해당하는 것이 있나요?` };
  }
  return unknown;
};

export const codeVerdict = (p: Policy, profile: Profile): Verdict | null => codeCheck(p, profile)?.verdict ?? null;

/** 서버 판정이 LLM 판정보다 앞선다. 서버가 판정을 바꿀 때는 이유·질문도 서버 것을 쓴다. */
export const combine = (server: Verdict | null, llm: Verdict): Verdict => {
  if (server === "불가") return "불가";
  if (server === "확인 필요" && llm === "가능") return "확인 필요";
  return llm;
};

export const merge = (server: Finding | null, llm: Finding): Finding => {
  const verdict = combine(server?.verdict ?? null, llm.verdict);
  const fromServer = server !== null && verdict !== llm.verdict;
  const chosen = fromServer ? server : llm;
  return { verdict, reason: chosen.reason, askUser: verdict === "확인 필요" ? chosen.askUser : null };
};
