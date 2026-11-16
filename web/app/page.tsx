// 채팅 화면은 3주째(T9)에 만든다. 지금은 배포·빌드 확인용 자리.
export default function Home() {
  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col justify-center gap-4 px-4">
      <h1 className="text-2xl font-semibold">청년 정책 안내 에이전트</h1>
      <p className="text-zinc-600 dark:text-zinc-400">
        조건을 고르면 받을 수 있는 청년 정책을 찾아 근거와 함께 설명합니다. 지금은 준비 중입니다.
      </p>
    </main>
  );
}
