import os
import sys
import re
import time
from datetime import datetime
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

APP_NAME = "Advanced Notepad"
MAX_RECENTS = 10

PY_KEYWORDS = {
    "False","None","True","and","as","assert","async","await","break","class","continue",
    "def","del","elif","else","except","finally","for","from","global","if","import",
    "in","is","lambda","nonlocal","not","or","pass","raise","return","try","while","with","yield"
}

class EditorTab:
    def __init__(self, app, notebook, title="Untitled", path=None):
        self.app = app
        self.path = path
        self.title = title
        self.modified = False
        self.autosave_enabled = False
        self.autosave_interval_ms = 5000  # 5 seconds
        self.wrap = tk.NONE

        # Frame container
        self.frame = ttk.Frame(notebook)
        self.create_widgets()
        self.bind_events()

    def create_widgets(self):
        # Outer grid: line numbers + text
        self.line_numbers = tk.Text(self.frame, width=5, padx=4, takefocus=0,
                                    state="disabled", background="#2b2b2b", foreground="#9aa0a6",
                                    borderwidth=0, highlightthickness=0)
        self.text = tk.Text(self.frame, undo=True, wrap=self.wrap, borderwidth=0, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self.frame, orient="vertical", command=self.on_scrollbar)
        self.text.configure(yscrollcommand=self.on_textscroll)

        # Status bar (per tab content region)
        self.status = ttk.Label(self.frame, text="Ln 1, Col 1 | 0 chars", anchor="w")

        # Grid layout
        self.frame.columnconfigure(1, weight=1)
        self.frame.rowconfigure(0, weight=1)
        self.line_numbers.grid(row=0, column=0, sticky="nsew")
        self.text.grid(row=0, column=1, sticky="nsew")
        self.scrollbar.grid(row=0, column=2, sticky="ns")
        self.status.grid(row=1, column=0, columnspan=3, sticky="ew")

        # Fonts and tags for syntax highlighting
        base_font = ("Consolas" if sys.platform.startswith("win") else "Menlo" if sys.platform == "darwin" else "DejaVu Sans Mono", 12)
        self.text.configure(font=base_font)
        self.line_numbers.configure(font=base_font)

        # Syntax highlight tags
        self.text.tag_configure("py_keyword", foreground="#c678dd")
        self.text.tag_configure("py_string", foreground="#98c379")
        self.text.tag_configure("py_comment", foreground="#5c6370")
        self.text.tag_configure("match_bracket", background="#3e4451")
        self.text.tag_configure("trailing_ws", background="#3a1f1f")

    def bind_events(self):
        self.text.bind("<<Modified>>", self.on_modified)
        self.text.bind("<KeyRelease>", self.on_key_release)
        self.text.bind("<ButtonRelease-1>", lambda e: self.update_status())
        self.text.bind("<MouseWheel>", lambda e: self.update_line_numbers())  # Windows
        self.text.bind("<Button-4>", lambda e: self.update_line_numbers())    # Linux scroll up
        self.text.bind("<Button-5>", lambda e: self.update_line_numbers())    # Linux scroll down
        self.text.bind("<FocusIn>", lambda e: self.app.update_title())

        # Auto-indent
        self.text.bind("<Return>", self.auto_indent)
        # Bracket match
        self.text.bind("<KeyRelease>", self.bracket_match)

        # Autosave ticker
        self.schedule_autosave()

    def on_scrollbar(self, *args):
        self.text.yview(*args)
        self.update_line_numbers()

    def on_textscroll(self, *args):
        self.scrollbar.set(*args)
        self.update_line_numbers()

    def load_content(self, content):
        self.text.delete("1.0", tk.END)
        self.text.insert("1.0", content)
        self.text.edit_reset()
        self.text.edit_modified(False)
        self.modified = False
        self.update_status()
        self.update_line_numbers()
        self.syntax_highlight_all()

    def get_content(self):
        return self.text.get("1.0", tk.END)

    def on_modified(self, event=None):
        if self.text.edit_modified():
            self.modified = True
            self.app.mark_tab_modified(self)
            self.text.edit_modified(False)
            self.update_status()
            self.update_line_numbers()
            self.syntax_highlight_visible()
            self.highlight_trailing_whitespace()

    def update_status(self):
        index = self.text.index(tk.INSERT)
        line, col = map(int, index.split("."))
        content = self.get_content()
        length = len(content.rstrip("\n"))
        self.status.config(text=f"Ln {line}, Col {col+1} | {length} chars")

    def update_line_numbers(self):
        # Display current visible line numbers
        self.line_numbers.config(state="normal")
        self.line_numbers.delete("1.0", tk.END)
        start = self.text.index("@0,0")
        end = self.text.index("@0,%d" % self.text.winfo_height())
        start_line = int(start.split(".")[0])
        end_line = int(end.split(".")[0]) + 1

        lines = "\n".join(str(i) for i in range(start_line, end_line))
        self.line_numbers.insert("1.0", lines)
        self.line_numbers.config(state="disabled")

    def on_key_release(self, event=None):
        self.update_status()
        self.syntax_highlight_visible()
        self.highlight_trailing_whitespace()

    def auto_indent(self, event):
        # Preserve indentation from current line; add extra indent after colon
        line_start = self.text.index("insert linestart")
        line_end = self.text.index("insert lineend")
        current_line = self.text.get(line_start, line_end)
        indent = re.match(r"[ \t]*", current_line).group(0)
        extra = "    " if current_line.rstrip().endswith(":") else ""
        self.text.insert("insert", "\n" + indent + extra)
        return "break"

    def bracket_match(self, event=None):
        self.text.tag_remove("match_bracket", "1.0", tk.END)
        pos = self.text.index(tk.INSERT)
        prev = self.text.index(f"{pos} -1c")
        ch = self.text.get(prev, pos)
        pairs = {"(": ")", "[": "]", "{": "}"}
        if ch in pairs:
            self.highlight_matching_bracket(prev, pairs[ch])

    def highlight_matching_bracket(self, start_index, closing_char):
        stack = 1
        idx = self.text.index(f"{start_index} +1c")
        while True:
            if idx == tk.END:
                break
            ch = self.text.get(idx, f"{idx} +1c")
            if ch == self.text.get(start_index, f"{start_index} +1c"):
                stack += 1
            elif ch == closing_char:
                stack -= 1
                if stack == 0:
                    self.text.tag_add("match_bracket", start_index, f"{start_index} +1c")
                    self.text.tag_add("match_bracket", idx, f"{idx} +1c")
                    break
            idx = self.text.index(f"{idx} +1c")

    def highlight_trailing_whitespace(self):
        self.text.tag_remove("trailing_ws", "1.0", tk.END)
        last_line = int(self.text.index(tk.END).split(".")[0])
        for i in range(1, last_line + 1):
            start = f"{i}.0"
            end = f"{i}.end"
            line = self.text.get(start, end)
            m = re.search(r"[ \t]+$", line)
            if m:
                ws_start = f"{i}.{m.start()}"
                ws_end = f"{i}.{m.end()}"
                self.text.tag_add("trailing_ws", ws_start, ws_end)

    # Syntax highlighting
    def syntax_highlight_all(self):
        self.text.tag_remove("py_keyword", "1.0", tk.END)
        self.text.tag_remove("py_string", "1.0", tk.END)
        self.text.tag_remove("py_comment", "1.0", tk.END)
        text = self.get_content()
        self.apply_python_highlight(text, "1.0")

    def syntax_highlight_visible(self):
        self.text.tag_remove("py_keyword", "1.0", tk.END)
        self.text.tag_remove("py_string", "1.0", tk.END)
        self.text.tag_remove("py_comment", "1.0", tk.END)
        start = self.text.index("@0,0")
        end = self.text.index("@0,%d" % self.text.winfo_height())
        sline = int(start.split(".")[0])
        eline = int(end.split(".")[0]) + 1
        region_start = f"{sline}.0"
        region_end = f"{eline}.0"
        segment = self.text.get(region_start, region_end)
        self.apply_python_highlight(segment, region_start)

    def apply_python_highlight(self, segment, start_index):
        # Strings (single, double, triple)
        for m in re.finditer(r"('''.*?'''|\"\"\".*?\"\"\"|'.*?'|\".*?\")", segment, flags=re.S):
            s = self.text.index(f"{start_index} +{m.start()}c")
            e = self.text.index(f"{start_index} +{m.end()}c")
            self.text.tag_add("py_string", s, e)
        # Comments
        for m in re.finditer(r"#.*", segment):
            s = self.text.index(f"{start_index} +{m.start()}c")
            e = self.text.index(f"{start_index} +{m.end()}c")
            self.text.tag_add("py_comment", s, e)
        # Keywords (word boundaries, not inside strings/comments ideally)
        # Simple pass: highlight keywords not overlapped by string/comment tags
        for kw in PY_KEYWORDS:
            for m in re.finditer(rf"\b{re.escape(kw)}\b", segment):
                s = self.text.index(f"{start_index} +{m.start()}c")
                e = self.text.index(f"{start_index} +{m.end()}c")
                # Check overlap with string/comment; skip if overlapping
                ranges = self.text.tag_ranges("py_string") + self.text.tag_ranges("py_comment")
                overlap = False
                for i in range(0, len(ranges), 2):
                    rs, re_ = ranges[i], ranges[i+1]
                    if (self.text.compare(s, ">=", rs) and self.text.compare(s, "<", re_)) or \
                       (self.text.compare(e, ">", rs) and self.text.compare(e, "<=", re_)):
                        overlap = True
                        break
                if not overlap:
                    self.text.tag_add("py_keyword", s, e)

    def toggle_wrap(self):
        self.wrap = tk.WORD if self.wrap == tk.NONE else tk.NONE
        self.text.configure(wrap=self.wrap)
        return self.wrap

    def toggle_autosave(self):
        self.autosave_enabled = not self.autosave_enabled
        return self.autosave_enabled

    def schedule_autosave(self):
        def tick():
            if self.autosave_enabled and self.path:
                self.app.save_file(tab=self, silent=True)
            self.frame.after(self.autosave_interval_ms, tick)
        self.frame.after(self.autosave_interval_ms, tick)

