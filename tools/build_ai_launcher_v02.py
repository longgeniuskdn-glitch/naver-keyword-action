from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import sys
import zipfile
from pathlib import Path
from typing import Any

try:
    import gdown
except ImportError as exc:  # pragma: no cover - CI installs it explicitly.
    raise SystemExit("gdown이 필요합니다: python -m pip install gdown") from exc

REPO = Path(__file__).resolve().parents[1]
WORK = REPO / ".build" / "ai_launcher_v02"
DOWNLOADS = WORK / "downloads"
EXTRACTED = WORK / "extracted"
DIST = REPO / "dist"
TEMPLATE = REPO / "ai_launcher_v02"

SOURCES = {
    "part04": {
        "id": "1nmR4fcX-bCCyvvHXQAZf7RnvrPnycMci",
        "filename": "PART04_AI_자동화_진단실_Linux검증_v1.zip",
    },
    "part05": {
        "id": "1rV4Ecr19ADEyZpKr8YocP3B4zr9LlYwY",
        "filename": "PART05_업무_접수_분류실_Linux검증_v1.zip",
    },
    "launcher01": {
        "id": "1SLIJNLzmgerOhYDQTTesxeRyTFgI_QV_",
        "filename": "우리회사_AI운영실_런처_MVP_Linux검증_v0.1.zip",
    },
}

