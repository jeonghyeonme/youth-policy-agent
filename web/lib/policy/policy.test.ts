// 실험(experiments/context-measurement)과 같은 결과를 내는지 확인한다. 기준 숫자는 log/016·017·019.
import { test } from "node:test";
import assert from "node:assert/strict";
import { normalizeUrl, parsePolicy, parseResponse } from "../sources/youthcenter.ts";
import { readExperiment, readSample, SAMPLE_DAY } from "../test/fixtures.ts";
import { codeCheck, codeVerdict, combine } from "./codeVerdict.ts";
import { dedupe, passesFilter } from "./filter.ts";
import { top } from "./rank.ts";
import type { Profile, Verdict } from "./types.ts";
import { UNEMPLOYED } from "./types.ts";

const load = (file: string) => parseResponse(readSample(`youthcenter/${file}`)).policies;

const A: Profile = { age: 26, region: "11", job: UNEMPLOYED };
const A_KEYWORDS = ["지원금", "보조금", "수당", "장기미취업"];
const B: Profile = { age: 27, region: "11", job: "0013001" };
const B_KEYWORDS = ["월세", "임차", "주거비"];

test("나이는 숫자로 읽고 0~0이면 제한 없음이다 (log/017)", () => {
  assert.equal(parsePolicy({ sprtTrgtAgeLmtYn: "Y", sprtTrgtMinAge: "0", sprtTrgtMaxAge: "0" }).age, null);
  assert.deepEqual(parsePolicy({ sprtTrgtAgeLmtYn: "N", sprtTrgtMinAge: "17", sprtTrgtMaxAge: "21" }).age, { min: 17, max: 21 });
});

test("질문 A': 정책 키워드 '보조금'으로 좁힌 73건이 필터 후 11건, 상위 8건은 실험과 같다", () => {
  const policies = load("probe_kywd_subsidy.json");
  assert.equal(policies.length, 73);
  const passed = policies.filter((p) => passesFilter(p, A, SAMPLE_DAY));
  assert.equal(passed.length, 11);
  assert.deepEqual(
    top(passed, A, A_KEYWORDS).map((p) => p.name),
    [
      "군장병 전자책 구독·구매 지원",
      "게임사 프로젝트 현장교육 프로그램",
      "사회복지시설 돌봄보조 인력 지원",
      "2026 취업날개 서비스 지원",
      "청년일자리도약장려금",
      "2026 서울형 강소기업 육성 지원",
      "무대기술인턴십 지원",
      "문화예술 연수단원 지원사업",
    ],
  );
});

test("질문 B: 서울 27살 재직자는 6건이 남고 '청년 월세 지원'이 1위다", () => {
  const passed = load("B_list.json").filter((p) => passesFilter(p, B, SAMPLE_DAY));
  assert.equal(passed.length, 6);
  assert.equal(top(passed, B, B_KEYWORDS)[0].name, "2026 청년 월세 지원");
});

test("마감된 정책과 나이가 안 맞는 정책은 거른다", () => {
  const passed = load("probe_kywd_subsidy.json").filter((p) => passesFilter(p, A, SAMPLE_DAY));
  assert.ok(passed.every((p) => !p.closed && (p.applyEnd === null || p.applyEnd >= SAMPLE_DAY)));
  assert.ok(!passed.some((p) => p.name === "고교 취업연계 장려금 지원"), "17~21세 정책이 26살에게 남으면 안 된다");
});

test("코드 판정은 이유를 단다: 학력 불일치는 '불가', 학력을 모르면 '확인 필요'와 질문", () => {
  const p = parsePolicy({ schoolCd: "0049005,0049006", sbizCd: "0014010", jobCd: "0013010", mrgSttsCd: "0055003" });
  const no = codeCheck(p, { ...A, school: "0049004" }); // 고교 졸업 < 대학 재학(목록의 가장 낮은 단계)
  assert.equal(no?.verdict, "불가");
  assert.match(no?.reason ?? "", /대학 재학, 대졸 예정/);
  const unknown = codeCheck(p, A);
  assert.equal(unknown?.verdict, "확인 필요");
  assert.match(unknown?.askUser ?? "", /학력/);
  assert.equal(codeCheck(p, { ...A, school: "0049005" }), null);
});

