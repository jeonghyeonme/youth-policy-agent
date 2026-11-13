// 테스트용 저장 샘플. 공공 API·Groq를 부르지 않는다(AGENTS.md "트래픽").
// 샘플은 experiments/에 하나만 두고 여기서 읽는다(복사하지 않는다). CI는 저장소 전체를 체크아웃하므로 읽을 수 있다.
import { readFileSync } from "node:fs";
import { join } from "node:path";

const EXPERIMENT = join(import.meta.dirname, "../../../experiments/context-measurement");

export const readSample = (path: string): unknown => JSON.parse(readFileSync(join(EXPERIMENT, "samples", path), "utf8"));
export const readExperiment = (path: string): unknown => JSON.parse(readFileSync(join(EXPERIMENT, path), "utf8"));

/** 샘플을 받은 날. 신청 가능 여부가 실행 날짜에 따라 바뀌지 않게 고정한다. */
export const SAMPLE_DAY = new Date(2026, 10, 8);
