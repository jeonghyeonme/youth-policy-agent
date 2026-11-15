// D9 2단계: 서버 필터. 지역은 보통 API 요청(zipCd)이 이미 거르지만, 저장된 응답이나 시도 단위 확인에도 쓴다.
import type { Policy, Profile } from "./types.ts";
import { ANY } from "./types.ts";

export const inRegion = (p: Policy, region: string): boolean => p.regionCodes.some((c) => c.startsWith(region));

export const ageFits = (p: Policy, age: number): boolean => p.age === null || (p.age.min <= age && age <= p.age.max);

/** 취업 요건. 코드가 없거나 "제한없음"이 있거나 사용자 상태가 있으면 통과. */
export const jobFits = (p: Policy, job: string): boolean =>
  p.jobCodes.length === 0 || p.jobCodes.includes(ANY.job) || p.jobCodes.includes(job);

export const isOpen = (p: Policy, today: Date): boolean => !p.closed && (p.applyEnd === null || p.applyEnd >= today);

export const passesFilter = (p: Policy, profile: Profile, today: Date): boolean =>
  inRegion(p, profile.region) && ageFits(p, profile.age) && jobFits(p, profile.job) && isOpen(p, today);

/**
 * 이름과 운영기관이 같은 정책은 하나만 남긴다. 같은 정책이 해마다 새 번호로 다시 등록돼 있다(log/030).
 * 정책 번호는 등록일로 시작하므로 큰 번호(최신)를 남긴다. 입력 순서는 지킨다.
 */
export const dedupe = (policies: readonly Policy[]): Policy[] => {
  const latest = new Map<string, Policy>();
  for (const p of policies) {
    const key = `${p.name.replace(/\s+/g, "")}|${p.operator}`;
    const seen = latest.get(key);
    if (!seen || p.id > seen.id) latest.set(key, p);
  }
  const keep = new Set(latest.values());
  return policies.filter((p) => keep.has(p));
};
