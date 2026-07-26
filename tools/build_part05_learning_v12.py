from __future__ import annotations

import json
import os
import shutil
import stat
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DIST = REPO / "dist"
INTEGRATED_NAME = "우리회사_AI운영실_런처_v0.4_PART05_직접학습"
STANDALONE_NAME = "PART05_업무_접수_분류실_직접학습_v1.2"


def _ignore(_src: str, names: list[str]) -> set[str]:
    return {
        name
        for name in names
        if name in {".git", ".venv", "venv", "__pycache__", ".pytest_cache", ".mypy_cache", ".DS_Store"}
        or name.endswith(".pyc")
    }


def _clean_runtime(root: Path) -> None:
    for pattern in ("**/*.db", "**/*.db-wal", "**/*.db-shm", "**/*.sqlite", "**/*.sqlite3", "**/*.log"):
        for path in root.glob(pattern):
            if path.is_file():
                path.unlink()
    for name in ("runtime", "logs"):
        folder = root / name
        if folder.exists():
            shutil.rmtree(folder)
        folder.mkdir(parents=True, exist_ok=True)
    (root / "memory").mkdir(parents=True, exist_ok=True)


def _make_executable(path: Path) -> None:
    if path.exists():
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def resolve_v03_source() -> Path:
    supplied = os.environ.get("V03_BUNDLE_DIR", "").strip()
    if not supplied:
        raise FileNotFoundError("V03_BUNDLE_DIR 환경변수로 검증된 v0.3 번들 경로를 전달해야 합니다.")
    root = Path(supplied).resolve()
    candidates = [root]
    candidates.extend(path.parent for path in root.rglob("launcher.py"))
    for candidate in sorted(set(candidates), key=lambda p: len(p.parts)):
        if (candidate / "launcher.py").exists() and (candidate / "modules" / "part05" / "app.py").exists():
            return candidate
    raise FileNotFoundError(f"v0.3 번들에서 PART 05를 찾지 못했습니다: {root}")


def _install_part05_learning(module_root: Path) -> None:
    original = module_root / "app.py"
    core = module_root / "app_core.py"
    if not core.exists():
        if not original.exists():
            raise FileNotFoundError(f"PART 05 app.py가 없습니다: {module_root}")
        original.replace(core)
    shutil.copy2(REPO / "part05_learning" / "adapter_app.py", original)
    shutil.copy2(REPO / "part05_learning" / "rules.py", module_root / "learning_rules.py")

    manifest_path = module_root / "module.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    manifest.update(
        {
            "schema_version": 1,
            "id": "part05-work-intake",
            "name": "PART 05｜업무 접수·분류실",
            "version": "1.2-learning",
            "description": "업무 분류를 사람이 수정하고 반복 피드백을 승인 규칙으로 전환해 다음 분류에 재사용합니다.",
            "entrypoint": "app.py",
            "args": ["--port", "{port}"],
            "default_port": 8795,
            "health_path": "/health",
            "ui_path": "/",
            "data_policy": "isolated-intake-shared-feedback",
            "launcher_compatibility": ">=0.3",
            "capabilities": [
                "start",
                "stop",
                "health",
                "open",
                "logs",
                "classification-correction",
                "feedback",
                "rule-approval",
                "approved-rule-application",
            ],
        }
    )
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    integration = module_root / "PART05_LEARNING_INTEGRATION.md"
    integration.write_text(
        """# PART 05 직접 학습 루프

1. 업무 대기열에서 `분류 수정`을 누릅니다.
2. 수정 분류·담당·긴급도·처리 모드와 적용 키워드를 입력합니다.
3. 같은 수정이 두 번 반복되면 규칙 후보가 됩니다.
4. 승인자가 후보를 승인해야 `INTAKE_RULES.md`에 기록되고 다음 분류에 적용됩니다.
5. 계약·법률·결제·환불·개인정보 안전 경계는 학습 규칙으로 낮출 수 없습니다.

사건 전체는 SQLite에, 승인된 운영 기준은 Markdown에 저장합니다.
""",
        encoding="utf-8",
    )


def build() -> tuple[Path, Path]:
    source = resolve_v03_source()
    DIST.mkdir(exist_ok=True)
    integrated = DIST / INTEGRATED_NAME
    standalone = DIST / STANDALONE_NAME
    for target in (integrated, standalone):
        if target.exists():
            shutil.rmtree(target)

    shutil.copytree(source, integrated, ignore=_ignore)
    _clean_runtime(integrated)
    part05 = integrated / "modules" / "part05"
    _install_part05_learning(part05)

    readme = integrated / "README.md"
    with readme.open("a", encoding="utf-8") as handle:
        handle.write(
            "\n\n## v0.4｜PART 05 직접 학습 루프\n\n"
            "업무 상세 화면에서 분류를 수정하면 공통 피드백 DB에 자동 저장됩니다. "
            "같은 수정이 반복돼도 사람 승인 전에는 다음 업무에 적용되지 않습니다.\n"
        )

    shutil.copytree(part05, standalone, ignore=_ignore)
    shutil.copytree(integrated / "common_feedback", standalone / "common_feedback", ignore=_ignore)
    for name in ("runtime", "memory"):
        (standalone / name).mkdir(parents=True, exist_ok=True)
    (standalone / "START_LINUX.sh").write_text(
        "#!/usr/bin/env bash\nset -euo pipefail\ncd \"$(dirname \"$0\")\"\npython3 app.py\n",
        encoding="utf-8",
    )
    _make_executable(standalone / "START_LINUX.sh")
    _make_executable(standalone / "START_MAC.command")
    _make_executable(integrated / "START_LINUX.sh")
    _make_executable(integrated / "START_MAC.command")
    _clean_runtime(standalone)

    print(f"[integrated] {integrated}")
    print(f"[standalone] {standalone}")
    return integrated, standalone


if __name__ == "__main__":
    build()
