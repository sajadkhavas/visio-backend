import subprocess
from pathlib import Path

allowed_env_files = {".env.example"}
tracked = subprocess.run(
    ["git", "ls-files"],
    check=True,
    capture_output=True,
    text=True,
).stdout.splitlines()

for filename in tracked:
    path = Path(filename)
    if path.name.startswith(".env") and path.name not in allowed_env_files:
        raise SystemExit(f"Refusing tracked environment file: {filename}")

private_key_marker = "-----BEGIN " + "PRIVATE KEY-----"
for filename in tracked:
    path = Path(filename)
    if not path.is_file():
        continue
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        continue
    if private_key_marker in text:
        raise SystemExit(f"Private key material detected in {filename}")

print("Secret-sanity gate passed: no tracked .env files or private-key material.")
