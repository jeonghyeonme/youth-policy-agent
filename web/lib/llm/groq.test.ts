import { test } from "node:test";
import assert from "node:assert/strict";
import { groqChatJson, MODEL, parseJsonContent, RateLimitError } from "./groq.ts";

test("```json 블록으로 싸인 응답도 읽는다", () => {
  assert.deepEqual(parseJsonContent('```json\n{"a":1}\n```'), { a: 1 });
});

test("요청: 모델과 JSON 모드를 쓰고, 키는 헤더에만 있다", async () => {
  let seen: { headers: Headers; body: string } | undefined;
  const fakeFetch = (async (_url: string, init: RequestInit) => {
    seen = { headers: new Headers(init.headers), body: String(init.body) };
    return Response.json({ choices: [{ message: { content: '{"ok":true}' } }], usage: { prompt_tokens: 1, completion_tokens: 1 } });
  }) as typeof fetch;
  const r = await groqChatJson("TEST_KEY", fakeFetch)([{ role: "user", content: "hi" }]);
  assert.deepEqual(r.json, { ok: true });
  assert.equal(seen?.headers.get("authorization"), "Bearer TEST_KEY");
  const body = JSON.parse(seen!.body);
  assert.equal(body.model, MODEL);
  assert.deepEqual(body.response_format, { type: "json_object" });
  assert.ok(!seen!.body.includes("TEST_KEY"));
});

test("429는 한도 오류로 바꾼다", async () => {
  const fakeFetch = (async () => new Response("", { status: 429, headers: { "retry-after": "12" } })) as typeof fetch;
  await assert.rejects(groqChatJson("K", fakeFetch)([]), (e: unknown) => e instanceof RateLimitError && e.retryAfterSeconds === 12);
});