test("학력은 순서로 본다: 목록보다 높으면 '확인 필요', 낮거나 범위 안에서 빠졌으면 '불가' (log/030)", () => {
  const base = { sbizCd: "0014010", jobCd: "0013010", mrgSttsCd: "0055003" };
  const highSchoolOnly = parsePolicy({ ...base, schoolCd: "0049004" });
  assert.equal(codeVerdict(highSchoolOnly, { ...A, school: "0049007" }), "확인 필요"); // 대졸자에게 "고교 졸업" 요건
  assert.equal(codeVerdict(highSchoolOnly, { ...A, school: "0049002" }), "불가"); // 고교 재학생
  const studentsOnly = parsePolicy({ ...base, schoolCd: "0049005,0049006,0049008" });
  assert.equal(codeVerdict(studentsOnly, { ...A, school: "0049007" }), "불가"); // 범위 안에서 대학 졸업만 빠짐
});

test("이름과 운영기관이 같은 정책은 최신 것 하나만 남긴다 (log/030)", () => {
  const old = parsePolicy({ plcyNo: "20240109005400100005", plcyNm: "청년전용 보증부 월세대출", operInstCdNm: "주택도시보증공사" });
  const now = parsePolicy({ plcyNo: "20260922005400113545", plcyNm: "청년전용  보증부 월세대출", operInstCdNm: "주택도시보증공사" });
  const other = parsePolicy({ plcyNo: "1", plcyNm: "다른 정책", operInstCdNm: "주택도시보증공사" });
  assert.deepEqual(dedupe([old, other, now]).map((p) => p.id), ["1", "20260922005400113545"]);
});

test("링크는 쓸 수 있는 주소로 바꾼다: 마크다운·scheme 없는 주소·위험한 값 (log/030)", () => {
  assert.equal(normalizeUrl("[www.hf.go.kr](https://www.hf.go.kr)"), "https://www.hf.go.kr");
  assert.equal(normalizeUrl(" www.khug.or.kr "), "https://www.khug.or.kr");
  assert.equal(normalizeUrl("http://nhuf.molit.go.kr/FP/x.jsp"), "http://nhuf.molit.go.kr/FP/x.jsp");
  assert.equal(normalizeUrl("javascript:alert(1)"), "");
  assert.equal(normalizeUrl("홈페이지 참고"), "");
});

type Labels = {
  labels: Record<"A" | "B", Record<string, [Verdict, string]>>;
  profiles: Record<"A" | "B", { schoolCd: string; mrgSttsCd: string; jobCd: string; sbizCd: string[] }>;
};
type Judged = { content: string };

test("Q4 혼합 판정: 서버 코드 판정 + 저장된 Groq 판정이 정답표와 14건 중 8건 맞고, 잘못된 '가능'은 0건 (log/019)", () => {
  const { labels, profiles } = readExperiment("q4/labels.json") as Labels;
  const samples = { A: load("probe_kywd_subsidy.json"), B: load("B_list.json") };
  let correct = 0;
  let unsafe = 0;
  for (const key of ["A", "B"] as const) {
    const judged = readSample(`groq/judge_${key}.json`) as Judged;
    const llm = new Map(
      (JSON.parse(judged.content).results as { plcyNm: string; verdict: Verdict }[]).map((r) => [r.plcyNm.trim(), r.verdict]),
    );
    const pr = profiles[key];
    const profile: Profile = { ...(key === "A" ? A : B), school: pr.schoolCd, marital: pr.mrgSttsCd, job: pr.jobCd, special: pr.sbizCd };
    for (const [name, [truth]] of Object.entries(labels[key])) {
      const policy = samples[key].find((p) => p.name === name.trim());
      assert.ok(policy, `샘플에 없는 정책: ${name}`);
      const verdict = combine(codeVerdict(policy, profile), llm.get(name.trim()) ?? "확인 필요");
      correct += Number(verdict === truth);
      unsafe += Number(verdict === "가능" && truth !== "가능");
    }
  }
  assert.equal(correct, 8);
  assert.equal(unsafe, 0);
});
