// D8: 공공 API 응답을 서버 메모리에 짧게 둔다. 키는 공공 API 요청값만 쓴다(나이·소득 같은 사용자 값은 넣지 않는다).
// 파일·DB·로그에 쓰지 않는다. 서버리스(Vercel)에서는 인스턴스마다 따로 있고 오래 살지 않는다.

export type TtlCache<V> = {
  get(key: string): V | undefined;
  set(key: string, value: V): void;
};

export const createTtlCache = <V>(ttlMs: number, maxEntries = 200, now: () => number = Date.now): TtlCache<V> => {
  const entries = new Map<string, { value: V; expires: number }>();
  return {
    get(key) {
      const hit = entries.get(key);
      if (!hit) return undefined;
      if (hit.expires <= now()) {
        entries.delete(key);
        return undefined;
      }
      return hit.value;
    },
    set(key, value) {
      if (!entries.has(key) && entries.size >= maxEntries) {
        const oldest = entries.keys().next().value;
        if (oldest !== undefined) entries.delete(oldest);
      }
      entries.set(key, { value, expires: now() + ttlMs });
    },
  };
};