MODULES = {
    "part04": {
        "id": "part04-ai-diagnosis",
        "name": "PART 04｜AI 자동화 진단실",
        "version": "1.1-module",
        "description": "반복 업무의 시간·비용·위험을 비교해 첫 자동화 프로젝트를 정합니다.",
        "port": 8794,
        "entrypoint": "app.py",
    },
    "part05": {
        "id": "part05-work-intake",
        "name": "PART 05｜업무 접수·분류실",
        "version": "1.1-module",
        "description": "수동 입력과 CSV 업무를 접수하고 유형·긴급도·담당·위험을 분류합니다.",
        "port": 8795,
        "entrypoint": "app.py",
    },
    "part06": {
        "id": "part06-knowledge-vault",
        "name": "PART 06｜회사 자료를 기억하는 AI 지식 창고",
        "version": "1.0-module",
        "description": "회사 자료를 로컬에서 색인하고 출처·버전·검토 기한과 함께 검색합니다.",
        "port": 8796,
        "entrypoint": "app.py",
    },
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def reset_dirs() -> None:
    if WORK.exists():
        shutil.rmtree(WORK)
    WORK.mkdir(parents=True)
    DOWNLOADS.mkdir()
    EXTRACTED.mkdir()
    DIST.mkdir(exist_ok=True)
    for name in (
        "우리회사_AI운영실_런처_v0.2",
        "PART04_AI_자동화_진단실_모듈호환_v1.1",
        "PART05_업무_접수_분류실_모듈호환_v1.1",
    ):
        target = DIST / name
        if target.exists():
            shutil.rmtree(target)


def download_sources() -> dict[str, Path]:
    result: dict[str, Path] = {}
    for key, info in SOURCES.items():
        destination = DOWNLOADS / str(info["filename"])
        print(f"[download] {key}: {info['id']}")
        downloaded = gdown.download(id=str(info["id"]), output=str(destination), quiet=False)
        if not downloaded or not destination.exists():
            raise RuntimeError(f"Google Drive 파일 다운로드 실패: {key}")
        if not zipfile.is_zipfile(destination):
            prefix = destination.read_bytes()[:200]
            raise RuntimeError(f"ZIP이 아닌 응답을 받았습니다: {key}: {prefix!r}")
        result[key] = destination
    return result


def extract_sources(paths: dict[str, Path]) -> dict[str, Path]:
    roots: dict[str, Path] = {}
    for key, archive in paths.items():
        target = EXTRACTED / key
        target.mkdir()
        with zipfile.ZipFile(archive) as zf:
            for item in zf.infolist():
                # ZIP slip 방지
                resolved = (target / item.filename).resolve()
                if target.resolve() not in resolved.parents and resolved != target.resolve():
                    raise RuntimeError(f"위험한 ZIP 경로: {item.filename}")
            zf.extractall(target)
        roots[key] = target
    return roots


def app_candidates(root: Path) -> list[Path]:
    candidates = []
    for path in root.rglob("app.py"):
        if any(part in {".venv", "venv", "__pycache__"} for part in path.parts):
            continue
        candidates.append(path.parent)
    return candidates


def score_app_root(path: Path) -> tuple[int, int, int]:
    score = 0
    if (path / "test_unittest.py").exists():
        score += 20
    if (path / "README.md").exists():
        score += 5
    if (path / "START_MAC.command").exists():
        score += 5
    if (path / "START_WINDOWS.bat").exists():
        score += 5
    return (score, -len(path.parts), -len(str(path)))


def find_app_root(root: Path) -> Path:
    candidates = app_candidates(root)
    if not candidates:
        raise FileNotFoundError(f"app.py를 찾지 못했습니다: {root}")
    return max(candidates, key=score_app_root)


def find_part06_root(root: Path) -> Path:
    manifest_candidates = []
    for manifest in root.rglob("module.json"):
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        text = " ".join(str(data.get(k, "")) for k in ("id", "name", "description")).lower()
        if any(token in text for token in ("part06", "part-06", "knowledge", "지식")):
            manifest_candidates.append(manifest.parent)
    if manifest_candidates:
        return min(manifest_candidates, key=lambda p: len(p.parts))
    for path in root.rglob("*"):
        if path.is_dir() and any(token in path.name.lower() for token in ("part06", "knowledge")):
            try:
                return find_app_root(path)
            except FileNotFoundError:
                pass
    raise FileNotFoundError("기존 런처에서 PART 06 모듈을 찾지 못했습니다.")


def ignore_copy(_src: str, names: list[str]) -> set[str]:
    ignored = {
        name for name in names
        if name in {".git", ".venv", "venv", "__pycache__", ".pytest_cache", ".mypy_cache", ".DS_Store"}
        or name.endswith(".pyc")
    }
    return ignored


def copy_clean(source: Path, destination: Path) -> None:
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination, ignore=ignore_copy)
    for pattern in ("**/*.db", "**/*.db-wal", "**/*.db-shm", "**/*.sqlite", "**/*.sqlite3", "**/*.log"):
        for path in destination.glob(pattern):
            if path.is_file():
                path.unlink()
    for dirname in ("runtime", "logs"):
        folder = destination / dirname
        if folder.exists():
            shutil.rmtree(folder)
        folder.mkdir(parents=True, exist_ok=True)
    for dirname in ("data", "output", "backups"):
        (destination / dirname).mkdir(parents=True, exist_ok=True)


def existing_entrypoint(module_root: Path, fallback: str) -> str:
    manifest = module_root / "module.json"
    if manifest.exists():
        try:
            value = json.loads(manifest.read_text(encoding="utf-8")).get("entrypoint")
            if isinstance(value, str) and (module_root / value).exists():
                return value
        except (OSError, json.JSONDecodeError):
            pass
    if (module_root / fallback).exists():
        return fallback
    candidates = [p for p in module_root.rglob("app.py") if p.is_file()]
    if not candidates:
        raise FileNotFoundError(f"모듈 실행 파일을 찾지 못했습니다: {module_root}")
    return str(min(candidates, key=lambda p: len(p.parts)).relative_to(module_root))


