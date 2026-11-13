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
