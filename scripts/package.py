"""Create a source-only ZIP, excluding credentials, local tools and telemetry."""
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parent.parent
destination = ROOT / "artifacts" / "AquaGuard-IoT-Codebase.zip"
destination.parent.mkdir(exist_ok=True)
files = [ROOT / "README.md", ROOT / ".gitignore"]
for folder in ("app", "web", "docs", "tests", "scripts", "firmware"):
    for path in (ROOT / folder).rglob("*"):
        relative = path.relative_to(ROOT)
        if (path.is_file() and not any(part in ("__pycache__", ".pio") for part in relative.parts)
                and path.name not in ("config.h", "tank_config.h") and path.suffix not in (".pyc", ".pyo")):
            files.append(path)
with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as bundle:
    for path in sorted(files):
        bundle.write(path, Path("AquaGuard") / path.relative_to(ROOT))
print(destination)
