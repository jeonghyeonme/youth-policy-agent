// 사람이 로컬에서 실제 키로 질문 한 턴을 돌려 보는 스크립트(AI 도구는 실행하지 않는다, AGENTS.md "API 키").
//   cd web && node --env-file=../.env scripts/try-question.ts A   (저장소 루트의 .env를 쓴다)
// 질문 하나에 온통청년 최대 2회, Groq 2회를 부른다. 결과 JSON을 화면에 찍는다(키는 찍지 않는다).
import { answer } from "../lib/chat/answer.ts";
import type { ChatRequest } from "../lib/chat/types.ts";
import { groqChatJson } from "../lib/llm/groq.ts";
import { fetchPolicies } from "../lib/sources/youthcenter.ts";

// 대표 질문 A·B(D2). 사용자 정보는 가상 인물이다(q4/labels.json과 같다).
const QUESTIONS: Record<string, ChatRequest> = {
  A: {
    question: "서울 사는 26살인데 아직 취업 못 했어요. 받을 수 있는 지원금 있어요?",
    profile: { age: 26, sggCode: "11110", job: "0013003", school: "0049007", marital: "0055002", householdSize: 1, incomeBand: "2천만 원 미만", housing: "무주택" },
  },
  B: {
    question: "첫 직장 때문에 자취를 시작해요. 연봉 3천인데 월세 지원 받을 수 있나요?",
    profile: { age: 27, sggCode: "11110", job: "0013001", school: "0049007", marital: "0055002", householdSize: 1, incomeBand: "3천~4천만 원", housing: "무주택" },
  },
};

const key = process.argv[2] ?? "A";
const req = QUESTIONS[key];
const youthKey = process.env.YOUTHCENTER_API_KEY;
const groqKey = process.env.GROQ_API_KEY;
if (!req || !youthKey || !groqKey) {
  console.error("사용법: node --env-file=../.env scripts/try-question.ts A|B  (.env에 YOUTHCENTER_API_KEY, GROQ_API_KEY 필요)");
  process.exit(1);
}

const usage: unknown[] = [];
const chat = groqChatJson(groqKey);
const started = Date.now();
const result = await answer(req, {
  chat: async (messages) => {
    const r = await chat(messages);
    usage.push(r.usage);
    return r;
  },
  fetchPolicies: (query) => fetchPolicies(query, youthKey),
  today: new Date(),
});
console.log(JSON.stringify({ question: key, seconds: (Date.now() - started) / 1000, groqUsage: usage, result }, null, 2));
