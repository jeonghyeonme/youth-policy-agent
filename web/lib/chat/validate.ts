// api/chat 요청 본문 검증(경계). 통과하면 안쪽 코드는 형식을 믿는다.
import { HOUSING, INCOME_BANDS } from "./types.ts";
import type { ChatRequest } from "./types.ts";

export class BadRequest extends Error {}

const code = (value: unknown, prefix: string, name: string): string => {
  if (typeof value !== "string" || !new RegExp(`^${prefix}\\d{3}$`).test(value)) throw new BadRequest(`${name} 코드가 올바르지 않다`);
  return value;
};

const optional = <T>(value: unknown, parse: (v: unknown) => T): T | undefined => (value === undefined ? undefined : parse(value));

const oneOf = <T extends string>(allowed: readonly T[], name: string) => (value: unknown): T => {
  if (typeof value !== "string" || !(allowed as readonly string[]).includes(value)) throw new BadRequest(`${name} 값이 올바르지 않다`);
  return value as T;
};

export const parseChatRequest = (body: unknown): ChatRequest => {
  const o = (body ?? {}) as Record<string, unknown>;
  const p = (o.profile ?? {}) as Record<string, unknown>;
  const question = typeof o.question === "string" ? o.question.trim() : "";
  if (question.length === 0 || question.length > 300) throw new BadRequest("질문은 1~300자다");
  if (typeof p.age !== "number" || !Number.isInteger(p.age) || p.age < 15 || p.age > 49) throw new BadRequest("나이는 15~49 정수다");
  if (typeof p.sggCode !== "string" || !/^\d{5}$/.test(p.sggCode)) throw new BadRequest("시군구 코드는 5자리 숫자다");
  const householdSize = optional(p.householdSize, (v) => {
    if (typeof v !== "number" || !Number.isInteger(v) || v < 1 || v > 6) throw new BadRequest("가구원 수는 1~6이다");
    return v;
  });
  return {
    question,
    profile: {
      age: p.age,
      sggCode: p.sggCode,
      job: code(p.job, "0013", "취업 상태"),
      school: optional(p.school, (v) => code(v, "0049", "학력")),
      marital: optional(p.marital, (v) => code(v, "0055", "혼인")),
      special: optional(p.special, (v) => {
        if (!Array.isArray(v)) throw new BadRequest("특화 요건은 목록이다");
        return v.map((c) => code(c, "0014", "특화 요건"));
      }),
      incomeBand: optional(p.incomeBand, oneOf(INCOME_BANDS, "소득 구간")),
      housing: optional(p.housing, oneOf(HOUSING, "주택 여부")),
      householdSize,
    },
  };
};
