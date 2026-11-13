// Groq 채팅 호출(D5, D7). OpenAI 호환 엔드포인트를 fetch로 부른다(SDK 없이).
// 키는 GROQ_API_KEY 환경변수로만 받는다. 요청·응답 본문을 로그에 남기지 않는다(AGENTS.md "개인정보").

const URL = "https://api.groq.com/openai/v1/chat/completions";
export const MODEL = "openai/gpt-oss-120b";
const TIMEOUT_MS = 60_000;

export type Message = { role: "system" | "user"; content: string };

export type Usage = { prompt_tokens: number; completion_tokens: number };

/** 분당·일당 한도에 걸렸을 때. 화면에는 "잠시 후 다시"로 보여 준다. */
export class RateLimitError extends Error {
  readonly retryAfterSeconds: number | null;
  constructor(retryAfterSeconds: number | null) {
    super("Groq 사용 한도에 걸렸다");
    this.retryAfterSeconds = retryAfterSeconds;
  }
}

export type ChatJson = (messages: Message[]) => Promise<{ json: unknown; usage: Usage | null }>;

/** 응답이 ```json 블록으로 싸여 와도 읽는다. */
export const parseJsonContent = (content: string): unknown => {
  const trimmed = content.trim().replace(/^```(?:json)?\s*/i, "").replace(/\s*```$/, "");
  return JSON.parse(trimmed);
};

/** JSON 하나를 돌려받는 호출. 실험(judge_experiment.py)과 같은 설정이다. */
export const groqChatJson =
  (apiKey: string, fetchImpl: typeof fetch = fetch): ChatJson =>
  async (messages) => {
    const res = await fetchImpl(URL, {
      method: "POST",
      headers: { Authorization: `Bearer ${apiKey}`, "Content-Type": "application/json" },
      body: JSON.stringify({ model: MODEL, messages, temperature: 0, response_format: { type: "json_object" } }),
      signal: AbortSignal.timeout(TIMEOUT_MS),
    });
    if (res.status === 429) {
      const retry = Number(res.headers.get("retry-after"));
      throw new RateLimitError(Number.isFinite(retry) && retry > 0 ? retry : null);
    }
    if (!res.ok) throw new Error(`Groq HTTP ${res.status}`);
    const data = (await res.json()) as { choices?: { message?: { content?: string } }[]; usage?: Usage };
    const content = data.choices?.[0]?.message?.content;
    if (typeof content !== "string") throw new Error("Groq 응답에 내용이 없다");
    return { json: parseJsonContent(content), usage: data.usage ?? null };
  };
