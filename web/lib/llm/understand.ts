// D9 1단계: 질문에서 온통청년 분류(대분류·중분류·정책 키워드)와 순위용 단어를 고른다.
// 고른 값은 코드정의서 목록으로 다시 검증한다. 목록 밖이면 버린다.
import type { ChatJson, Message } from "./groq.ts";
import { KEYWORD, MAJOR, MINOR, pick } from "./vocab.ts";
import type { Keyword, Major, Minor } from "./vocab.ts";

export type Understanding = { major: Major; minor: Minor | null; keyword: Keyword | null; terms: string[] };

const SYSTEM = `너는 청년 정책 검색 도우미다. 사용자의 질문을 읽고 온통청년 정책 분류를 고른다.
- major: 반드시 다음 중 하나 — ${MAJOR.join(", ")}
- minor: 다음 중 질문에 가장 맞는 하나, 애매하면 null — ${MINOR.join(", ")}
- keyword: 다음 중 질문에 분명히 맞는 하나, 애매하면 null — ${KEYWORD.join(", ")}
- terms: 정책 이름·설명에서 찾을 짧은 단어 2~5개(예: 월세, 지원금). 사용자의 개인 정보(나이, 지역, 소득 등)는 넣지 않는다.
JSON 하나만 출력한다: {"major": "...", "minor": "..." 또는 null, "keyword": "..." 또는 null, "terms": ["..."]}`;

export const understandMessages = (question: string): Message[] => [
  { role: "system", content: SYSTEM },
  { role: "user", content: question },
];

/** LLM 출력을 검증한다. major가 목록에 없으면 질문을 이해하지 못한 것으로 보고 실패한다. */
export const parseUnderstanding = (json: unknown): Understanding => {
  const o = (json ?? {}) as Record<string, unknown>;
  const major = pick(MAJOR, o.major);
  if (!major) throw new Error("질문에서 정책 분류를 고르지 못했다");
  const terms = Array.isArray(o.terms)
    ? o.terms.filter((t): t is string => typeof t === "string" && t.length > 0 && t.length <= 20).slice(0, 5)
    : [];
  return { major, minor: pick(MINOR, o.minor), keyword: pick(KEYWORD, o.keyword), terms };
};

export const understand = async (question: string, chat: ChatJson): Promise<Understanding> =>
  parseUnderstanding((await chat(understandMessages(question))).json);
