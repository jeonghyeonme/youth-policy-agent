// 질문 한 턴: 이해(LLM) → 온통청년 호출 → 필터·순위(D9) → 코드 판정 + 서술형 판정(D10) → 카드.
// 외부 호출(온통청년, Groq)은 인자로 받는다. 테스트는 가짜를 넣는다.
import type { ChatJson } from "../llm/groq.ts";
import { estimateTokens, judge, judgeMessages } from "../llm/judge.ts";
import { understand } from "../llm/understand.ts";
import { codeVerdict, combine } from "../policy/codeVerdict.ts";
import { passesFilter } from "../policy/filter.ts";
import { TOP_N, top } from "../policy/rank.ts";
import type { Policy, Profile } from "../policy/types.ts";
import type { PolicyPage, PolicyQuery } from "../sources/youthcenter.ts";
import type { Card, ChatRequest, ChatResponse } from "./types.ts";

export type Deps = {
  chat: ChatJson;
  fetchPolicies: (query: PolicyQuery) => Promise<PolicyPage>;
  today: Date;
};

/** 판정 프롬프트 입력 토큰 상한. 분당 8,000토큰 가정에서 출력·이해 단계 몫을 남긴다(D9, groq-models.md). */
export const JUDGE_INPUT_BUDGET = 4_500;

const toProfile = (p: ChatRequest["profile"]): Profile => ({
  age: p.age,
  region: p.sggCode,
  job: p.job,
  school: p.school,
  marital: p.marital,
  special: p.special,
});

const ymd = (d: Date | null): string | null =>
  d ? `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}` : null;

export const answer = async (req: ChatRequest, deps: Deps): Promise<ChatResponse> => {
  const u = await understand(req.question, deps.chat);
  const profile = toProfile(req.profile);

  // 1단계: 요청 좁히기. 키워드로 좁혀 0건이면 대분류만으로 한 번 더 부른다(호출 최대 2회).
  const base: PolicyQuery = { zipCd: req.profile.sggCode, lclsfNm: u.major };
  const narrowed: PolicyQuery = { ...base, mclsfNm: u.minor ?? undefined, plcyKywdNm: u.keyword ?? undefined };
  const filterPage = (page: PolicyPage): Policy[] => page.policies.filter((p) => passesFilter(p, profile, deps.today));
  let matched = filterPage(await deps.fetchPolicies(narrowed));
  if (matched.length === 0 && (u.minor || u.keyword)) matched = filterPage(await deps.fetchPolicies(base));

  // 3단계: 순위 상위 N건. 판정 프롬프트가 예산을 넘으면 뒤에서부터 줄인다.
  let picked = top(matched, profile, u.terms, TOP_N);
  while (picked.length > 1 && estimateTokens(judgeMessages(req.profile, picked)) > JUDGE_INPUT_BUDGET) {
    picked = picked.slice(0, -1);
  }

  const judged = picked.length > 0 ? await judge(req.profile, picked, deps.chat) : new Map();
  const cards: Card[] = picked.map((p) => {
    const llm = judged.get(p.id) ?? { verdict: "확인 필요" as const, reason: "", askUser: null };
    const verdict = combine(codeVerdict(p, profile), llm.verdict);
    return {
      id: p.id,
      name: p.name,
      operator: p.operator,
      support: p.support.slice(0, 200),
      verdict,
      reason: llm.reason,
      askUser: verdict === "확인 필요" ? llm.askUser : null,
      applyEnd: ymd(p.applyEnd),
      url: p.url,
    };
  });

  return {
    query: { major: u.major, minor: u.minor, keyword: u.keyword, terms: u.terms },
    matched: matched.length,
    cards,
    more: matched.length - cards.length,
  };
};
