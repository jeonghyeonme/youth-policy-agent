// 대화 한 턴. 키는 여기서만 읽는다(D11). 요청 본문(질문·선택값)을 로그에 남기지 않는다(AGENTS.md "개인정보", D10).
import { answer } from "@/lib/chat/answer.ts";
import { BadRequest, parseChatRequest } from "@/lib/chat/validate.ts";
import { groqChatJson, RateLimitError } from "@/lib/llm/groq.ts";
import { fetchPolicies } from "@/lib/sources/youthcenter.ts";

const error = (status: number, message: string) => Response.json({ error: message }, { status });

export async function POST(request: Request) {
  const youthKey = process.env.YOUTHCENTER_API_KEY;
  const groqKey = process.env.GROQ_API_KEY;
  if (!youthKey || !groqKey) return error(500, "서버 설정이 끝나지 않았습니다");

  let req;
  try {
    req = parseChatRequest(await request.json());
  } catch (e) {
    return error(400, e instanceof BadRequest ? e.message : "요청 형식이 올바르지 않습니다");
  }

  try {
    const result = await answer(req, {
      chat: groqChatJson(groqKey),
      fetchPolicies: (query) => fetchPolicies(query, youthKey),
      today: new Date(),
    });
    return Response.json(result);
  } catch (e) {
    if (e instanceof RateLimitError) return error(503, "지금 이용자가 많습니다. 잠시 후 다시 시도해 주세요");
    // 원인만 남기고 요청 내용은 남기지 않는다
    console.error("chat failed:", e instanceof Error ? e.message : "unknown");
    return error(502, "정책 정보를 가져오지 못했습니다. 잠시 후 다시 시도해 주세요");
  }
}