class NotepadApp:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_NAME)
        self.theme_dark = False
        self.recent_files = []

        self.create_ui()
        self.apply_theme()

        # New initial tab
        self.new_tab()

    def create_ui(self):
        # Menu
        self.menu = tk.Menu(self.root)
        self.root.config(menu=self.menu)

        self.file_menu = tk.Menu(self.menu, tearoff=0)
        self.edit_menu = tk.Menu(self.menu, tearoff=0)
        self.search_menu = tk.Menu(self.menu, tearoff=0)
        self.view_menu = tk.Menu(self.menu, tearoff=0)
        self.tools_menu = tk.Menu(self.menu, tearoff=0)
        self.recent_menu = tk.Menu(self.file_menu, tearoff=0)

        self.menu.add_cascade(label="File", menu=self.file_menu)
        self.menu.add_cascade(label="Edit", menu=self.edit_menu)
        self.menu.add_cascade(label="Search", menu=self.search_menu)
        self.menu.add_cascade(label="View", menu=self.view_menu)
        self.menu.add_cascade(label="Tools", menu=self.tools_menu)

        # File menu
        self.file_menu.add_command(label="New Tab", command=self.new_tab, accelerator="Ctrl+N")
        self.file_menu.add_command(label="Open...", command=self.open_file, accelerator="Ctrl+O")
        self.file_menu.add_cascade(label="Open Recent", menu=self.recent_menu)
        self.file_menu.add_separator()
        self.file_menu.add_command(label="Save", command=self.save_file, accelerator="Ctrl+S")
        self.file_menu.add_command(label="Save As...", command=lambda: self.save_file(save_as=True), accelerator="Ctrl+Shift+S")
        self.file_menu.add_command(label="Save All", command=self.save_all)
        self.file_menu.add_separator()
        self.file_menu.add_command(label="Close Tab", command=self.close_tab, accelerator="Ctrl+W")
        self.file_menu.add_command(label="Exit", command=self.on_exit)

        # Edit menu
        self.edit_menu.add_command(label="Undo", command=lambda: self.current_text_event("undo"), accelerator="Ctrl+Z")
        self.edit_menu.add_command(label="Redo", command=lambda: self.current_text_event("redo"), accelerator="Ctrl+Y")
        self.edit_menu.add_separator()
        self.edit_menu.add_command(label="Cut", command=lambda: self.current_text_event("cut"), accelerator="Ctrl+X")
        self.edit_menu.add_command(label="Copy", command=lambda: self.current_text_event("copy"), accelerator="Ctrl+C")
        self.edit_menu.add_command(label="Paste", command=lambda: self.current_text_event("paste"), accelerator="Ctrl+V")
        self.edit_menu.add_command(label="Select All", command=lambda: self.current_text_event("select_all"), accelerator="Ctrl+A")
        self.edit_menu.add_separator()
        self.edit_menu.add_command(label="Insert Date/Time", command=self.insert_datetime)

        # Search menu
        self.search_menu.add_command(label="Find/Replace...", command=self.open_find_dialog, accelerator="Ctrl+F")
        self.search_menu.add_command(label="Find Next", command=lambda: self.find_next(), accelerator="F3")
        self.search_menu.add_command(label="Find Previous", command=lambda: self.find_prev(), accelerator="Shift+F3")

        # View menu
        self.view_menu.add_command(label="Toggle Line Numbers", command=self.toggle_line_numbers)
        self.view_menu.add_command(label="Toggle Word Wrap", command=self.toggle_word_wrap)
        self.view_menu.add_command(label="Toggle Dark Mode", command=self.toggle_theme)
        self.view_menu.add_separator()
        self.view_menu.add_command(label="Zoom In", command=lambda: self.zoom(1), accelerator="Ctrl++")
        self.view_menu.add_command(label="Zoom Out", command=lambda: self.zoom(-1), accelerator="Ctrl+-")
        self.view_menu.add_command(label="Reset Zoom", command=lambda: self.zoom(0), accelerator="Ctrl+0")

        # Tools menu
        self.tools_menu.add_command(label="Toggle Autosave (Current Tab)", command=self.toggle_autosave_current)
        self.tools_menu.add_separator()
        self.tools_menu.add_command(label="Trim Trailing Whitespace", command=self.trim_trailing_ws)
        self.tools_menu.add_command(label="Convert Tabs to Spaces", command=self.tabs_to_spaces)
        self.tools_menu.add_command(label="Convert Spaces to Tabs", command=self.spaces_to_tabs)

        # Notebook
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True)
        self.notebook.bind("<<NotebookTabChanged>>", lambda e: self.update_title())

        # Key bindings (global)
        self.root.bind("<Control-n>", lambda e: self.new_tab())
        self.root.bind("<Control-o>", lambda e: self.open_file())
        self.root.bind("<Control-s>", lambda e: self.save_file())
        self.root.bind("<Control-Shift-S>", lambda e: self.save_file(save_as=True))
        self.root.bind("<Control-w>", lambda e: self.close_tab())
        self.root.bind("<Control-f>", lambda e: self.open_find_dialog())
        self.root.bind("<F3>", lambda e: self.find_next())
        self.root.bind("<Shift-F3>", lambda e: self.find_prev())
        self.root.bind("<Control-Key-plus>", lambda e: self.zoom(1))
        self.root.bind("<Control-Key-minus>", lambda e: self.zoom(-1))
        self.root.bind("<Control-Key-0>", lambda e: self.zoom(0))
        self.root.protocol("WM_DELETE_WINDOW", self.on_exit)

        self.find_dialog = None
        self.find_state = {"pattern": "", "case": False, "word": False, "regex": False}

    # Tabs
    def new_tab(self, title="Untitled", path=None, content=""):
        tab = EditorTab(self, self.notebook, title=title, path=path)
        tab.load_content(content)
        self.notebook.add(tab.frame, text=title)
        self.notebook.select(tab.frame)
        self.update_title()
        return tab

    def current_tab(self):
        curr = self.notebook.select()
        if not curr:
            return None
        for child in self.notebook.winfo_children():
            if str(child) == curr:
                # Find matching EditorTab by frame
                for tab in self.all_tabs():
                    if tab.frame == child:
                        return tab
        return None

    def all_tabs(self):
        tabs = []
        for child in self.notebook.winfo_children():
            tabs.append(getattr(child, "_editor_tab", None))
        # If attribute not set, rebuild list by walking children
        real_tabs = []
        for child in self.notebook.winfo_children():
            # We stored tab object in widget? Let's map by storing in a dict:
            pass
        # Fallback: reconstruct by scanning frames
        real_tabs = []
        for child in self.notebook.winfo_children():
            # Our EditorTab created frames; find via a cache
            # Instead, store tabs in a list ourselves:
            pass
        # Simpler: keep registry on self
        return getattr(self, "_tabs", [])

    def register_tab(self, tab):
        if not hasattr(self, "_tabs"):
            self._tabs = []
        self._tabs.append(tab)
        # Attach back-reference to frame (optional)
        tab.frame._tab_obj = tab

    def mark_tab_modified(self, tab):
        idx = self.notebook.index(tab.frame)
        label = tab.title
        if tab.modified and not label.endswith("*"):
            label += " *"
        elif not tab.modified:
            label = tab.title
        self.notebook.tab(idx, text=label)
        self.update_title()

    def open_file(self):
        path = filedialog.askopenfilename(filetypes=[("All Files", "*.*"), ("Text Files", "*.txt"), ("Python Files", "*.py")])
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            messagebox.showerror(APP_NAME, f"Could not open file:\n{e}")
            return
        title = os.path.basename(path)
        tab = self.new_tab(title=title, path=path, content=content)
        self.register_tab(tab)
        self.add_recent(path)

    def save_file(self, tab=None, save_as=False, silent=False):
        tab = tab or self.current_tab()
        if not tab:
            return
        path = tab.path
        if save_as or not path:
            path = filedialog.asksaveasfilename(defaultextension=".txt",
                                                filetypes=[("Text Files", "*.txt"), ("Python Files", "*.py"), ("All Files", "*.*")])
            if not path:
                return
            tab.path = path
            tab.title = os.path.basename(path)
            self.notebook.tab(tab.frame, text=tab.title)
            self.update_title()
        content = tab.get_content()
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
        except Exception as e:
            if not silent:
                messagebox.showerror(APP_NAME, f"Could not save file:\n{e}")
            return
        tab.modified = False
        self.mark_tab_modified(tab)
        if not silent:
            self.status_message(f"Saved: {path}")
        # Highlight entire after save
        tab.syntax_highlight_all()
        self.add_recent(path)

    def save_all(self):
        for tab in self._tabs:
            if tab.path:
                self.save_file(tab=tab, silent=True)
        self.status_message("All open files saved.")

    def close_tab(self):
        tab = self.current_tab()
        if not tab:
            return
        if tab.modified:
            ans = messagebox.askyesnocancel(APP_NAME, "Save changes before closing?")
            if ans is None:
                return
            if ans:
                self.save_file(tab=tab)
        self.notebook.forget(tab.frame)
        self._tabs.remove(tab)
        self.update_title()

    def on_exit(self):
        # Prompt for modified tabs
        for tab in list(self._tabs):
            self.notebook.select(tab.frame)
            if tab.modified:
                ans = messagebox.askyesnocancel(APP_NAME, f"Save changes to {tab.title}?")
                if ans is None:
                    return
                if ans:
                    self.save_file(tab=tab)
        self.root.destroy()

    def add_recent(self, path):
        if path in self.recent_files:
            self.recent_files.remove(path)
        self.recent_files.insert(0, path)
        self.recent_files = self.recent_files[:MAX_RECENTS]
        self.refresh_recent_menu()

    def refresh_recent_menu(self):
        self.recent_menu.delete(0, tk.END)
        if not self.recent_files:
            self.recent_menu.add_command(label="(No recent files)", state="disabled")
            return
        for p in self.recent_files:
            self.recent_menu.add_command(label=p, command=lambda path=p: self.open_recent(path))
        self.recent_menu.add_separator()
        self.recent_menu.add_command(label="Clear Recents", command=self.clear_recents)

    def open_recent(self, path):
        if not os.path.exists(path):
            messagebox.showwarning(APP_NAME, "File not found. Removing from recents.")
            self.recent_files = [p for p in self.recent_files if p != path]
            self.refresh_recent_menu()
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            messagebox.showerror(APP_NAME, f"Could not open file:\n{e}")
            return
        title = os.path.basename(path)
        tab = self.new_tab(title=title, path=path, content=content)
        self.register_tab(tab)

    def clear_recents(self):
        self.recent_files = []
        self.refresh_recent_menu()

    # Edit helpers
    def current_text_event(self, action):
        tab = self.current_tab()
        if not tab:
            return
        t = tab.text
        if action == "undo":
            t.event_generate("<<Undo>>")
        elif action == "redo":
            t.event_generate("<<Redo>>")
        elif action == "cut":
            t.event_generate("<<Cut>>")
        elif action == "copy":
            t.event_generate("<<Copy>>")
        elif action == "paste":
            t.event_generate("<<Paste>>")
        elif action == "select_all":
            t.tag_add(tk.SEL, "1.0", tk.END)
            t.mark_set(tk.INSERT, "1.0")
            t.see(tk.INSERT)

    def insert_datetime(self):
        tab = self.current_tab()
        if not tab:
            return
        tab.text.insert(tk.INSERT, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    # Find/Replace
    def open_find_dialog(self):
        if self.find_dialog and tk.Toplevel.winfo_exists(self.find_dialog):
            self.find_dialog.lift()
            return
        self.find_dialog = tk.Toplevel(self.root)
        self.find_dialog.title("Find/Replace")
        self.find_dialog.resizable(False, False)
        self.find_dialog.transient(self.root)

        ttk.Label(self.find_dialog, text="Find:").grid(row=0, column=0, sticky="e", padx=6, pady=6)
        find_entry = ttk.Entry(self.find_dialog, width=32)
        find_entry.grid(row=0, column=1, columnspan=3, sticky="we", padx=6, pady=6)

        ttk.Label(self.find_dialog, text="Replace:").grid(row=1, column=0, sticky="e", padx=6, pady=6)
        replace_entry = ttk.Entry(self.find_dialog, width=32)
        replace_entry.grid(row=1, column=1, columnspan=3, sticky="we", padx=6, pady=6)

        case_var = tk.BooleanVar(value=self.find_state["case"])
        word_var = tk.BooleanVar(value=self.find_state["word"])
        regex_var = tk.BooleanVar(value=self.find_state["regex"])

        ttk.Checkbutton(self.find_dialog, text="Match case", variable=case_var).grid(row=2, column=0, sticky="w", padx=6)
        ttk.Checkbutton(self.find_dialog, text="Whole word", variable=word_var).grid(row=2, column=1, sticky="w", padx=6)
        ttk.Checkbutton(self.find_dialog, text="Regex", variable=regex_var).grid(row=2, column=2, sticky="w", padx=6)

        btn_find_next = ttk.Button(self.find_dialog, text="Find Next", command=lambda: self.find_next(find_entry.get(), case_var.get(), word_var.get(), regex_var.get()))
        btn_find_prev = ttk.Button(self.find_dialog, text="Find Prev", command=lambda: self.find_prev(find_entry.get(), case_var.get(), word_var.get(), regex_var.get()))
        btn_replace = ttk.Button(self.find_dialog, text="Replace", command=lambda: self.replace_one(find_entry.get(), replace_entry.get(), case_var.get(), word_var.get(), regex_var.get()))
        btn_replace_all = ttk.Button(self.find_dialog, text="Replace All", command=lambda: self.replace_all(find_entry.get(), replace_entry.get(), case_var.get(), word_var.get(), regex_var.get()))
        btn_close = ttk.Button(self.find_dialog, text="Close", command=self.find_dialog.destroy)

        btn_find_next.grid(row=3, column=0, padx=6, pady=10)
        btn_find_prev.grid(row=3, column=1, padx=6, pady=10)
        btn_replace.grid(row=3, column=2, padx=6, pady=10)
        btn_replace_all.grid(row=3, column=3, padx=6, pady=10)
        btn_close.grid(row=4, column=3, sticky="e", padx=6, pady=6)

        find_entry.focus_set()

    def _build_pattern(self, text, case, word, regex):
        flags = 0 if case else re.IGNORECASE
        if not regex:
            text = re.escape(text)
        if word:
            text = rf"\b{text}\b"
        try:
            pat = re.compile(text, flags)
            return pat
        except re.error as e:
            messagebox.showerror(APP_NAME, f"Invalid regex:\n{e}")
            return None

    def find_next(self, pattern=None, case=None, word=None, regex=None):
        tab = self.current_tab()
        if not tab:
            return
        if pattern is None:
            pattern = self.find_state["pattern"]
            case = self.find_state["case"]
            word = self.find_state["word"]
            regex = self.find_state["regex"]
        else:
            self.find_state.update({"pattern": pattern, "case": case, "word": word, "regex": regex})

        if not pattern:
            return
        pat = self._build_pattern(pattern, case, word, regex)
        if not pat:
            return

        start = tab.text.index(tk.INSERT)
        content = tab.text.get("1.0", tk.END)
        offset = self.index_to_offset(tab.text, start)
        m = pat.search(content, pos=offset+1)
        if not m:
            m = pat.search(content, pos=0)
            if not m:
                self.status_message("Not found.")
                return
        s = self.offset_to_index(tab.text, m.start())
        e = self.offset_to_index(tab.text, m.end())
        tab.text.tag_remove(tk.SEL, "1.0", tk.END)
        tab.text.tag_add(tk.SEL, s, e)
        tab.text.mark_set(tk.INSERT, e)
        tab.text.see(s)
        self.status_message("Match found.")

    def find_prev(self, pattern=None, case=None, word=None, regex=None):
        tab = self.current_tab()
        if not tab:
            return
        if pattern is None:
            pattern = self.find_state["pattern"]
            case = self.find_state["case"]
            word = self.find_state["word"]
            regex = self.find_state["regex"]
        else:
            self.find_state.update({"pattern": pattern, "case": case, "word": word, "regex": regex})

        if not pattern:
            return
        pat = self._build_pattern(pattern, case, word, regex)
        if not pat:
            return

        content = tab.text.get("1.0", tk.END)
        insert = tab.text.index(tk.INSERT)
        offset = self.index_to_offset(tab.text, insert)
        matches = list(pat.finditer(content[:max(0, offset)]))
        if not matches:
            matches = list(pat.finditer(content))
            if not matches:
                self.status_message("Not found.")
                return
        m = matches[-1]
        s = self.offset_to_index(tab.text, m.start())
        e = self.offset_to_index(tab.text, m.end())
        tab.text.tag_remove(tk.SEL, "1.0", tk.END)
        tab.text.tag_add(tk.SEL, s, e)
        tab.text.mark_set(tk.INSERT, s)
        tab.text.see(s)
        self.status_message("Match found.")

    def replace_one(self, pattern, replacement, case, word, regex):
        tab = self.current_tab()
        if not tab:
            return
        if not pattern:
            return
        sel = tab.text.tag_ranges(tk.SEL)
        if sel:
            s, e = sel
            current = tab.text.get(s, e)
            pat = self._build_pattern(pattern, case, word, regex)
            if not pat:
                return
            if pat.fullmatch(current):
                tab.text.delete(s, e)
                tab.text.insert(s, replacement)
                tab.text.tag_remove(tk.SEL, "1.0", tk.END)
                tab.text.mark_set(tk.INSERT, s)
                self.status_message("Replaced selection.")
                return
        # If no selection or not matching, find next and replace
        self.find_next(pattern, case, word, regex)
        sel = tab.text.tag_ranges(tk.SEL)
        if sel:
            s, e = sel
            tab.text.delete(s, e)
            tab.text.insert(s, replacement)
            tab.text.tag_remove(tk.SEL, "1.0", tk.END)
            tab.text.mark_set(tk.INSERT, s)
            self.status_message("Replaced match.")

    def replace_all(self, pattern, replacement, case, word, regex):
        tab = self.current_tab()
        if not tab:
            return
        pat = self._build_pattern(pattern, case, word, regex)
        if not pat:
            return
        content = tab.text.get("1.0", tk.END)
        new = pat.sub(replacement, content)
        tab.text.delete("1.0", tk.END)
        tab.text.insert("1.0", new)
        self.status_message("Replace all done.")

    # Helpers to convert between text index and offset
    def index_to_offset(self, text_widget, index):
        # index like "line.column"
        line, col = map(int, str(index).split("."))
        offset = 0
        for i in range(1, line):
            offset += len(text_widget.get(f"{i}.0", f"{i}.end")) + 1  # include newline
        offset += col
        return offset

    def offset_to_index(self, text_widget, offset):
        # Walk lines until offset fits
        line = 1
        while True:
            line_len = len(text_widget.get(f"{line}.0", f"{line}.end")) + 1
            if offset < line_len:
                return f"{line}.{offset}"
            offset -= line_len
            line += 1

    # View and tools
    def toggle_line_numbers(self):
        tab = self.current_tab()
        if not tab:
            return
        if tab.line_numbers.winfo_viewable():
            tab.line_numbers.grid_remove()
        else:
            tab.line_numbers.grid()
            tab.update_line_numbers()

    def toggle_word_wrap(self):
        tab = self.current_tab()
        if not tab:
            return
        state = tab.toggle_wrap()
        self.status_message("Word wrap " + ("enabled" if state == tk.WORD else "disabled"))

    def toggle_theme(self):
        self.theme_dark = not self.theme_dark
        self.apply_theme()

    def apply_theme(self):
        bg = "#1e1e1e" if self.theme_dark else "#ffffff"
        fg = "#d4d4d4" if self.theme_dark else "#000000"
        ln_bg = "#2b2b2b" if self.theme_dark else "#f0f0f0"
        ln_fg = "#9aa0a6" if self.theme_dark else "#7a7a7a"

        style = ttk.Style()
        if sys.platform == "win":
            style.theme_use("vista")
        else:
            style.theme_use("clam")

        self.root.configure(bg=bg)
        for tab in getattr(self, "_tabs", []):
            tab.text.configure(background=bg, foreground=fg, insertbackground=fg)
            tab.line_numbers.configure(background=ln_bg, foreground=ln_fg)
            tab.status.configure(background=ln_bg, foreground=ln_fg)
            # Update tags in dark mode (colors set already fit)
            tab.update_line_numbers()

    def zoom(self, delta):
        tab = self.current_tab()
        if not tab:
            return
        font = tab.text.cget("font")
        family, size = font.split(" ")[0], int(font.split(" ")[-1])
        if delta == 0:
            size = 12
        else:
            size = max(8, min(36, size + delta))
        new_font = (family, size)
        tab.text.configure(font=new_font)
        tab.line_numbers.configure(font=new_font)

    def toggle_autosave_current(self):
        tab = self.current_tab()
        if not tab:
            return
        enabled = tab.toggle_autosave()
        self.status_message("Autosave " + ("enabled" if enabled else "disabled"))

    def trim_trailing_ws(self):
        tab = self.current_tab()
        if not tab:
            return
        last_line = int(tab.text.index(tk.END).split(".")[0])
        for i in range(1, last_line + 1):
            start = f"{i}.0"
            end = f"{i}.end"
            line = tab.text.get(start, end)
            tab.text.delete(start, end)
            tab.text.insert(start, line.rstrip())
        tab.highlight_trailing_whitespace()
        self.status_message("Trimmed trailing whitespace.")

    def tabs_to_spaces(self):
        tab = self.current_tab()
        if not tab:
            return
        content = tab.text.get("1.0", tk.END).replace("\t", "    ")
        tab.text.delete("1.0", tk.END)
        tab.text.insert("1.0", content)
        self.status_message("Converted tabs to spaces.")

    def spaces_to_tabs(self):
        tab = self.current_tab()
        if not tab:
            return
        content = re.sub(r" {4}", "\t", tab.text.get("1.0", tk.END))
        tab.text.delete("1.0", tk.END)
        tab.text.insert("1.0", content)
        self.status_message("Converted spaces to tabs.")

    def update_title(self):
        tab = self.current_tab()
        if not tab:
            self.root.title(APP_NAME)
            return
        path_info = f" - {tab.path}" if tab.path else ""
        mod = "*" if tab.modified else ""
        self.root.title(f"{APP_NAME} | {tab.title}{mod}{path_info}")

    def status_message(self, msg):
        # Show in window title briefly
        self.root.title(f"{APP_NAME} — {msg}")
        self.root.after(2000, self.update_title)

def main():
    root = tk.Tk()
    app = NotepadApp(root)
    # Registry for tabs since early methods referenced it
    app._tabs = []
    # Hook tab registration to new_tab
    original_new_tab = app.new_tab
    def new_tab_hook(*args, **kwargs):
        tab = original_new_tab(*args, **kwargs)
        app.register_tab(tab)
        return tab
    app.new_tab = new_tab_hook

    root.geometry("1000x700")
    root.minsize(600, 400)
    root.mainloop()

if __name__ == "__main__":
    main()
