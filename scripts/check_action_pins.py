import re
from pathlib import Path

WORKFLOW_ROOT = Path(".github/workflows")
PIN = re.compile(r"^\s*uses:\s*[^@\s]+@[0-9a-f]{40}(?:\s+#.*)?$")

violations: list[str] = []
for path in sorted(WORKFLOW_ROOT.glob("*.yml")):
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if "uses:" in line and not PIN.match(line):
            violations.append(f"{path}:{number}: {line.strip()}")

if violations:
    raise SystemExit("Unpinned GitHub Actions references:\n" + "\n".join(violations))

print("All GitHub Actions references are pinned to immutable commit SHAs.")
