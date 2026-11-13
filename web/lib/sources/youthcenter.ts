// 온통청년 청년정책 API(개편 형식). 실측 결과는 experiments/context-measurement/api-survey.md, results.md.
// 서버에서만 부른다. 키는 YOUTHCENTER_API_KEY 환경변수로만 받는다.
import type { Policy } from "../policy/types.ts";
import { isClosedCode } from "../policy/types.ts";
import { createTtlCache } from "./cache.ts";

const URL_BASE = "https://www.youthcenter.go.kr/go/ythip/getPlcy";
const PAGE_SIZE = 100;
const TIMEOUT_MS = 20_000;

/** API에 보내는 조건. 모두 공공 API 요청값이라 캐시 키로 써도 된다(D8). 사용자 문장은 넣지 않는다(AGENTS.md). */
export type PolicyQuery = {
  /** 시군구 5자리 법정동 코드. 시도 앞자리(예: "11")는 API가 무시한다(log/011). */
  zipCd?: string;
  /** 대분류: 일자리, 주거, 교육, 복지문화, 참여권리 */
  lclsfNm?: string;
  /** 중분류(코드정의서 17개 중 하나) */
  mclsfNm?: string;
  /** 정책 키워드(코드정의서 17개 중 하나) */
  plcyKywdNm?: string;
};

/** API가 돌려주는 정책 한 건. 값은 모두 문자열(빈 값은 "" 또는 공백). */
export type RawPolicy = Record<string, string>;

const text = (raw: RawPolicy, key: string): string => (raw[key] ?? "").trim();
const list = (raw: RawPolicy, key: string): string[] =>
  text(raw, key)
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
const int = (raw: RawPolicy, key: string): number => Number.parseInt(text(raw, key), 10) || 0;

/** "20260301 ~ 20261231"처럼 적힌 신청기간에서 마지막 날짜를 읽는다. */
const applyEnd = (raw: RawPolicy): Date | null => {
  const dates = text(raw, "aplyYmd").match(/\d{8}/g);
  const last = dates?.at(-1);
  if (!last) return null;
  return new Date(Number(last.slice(0, 4)), Number(last.slice(4, 6)) - 1, Number(last.slice(6, 8)));
};

/** API 응답 한 건을 Policy로 바꾼다. 나이는 숫자로만 판단하고 0~0이면 제한 없음(log/017). */
export const parsePolicy = (raw: RawPolicy): Policy => {
  const min = int(raw, "sprtTrgtMinAge");
  const max = int(raw, "sprtTrgtMaxAge");
  return {
    id: text(raw, "plcyNo"),
    name: text(raw, "plcyNm"),
    keywords: list(raw, "plcyKywdNm"),
    summary: text(raw, "plcyExplnCn"),
    support: text(raw, "plcySprtCn"),
    operator: text(raw, "operInstCdNm") || text(raw, "sprvsnInstCdNm"),
    regionCodes: list(raw, "zipCd"),
    age: max > 0 ? { min, max } : null,
    jobCodes: list(raw, "jobCd"),
    schoolCodes: list(raw, "schoolCd"),
    maritalCodes: list(raw, "mrgSttsCd"),
    specialCodes: list(raw, "sbizCd"),
    closed: isClosedCode(text(raw, "aplyPrdSeCd")),
    applyEnd: applyEnd(raw),
    views: int(raw, "inqCnt"),
    incomeNote: text(raw, "earnEtcCn"),
    extraQualification: text(raw, "addAplyQlfcCndCn"),
    excluded: text(raw, "ptcpPrpTrgtCn"),
    applyMethod: text(raw, "plcyAplyMthdCn"),
    url: text(raw, "aplyUrlAddr") || text(raw, "refUrlAddr1"),
  };
};

export type PolicyPage = { total: number; policies: Policy[] };

/** 응답 본문(JSON)을 해석한다. 구조가 다르면 바로 실패시킨다. */
export const parseResponse = (body: unknown): PolicyPage => {
  const result = (body as { result?: { pagging?: { totCount?: number }; youthPolicyList?: RawPolicy[] } })?.result;
  if (!result || !Array.isArray(result.youthPolicyList)) {
    throw new Error("온통청년 응답 형식이 예상과 다르다(result.youthPolicyList 없음)");
  }
  return { total: Number(result.pagging?.totCount ?? result.youthPolicyList.length), policies: result.youthPolicyList.map(parsePolicy) };
};

/** 요청 URL을 만든다. 키는 여기서만 붙는다. 이 URL을 로그에 찍지 않는다. */
export const buildUrl = (query: PolicyQuery, apiKey: string, page = 1): string => {
  const params = new URLSearchParams({ apiKeyNm: apiKey, pageNum: String(page), pageSize: String(PAGE_SIZE), rtnType: "json" });
  for (const [k, v] of Object.entries(query)) if (v) params.set(k, v);
  return `${URL_BASE}?${params}`;
};

/** 캐시 키: 공공 API 요청값만(D8). 키(apiKey)는 넣지 않는다. */
export const cacheKey = (query: PolicyQuery): string =>
  JSON.stringify(Object.entries(query).filter(([, v]) => v).sort(([a], [b]) => a.localeCompare(b)));

const cache = createTtlCache<PolicyPage>(10 * 60_000);

/** 정책 첫 페이지(최대 100건)를 가져온다. D9 1단계로 요청을 좁히면 대부분 한 페이지에 들어온다(실측 73건). */
export const fetchPolicies = async (
  query: PolicyQuery,
  apiKey: string,
  fetchImpl: typeof fetch = fetch,
): Promise<PolicyPage> => {
  const key = cacheKey(query);
  const hit = cache.get(key);
  if (hit) return hit;
  const res = await fetchImpl(buildUrl(query, apiKey), { signal: AbortSignal.timeout(TIMEOUT_MS) });
  if (!res.ok) throw new Error(`온통청년 API HTTP ${res.status}`);
  const page = parseResponse(await res.json());
  cache.set(key, page);
  return page;
};
