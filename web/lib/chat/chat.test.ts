// 질문 한 턴을 가짜 Groq와 저장 샘플로 돌린다. API·Groq를 부르지 않는다.
import { test } from "node:test";
import assert from "node:assert/strict";
import { answer, JUDGE_INPUT_BUDGET } from "./answer.ts";
import type { Deps } from "./answer.ts";
import { BadRequest, parseChatRequest } from "./validate.ts";
import type { ChatRequest } from "./types.ts";
import type { ChatJson, Message } from "../llm/groq.ts";
import { estimateTokens, judgeMessages, parseJudgements } from "../llm/judge.ts";
import { parseUnderstanding } from "../llm/understand.ts";
import { medianIncomeTable } from "../policy/medianIncome.ts";
import { parseResponse } from "../sources/youthcenter.ts";
import type { PolicyQuery } from "../sources/youthcenter.ts";
import { readSample, SAMPLE_DAY } from "../test/fixtures.ts";

const QUESTION_A = "서울 사는 26살인데 아직 취업 못 했어요. 받을 수 있는 지원금 있어요?";
const REQ_A: ChatRequest = {
  question: QUESTION_A,
  profile: { age: 26, sggCode: "11110", job: "0013003", school: "0049007", marital: "0055002", householdSize: 1, incomeBand: "2천만 원 미만" },
};
const subsidyPage = parseResponse(readSample("youthcenter/probe_kywd_subsidy.json"));
const emptyPage = { total: 0, policies: [] };

/** 첫 호출은 이해 단계, 두 번째는 판정 단계로 보고 정해 둔 답을 돌려준다. */
const fakeChat = (understanding: unknown, verdict: string = "가능") => {
  const calls: Message[][] = [];
  const chat: ChatJson = async (messages) => {
    calls.push(messages);
    if (calls.length === 1) return { json: understanding, usage: null };
    const ids = [...messages[1].content.matchAll(/"id":"([^"]+)"/g)].map((m) => m[1]);
    return { json: { results: ids.map((id) => ({ id, verdict, reason: "테스트", ask_user: null })) }, usage: null };
  };
  return { chat, calls };
};

const deps = (chat: ChatJson, pages: (q: PolicyQuery) => typeof subsidyPage, queries: PolicyQuery[] = []): Deps => ({
  chat,
  fetchPolicies: async (q) => {
    queries.push(q);
    return pages(q);
  },
  today: SAMPLE_DAY,
});

test("질문 A 한 턴: 키워드로 좁혀 11건이 남고, 상위 8건 카드와 나머지 3건을 돌려준다 (M1)", async () => {
  const { chat, calls } = fakeChat({ major: "일자리", minor: null, keyword: "보조금", terms: ["지원금", "보조금", "수당"] });
  const res = await answer(REQ_A, deps(chat, () => subsidyPage));
  assert.equal(calls.length, 2);
  assert.equal(res.matched, 11);
  assert.equal(res.cards.length, 8);
  assert.equal(res.more, 3);
  assert.deepEqual(res.query, { major: "일자리", minor: null, keyword: "보조금", terms: ["지원금", "보조금", "수당"] });
});

test("서버 코드 판정이 LLM의 '가능'보다 앞선다: 군인 대상 정책은 '확인 필요'로 내려간다 (D10)", async () => {
  const { chat } = fakeChat({ major: "일자리", keyword: "보조금", terms: ["지원금"] }, "가능");
  const res = await answer(REQ_A, deps(chat, () => subsidyPage));
  const soldier = res.cards.find((c) => c.name === "군장병 전자책 구독·구매 지원");
  assert.equal(soldier?.verdict, "확인 필요");
});

test("개인정보: 공공 API 요청에는 시군구 코드와 코드정의서 분류 값만 들어가고, 질문 문장과 목록 밖 값은 들어가지 않는다", async () => {
  const queries: PolicyQuery[] = [];
  const { chat } = fakeChat({ major: "일자리", minor: "서울 26살 미취업", keyword: QUESTION_A, terms: ["지원금"] });
  await answer(REQ_A, deps(chat, () => subsidyPage, queries));
  assert.deepEqual(queries, [{ zipCd: "11110", lclsfNm: "일자리", mclsfNm: undefined, plcyKywdNm: undefined }]);
  for (const q of queries) for (const v of Object.values(q)) assert.ok(!v || !QUESTION_A.includes(v), `질문 문장이 새었다: ${v}`);
});

