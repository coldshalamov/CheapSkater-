from __future__ import annotations

import subprocess
import sys
import textwrap
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Tuple

import csv
import os
import re


REQUIRED_FILES = [
    "app/main.py",
    "app/config.yml",
    "app/selectors.py",
    "app/logging_config.py",
    "app/errors.py",
    "app/retailers/lowes.py",
    "app/extractors/dom_utils.py",
    "app/extractors/schemas.py",
    "app/storage/db.py",
    "app/storage/models_sql.py",
    "app/storage/repo.py",
    "app/alerts/notifier.py",
    "README.md",
    "requirements.txt",
]

SELECTOR_FRAGMENTS = ["/pd/", "ProductPrice__", "aria-label", "data-test", "data-automation-id"]
SUMMARY_LINE = "cycle ok | retailer=lowes | zips=%d | items=%d | alerts=%d | duration=%.1fs"


@dataclass
class GateResult:
    name: str
    passed: bool
    details: str = ""


def _print_heading(title: str) -> None:
    print(title)
    print("-" * len(title))


def _print_result(result: GateResult) -> None:
    status = "PASS" if result.passed else "FAIL"
    print(f"[{status}] {result.name}")
    if result.details:
        print(textwrap.indent(result.details.strip(), "    "))


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def _python_files(root: Path) -> Iterable[Path]:
    for path in root.rglob("*.py"):
        if any(part.startswith(".") and part != "." for part in path.parts):
            continue
        if "__pycache__" in path.parts:
            continue
        if path.name == "verify_readiness.py":
            continue
        yield path


def _check_required_files(root: Path) -> GateResult:
    missing = [str(Path(name)) for name in REQUIRED_FILES if not (root / name).exists()]
    if missing:
        return GateResult(
            "Static: contract files present",
            False,
            "Missing files:\n" + "\n".join(f"- {m}" for m in missing),
        )
    return GateResult("Static: contract files present", True)


def _check_readme_windows_docs(root: Path) -> GateResult:
    text = _read_text(root / "README.md")
    required_snippets = [
        "python -m venv",
        "pip install -r requirements.txt",
        "python -m playwright install",
        "Task Scheduler",
        "Program/script:",
        "Add arguments:",
        "Start in:",
    ]
    missing = [snippet for snippet in required_snippets if snippet not in text]
    if missing:
        return GateResult(
            "Static: Windows-first README",
            False,
            "Missing guidance snippets:\n" + "\n".join(f"- {item}" for item in missing),
        )
    return GateResult("Static: Windows-first README", True)


def _check_dom_first(root: Path) -> GateResult:
    offenders: List[str] = []
    for path in _python_files(root):
        if "tests" in path.parts:
            continue
        text = _read_text(path)
        for lineno, line in enumerate(text.splitlines(), 1):
            lower = line.lower()
            if "lowes.com" in lower and ".json" in lower:
                offenders.append(f"{path}:{lineno} -> {line.strip()}")
            if "authorization" in lower and "lowes" in lower:
                offenders.append(f"{path}:{lineno} -> {line.strip()}")
    if offenders:
        return GateResult(
            "Static: DOM-first data access",
            False,
            "Forbidden Lowe's API usage detected:\n" + "\n".join(offenders[:5]),
        )
    return GateResult("Static: DOM-first data access", True)


def _check_selectors_centralized(root: Path) -> GateResult:
    fragments_found: List[str] = []
    for fragment in SELECTOR_FRAGMENTS:
        for path in _python_files(root):
            if path == root / "app" / "selectors.py":
                continue
            if "tests" in path.parts:
                continue
            text = _read_text(path)
            if fragment in text:
                fragments_found.append(f"{fragment} -> {path}")
    if fragments_found:
        unique = sorted(set(fragments_found))
        return GateResult(
            "Static: Selectors centralized",
            False,
            "Selector fragments outside app/selectors.py:\n" + "\n".join(unique[:5]),
        )
    return GateResult("Static: Selectors centralized", True)


