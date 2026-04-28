from __future__ import annotations

import os
import queue
import sys
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
from .difficulty import DIFFICULTY_SCOPE_CHOICES, parse_difficulty_scope
from .download import DownloadOptions, DownloadResult, download_report
from .env import load_env_file
from .errors import DownloadCancelled, LogVaultError


class LogVaultApp:
    def __init__(self, root: Any) -> None:
        self.root = root
        self.root.title("LogVault - Warcraft Logs Exporter")
        self.icon_image: Any | None = None
        self._set_window_icon()
        self.root.geometry("980x720")
        self.root.minsize(760, 520)

        self.messages: queue.Queue[tuple[str, Any]] = queue.Queue()
        self.worker: threading.Thread | None = None
        self.cancel_event = threading.Event()
        self.last_result: DownloadResult | CharacterReportsResult | None = None

        self.env_path = default_env_path()
        load_env_file(Path(".env"))
        if self.env_path != Path(".env"):
            load_env_file(self.env_path)
        self.mode_var = tk.StringVar(value="report")
        self.report_var = tk.StringVar()
        self.fight_var = tk.StringVar(value="last")
        self.include_trash_var = tk.BooleanVar(value=False)
        self.character_var = tk.StringVar()
        self.server_var = tk.StringVar()
        self.region_var = tk.StringVar(value="eu")
        self.difficulty_var = tk.StringVar(value="All")
        self.encounter_var = tk.StringVar()
        self.season_start_var = tk.StringVar()
        self.season_end_var = tk.StringVar()
        self.max_reports_var = tk.StringVar(value="0")
        self.client_id_var = tk.StringVar(value=os.getenv("WCL_CLIENT_ID", ""))
        self.client_secret_var = tk.StringVar(value=os.getenv("WCL_CLIENT_SECRET", ""))
        self.save_env_var = tk.BooleanVar(value=True)
        self.tables_var = tk.StringVar(value="standard")
        self.events_var = tk.StringVar(value="compact")
        self.filter_var = tk.StringVar()
        self.out_var = tk.StringVar(value="exports")
        self.zip_var = tk.BooleanVar(value=True)
        self.archive_only_var = tk.BooleanVar(value=True)
        self.allow_unlisted_var = tk.BooleanVar(value=True)
        self.limit_var = tk.StringVar(value="10000")
        self.max_pages_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Ready.")

        self._configure_style()
        self._build()
        self._poll_messages()

    def _configure_style(self) -> None:
        self.colors = {
            "bg": "#111418",
            "panel": "#1a2027",
            "panel_alt": "#202832",
            "text": "#ecf0f3",
            "muted": "#aeb8c2",
            "gold": "#d8a640",
            "gold_light": "#f1d179",
            "blue": "#6aa9e8",
            "line": "#384452",
        }
        self.root.configure(bg=self.colors["bg"])
        self.root.option_add("*Background", self.colors["panel"])
        self.root.option_add("*Foreground", self.colors["text"])
        self.root.option_add("*selectBackground", self.colors["gold"])
        self.root.option_add("*selectForeground", "#17120a")
        self.root.option_add("*insertBackground", self.colors["text"])
        self.root.option_add("*Listbox.background", "#0f1318")
        self.root.option_add("*Listbox.foreground", self.colors["text"])
        self.root.option_add("*Listbox.selectBackground", self.colors["gold"])
        self.root.option_add("*Listbox.selectForeground", "#17120a")
        self.root.option_add("*TCombobox*Listbox.background", "#0f1318")
        self.root.option_add("*TCombobox*Listbox.foreground", self.colors["text"])
        self.root.option_add("*TCombobox*Listbox.selectBackground", self.colors["gold"])
        self.root.option_add("*TCombobox*Listbox.selectForeground", "#17120a")
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure("TFrame", background=self.colors["bg"])
        style.configure("Panel.TFrame", background=self.colors["panel"])
        style.configure("TLabel", background=self.colors["panel"], foreground=self.colors["text"])
        style.configure("Root.TLabel", background=self.colors["bg"], foreground=self.colors["muted"])
        style.configure("Muted.TLabel", background=self.colors["panel"], foreground=self.colors["muted"])
        style.configure(
            "TLabelframe",
            background=self.colors["panel"],
            foreground=self.colors["gold_light"],
            bordercolor=self.colors["line"],
            relief="solid",
        )
        style.configure(
            "TLabelframe.Label",
            background=self.colors["bg"],
            foreground=self.colors["gold_light"],
            font=("TkDefaultFont", 11, "bold"),
        )
        style.configure(
            "TEntry",
            background="#0f1318",
            fieldbackground="#0f1318",
            foreground=self.colors["text"],
            bordercolor=self.colors["line"],
            lightcolor=self.colors["line"],
            darkcolor="#0a0d11",
            insertcolor=self.colors["text"],
            padding=(6, 4),
        )
        style.map(
            "TEntry",
            fieldbackground=[
                ("disabled", "#151a20"),
                ("readonly", "#0f1318"),
                ("focus", "#0f1318"),
                ("active", "#0f1318"),
            ],
            foreground=[("disabled", "#6f7984"), ("readonly", self.colors["text"])],
            bordercolor=[("focus", self.colors["gold"]), ("active", self.colors["blue"])],
        )
        style.configure(
            "TCombobox",
            background="#0f1318",
            fieldbackground="#0f1318",
            foreground=self.colors["text"],
            bordercolor=self.colors["line"],
            arrowcolor=self.colors["gold"],
            lightcolor=self.colors["line"],
            darkcolor="#0a0d11",
            selectbackground=self.colors["gold"],
            selectforeground="#17120a",
            padding=(6, 4),
        )
        style.map(
            "TCombobox",
            background=[
                ("pressed", "#202832"),
                ("active", "#202832"),
                ("readonly", "#0f1318"),
                ("disabled", "#151a20"),
            ],
            fieldbackground=[
                ("pressed", "#0f1318"),
                ("active", "#0f1318"),
                ("readonly", "#0f1318"),
                ("focus", "#0f1318"),
                ("disabled", "#151a20"),
            ],
            foreground=[("disabled", "#6f7984"), ("readonly", self.colors["text"])],
            arrowcolor=[
                ("pressed", self.colors["gold_light"]),
                ("active", self.colors["gold_light"]),
                ("disabled", "#6f7984"),
            ],
            bordercolor=[("focus", self.colors["gold"]), ("active", self.colors["blue"])],
        )
        style.configure(
            "TCheckbutton",
            background=self.colors["panel"],
            foreground=self.colors["text"],
            focuscolor=self.colors["panel"],
            indicatorbackground="#0f1318",
            indicatorforeground=self.colors["gold"],
        )
        style.map(
            "TCheckbutton",
            background=[("active", self.colors["panel"]), ("pressed", self.colors["panel_alt"])],
            foreground=[("disabled", "#6f7984"), ("active", self.colors["gold_light"])],
            indicatorbackground=[
                ("selected", self.colors["gold"]),
                ("pressed", self.colors["panel_alt"]),
                ("active", "#202832"),
            ],
        )
        style.configure(
            "TRadiobutton",
            background=self.colors["panel"],
            foreground=self.colors["text"],
            focuscolor=self.colors["panel"],
            indicatorbackground="#0f1318",
            indicatorforeground=self.colors["gold"],
        )
        style.map(
            "TRadiobutton",
            background=[("active", self.colors["panel"]), ("pressed", self.colors["panel_alt"])],
            foreground=[("disabled", "#6f7984"), ("active", self.colors["gold_light"])],
            indicatorbackground=[
                ("selected", self.colors["gold"]),
                ("pressed", self.colors["panel_alt"]),
                ("active", "#202832"),
            ],
        )
        style.configure(
            "TButton",
            background=self.colors["panel_alt"],
            foreground=self.colors["text"],
            bordercolor=self.colors["line"],
            lightcolor=self.colors["line"],
            darkcolor="#0a0d11",
            focuscolor=self.colors["panel_alt"],
            padding=(12, 7),
        )
        style.map(
            "TButton",
            background=[("pressed", "#141a21"), ("active", "#263140"), ("disabled", "#151a20")],
            foreground=[("disabled", "#6f7984"), ("active", self.colors["text"])],
            bordercolor=[("focus", self.colors["gold"]), ("active", self.colors["blue"])],
        )
        style.configure(
            "Accent.TButton",
            background=self.colors["gold"],
            foreground="#17120a",
            font=("TkDefaultFont", 10, "bold"),
            borderwidth=0,
            padding=(14, 8),
        )
        style.map(
            "Accent.TButton",
            background=[
                ("pressed", "#b47a24"),
                ("active", self.colors["gold_light"]),
                ("disabled", "#5f5131"),
            ],
            foreground=[("disabled", "#a9a9a9")],
            bordercolor=[("focus", self.colors["gold_light"]), ("active", self.colors["gold_light"])],
        )
        style.configure(
            "Horizontal.TProgressbar",
            background=self.colors["gold"],
            troughcolor="#0f1318",
            bordercolor=self.colors["line"],
            lightcolor=self.colors["gold_light"],
            darkcolor="#8a5417",
        )
        style.configure(
            "Vertical.TScrollbar",
            background=self.colors["panel_alt"],
            troughcolor="#0f1318",
            bordercolor=self.colors["line"],
            arrowcolor=self.colors["gold"],
        )
        style.map(
            "Vertical.TScrollbar",
            background=[("pressed", "#141a21"), ("active", "#263140")],
            arrowcolor=[("pressed", self.colors["gold_light"]), ("active", self.colors["gold_light"])],
        )
        style.configure("ComboboxPopdownFrame", background="#0f1318", bordercolor=self.colors["line"])

    def _set_window_icon(self) -> None:
        try:
            png_path = asset_path("logvault.png")
            if png_path.exists():
                self.icon_image = tk.PhotoImage(file=str(png_path))
                self.root.iconphoto(True, self.icon_image)
            ico_path = asset_path("logvault.ico")
            if os.name == "nt" and ico_path.exists():
                self.root.iconbitmap(default=str(ico_path))
        except (OSError, tk.TclError):
            self.icon_image = None

    def _build(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        shell = ttk.Frame(self.root)
        shell.grid(row=0, column=0, sticky="nsew")
        shell.columnconfigure(0, weight=1)
        shell.rowconfigure(0, weight=1)

        self.scroll_canvas = tk.Canvas(shell, bg=self.colors["bg"], bd=0, highlightthickness=0)
        scrollbar = ttk.Scrollbar(shell, orient="vertical", command=self.scroll_canvas.yview)
        self.scroll_canvas.configure(yscrollcommand=scrollbar.set)
        self.scroll_canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        root_frame = ttk.Frame(self.scroll_canvas, padding=14)
        self.scroll_window = self.scroll_canvas.create_window((0, 0), window=root_frame, anchor="nw")
        root_frame.bind("<Configure>", self._update_scroll_region)
        self.scroll_canvas.bind("<Configure>", self._resize_scroll_window)
        self.root.bind_all("<MouseWheel>", self._on_mousewheel)
        self.root.bind_all("<Button-4>", self._on_mousewheel)
        self.root.bind_all("<Button-5>", self._on_mousewheel)

        root_frame.columnconfigure(0, weight=1)
        root_frame.rowconfigure(5, weight=1)

        self._wordmark(root_frame).grid(row=0, column=0, sticky="ew", pady=(0, 12))

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
        ttk.Combobox(source, textvariable=self.difficulty_var, values=DIFFICULTY_SCOPE_CHOICES, width=18).grid(
            row=4, column=3, sticky="w", padx=6, pady=6
        )
        self._label(source, "Encounter", 5, 0)
        ttk.Entry(source, textvariable=self.encounter_var).grid(row=5, column=1, columnspan=3, sticky="ew", padx=6, pady=6)
        self._label(source, "Season start", 6, 0)
        ttk.Entry(source, textvariable=self.season_start_var, width=16).grid(row=6, column=1, sticky="w", padx=6, pady=6)
        self._label(source, "Season end", 6, 2)
        ttk.Entry(source, textvariable=self.season_end_var, width=16).grid(row=6, column=3, sticky="w", padx=6, pady=6)
        self._label(source, "Max reports", 7, 0)
        ttk.Entry(source, textvariable=self.max_reports_var, width=12).grid(row=7, column=1, sticky="w", padx=6, pady=6)
        ttk.Label(source, text="Dates: YYYY-MM-DD. Max reports 0 means no local cap.").grid(
            row=7, column=2, columnspan=2, sticky="w", padx=6, pady=6
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
        ttk.Checkbutton(credentials, text="Save credentials to app .env", variable=self.save_env_var).grid(
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
        ttk.Combobox(export, textvariable=self.events_var, values=("compact", "essential", "full", "none"), width=24).grid(
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
        ttk.Checkbutton(export, text="Keep only archive", variable=self.archive_only_var).grid(
            row=3, column=2, sticky="w", padx=6, pady=6
        )
        ttk.Checkbutton(export, text="Allow unlisted reports", variable=self.allow_unlisted_var).grid(
            row=3, column=3, sticky="w", padx=6, pady=6
        )
        self._label(export, "Events/page", 4, 0)
        ttk.Entry(export, textvariable=self.limit_var, width=14).grid(row=4, column=1, sticky="w", padx=6, pady=6)
        self._label(export, "Max pages", 4, 2)
        ttk.Entry(export, textvariable=self.max_pages_var, width=14).grid(row=4, column=3, sticky="w", padx=6, pady=6)

        actions = ttk.Frame(root_frame)
        actions.grid(row=4, column=0, sticky="ew", pady=(8, 6))
        actions.columnconfigure(3, weight=1)
        self.download_button = ttk.Button(actions, text="Download", style="Accent.TButton", command=self._start_download)
        self.download_button.grid(row=0, column=0, sticky="w")
        self.cancel_button = ttk.Button(actions, text="Cancel", command=self._cancel_download, state="disabled")
        self.cancel_button.grid(row=0, column=1, sticky="w", padx=(8, 0))
        self.open_button = ttk.Button(actions, text="Open output folder", command=self._open_output, state="disabled")
        self.open_button.grid(row=0, column=2, sticky="w", padx=(8, 0))
        self.progress = ttk.Progressbar(actions, mode="indeterminate")
        self.progress.grid(row=0, column=3, sticky="ew", padx=(12, 0))
        ttk.Label(actions, textvariable=self.status_var, style="Root.TLabel").grid(
            row=1,
            column=0,
            columnspan=4,
            sticky="w",
            pady=(6, 0),
        )

        log_frame = ttk.LabelFrame(root_frame, text="Progress")
        log_frame.grid(row=5, column=0, sticky="nsew", pady=(8, 0))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.log = scrolledtext.ScrolledText(log_frame, height=14, wrap="word", state="disabled")
        self.log.configure(
            background="#0c1015",
            foreground=self.colors["text"],
            insertbackground=self.colors["text"],
            relief="flat",
            borderwidth=0,
            font=("Menlo", 11),
        )
        self.log.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)

    def _wordmark(self, parent: Any) -> Any:
        canvas = tk.Canvas(parent, height=122, bg=self.colors["bg"], bd=0, highlightthickness=0)

        def draw(_event=None) -> None:
            canvas.delete("all")
            width = max(canvas.winfo_width(), 760)
            left = 10
            right = width - 10
            center = width / 2
            canvas.create_rectangle(left, 24, right, 105, fill="#161b22", outline="#61441d", width=3)
            canvas.create_line(left + 18, 40, right - 18, 40, fill="#b7802d", width=1)
            canvas.create_line(left + 18, 88, right - 18, 88, fill="#b7802d", width=1)
            for x in (left + 42, right - 42):
                canvas.create_polygon(
                    x, 14, x + 22, 64, x, 114, x - 22, 64,
                    fill="#0c1015",
                    outline=self.colors["gold"],
                    width=3,
                )
            canvas.create_text(
                center + 3,
                72,
                text="LogVault",
                fill="#050505",
                font=("Georgia", 42, "bold"),
            )
            canvas.create_text(
                center,
                68,
                text="LogVault",
                fill=self.colors["gold_light"],
                font=("Georgia", 42, "bold"),
            )
            canvas.create_text(
                center,
                103,
                text="WARCRAFT LOGS EXPORTER",
                fill=self.colors["blue"],
                font=("TkDefaultFont", 10, "bold"),
            )

        canvas.bind("<Configure>", draw)
        canvas.after_idle(draw)
        return canvas

    def _update_scroll_region(self, _event=None) -> None:
        self.scroll_canvas.configure(scrollregion=self.scroll_canvas.bbox("all"))

    def _resize_scroll_window(self, event: Any) -> None:
        self.scroll_canvas.itemconfigure(self.scroll_window, width=event.width)

    def _on_mousewheel(self, event: Any) -> None:
        if event.widget == self.log or str(event.widget).startswith(str(self.log)):
            return
        if getattr(event, "num", None) == 4:
            units = -3
        elif getattr(event, "num", None) == 5:
            units = 3
        else:
            delta = int(getattr(event, "delta", 0) or 0)
            units = -1 * int(delta / 120) if abs(delta) >= 120 else (-1 if delta > 0 else 1)
        self.scroll_canvas.yview_scroll(units, "units")

    def _label(self, parent: Any, text: str, row: int, column: int) -> None:
        ttk.Label(parent, text=text).grid(row=row, column=column, sticky="w", padx=(8, 0), pady=6)

    def _browse_output(self) -> None:
        selected = filedialog.askdirectory(initialdir=self.out_var.get() or ".")
        if selected:
            self.out_var.set(selected)

    def _start_download(self) -> None:
        if self.worker and self.worker.is_alive():
            self.status_var.set("Download is already running.")
            return
        self.cancel_event.clear()
        self._clear_log()
        self._append_log("Validating input...")
        try:
            options = self._collect_options()
        except ValueError as exc:
            self.status_var.set("Input error.")
            self._append_log(f"Invalid input: {exc}")
            messagebox.showerror("Invalid input", str(exc))
            return

        if self.save_env_var.get():
            try:
                saved_path = self._save_env(options)
            except OSError as exc:
                self.status_var.set("Could not save credentials.")
                self._append_log(f"Could not save credentials: {exc}")
                messagebox.showerror("Could not save credentials", str(exc))
                return
            self._append_log(f"Saved credentials to {saved_path}")

        self.last_result = None
        self.open_button.configure(state="disabled")
        self.download_button.configure(state="disabled")
        self.cancel_button.configure(state="normal")
        self.progress.start(12)
        self.status_var.set("Downloading...")
        self._append_log("Starting download...")

        self.worker = threading.Thread(target=self._download_worker, args=(options,), daemon=True)
        self.worker.start()

    def _collect_options(self) -> DownloadOptions | CharacterReportsOptions:
        report = self.report_var.get().strip()
        difficulty_ids = parse_difficulty_scope(self.difficulty_var.get())
        encounter = self.encounter_var.get().strip() or None
        if self.mode_var.get() == "report" and not report:
            raise ValueError("Report URL or code is required.")

        limit = parse_positive_int(self.limit_var.get().strip(), "Events/page")
        max_pages_text = self.max_pages_var.get().strip()
        max_pages = parse_positive_int(max_pages_text, "Max pages") if max_pages_text else None
        max_reports_text = self.max_reports_var.get().strip()
        max_reports = parse_non_negative_int(max_reports_text, "Max reports") if max_reports_text else 0
        make_zip = self.zip_var.get()
        archive_only = self.archive_only_var.get()
        if archive_only and not make_zip:
            raise ValueError("Keep only archive requires Create zip archive.")

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
                difficulty_ids=difficulty_ids,
                encounter=encounter,
                season_start=self.season_start_var.get().strip() or None,
                season_end=self.season_end_var.get().strip() or None,
                max_reports=max_reports or None,
                fight=self.fight_var.get().strip() or "boss",
                include_trash=self.include_trash_var.get(),
                tables=self.tables_var.get().strip() or "standard",
                events=self.events_var.get().strip() or "standard",
                filter_expression=self.filter_var.get().strip() or None,
                out=Path(self.out_var.get().strip() or "exports"),
                make_zip=make_zip,
                archive_only=archive_only,
                limit=limit,
                max_pages=max_pages,
                allow_unlisted=self.allow_unlisted_var.get(),
                client_id=self.client_id_var.get().strip() or None,
                client_secret=self.client_secret_var.get().strip() or None,
                cancel_check=self.cancel_event.is_set,
            )

        return DownloadOptions(
            report=report,
            fight=self.fight_var.get().strip() or None,
            include_trash=self.include_trash_var.get(),
            tables=self.tables_var.get().strip() or "standard",
            events=self.events_var.get().strip() or "standard",
            filter_expression=self.filter_var.get().strip() or None,
            out=Path(self.out_var.get().strip() or "exports"),
            make_zip=make_zip,
            archive_only=archive_only,
            limit=limit,
            max_pages=max_pages,
            allow_unlisted=self.allow_unlisted_var.get(),
            client_id=self.client_id_var.get().strip() or None,
            client_secret=self.client_secret_var.get().strip() or None,
            difficulty_ids=difficulty_ids,
            encounter=encounter,
            cancel_check=self.cancel_event.is_set,
        )

    def _save_env(self, options: DownloadOptions | CharacterReportsOptions) -> Path:
        lines = [
            "# Warcraft Logs OAuth client credentials.",
            f"WCL_CLIENT_ID={options.client_id or ''}",
            f"WCL_CLIENT_SECRET={options.client_secret or ''}",
        ]
        self.env_path.parent.mkdir(parents=True, exist_ok=True)
        self.env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        os.environ["WCL_CLIENT_ID"] = options.client_id or ""
        os.environ["WCL_CLIENT_SECRET"] = options.client_secret or ""
        return self.env_path

    def _download_worker(self, options: DownloadOptions | CharacterReportsOptions) -> None:
        try:
            if isinstance(options, CharacterReportsOptions):
                result = download_character_reports(options, progress=lambda message: self.messages.put(("log", message)))
            else:
                result = download_report(options, progress=lambda message: self.messages.put(("log", message)))
        except DownloadCancelled as exc:
            self.messages.put(("cancelled", str(exc)))
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
            elif kind == "cancelled":
                self._finish_running()
                self.status_var.set("Cancelled.")
                self._append_log(str(payload) or "Download cancelled.")
            elif kind == "error":
                self._finish_running()
                self.status_var.set("Download failed.")
                self._append_log(f"Error: {payload}")
                messagebox.showerror("Download failed", str(payload))
            elif kind == "done":
                self._finish_running()
                self.status_var.set("Finished.")
                self.last_result = payload
                self.open_button.configure(state="normal")
                self._append_log("Finished.")
                messagebox.showinfo("Download complete", f"Saved to:\n{self._primary_output(payload)}")
        self.root.after(100, self._poll_messages)

    def _finish_running(self) -> None:
        self.progress.stop()
        self.download_button.configure(state="normal")
        self.cancel_button.configure(state="disabled")

    def _cancel_download(self) -> None:
        if not self.worker or not self.worker.is_alive():
            self.status_var.set("No active download.")
            return
        if not self.cancel_event.is_set():
            self.cancel_event.set()
            self._append_log("Cancellation requested. Waiting for the active request to stop...")
        self.cancel_button.configure(state="disabled")
        self.status_var.set("Cancelling...")

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
        webbrowser.open(self._primary_output(self.last_result).resolve().as_uri())

    def _primary_output(self, result: DownloadResult | CharacterReportsResult) -> Path:
        if result.out_dir.exists():
            return result.out_dir
        if result.archive is not None:
            return result.archive
        return result.out_dir


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


def asset_path(name: str) -> Path:
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base) / "assets" / name
    return Path(__file__).resolve().parents[2] / "assets" / name


def default_env_path() -> Path:
    if not getattr(sys, "frozen", False):
        return Path(".env")
    if sys.platform == "win32":
        base = Path(os.getenv("APPDATA") or Path.home() / "AppData" / "Roaming")
        return base / "LogVault" / ".env"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "LogVault" / ".env"
    base = Path(os.getenv("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "logvault" / ".env"


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
