// D10 1단계: 코드 요건은 서버가 기계적으로 판정한다. LLM은 이 코드를 잘못 읽었다(log/019: 특화 요건 무시, "대졸 예정"을 "대졸"로).
import type { Policy, Profile, Verdict } from "./types.ts";
import { ANY } from "./types.ts";

/** 요건 목록 하나를 판정한다. 제한이 없으면 null, 사용자 값을 모르면 "확인 필요". */
const checkList = (codes: string[], any: string, value: string | undefined): Verdict | null => {
  if (codes.length === 0 || codes.includes(any)) return null;
  if (value === undefined) return "확인 필요";
  return codes.includes(value) ? null : "불가";
};

/**
 * 코드로 결론이 나면 판정을, 아니면 null을 돌려준다.
 * 학력·혼인·취업: 목록에 사용자 값이 없으면 "불가". 특화 요건(여성·수급자 등): 사용자가 해당한다고 답하지 않았으면 "확인 필요".
 */
export const codeVerdict = (p: Policy, profile: Profile): Verdict | null => {
  const results = [
    checkList(p.schoolCodes, ANY.school, profile.school),
    checkList(p.maritalCodes, ANY.marital, profile.marital),
    checkList(p.jobCodes, ANY.job, profile.job),
  ];
  if (results.includes("불가")) return "불가";
  const special = p.specialCodes.filter((c) => c !== ANY.special);
  if (special.length > 0 && !special.some((c) => profile.special?.includes(c))) return "확인 필요";
  return results.includes("확인 필요") ? "확인 필요" : null;
};

/** 서버 판정이 LLM 판정보다 앞선다. 서버가 결론을 못 내면 LLM 판정을 쓴다. */
export const combine = (server: Verdict | null, llm: Verdict): Verdict => {
  if (server === "불가") return "불가";
  if (server === "확인 필요" && llm === "가능") return "확인 필요";
  return llm;
};