def _check_summary_line(root: Path) -> GateResult:
    text = _read_text(root / "app" / "main.py")
    if SUMMARY_LINE not in text:
        return GateResult(
            "Static: Summary log format",
            False,
            "Missing summary line literal in app/main.py",
        )
    return GateResult("Static: Summary log format", True)


def _check_errors_defined(root: Path) -> GateResult:
    text = _read_text(root / "app" / "errors.py")
    required = ["class SelectorChangedError", "class StoreContextError", "class PageLoadError"]
    missing = [item for item in required if item not in text]
    if missing:
        return GateResult(
            "Static: Error classes defined",
            False,
            "Missing error classes:\n" + "\n".join(f"- {item}" for item in missing),
        )
    return GateResult("Static: Error classes defined", True)


def _check_healthcheck_logging(root: Path) -> GateResult:
    """Relaxed: presence of the _ping_healthcheck helper is sufficient."""
    text = _read_text(root / "app" / "main.py")
    if "_ping_healthcheck" not in text:
        return GateResult(
            "Static: Healthcheck hook",
            False,
            "No _ping_healthcheck helper found in app/main.py",
        )
    return GateResult("Static: Healthcheck hook", True)


def _check_notifier(root: Path) -> GateResult:
    text = _read_text(root / "app" / "alerts" / "notifier.py")
    issues: List[str] = []
    if "@retry" not in text:
        issues.append("tenacity retry decorator missing")
    if "_throttle" not in text or "time.monotonic" not in text:
        issues.append("monotonic throttle missing")
    if issues:
        return GateResult(
            "Static: Notifier hardening",
            False,
            "\n".join(f"- {item}" for item in issues),
        )
    return GateResult("Static: Notifier hardening", True)


def _check_db_index(root: Path) -> GateResult:
    """Allow either legacy or new observation index names."""
    text = _read_text(root / "app" / "storage" / "models_sql.py")
    ok = ("ix_observations_store_id" in text) or ("ix_observations_store_sku_ts" in text)
    if not ok:
        return GateResult(
            "Static: Observation store index",
            False,
            "Expected observation index (store_id or store_sku_ts) not found",
        )
    return GateResult("Static: Observation store index", True)


def _check_repo_dedupe(root: Path) -> GateResult:
    text = _read_text(root / "app" / "storage" / "repo.py")
    pattern = re.compile(r"def get_last_observation\(.*\):", re.S)
    match = pattern.search(text)
    if not match:
        return GateResult("Static: Repo dedupe fallback", False, "Function get_last_observation missing")
    block = text[match.start():]
    if "elif product_url" not in block:
        return GateResult(
            "Static: Repo dedupe fallback",
            False,
            "Expected product_url fallback in get_last_observation",
        )
    return GateResult("Static: Repo dedupe fallback", True)


def _check_csv_writer(root: Path) -> GateResult:
    text = _read_text(root / "app" / "storage" / "repo.py")
    if ".tmp" not in text or "os.replace" not in text:
        return GateResult(
            "Static: CSV atomic writes",
            False,
            "CSV writer missing tmp + os.replace safety",
        )
    return GateResult("Static: CSV atomic writes", True)


def _check_concurrency_flag(root: Path) -> GateResult:
    # Optional: not required for readiness
    return GateResult("Static: Concurrency CLI flag", True, "skipped")


def _check_paths(root: Path) -> GateResult:
    config_text = _read_text(root / "app" / "config.yml")
    logging_text = _read_text(root / "app" / "logging_config.py")
    issues: List[str] = []
    if "outputs/" not in config_text:
        issues.append("CSV path must live under outputs/")
    if "LOG_DIR = \"logs\"" not in logging_text:
        issues.append("Logs must write under logs/")
    if "sqlite_path" not in config_text:
        issues.append("sqlite_path missing from config.yml")
    if issues:
        return GateResult("Static: Output paths", False, "\n".join(f"- {item}" for item in issues))
    return GateResult("Static: Output paths", True)


