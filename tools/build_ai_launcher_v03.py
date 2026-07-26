from __future__ import annotations

import os
import shutil
import sys
import zipfile
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
REPO = TOOLS.parent
DIST = REPO / "dist"
SOURCE_NAME = "우리회사_AI운영실_런처_v0.2"
TARGET_NAME = "우리회사_AI운영실_런처_v0.3_피드백_MD승인"


def zip_tree(source: Path, archive: Path) -> None:
    if archive.exists():
        archive.unlink()
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(source.rglob("*")):
            if path.is_file():
                zf.write(path, Path(source.name) / path.relative_to(source))


def resolve_v02_source() -> Path:
    supplied = os.environ.get("V02_BUNDLE_DIR", "").strip()
    if supplied:
        source = Path(supplied).resolve()
        if not (source / "launcher.py").exists() or not (source / "modules").is_dir():
            raise FileNotFoundError(f"v0.2 번들 구조를 확인할 수 없습니다: {source}")
        return source

    if str(TOOLS) not in sys.path:
        sys.path.insert(0, str(TOOLS))
    import build_ai_launcher_v02 as v02

    v02.build()
    source = DIST / SOURCE_NAME
    if not source.exists():
        raise FileNotFoundError(f"v0.2 빌드 결과가 없습니다: {source}")
    return source


def build() -> Path:
    source = resolve_v02_source()
    DIST.mkdir(exist_ok=True)
    target = DIST / TARGET_NAME
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target)

    original_launcher = target / "launcher.py"
    shutil.copy2(original_launcher, target / "launcher_core.py")
    shutil.copy2(REPO / "ai_launcher_v03" / "launcher.py", original_launcher)

    feedback_target = target / "common_feedback"
    if feedback_target.exists():
        shutil.rmtree(feedback_target)
    shutil.copytree(
        REPO / "common_feedback",
        feedback_target,
        ignore=shutil.ignore_patterns("__pycache__", "test_*.py", "*.pyc"),
    )

    (target / "memory").mkdir(exist_ok=True)
    readme = target / "README.md"
    with readme.open("a", encoding="utf-8") as handle:
        handle.write("\n\n---\n\n")
        handle.write((REPO / "ai_launcher_v03" / "README.md").read_text(encoding="utf-8"))

    archive = DIST / f"{TARGET_NAME}.zip"
    zip_tree(target, archive)
    print(f"[v0.3 bundle] {archive}")
    return archive


if __name__ == "__main__":
    build()
