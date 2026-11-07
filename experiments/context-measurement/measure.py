"""저장해 둔 공공 API 응답 샘플로 LLM에 넘길 컨텍스트 크기를 잰다.

API를 호출하지 않는다. 사람이 받아 둔 응답 파일(JSON 또는 XML)만 읽는다.
토큰 기준(Q5)이 정해지기 전이라 UTF-8 바이트와 글자 수로 잰다.

    python3 measure.py samples/youthcenter/*.json
    python3 measure.py samples/youthcenter/*.json --keep fields/youthcenter.txt

--keep 파일에는 남길 필드 이름을 한 줄에 하나씩 적는다(# 뒤는 주석).
남긴 필드만으로 다시 재서 "서버 필터링 후" 크기를 본다.
"""

from __future__ import annotations

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

# 요청 URL을 통째로 저장하면 키가 샘플에 섞인다. 이 이름이 보이면 재지 않고 멈춘다.
KEY_PARAM_NAMES = ("servicekey", "apikeynm", "openapivlak", "authkey")

Record = dict[str, str]


@dataclass(frozen=True)
class Size:
    bytes: int
    chars: int

    @staticmethod
    def of(text: str) -> Size:
        return Size(len(text.encode("utf-8")), len(text))


@dataclass(frozen=True)
class Measurement:
    file: str
    raw: Size
    records: int
    compact: Size
    kept: Size | None


def find_key_param(text: str) -> str | None:
    lowered = text.lower()
    return next((name for name in KEY_PARAM_NAMES if name in lowered), None)


def records_from_json(data: object) -> list[Record]:
    """응답 안에서 dict가 가장 많이 든 리스트를 정책·공고 목록으로 본다."""
    best: list[dict] = []

    def walk(node: object) -> None:
        nonlocal best
        if isinstance(node, list):
            dicts = [x for x in node if isinstance(x, dict)]
            if len(dicts) > len(best):
                best = dicts
            for x in node:
                walk(x)
        elif isinstance(node, dict):
            for v in node.values():
                walk(v)

    walk(data)
    return [{k: "" if v is None else str(v) for k, v in d.items()} for d in best]


def records_from_xml(root: ET.Element) -> list[Record]:
    """같은 이름의 자식 요소가 가장 많이 반복되는 곳을 목록으로 본다."""
    best: list[ET.Element] = []
    for parent in root.iter():
        groups: dict[str, list[ET.Element]] = {}
        for child in parent:
            if len(child):
                groups.setdefault(child.tag, []).append(child)
        for group in groups.values():
            if len(group) > len(best):
                best = group
    return [{f.tag: (f.text or "").strip() for f in item} for item in best]


def parse_records(text: str) -> list[Record]:
    stripped = text.lstrip()
    if stripped.startswith("<"):
        return records_from_xml(ET.fromstring(stripped))
    return records_from_json(json.loads(stripped))


def compact(records: list[Record]) -> str:
    # 빈 값은 LLM에 넘길 이유가 없어 뺀다.
    cleaned = [{k: v for k, v in r.items() if v} for r in records]
    return json.dumps(cleaned, ensure_ascii=False, separators=(",", ":"))


def measure(path: Path, keep: list[str] | None) -> Measurement:
    text = path.read_text(encoding="utf-8")
    leaked = find_key_param(text)
    if leaked:
        raise ValueError(f"{path}: '{leaked}'가 들어 있다. 키가 섞였을 수 있어 재지 않는다")
    records = parse_records(text)
    kept = None
    if keep is not None:
        kept = Size.of(compact([{k: r.get(k, "") for k in keep} for r in records]))
    return Measurement(str(path), Size.of(text), len(records), Size.of(compact(records)), kept)


def read_keep(path: Path) -> list[str]:
    lines = (line.split("#", 1)[0].strip() for line in path.read_text(encoding="utf-8").splitlines())
    return [line for line in lines if line]


def per_record(size: Size, n: int) -> str:
    return f"{size.chars // n:,}" if n else "-"


def to_markdown(rows: list[Measurement]) -> str:
    has_kept = any(m.kept for m in rows)
    head = ["파일", "건수", "원본 바이트", "원본 글자", "정리 후 글자", "건당 글자"]
    if has_kept:
        head += ["필드 추린 후 글자", "건당 글자(추린 후)"]
    lines = ["| " + " | ".join(head) + " |", "|" + " --- |" * len(head)]
    for m in rows:
        cells = [m.file, f"{m.records:,}", f"{m.raw.bytes:,}", f"{m.raw.chars:,}",
                 f"{m.compact.chars:,}", per_record(m.compact, m.records)]
        if has_kept:
            cells += [f"{m.kept.chars:,}", per_record(m.kept, m.records)] if m.kept else ["-", "-"]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("samples", nargs="+", type=Path, help="저장한 응답 파일(JSON/XML)")
    parser.add_argument("--keep", type=Path, help="남길 필드 목록 파일")
    args = parser.parse_args(argv)
    keep = read_keep(args.keep) if args.keep else None
    try:
        rows = [measure(p, keep) for p in args.samples]
    except ValueError as e:
        print(e, file=sys.stderr)
        return 1
    print(to_markdown(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