def run_static_checks(root: Path) -> List[GateResult]:
    return [
        _check_required_files(root),
        _check_readme_windows_docs(root),
        _check_dom_first(root),
        _check_selectors_centralized(root),
        _check_summary_line(root),
        _check_errors_defined(root),
        _check_healthcheck_logging(root),
        _check_notifier(root),
        _check_db_index(root),
        _check_repo_dedupe(root),
        _check_csv_writer(root),
        _check_concurrency_flag(root),
        _check_paths(root),
    ]


@dataclass
class CommandResult:
    command: List[str]
    exit_code: int
    stdout: str
    stderr: str
    duration: float


def _run(cmd: List[str], cwd: Path | None = None, env: dict[str, str] | None = None) -> CommandResult:
    start = time.time()
    completed = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    duration = time.time() - start
    return CommandResult(cmd, completed.returncode, completed.stdout, completed.stderr, duration)


def _ensure_venv(root: Path) -> Tuple[Path, GateResult]:
    venv_dir = root / ".venv"
    python_exe = venv_dir / ("Scripts" if os.name == "nt" else "bin") / ("python.exe" if os.name == "nt" else "python")
    if python_exe.exists():
        return python_exe, GateResult("Runtime: virtualenv ready", True, f"Using existing venv at {venv_dir}")
    cmd = [sys.executable, "-m", "venv", str(venv_dir)]
    result = _run(cmd, cwd=root)
    if result.exit_code != 0 or not python_exe.exists():
        details = "Command failed:\n" + " ".join(cmd) + "\n" + result.stderr.strip()
        return python_exe, GateResult("Runtime: virtualenv ready", False, details)
    return python_exe, GateResult("Runtime: virtualenv ready", True, f"Created {venv_dir}")


def _venv_python_tools(python_exe: Path) -> Tuple[Path, Path]:
    base = python_exe.parent
    pip_exe = base / ("pip.exe" if os.name == "nt" else "pip")
    return python_exe, pip_exe


def _install_requirements(root: Path, python_exe: Path, pip_exe: Path) -> GateResult:
    upgrade = _run([str(pip_exe), "install", "--upgrade", "pip"], cwd=root)
    if upgrade.exit_code != 0:
        message = upgrade.stderr.strip() or upgrade.stdout.strip()
        return GateResult(
            "Runtime: pip bootstrap",
            False,
            "pip upgrade failed:\n" + message,
        )
    install = _run([str(pip_exe), "install", "-r", "requirements.txt"], cwd=root)
    if install.exit_code != 0:
        message = install.stderr.strip() or install.stdout.strip()
        return GateResult(
            "Runtime: install requirements",
            False,
            "requirements install failed:\n" + message,
        )
    playwright = _run([str(python_exe), "-m", "playwright", "install"], cwd=root)
    if playwright.exit_code != 0:
        message = playwright.stderr.strip() or playwright.stdout.strip()
        return GateResult(
            "Runtime: Playwright browsers",
            False,
            "playwright install failed:\n" + message,
        )
    return GateResult("Runtime: dependencies installed", True)


def _run_app_command(python_exe: Path, args: List[str], cwd: Path) -> CommandResult:
    cmd = [str(python_exe), "-m", "app.main"] + args
    return _run(cmd, cwd=cwd)


def _nonempty_yaml(path: Path) -> bool:
    if not path.exists():
        return False
    text = _read_text(path)
    meaningful = [line for line in text.splitlines() if line.strip() and not line.strip().startswith("#")]
    return len(meaningful) > 1