test("키워드로 좁혀 0건이면 대분류만으로 한 번 더 부른다(최대 2회)", async () => {
  const queries: PolicyQuery[] = [];
  const { chat } = fakeChat({ major: "일자리", keyword: "인턴", terms: [] });
  const res = await answer(REQ_A, deps(chat, (q) => (q.plcyKywdNm ? emptyPage : subsidyPage), queries));
  assert.equal(queries.length, 2);
  assert.equal(queries[1].plcyKywdNm, undefined);
  assert.equal(res.matched, 11);
});

test("남는 정책이 없으면 판정 단계를 부르지 않는다", async () => {
  const { chat, calls } = fakeChat({ major: "일자리", terms: [] });
  const res = await answer(REQ_A, deps(chat, () => emptyPage));
  assert.equal(calls.length, 1);
  assert.deepEqual(res.cards, []);
});

test("판정 프롬프트가 토큰 예산을 넘으면 카드 수를 줄인다", async () => {
  const long = { ...subsidyPage, policies: subsidyPage.policies.map((p) => ({ ...p, support: p.support + "가".repeat(3000) })) };
  const { chat, calls } = fakeChat({ major: "일자리", keyword: "보조금", terms: [] });
  const res = await answer(REQ_A, deps(chat, () => long));
  assert.ok(res.cards.length < 8 && res.cards.length >= 1);
  assert.ok(estimateTokens(calls[1]) <= JUDGE_INPUT_BUDGET || res.cards.length === 1);
});

test("판정 결과가 빠지거나 이상하면 '확인 필요'로 둔다", () => {
  const m = parseJudgements({ results: [{ id: "a", verdict: "아마도" }, { id: "x", verdict: "가능" }, { id: "b", verdict: "가능", ask_user: "?" }] }, ["a", "b", "c"]);
  assert.equal(m.get("a")?.verdict, "확인 필요");
  assert.equal(m.get("b")?.askUser, null);
  assert.equal(m.get("c")?.verdict, "확인 필요");
  assert.equal(m.has("x"), false);
});

test("이해 단계: 대분류가 목록 밖이면 실패하고, 중분류·키워드는 목록 밖이면 버린다", () => {
  assert.throws(() => parseUnderstanding({ major: "취업" }));
  assert.deepEqual(parseUnderstanding({ major: "주거", minor: "월세", keyword: "주거지원", terms: ["월세", 3] }), {
    major: "주거",
    minor: null,
    keyword: "주거지원",
    terms: ["월세"],
  });
});

test("판정 프롬프트에 중위소득 표와 소득 구간이 들어가고, 시군구 코드는 들어가지 않는다", () => {
  const text = judgeMessages(REQ_A.profile, subsidyPage.policies.slice(0, 1))[1].content;
  assert.match(text, /1인 가구: 월 256만 원/);
  assert.match(text, /2천만 원 미만/);
  assert.ok(!text.includes("11110"));
  assert.match(medianIncomeTable(), /4인 가구: 월 649만 원/);
});

test("요청 검증: 형식이 틀리면 400으로 돌려보낼 오류를 낸다", () => {
  const ok = parseChatRequest({ question: " 질문 ", profile: { age: 26, sggCode: "11110", job: "0013003" } });
  assert.equal(ok.question, "질문");
  for (const bad of [
    { question: "", profile: { age: 26, sggCode: "11110", job: "0013003" } },
    { question: "q", profile: { age: 26, sggCode: "11", job: "0013003" } },
    { question: "q", profile: { age: 26.5, sggCode: "11110", job: "0013003" } },
    { question: "q", profile: { age: 26, sggCode: "11110", job: "9999999" } },
    { question: "q", profile: { age: 26, sggCode: "11110", job: "0013003", incomeBand: "1억" } },
  ]) {
    assert.throws(() => parseChatRequest(bad), BadRequest);
  }
});
