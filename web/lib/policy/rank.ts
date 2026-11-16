// D9 3단계: 순위. 키워드 일치 → 맞춤도 → 지역 전용 순으로 점수를 매기고, 동점이면 마감 임박 → 조회수.
import type { Policy, Profile } from "./types.ts";
import { UNEMPLOYED } from "./types.ts";

export const TOP_N = 8;

/** 질문에서 뽑은 키워드가 정책 이름·키워드·설명·지원 내용에 몇 개 들어 있나 */
export const keywordHits = (p: Policy, keywords: readonly string[]): number => {
  const text = [p.name, p.keywords.join(","), p.summary, p.support].join(" ");
  return keywords.filter((k) => text.includes(k)).length;
};

/** 시군구 전용 2, 시도 전역 1, 전국 0. 사용자가 스스로 찾기 어려운 동네 정책을 앞에 둔다. */
export const locality = (p: Policy): 0 | 1 | 2 => {
  const n = p.regionCodes.length;
  return n <= 5 ? 2 : n <= 30 ? 1 : 0;
};

/** 조건이 사용자에게 콕 집어 맞는 정도: 미취업을 명시했는지, 청년 나이대로 좁혔는지 */
export const fit = (p: Policy, profile: Profile): number =>
  (profile.job === UNEMPLOYED && p.jobCodes.includes(UNEMPLOYED) ? 1 : 0) + (p.age !== null && p.age.max <= 39 ? 1 : 0);

const score = (p: Policy, profile: Profile, keywords: readonly string[]): number =>
  2 * keywordHits(p, keywords) + fit(p, profile) + locality(p);

const endTime = (p: Policy): number => p.applyEnd?.getTime() ?? Number.POSITIVE_INFINITY;

export const rank = (policies: readonly Policy[], profile: Profile, keywords: readonly string[]): Policy[] =>
  [...policies].sort(
    (a, b) =>
      score(b, profile, keywords) - score(a, profile, keywords) || endTime(a) - endTime(b) || b.views - a.views,
  );

export const top = (policies: readonly Policy[], profile: Profile, keywords: readonly string[], n = TOP_N): Policy[] =>
  rank(policies, profile, keywords).slice(0, n);