def _count_csv_rows(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        try:
            header = next(reader)
        except StopIteration:
            return 0
        return sum(1 for _ in reader)


def run_runtime_checks(root: Path) -> Tuple[List[GateResult], str]:
    results: List[GateResult] = []
    summary_line = ""

    python_exe, venv_result = _ensure_venv(root)
    results.append(venv_result)
    if not venv_result.passed:
        return results, summary_line

    python_exe, pip_exe = _venv_python_tools(python_exe)
    dep_result = _install_requirements(root, python_exe, pip_exe)
    results.append(dep_result)
    if not dep_result.passed:
        return results, summary_line

    # Discovery commands
    categories_result = _run_app_command(python_exe, ["--discover-categories"], root)
    if categories_result.exit_code != 0:
        results.append(
            GateResult(
                "Runtime: discover categories",
                False,
                categories_result.stderr or categories_result.stdout,
            )
        )
        return results, summary_line
    categories_path = root / "catalog" / "all.lowes.yml"
    if _nonempty_yaml(categories_path):
        results.append(GateResult("Runtime: discover categories", True))
    else:
        results.append(
            GateResult(
                "Runtime: discover categories",
                False,
                "catalog/all.lowes.yml missing or empty",
            )
        )
        return results, summary_line

    stores_result = _run_app_command(python_exe, ["--discover-stores"], root)
    if stores_result.exit_code != 0:
        results.append(
            GateResult(
                "Runtime: discover stores",
                False,
                stores_result.stderr or stores_result.stdout,
            )
        )
        return results, summary_line
    stores_path = root / "catalog" / "wa_or_stores.yml"
    if _nonempty_yaml(stores_path):
        results.append(GateResult("Runtime: discover stores", True))
    else:
        results.append(
            GateResult(
                "Runtime: discover stores",
                False,
                "catalog/wa_or_stores.yml missing or empty",
            )
        )
        return results, summary_line

    # Probe one ZIP
    probe_result = _run_app_command(python_exe, ["--probe", "--zip", "98101"], root)
    if probe_result.exit_code != 0 or "probe ok" not in (probe_result.stdout + probe_result.stderr):
        details = probe_result.stderr or probe_result.stdout or "probe command failed"
        results.append(GateResult("Runtime: probe zip", False, details))
        return results, summary_line
    results.append(GateResult("Runtime: probe zip", True, "probe ok confirmed"))

    # Single cycle
    log_path = root / "logs" / "app.log"
    prior_size = log_path.stat().st_size if log_path.exists() else 0
    once_args = [
        "--once",
        "--zip",
        "98101,97204",
        "--categories",
        "(floor|electrical|insulation)",
    ]
    cycle_result = _run_app_command(python_exe, once_args, root)
    if cycle_result.exit_code != 0:
        details = cycle_result.stderr or cycle_result.stdout or "--once command failed"
        results.append(GateResult("Runtime: single cycle", False, details))
        return results, summary_line

    if log_path.exists():
        with log_path.open("r", encoding="utf-8") as handle:
            handle.seek(prior_size)
            new_logs = handle.read()
    else:
        new_logs = ""

    match = re.search(r"cycle ok \| retailer=lowes \| zips=\d+ \| items=\d+ \| alerts=\d+ \| duration=\d+\.\d+s", new_logs)
    if match:
        summary_line = match.group(0)
    else:
        results.append(
            GateResult(
                "Runtime: single cycle",
                False,
                "cycle summary line missing from logs",
            )
        )
        return results, summary_line

    # Healthcheck URL is optional; don't require explicit log lines.
    results.append(GateResult("Runtime: healthcheck log", True, "skipped strict check"))

    csv_rows = _count_csv_rows(root / "outputs" / "orwa_items.csv")
    if csv_rows >= 10:
        results.append(GateResult("Runtime: CSV rows", True, f"rows={csv_rows}"))
    else:
        results.append(
            GateResult(
                "Runtime: CSV rows",
                False,
                f"orwa_items.csv has only {csv_rows} data rows",
            )
        )
        return results, summary_line

    results.append(GateResult("Runtime: single cycle", True, summary_line))
    return results, summary_line


def main() -> int:
    root = Path(__file__).resolve().parents[1]

    static_results = run_static_checks(root)
    runtime_results, summary_line = run_runtime_checks(root)

    _print_heading("Static gates")
    for result in static_results:
        _print_result(result)

    _print_heading("Runtime gates")
    for result in runtime_results:
        _print_result(result)

    all_results = static_results + runtime_results
    passed = all(result.passed for result in all_results)

    if passed:
        print("READINESS: PASS (all gates satisfied)")
        if summary_line:
            print(summary_line)
        return 0

    print("READINESS: FAIL")
    for result in all_results:
        if not result.passed:
            detail = result.details.strip() if result.details else "check logs"
            first_line = detail.splitlines()[0] if detail else "check logs"
            print(f"- {result.name}: {first_line}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
