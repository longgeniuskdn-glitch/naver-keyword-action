from __future__ import annotations

import json
import zipfile
from pathlib import Path

import build_ai_launcher_v02 as build_module


EXCLUDED_DIRS = {
    ".git", ".venv", "venv", "__pycache__", ".pytest_cache",
    "tests", "test", "scripts", "docs", "backups", "output",
}

ORIGINAL_EXTRACT_SOURCES = build_module.extract_sources


def safe_extract_zip(archive: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    base = destination.resolve()
    with zipfile.ZipFile(archive) as zf:
        for item in zf.infolist():
            target = (destination / item.filename).resolve()
            if target != base and base not in target.parents:
                raise RuntimeError(f"위험한 내부 ZIP 경로: {item.filename}")
        zf.extractall(destination)


def expand_nested_archives(root: Path, max_depth: int = 3) -> Path:
    processed: set[Path] = set()
    for depth in range(1, max_depth + 1):
        nested = [
            path for path in sorted(root.rglob("*.zip"))
            if path.is_file() and path.resolve() not in processed
        ]
        if not nested:
            break
        for archive in nested:
            processed.add(archive.resolve())
            destination = archive.with_suffix("")
            if destination.exists():
                destination = archive.parent / f"{archive.stem}_extracted"
            safe_extract_zip(archive, destination)
            print(
                f"[nested zip depth={depth}] "
                f"{archive.relative_to(root)} -> {destination.relative_to(root)}"
            )
    return root


def extract_sources(paths: dict[str, Path]) -> dict[str, Path]:
    roots = ORIGINAL_EXTRACT_SOURCES(paths)
    for key, root in roots.items():
        expand_nested_archives(root)
        files = [str(path.relative_to(root)) for path in sorted(root.rglob("*")) if path.is_file()]
        print(f"[extracted files] {key}: {len(files)}")
        for name in files[:80]:
            print(f"  - {name}")
    return roots


def score_python_file(path: Path) -> int:
    name = path.name.lower()
    if name.startswith("test_") or name.endswith("_test.py"):
        return -10_000
    if any(part.lower() in EXCLUDED_DIRS for part in path.parts):
        return -5_000
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")[:200_000]
    except OSError:
        return -10_000

    score = 0
    preferred_names = {
        "app.py": 200,
        "main.py": 170,
        "server.py": 150,
        "launcher.py": 100,
        "run.py": 90,
    }
    score += preferred_names.get(name, 0)
    if "app" in name:
        score += 80
    if "server" in name:
        score += 70
    if "diagnosis" in name or "intake" in name or "knowledge" in name:
        score += 50
    signals = {
        "ThreadingHTTPServer": 90,
        "HTTPServer": 60,
        "serve_forever": 80,
        "--port": 70,
        "argparse": 25,
        "if __name__": 30,
        "/health": 35,
        "BaseHTTPRequestHandler": 50,
    }
    for token, points in signals.items():
        if token in text:
            score += points
    return score


def python_candidates(root: Path) -> list[Path]:
    candidates = [path for path in root.rglob("*.py") if path.is_file()]
    candidates.sort(key=lambda path: (score_python_file(path), -len(path.parts)), reverse=True)
    return candidates


def project_root_for(entrypoint: Path, extraction_root: Path) -> Path:
    candidates: list[Path] = []
    current = entrypoint.parent
    extraction_root = extraction_root.resolve()
    while True:
        candidates.append(current)
        if current.resolve() == extraction_root or extraction_root not in current.resolve().parents:
            break
        current = current.parent

    def root_score(folder: Path) -> tuple[int, int]:
        score = 0
        markers = [
            "README.md", "START_HERE.md", "START_MAC.command",
            "START_WINDOWS.bat", "test_unittest.py", "requirements.txt",
            "AGENTS.md", "SPEC.md",
        ]
        for marker in markers:
            if (folder / marker).exists():
                score += 20
        if (folder / "data").exists():
            score += 5
        if (folder / "output").exists():
            score += 5
        if (folder / "backups").exists():
            score += 5
        distance = len(entrypoint.parent.relative_to(folder).parts) if folder != entrypoint.parent else 0
        return score, -distance

    return max(candidates, key=root_score)


def find_app_root(root: Path) -> Path:
    candidates = python_candidates(root)
    if not candidates or score_python_file(candidates[0]) <= 0:
        names = [str(path.relative_to(root)) for path in sorted(root.rglob("*")) if path.is_file()]
        raise FileNotFoundError(
            "실행 가능한 Python 서버 파일을 찾지 못했습니다.\n" + "\n".join(names[:200])
        )
    chosen = candidates[0]
    print(f"[entrypoint detect] {chosen.relative_to(root)} score={score_python_file(chosen)}")
    return project_root_for(chosen, root)


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
    candidates = python_candidates(module_root)
    if not candidates or score_python_file(candidates[0]) <= 0:
        raise FileNotFoundError(f"모듈 실행 파일을 찾지 못했습니다: {module_root}")
    return str(candidates[0].relative_to(module_root))


build_module.extract_sources = extract_sources
build_module.find_app_root = find_app_root
build_module.existing_entrypoint = existing_entrypoint

if __name__ == "__main__":
    build_module.build()
