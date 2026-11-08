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


# 반복 목록이 문서 내용의 이 비율보다 작으면 목록 응답이 아니라 한 건짜리(상세) 응답으로 본다.
LIST_SHARE = 0.5


def json_value(v: object) -> str:
    if v is None or v == [] or v == {}:
        return ""
    return v.strip() if isinstance(v, str) else json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else str(v)


def scalar_len(node: object) -> int:
    """리스트·dict 안의 문자열·숫자 값 길이 합. 바로 아래 값만이 아니라 전체를 센다(dict 리스트는 항목의 바로 아래 값만)."""
    if isinstance(node, list) and node and all(isinstance(x, dict) for x in node):
        return sum(len(str(v)) for d in node for v in d.values() if not isinstance(v, (list, dict)))
    if isinstance(node, dict):
        return sum(scalar_len(v) if isinstance(v, (list, dict)) else len(str(v)) for v in node.values())
    if isinstance(node, list):
        return sum(scalar_len(v) if isinstance(v, (list, dict)) else len(str(v)) for v in node)
    return len(str(node))


def flatten_json(node: object, out: Record, name: str = "value") -> Record:
    """한 건짜리 문서를 필드 이름 → 값으로 편다. 같은 이름이 또 나오면 뒤에 번호를 붙인다(XML과 같은 규칙)."""
    if isinstance(node, dict):
        for k, v in node.items():
            flatten_json(v, out, k)
    elif isinstance(node, list):
        for v in node:
            flatten_json(v, out, name)
    else:
        key, n = name, 2
        while key in out:
            key, n = f"{name}.{n}", n + 1
        out[key] = json_value(node)
    return out


def records_from_json(data: object) -> list[Record]:
    """내용이 가장 많이 든 dict 리스트를 정책·공고 목록으로 본다. 그런 리스트가 없으면 문서 전체가 한 건이다."""
    best: list[dict] = []
    best_size = 0

    def walk(node: object) -> None:
        nonlocal best, best_size
        if isinstance(node, list):
            dicts = [x for x in node if isinstance(x, dict)]
            size = scalar_len(dicts)  # 다른 목록을 감싸기만 하는 리스트는 0이 된다
            if dicts and size > best_size:
                best, best_size = dicts, size
            for x in node:
                walk(x)
        elif isinstance(node, dict):
            for v in node.values():
                walk(v)

    walk(data)
    if best_size < LIST_SHARE * scalar_len(data):
        return [flatten_json(data, {})]
    return [{k: json_value(v) for k, v in d.items()} for d in best]


def text_len(elem: ET.Element) -> int:
    return sum(len((e.text or "").strip()) for e in elem.iter())


def flatten_xml(elem: ET.Element) -> Record:
    out: Record = {}
    for e in elem.iter():
        if not len(e) and (e.text or "").strip():
            key, n = e.tag, 2
            while key in out:
                key, n = f"{e.tag}.{n}", n + 1
            out[key] = e.text.strip()
    return out


def records_from_xml(root: ET.Element) -> list[Record]:
    """같은 이름으로 반복되는 자식 요소 중 내용이 가장 많은 묶음을 목록으로 본다. 작으면 문서 전체가 한 건이다."""
    best: list[ET.Element] = []
    best_size = 0
    for parent in root.iter():
        groups: dict[str, list[ET.Element]] = {}
        for child in parent:
            if len(child):
                groups.setdefault(child.tag, []).append(child)
        for group in groups.values():
            size = sum(text_len(g) for g in group) if len(group) > 1 else 0  # 한 번만 나오는 감싸개는 목록이 아니다
            if size > best_size:
                best, best_size = group, size
    if best_size < LIST_SHARE * text_len(root):
        return [flatten_xml(root)]
    return [flatten_xml(item) for item in best]


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
