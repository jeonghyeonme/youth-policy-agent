"""저장소 안 Markdown의 상대 링크가 실제 파일을 가리키는지 확인한다.

외부 URL(http·mailto)과 같은 문서 안 앵커(#...)는 보지 않는다.
경로 뒤 앵커는 떼고 파일이 있는지만 본다.

    python3 .github/scripts/check_links.py
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
SKIP_DIRS = {".git", "node_modules", ".venv", "venv"}


def broken_links(md: Path) -> list[str]:
    text = md.read_text(encoding="utf-8")
    text = re.sub(r"```.*?```", "", text, flags=re.S)  # 코드 블록 안은 링크가 아니다
    broken = []
    for target in LINK.findall(text):
        if re.match(r"[a-z]+:", target) or target.startswith("#"):
            continue
        path = target.split("#", 1)[0]
        if not (md.parent / path).exists():
            broken.append(target)
    return broken


def main() -> int:
    failed = 0
    for md in sorted(ROOT.rglob("*.md")):
        if SKIP_DIRS & set(md.relative_to(ROOT).parts):
            continue
        for target in broken_links(md):
            print(f"{md.relative_to(ROOT)}: 깨진 링크 {target}")
            failed += 1
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
