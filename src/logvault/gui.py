from __future__ import annotations

import os
import queue
import threading
import webbrowser
from pathlib import Path
from typing import Any

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, scrolledtext, ttk
except ImportError:  # pragma: no cover - depends on OS Python packages.
    tk = None
    ttk = None
    filedialog = None
    messagebox = None
    scrolledtext = None

from .character_export import CharacterReportsOptions, CharacterReportsResult, download_character_reports
from .difficulty import DIFFICULTY_CHOICES, parse_difficulty
from .download import DownloadOptions, DownloadResult, download_report
from .env import load_env_file
from .errors import LogVaultError


class LogVaultApp:
    def __init__(self, root: Any) -> None:
        self.root = root
        self.root.title("LogVault")
        self.root.geometry("960x820")
        self.root.minsize(820, 720)

        self.messages: queue.Queue[tuple[str, Any]] = queue.Queue()
        self.worker: threading.Thread | None = None
        self.last_result: DownloadResult | CharacterReportsResult | None = None

        load_env_file(Path(".env"))
        self.mode_var = tk.StringVar(value="report")
        self.report_var = tk.StringVar()
        self.fight_var = tk.StringVar(value="last")
        self.include_trash_var = tk.BooleanVar(value=False)
        self.character_var = tk.StringVar()
        self.server_var = tk.StringVar()
        self.region_var = tk.StringVar(value="eu")
        self.difficulty_var = tk.StringVar(value="All")
        self.season_start_var = tk.StringVar()
        self.season_end_var = tk.StringVar()
        self.max_reports_var = tk.StringVar(value="0")
        self.client_id_var = tk.StringVar(value=os.getenv("WCL_CLIENT_ID", ""))
        self.client_secret_var = tk.StringVar(value=os.getenv("WCL_CLIENT_SECRET", ""))
        self.save_env_var = tk.BooleanVar(value=False)
        self.tables_var = tk.StringVar(value="standard")
        self.events_var = tk.StringVar(value="standard")
        self.filter_var = tk.StringVar()
        self.out_var = tk.StringVar(value="exports")
        self.zip_var = tk.BooleanVar(value=True)
        self.allow_unlisted_var = tk.BooleanVar(value=True)
        self.limit_var = tk.StringVar(value="10000")
        self.max_pages_var = tk.StringVar()

        self._build()
        self._poll_messages()

    def _build(self) -> None:
        root_frame = ttk.Frame(self.root, padding=12)
        root_frame.grid(row=0, column=0, sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        root_frame.columnconfigure(0, weight=1)
        root_frame.rowconfigure(5, weight=1)

        title = ttk.Label(root_frame, text="LogVault", font=("TkDefaultFont", 18, "bold"))
        title.grid(row=0, column=0, sticky="w")

        source = ttk.LabelFrame(root_frame, text="Report")
        source.grid(row=1, column=0, sticky="ew", pady=(12, 8))
        source.columnconfigure(1, weight=1)
        source.columnconfigure(3, weight=1)
        ttk.Radiobutton(source, text="Single report", variable=self.mode_var, value="report").grid(
            row=0, column=0, sticky="w", padx=(8, 0), pady=6
        )
        ttk.Radiobutton(source, text="Character reports", variable=self.mode_var, value="character").grid(
            row=0, column=1, sticky="w", padx=6, pady=6
        )
        self._label(source, "URL or code", 1, 0)
        ttk.Entry(source, textvariable=self.report_var).grid(row=1, column=1, columnspan=3, sticky="ew", padx=6, pady=6)
        self._label(source, "Fight", 2, 0)
        fight = ttk.Combobox(source, textvariable=self.fight_var, values=("", "last", "boss", "all"), width=18)
        fight.grid(row=2, column=1, sticky="w", padx=6, pady=6)
        ttk.Checkbutton(source, text="Include trash by default", variable=self.include_trash_var).grid(
            row=2, column=2, sticky="w", padx=6, pady=6
        )
        self._label(source, "Character", 3, 0)
        ttk.Entry(source, textvariable=self.character_var).grid(row=3, column=1, sticky="ew", padx=6, pady=6)
        self._label(source, "Realm slug", 3, 2)
        ttk.Entry(source, textvariable=self.server_var).grid(row=3, column=3, sticky="ew", padx=6, pady=6)
        self._label(source, "Region", 4, 0)
        ttk.Combobox(source, textvariable=self.region_var, values=("eu", "us", "kr", "tw", "cn"), width=10).grid(
            row=4, column=1, sticky="w", padx=6, pady=6
        )
        self._label(source, "Difficulty", 4, 2)
        ttk.Combobox(source, textvariable=self.difficulty_var, values=DIFFICULTY_CHOICES, width=14, state="readonly").grid(
            row=4, column=3, sticky="w", padx=6, pady=6
        )
        self._label(source, "Season start", 5, 0)
        ttk.Entry(source, textvariable=self.season_start_var, width=16).grid(row=5, column=1, sticky="w", padx=6, pady=6)
        self._label(source, "Season end", 5, 2)
        ttk.Entry(source, textvariable=self.season_end_var, width=16).grid(row=5, column=3, sticky="w", padx=6, pady=6)
        self._label(source, "Max reports", 6, 0)
        ttk.Entry(source, textvariable=self.max_reports_var, width=12).grid(row=6, column=1, sticky="w", padx=6, pady=6)
        ttk.Label(source, text="Dates: YYYY-MM-DD. Max reports 0 means no local cap.").grid(
            row=6, column=2, columnspan=2, sticky="w", padx=6, pady=6
        )

        credentials = ttk.LabelFrame(root_frame, text="Warcraft Logs OAuth client")
        credentials.grid(row=2, column=0, sticky="ew", pady=8)
        credentials.columnconfigure(1, weight=1)
        credentials.columnconfigure(3, weight=1)
        self._label(credentials, "Client ID", 0, 0)
        ttk.Entry(credentials, textvariable=self.client_id_var).grid(row=0, column=1, sticky="ew", padx=6, pady=6)
        self._label(credentials, "Client secret", 0, 2)
        ttk.Entry(credentials, textvariable=self.client_secret_var, show="*").grid(
            row=0, column=3, sticky="ew", padx=6, pady=6
        )
        ttk.Checkbutton(credentials, text="Save credentials to local .env", variable=self.save_env_var).grid(
            row=1, column=1, columnspan=3, sticky="w", padx=6, pady=(2, 8)
        )

        export = ttk.LabelFrame(root_frame, text="Export")
        export.grid(row=3, column=0, sticky="ew", pady=8)
        export.columnconfigure(1, weight=1)
        export.columnconfigure(3, weight=1)
        self._label(export, "Tables", 0, 0)
        ttk.Combobox(export, textvariable=self.tables_var, values=("standard", "none"), width=24).grid(
            row=0, column=1, sticky="ew", padx=6, pady=6
        )
        self._label(export, "Events", 0, 2)
        ttk.Combobox(export, textvariable=self.events_var, values=("standard", "none"), width=24).grid(
            row=0, column=3, sticky="ew", padx=6, pady=6
        )
        self._label(export, "Filter", 1, 0)
        ttk.Entry(export, textvariable=self.filter_var).grid(row=1, column=1, columnspan=3, sticky="ew", padx=6, pady=6)
        self._label(export, "Output", 2, 0)
        ttk.Entry(export, textvariable=self.out_var).grid(row=2, column=1, columnspan=2, sticky="ew", padx=6, pady=6)
        ttk.Button(export, text="Browse", command=self._browse_output).grid(row=2, column=3, sticky="e", padx=6, pady=6)
        ttk.Checkbutton(export, text="Create zip archive", variable=self.zip_var).grid(
            row=3, column=1, sticky="w", padx=6, pady=6
        )
        ttk.Checkbutton(export, text="Allow unlisted reports", variable=self.allow_unlisted_var).grid(
            row=3, column=2, sticky="w", padx=6, pady=6
        )
        self._label(export, "Events/page", 4, 0)
        ttk.Entry(export, textvariable=self.limit_var, width=14).grid(row=4, column=1, sticky="w", padx=6, pady=6)
        self._label(export, "Max pages", 4, 2)
        ttk.Entry(export, textvariable=self.max_pages_var, width=14).grid(row=4, column=3, sticky="w", padx=6, pady=6)

        actions = ttk.Frame(root_frame)
        actions.grid(row=4, column=0, sticky="ew", pady=(8, 6))
        actions.columnconfigure(2, weight=1)
        self.download_button = ttk.Button(actions, text="Download", command=self._start_download)
        self.download_button.grid(row=0, column=0, sticky="w")
        self.open_button = ttk.Button(actions, text="Open output folder", command=self._open_output, state="disabled")
        self.open_button.grid(row=0, column=1, sticky="w", padx=(8, 0))
        self.progress = ttk.Progressbar(actions, mode="indeterminate")
        self.progress.grid(row=0, column=2, sticky="ew", padx=(12, 0))

        log_frame = ttk.LabelFrame(root_frame, text="Progress")
        log_frame.grid(row=5, column=0, sticky="nsew", pady=(8, 0))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.log = scrolledtext.ScrolledText(log_frame, height=14, wrap="word", state="disabled")
        self.log.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)

    def _label(self, parent: Any, text: str, row: int, column: int) -> None:
        ttk.Label(parent, text=text).grid(row=row, column=column, sticky="w", padx=(8, 0), pady=6)

    def _browse_output(self) -> None:
        selected = filedialog.askdirectory(initialdir=self.out_var.get() or ".")
        if selected:
            self.out_var.set(selected)

    def _start_download(self) -> None:
        if self.worker and self.worker.is_alive():
            return
        try:
            options = self._collect_options()
        except ValueError as exc:
            messagebox.showerror("Invalid input", str(exc))
            return

        if self.save_env_var.get():
            self._save_env(options)

        self.last_result = None
        self.open_button.configure(state="disabled")
        self.download_button.configure(state="disabled")
        self.progress.start(12)
        self._clear_log()
        self._append_log("Starting download...")

        self.worker = threading.Thread(target=self._download_worker, args=(options,), daemon=True)
        self.worker.start()

    def _collect_options(self) -> DownloadOptions | CharacterReportsOptions:
        report = self.report_var.get().strip()
        difficulty_id = parse_difficulty(self.difficulty_var.get())
        if self.mode_var.get() == "report" and not report:
            raise ValueError("Report URL or code is required.")

        limit = parse_positive_int(self.limit_var.get().strip(), "Events/page")
        max_pages_text = self.max_pages_var.get().strip()
        max_pages = parse_positive_int(max_pages_text, "Max pages") if max_pages_text else None
        max_reports_text = self.max_reports_var.get().strip()
        max_reports = parse_non_negative_int(max_reports_text, "Max reports") if max_reports_text else 0

        if self.mode_var.get() == "character":
            character = self.character_var.get().strip()
            server = self.server_var.get().strip()
            if not character:
                raise ValueError("Character name is required in Character reports mode.")
            if not server:
                raise ValueError("Realm slug is required in Character reports mode.")
            return CharacterReportsOptions(
                character_name=character,
                server_slug=server,
                server_region=self.region_var.get().strip() or "eu",
                difficulty_id=difficulty_id,
                season_start=self.season_start_var.get().strip() or None,
                season_end=self.season_end_var.get().strip() or None,
                max_reports=max_reports or None,
                fight=self.fight_var.get().strip() or "boss",
                include_trash=self.include_trash_var.get(),
                tables=self.tables_var.get().strip() or "standard",
                events=self.events_var.get().strip() or "standard",
                filter_expression=self.filter_var.get().strip() or None,
                out=Path(self.out_var.get().strip() or "exports"),
                make_zip=self.zip_var.get(),
                limit=limit,
                max_pages=max_pages,
                allow_unlisted=self.allow_unlisted_var.get(),
                client_id=self.client_id_var.get().strip() or None,
                client_secret=self.client_secret_var.get().strip() or None,
            )

        return DownloadOptions(
            report=report,
            fight=self.fight_var.get().strip() or None,
            include_trash=self.include_trash_var.get(),
            tables=self.tables_var.get().strip() or "standard",
            events=self.events_var.get().strip() or "standard",
            filter_expression=self.filter_var.get().strip() or None,
            out=Path(self.out_var.get().strip() or "exports"),
            make_zip=self.zip_var.get(),
            limit=limit,
            max_pages=max_pages,
            allow_unlisted=self.allow_unlisted_var.get(),
            client_id=self.client_id_var.get().strip() or None,
            client_secret=self.client_secret_var.get().strip() or None,
            difficulty_id=difficulty_id,
        )

    def _save_env(self, options: DownloadOptions | CharacterReportsOptions) -> None:
        lines = [
            "# Warcraft Logs OAuth client credentials.",
            f"WCL_CLIENT_ID={options.client_id or ''}",
            f"WCL_CLIENT_SECRET={options.client_secret or ''}",
        ]
        Path(".env").write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _download_worker(self, options: DownloadOptions | CharacterReportsOptions) -> None:
        try:
            if isinstance(options, CharacterReportsOptions):
                result = download_character_reports(options, progress=lambda message: self.messages.put(("log", message)))
            else:
                result = download_report(options, progress=lambda message: self.messages.put(("log", message)))
        except (LogVaultError, ValueError) as exc:
            self.messages.put(("error", str(exc)))
        except Exception as exc:  # pragma: no cover - defensive GUI boundary.
            self.messages.put(("error", f"Unexpected error: {exc}"))
        else:
            self.messages.put(("done", result))

    def _poll_messages(self) -> None:
        while True:
            try:
                kind, payload = self.messages.get_nowait()
            except queue.Empty:
                break
            if kind == "log":
                self._append_log(str(payload))
            elif kind == "error":
                self._finish_running()
                self._append_log(f"Error: {payload}")
                messagebox.showerror("Download failed", str(payload))
            elif kind == "done":
                self._finish_running()
                self.last_result = payload
                self.open_button.configure(state="normal")
                self._append_log("Finished.")
                messagebox.showinfo("Download complete", f"Saved to:\n{payload.out_dir}")
        self.root.after(100, self._poll_messages)

    def _finish_running(self) -> None:
        self.progress.stop()
        self.download_button.configure(state="normal")

    def _clear_log(self) -> None:
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

    def _append_log(self, message: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", message.rstrip() + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _open_output(self) -> None:
        if not self.last_result:
            return
        webbrowser.open(self.last_result.out_dir.resolve().as_uri())


def parse_positive_int(value: str, label: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError(f"{label} must be an integer.") from exc
    if parsed <= 0:
        raise ValueError(f"{label} must be greater than zero.")
    return parsed


def parse_non_negative_int(value: str, label: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError(f"{label} must be an integer.") from exc
    if parsed < 0:
        raise ValueError(f"{label} must be zero or greater.")
    return parsed


def main() -> int:
    if tk is None or ttk is None:
        print("Tkinter is not available. On Linux install python3-tk, then run logvault-gui again.")
        return 1
    root = tk.Tk()
    LogVaultApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
