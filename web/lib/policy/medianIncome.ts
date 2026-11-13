// 2026년 기준 중위소득(월, 원). 출처: 복지로 "2026년도 '기준 중위소득' 역대 최대 인상"(2025-08-08, 정보제공 보건복지부),
// https://www.bokjiro.go.kr/ssis-tbu/cms/pc/news/promotion/1308418_1118.html (2026-11-13 확인).
// LLM은 연봉과 "중위소득 150%"를 비교하지 못했다(log/019). 그래서 서버가 표를 함께 준다(D10 구현 때 시험할 것).

export const MEDIAN_INCOME_YEAR = 2026;

export const MEDIAN_INCOME_MONTHLY: Readonly<Record<1 | 2 | 3 | 4 | 5 | 6, number>> = {
  1: 2_564_238,
  2: 4_199_292,
  3: 5_359_036,
  4: 6_494_738,
  5: 7_556_719,
  6: 8_555_952,
};

const won = (n: number): string => `${Math.round(n / 10_000).toLocaleString("ko-KR")}만 원`;

/** LLM 프롬프트에 넣을 짧은 표. 가구원 수를 알면 그 줄만, 모르면 1~4인. */
export const medianIncomeTable = (householdSize?: number): string => {
  const sizes = householdSize && householdSize >= 1 ? [Math.min(householdSize, 6) as 1 | 2 | 3 | 4 | 5 | 6] : ([1, 2, 3, 4] as const);
  const rows = sizes.map((n) => {
    const m = MEDIAN_INCOME_MONTHLY[n];
    return `${n}인 가구: 월 ${won(m)}(연 ${won(m * 12)}), 150%는 월 ${won(m * 1.5)}(연 ${won(m * 18)})`;
  });
  return `${MEDIAN_INCOME_YEAR}년 기준 중위소득(보건복지부)\n${rows.join("\n")}`;
};
