// D10 2단계: 서술형 자격 조건을 LLM이 판정한다. 실험(judge_experiment.py)의 프롬프트에 log/019의 개선 두 가지를 더했다.
//  1) "불가"는 신청 주체가 기업·기관이거나 원문이 분명히 배제할 때만. 나머지는 "확인 필요".
//  2) 중위소득 기준표를 함께 준다(연봉과 비교하지 못하던 문제).
import type { ChatRequest } from "../chat/types.ts";
import { medianIncomeTable } from "../policy/medianIncome.ts";
import type { Policy, Verdict } from "../policy/types.ts";
import type { ChatJson, Message } from "./groq.ts";

export type Judgement = { verdict: Verdict; reason: string; askUser: string | null };

const VERDICTS: readonly Verdict[] = ["가능", "불가", "확인 필요"];

const SYSTEM = `너는 한국 청년 정책 자격 판정 도우미다. 사용자 정보와 정책 목록을 받으면 정책마다 사용자가 지금 신청할 수 있는지 판정한다.
- verdict는 "가능", "불가", "확인 필요" 중 하나다.
- "불가"는 두 경우에만 쓴다: (1) 기업·사업주·기관이 신청하는 사업이라 청년 개인이 신청할 수 없을 때, (2) 정책 원문이 사용자에게 해당하는 조건을 분명히 배제할 때. 그 밖에 조건이 애매하거나 사용자 정보가 부족하면 "확인 필요"다.
- "확인 필요"면 ask_user에 사용자에게 물을 질문을 한 문장으로 쓴다. 그 밖에는 null이다.
- 소득 조건이 "중위소득 몇 %"로 적혀 있으면 함께 준 기준 중위소득 표로 사용자 소득 구간과 비교한다. 구간이 걸쳐 판단할 수 없으면 "확인 필요"다.
- 정책 원문에 없는 조건을 지어내지 않는다. reason은 원문 근거를 담은 한 문장이다.
JSON 하나만 출력한다: {"results": [{"id": "...", "verdict": "...", "reason": "...", "ask_user": "..." 또는 null}]}`;

const describeProfile = (p: ChatRequest["profile"]): string =>
  [
    `나이 ${p.age}세`,
    `취업 상태 코드 ${p.job}`,
    p.school && `학력 코드 ${p.school}`,
    p.marital && `혼인 코드 ${p.marital}`,
    p.incomeBand && `본인 연 소득 ${p.incomeBand}`,
    p.housing && `주택 ${p.housing}`,
    p.householdSize && `가구원 ${p.householdSize}명`,
  ]
    .filter(Boolean)
    .join(", ");

/** LLM에 넘길 정책. 코드 요건은 서버가 판정하므로 넣지 않고, 서술형만 넣는다. */
const policyForLlm = (p: Policy) =>
  Object.fromEntries(
    Object.entries({
      id: p.id,
      정책명: p.name,
      운영기관: p.operator,
      설명: p.summary,
      지원내용: p.support,
      나이: p.age ? `${p.age.min}~${p.age.max}세` : "제한 없음",
      소득조건: p.incomeNote,
      추가자격: p.extraQualification,
      참여제한: p.excluded,
    }).filter(([, v]) => v),
  );

export const judgeMessages = (profile: ChatRequest["profile"], policies: readonly Policy[]): Message[] => [
  { role: "system", content: SYSTEM },
  {
    role: "user",
    content: [
      `사용자 정보: ${describeProfile(profile)}`,
      medianIncomeTable(profile.householdSize),
      `정책 목록:\n${JSON.stringify(policies.map(policyForLlm))}`,
    ].join("\n\n"),
  },
];

/** LLM 출력을 정책 id별 판정으로 바꾼다. 빠지거나 이상한 항목은 "확인 필요"로 둔다(조심하는 쪽). */
export const parseJudgements = (json: unknown, ids: readonly string[]): Map<string, Judgement> => {
  const results = Array.isArray((json as { results?: unknown })?.results) ? (json as { results: unknown[] }).results : [];
  const byId = new Map<string, Judgement>();
  for (const r of results) {
    const o = (r ?? {}) as Record<string, unknown>;
    if (typeof o.id !== "string" || !ids.includes(o.id)) continue;
    const verdict = VERDICTS.includes(o.verdict as Verdict) ? (o.verdict as Verdict) : "확인 필요";
    byId.set(o.id, {
      verdict,
      reason: typeof o.reason === "string" ? o.reason : "",
      askUser: verdict === "확인 필요" && typeof o.ask_user === "string" ? o.ask_user : null,
    });
  }
  for (const id of ids) {
    if (!byId.has(id)) byId.set(id, { verdict: "확인 필요", reason: "판정 결과를 받지 못했다", askUser: null });
  }
  return byId;
};

export const judge = async (
  profile: ChatRequest["profile"],
  policies: readonly Policy[],
  chat: ChatJson,
): Promise<Map<string, Judgement>> =>
  parseJudgements((await chat(judgeMessages(profile, policies))).json, policies.map((p) => p.id));

/** 프롬프트 토큰 대략값. 실측 o200k 기준 한국어 1글자 0.46~0.66토큰(log/012). 넉넉히 0.7로 센다. */
export const estimateTokens = (messages: readonly Message[]): number =>
  Math.ceil(messages.reduce((n, m) => n + m.content.length, 0) * 0.7);
