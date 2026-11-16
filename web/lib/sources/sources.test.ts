import { test } from "node:test";
import assert from "node:assert/strict";
import { createTtlCache } from "./cache.ts";
import { buildUrl, cacheKey, fetchPolicies, parseResponse } from "./youthcenter.ts";
import { readSample } from "../test/fixtures.ts";

test("캐시는 만료 시간이 지나면 비우고, 가득 차면 가장 오래된 것부터 버린다", () => {
  let now = 0;
  const cache = createTtlCache<number>(1000, 2, () => now);
  cache.set("a", 1);
  cache.set("b", 2);
  cache.set("c", 3);
  assert.equal(cache.get("a"), undefined);
  assert.equal(cache.get("c"), 3);
  now = 1000;
  assert.equal(cache.get("c"), undefined);
});

test("캐시 키는 요청값만 쓰고 순서와 빈 값에 영향받지 않는다 (D8)", () => {
  assert.equal(cacheKey({ zipCd: "11110", lclsfNm: "일자리" }), cacheKey({ lclsfNm: "일자리", zipCd: "11110", mclsfNm: "" }));
});

test("요청 URL에 조건과 키 파라미터가 들어간다", () => {
  const url = new URL(buildUrl({ zipCd: "11110", plcyKywdNm: "보조금" }, "TEST_KEY"));
  assert.equal(url.searchParams.get("zipCd"), "11110");
  assert.equal(url.searchParams.get("plcyKywdNm"), "보조금");
  assert.equal(url.searchParams.get("apiKeyNm"), "TEST_KEY");
  assert.equal(url.searchParams.get("rtnType"), "json");
});

test("응답 형식이 다르면 바로 실패한다", () => {
  assert.throws(() => parseResponse({ resultCode: 500 }), /형식/);
});

test("같은 조건은 두 번째부터 캐시에서 돌려준다", async () => {
  const body = readSample("youthcenter/probe_kywd_subsidy.json");
  let calls = 0;
  const fakeFetch = (async () => {
    calls += 1;
    return new Response(JSON.stringify(body), { status: 200 });
  }) as typeof fetch;
  const query = { zipCd: "11110", lclsfNm: "일자리", plcyKywdNm: "보조금", mclsfNm: "테스트-캐시" };
  const first = await fetchPolicies(query, "TEST_KEY", fakeFetch);
  const second = await fetchPolicies(query, "TEST_KEY", fakeFetch);
  assert.equal(first.total, 73);
  assert.equal(second, first);
  assert.equal(calls, 1);
});