def write_manifest(module_root: Path, key: str) -> None:
    config = dict(MODULES[key])
    entrypoint = existing_entrypoint(module_root, str(config["entrypoint"]))
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "id": config["id"],
        "name": config["name"],
        "version": config["version"],
        "description": config["description"],
        "entrypoint": entrypoint,
        "args": ["--port", "{port}"],
        "default_port": config["port"],
        "health_path": "/health",
        "ui_path": "/",
        "data_policy": "isolated",
        "launcher_compatibility": ">=0.2",
        "capabilities": ["start", "stop", "health", "open", "logs"],
    }
    (module_root / "module.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (module_root / "MODULE_INTEGRATION.md").write_text(
        f"""# 통합 런처 모듈 정보

- 모듈 ID: `{manifest['id']}`
- 표시 이름: {manifest['name']}
- 기본 포트: `{manifest['default_port']}`
- 상태 점검: `{manifest['health_path']}`
- 데이터 정책: 모듈별 분리

이 어댑터는 기존 핵심 업무 로직과 SQLite 구조를 합치지 않습니다. 통합 런처는 실행·종료·상태·포트·로그만 관리합니다.

## 독립 실행

기존 운영체제용 실행 파일 또는 다음 명령을 계속 사용할 수 있습니다.

```bash
python3 {manifest['entrypoint']} --port {manifest['default_port']}
```
""",
        encoding="utf-8",
    )


def make_executable(path: Path) -> None:
    if path.exists():
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def copy_template(bundle: Path) -> None:
    for path in TEMPLATE.iterdir():
        if path.name == "__pycache__":
            continue
        target = bundle / path.name
        if path.is_dir():
            shutil.copytree(path, target)
        else:
            shutil.copy2(path, target)
    (bundle / "modules").mkdir()
    (bundle / "runtime").mkdir()
    (bundle / "logs").mkdir()
    make_executable(bundle / "START_MAC.command")
    make_executable(bundle / "START_LINUX.sh")


def append_readme_table(bundle: Path) -> None:
    readme = bundle / "README.md"
    with readme.open("a", encoding="utf-8") as handle:
        handle.write("\n## 빌드에 포함된 모듈 규격\n\n")
        handle.write("| 모듈 | 버전 | 포트 | 상태 점검 |\n|---|---:|---:|---|\n")
        for key in ("part04", "part05", "part06"):
            data = MODULES[key]
            handle.write(f"| {data['name']} | {data['version']} | {data['port']} | `/health` |\n")


def build() -> None:
    reset_dirs()
    archives = download_sources()
    roots = extract_sources(archives)

    source_roots = {
        "part04": find_app_root(roots["part04"]),
        "part05": find_app_root(roots["part05"]),
        "part06": find_part06_root(roots["launcher01"]),
    }
    print("[source roots]")
    for key, value in source_roots.items():
        print(f"  {key}: {value}")

    bundle = DIST / "우리회사_AI운영실_런처_v0.2"
    bundle.mkdir()
    copy_template(bundle)

    for key in ("part04", "part05", "part06"):
        module_dest = bundle / "modules" / key
        copy_clean(source_roots[key], module_dest)
        write_manifest(module_dest, key)
        make_executable(module_dest / "START_MAC.command")
        make_executable(module_dest / "START_LINUX.sh")

    append_readme_table(bundle)

    standalone_targets = {
        "part04": DIST / "PART04_AI_자동화_진단실_모듈호환_v1.1",
        "part05": DIST / "PART05_업무_접수_분류실_모듈호환_v1.1",
    }
    for key, target in standalone_targets.items():
        copy_clean(bundle / "modules" / key, target)
        write_manifest(target, key)
        make_executable(target / "START_MAC.command")
        make_executable(target / "START_LINUX.sh")

    build_manifest = {
        "launcher_version": "0.2",
        "build_python": sys.version,
        "sources": {
            key: {
                "drive_file_id": SOURCES[key]["id"],
                "filename": SOURCES[key]["filename"],
                "sha256": sha256(archive),
            }
            for key, archive in archives.items()
        },
        "modules": [json.loads((bundle / "modules" / key / "module.json").read_text(encoding="utf-8")) for key in ("part04", "part05", "part06")],
    }
    (bundle / "BUILD_MANIFEST.json").write_text(
        json.dumps(build_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"[done] {bundle}")


if __name__ == "__main__":
    build()
