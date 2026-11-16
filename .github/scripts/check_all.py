"""CI가 하던 검사를 로컬에서 한 번에 돌린다(D15). PR을 올리기 전에 실행하고 결과를 PR 설명 "확인"에 적는다.

    py .github/scripts/check_all.py        # Windows
    python3 .github/scripts/check_all.py   # macOS·Linux

공공 API·Groq를 부르지 않는다. web/ 의존성이 없으면 먼저 `npm ci`를 돌린다.
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "web"

STEPS = [
    ("측정·수집 스크립트 테스트", [sys.executable, "-m", "unittest", "discover", "-s", "experiments/context-measurement", "-p", "test_*.py"], ROOT),
    ("문서 상대 링크 확인", [sys.executable, ".github/scripts/check_links.py"], ROOT),
    ("web: 린트", "npm run lint", WEB),
    ("web: 타입 검사", "npm run typecheck", WEB),
    ("web: 테스트", "npm test", WEB),
    ("web: 빌드", "npm run build", WEB),
]


def main() -> int:
    if not (WEB / "node_modules").exists():
        print("web/node_modules가 없어 npm ci부터 돌린다")
        if subprocess.run("npm ci", cwd=WEB, shell=True).returncode != 0:
            return 1
    results = []
    for name, cmd, cwd in STEPS:
        print(f"\n=== {name} ===", flush=True)
        ok = subprocess.run(cmd, cwd=cwd, shell=isinstance(cmd, str)).returncode == 0
        results.append((name, ok))
        if not ok:
            break
    print("\n=== 결과 ===")
    for name, ok in results:
        print(f"{'통과' if ok else '실패'}  {name}")
    skipped = [name for name, _, _ in STEPS[len(results):]]
    for name in skipped:
        print(f"건너뜀  {name}")
    return 0 if all(ok for _, ok in results) and not skipped else 1


if __name__ == "__main__":
    sys.exit(main())
