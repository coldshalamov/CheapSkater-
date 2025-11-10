from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import webbrowser
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests
import tkinter as tk
from tkinter import ttk

LOG_DIR = Path("logs")
LOG_FILE = LOG_DIR / "launcher.log"
SCRAPER_LOG = LOG_DIR / "scraper.log"
DASHBOARD_LOG = LOG_DIR / "dashboard.log"
DASHBOARD_URL = "http://localhost:8000"


@dataclass
class ProcessHandle:
    process: subprocess.Popen
    log_handle: Optional[object]

    def terminate(self) -> None:
        if self.process.poll() is None:
            try:
                self.process.terminate()
                self.process.wait(timeout=5)
            except Exception:
                try:
                    self.process.kill()
                except Exception:
                    pass
        if self.log_handle and not self.log_handle.closed:
            try:
                self.log_handle.close()
            except Exception:
                pass


class LauncherGUI:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("CheapSkater Launcher")
        self.root.geometry("520x240")

        LOG_DIR.mkdir(exist_ok=True)
        LOG_FILE.touch(exist_ok=True)

        self.python_cmd = self._detect_python()
        self.scraper_handle: Optional[ProcessHandle] = None
        self.dashboard_handle: Optional[ProcessHandle] = None

        self.status_var = tk.StringVar(value="Idle")
        self.summary_var = tk.StringVar(value="No scrape data detected yet.")

        self._build_layout()
        self._log("Launcher GUI started")
        self._ensure_dashboard()

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self._update_status_periodically()

    def _detect_python(self) -> str:
        venv = Path(".venv")
        if os.name == "nt":
            candidate = venv / "Scripts" / "python.exe"
        else:
            candidate = venv / "bin" / "python"
        if candidate.exists():
            return str(candidate)
        return sys.executable

    def _build_layout(self) -> None:
        padding = {"padx": 10, "pady": 10}

        status_frame = ttk.Frame(self.root)
        status_frame.pack(fill=tk.X, **padding)
        ttk.Label(status_frame, text="Status:").pack(side=tk.LEFT)
        ttk.Label(status_frame, textvariable=self.status_var).pack(side=tk.LEFT)

        summary_frame = ttk.Frame(self.root)
        summary_frame.pack(fill=tk.X, **padding)
        ttk.Label(summary_frame, text="Last scrape:").pack(side=tk.LEFT)
        ttk.Label(summary_frame, textvariable=self.summary_var, wraplength=460).pack(
            side=tk.LEFT
        )

        button_frame = ttk.Frame(self.root)
        button_frame.pack(fill=tk.X, **padding)

        ttk.Button(button_frame, text="Run Full Scrape", command=self.run_scrape).pack(
            side=tk.LEFT, padx=5
        )
        ttk.Button(button_frame, text="Open Dashboard", command=self.open_dashboard).pack(
            side=tk.LEFT, padx=5
        )
        ttk.Button(button_frame, text="View Logs", command=self.view_logs).pack(
            side=tk.LEFT, padx=5
        )
        ttk.Button(button_frame, text="Stop", command=self.stop_processes).pack(
            side=tk.LEFT, padx=5
        )

    def _open_log_file(self, path: Path) -> object:
        handle = path.open("a", encoding="utf-8")
        return handle

    def _log(self, message: str) -> None:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with LOG_FILE.open("a", encoding="utf-8") as handle:
            handle.write(f"[{timestamp}] {message}\n")

    def _spawn_process(self, log_path: Path, *args: str) -> ProcessHandle:
        self._log(f"Starting process: {' '.join(args)}")
        log_handle = self._open_log_file(log_path)
        process = subprocess.Popen(
            [self.python_cmd, *args],
            stdout=log_handle,
            stderr=subprocess.STDOUT,
        )
        return ProcessHandle(process=process, log_handle=log_handle)

    def _ensure_dashboard(self) -> None:
        if self.dashboard_handle and self.dashboard_handle.process.poll() is None:
            return
        self.dashboard_handle = self._spawn_process(
            DASHBOARD_LOG,
            "-m",
            "uvicorn",
            "app.dashboard:app",
            "--host",
            "0.0.0.0",
            "--port",
            "8000",
        )
        self._log("Dashboard started")

    def run_scrape(self) -> None:
        if self.scraper_handle and self.scraper_handle.process.poll() is None:
            return
        self.scraper_handle = self._spawn_process(
            SCRAPER_LOG,
            "-m",
            "app.main",
            "--once",
        )
        self.status_var.set("Scraper running…")
        self._log("Scraper run triggered")

    def open_dashboard(self) -> None:
        self._ensure_dashboard()
        self._log("Opening dashboard in browser")
        threading.Thread(target=webbrowser.open, args=(DASHBOARD_URL,), daemon=True).start()

    def view_logs(self) -> None:
        self._log("Opening launcher log file")
        webbrowser.open(LOG_FILE.resolve().as_uri())

    def stop_processes(self) -> None:
        if self.scraper_handle:
            self.scraper_handle.terminate()
            self.scraper_handle = None
            self._log("Scraper process stopped")
        if self.dashboard_handle:
            self.dashboard_handle.terminate()
            self.dashboard_handle = None
            self._log("Dashboard process stopped")
        self.status_var.set("Stopped")

    def _fetch_dashboard_stats(self) -> Optional[str]:
        try:
            response = requests.get(f"{DASHBOARD_URL}/api/stats", timeout=2)
            if response.ok:
                data = response.json()
                total = data.get("total_items", 0)
                quarantine = data.get("quarantine_count", 0)
                last_scrape = data.get("last_scrape")
                return (
                    f"Items: {total} | Quarantine: {quarantine} | Last scrape: "
                    f"{last_scrape or 'unknown'}"
                )
        except requests.RequestException:
            return None
        except json.JSONDecodeError:
            return None
        return None

    def _file_summary(self) -> str:
        csv_path = Path("outputs/orwa_items.csv")
        sqlite_path = Path("orwa_lowes.sqlite")
        parts = []
        if csv_path.exists():
            ts = datetime.fromtimestamp(csv_path.stat().st_mtime, tz=timezone.utc)
            parts.append(f"CSV updated {ts.isoformat()}")
        else:
            parts.append("CSV missing")
        if sqlite_path.exists():
            ts = datetime.fromtimestamp(sqlite_path.stat().st_mtime, tz=timezone.utc)
            parts.append(f"SQLite updated {ts.isoformat()}")
        else:
            parts.append("SQLite missing")
        return " | ".join(parts)

    def _update_status_periodically(self) -> None:
        status_parts = []
        if self.scraper_handle:
            if self.scraper_handle.process.poll() is None:
                status_parts.append("Scraper: running")
            else:
                status_parts.append(
                    f"Scraper finished (code {self.scraper_handle.process.returncode})"
                )
                if (
                    self.scraper_handle.log_handle
                    and not self.scraper_handle.log_handle.closed
                ):
                    try:
                        self.scraper_handle.log_handle.close()
                    except Exception:
                        pass
        else:
            status_parts.append("Scraper: idle")

        if self.dashboard_handle and self.dashboard_handle.process.poll() is None:
            status_parts.append("Dashboard: running")
        else:
            status_parts.append("Dashboard: stopped")
            if (
                self.dashboard_handle
                and self.dashboard_handle.log_handle
                and not self.dashboard_handle.log_handle.closed
            ):
                try:
                    self.dashboard_handle.log_handle.close()
                except Exception:
                    pass

        self.status_var.set(" | ".join(status_parts))

        summary = self._fetch_dashboard_stats()
        if summary:
            self.summary_var.set(summary)
        else:
            self.summary_var.set(self._file_summary())

        self.root.after(5000, self._update_status_periodically)

    def on_close(self) -> None:
        self.stop_processes()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    gui = LauncherGUI()
    gui.run()


if __name__ == "__main__":
    main()
