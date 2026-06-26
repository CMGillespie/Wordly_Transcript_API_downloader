import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import requests
import os
import json
import time
import threading
import re
from datetime import datetime

# --- Constants & Versioning ---
# v3.2.0 - Added date filter (Download Everything / From Date Forward / Date Range)
VERSION = "3.2.0"
CONFIG_FILE = "wordly_config.json"
INVENTORY_FILE = "wordly_inventory.json"
BASE_URL = "https://api.wordly.ai"

class WordlyDownloaderApp:
    def __init__(self, root):
        self.root = root
        self.root.title(f"Wordly Transcript Downloader - v{VERSION}")
        self.root.geometry("1000x950")
        
        # --- State Variables ---
        self.api_key = tk.StringVar()
        self.download_path = tk.StringVar(value=os.path.join(os.path.expanduser("~"), "Desktop"))
        self.sync_interval = tk.StringVar(value="1") 
        self.is_running = False
        self.processed_ids = {}

        self.want_txt = tk.BooleanVar(value=True)
        self.want_srt = tk.BooleanVar(value=False)
        self.want_xml = tk.BooleanVar(value=False)

        # --- Date Filter ---
        self.date_filter_mode = tk.StringVar(value="all")  # all | from_date | date_range
        self.date_filter_from = tk.StringVar(value="")
        self.date_filter_to = tk.StringVar(value="")

        self.load_settings()
        self.setup_ui()
        
        # Intercept Close Button
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def setup_ui(self):
        style = ttk.Style()
        style.configure("TLabel", font=("TkDefaultFont", 12))
        style.configure("TButton", font=("TkDefaultFont", 12))
        style.configure("TCheckbutton", font=("TkDefaultFont", 12))
        
        main_frame = ttk.Frame(self.root, padding="30")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Version Header
        ttk.Label(main_frame, text=f"Wordly Portal Scraper Engine | v{VERSION}", font=("TkDefaultFont", 10, "italic")).pack(anchor=tk.E)
        
        # 1. API Key
        ttk.Label(main_frame, text="Wordly API Key:", font=("TkDefaultFont", 12, "bold")).pack(anchor=tk.W)
        ttk.Entry(main_frame, textvariable=self.api_key, width=50, show="*", font=("TkDefaultFont", 12)).pack(anchor=tk.W, pady=(0, 20))

        # 2. Folder Picker
        ttk.Label(main_frame, text="Master Download Folder:", font=("TkDefaultFont", 12, "bold")).pack(anchor=tk.W)
        f_frame = ttk.Frame(main_frame)
        f_frame.pack(fill=tk.X, pady=(0, 20))
        ttk.Entry(f_frame, textvariable=self.download_path, width=45, font=("TkDefaultFont", 12)).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(f_frame, text="Browse Folder", command=self.browse_folder).pack(side=tk.LEFT)

        # 3. Sync Settings
        s_frame = ttk.Frame(main_frame)
        s_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(s_frame, text="Check for new transcripts every (minutes):", font=("TkDefaultFont", 12)).pack(side=tk.LEFT)
        ttk.Entry(s_frame, textvariable=self.sync_interval, width=5, font=("TkDefaultFont", 12)).pack(side=tk.LEFT, padx=10)

        # 4. Formats
        fmt_frame = ttk.LabelFrame(main_frame, text=" Select File Formats ", padding="20")
        fmt_frame.pack(fill=tk.X, pady=10)
        tk.Checkbutton(fmt_frame, text="Plain Text (.txt)", variable=self.want_txt, font=("TkDefaultFont", 12)).pack(side=tk.LEFT, padx=20)
        tk.Checkbutton(fmt_frame, text="Subtitles (.srt)", variable=self.want_srt, font=("TkDefaultFont", 12)).pack(side=tk.LEFT, padx=20)
        tk.Checkbutton(fmt_frame, text="Custom XML (.xml)", variable=self.want_xml, font=("TkDefaultFont", 12)).pack(side=tk.LEFT, padx=20)

        # 5. Date Filter
        filter_frame = ttk.LabelFrame(main_frame, text=" Download Filter ", padding="20")
        filter_frame.pack(fill=tk.X, pady=10)

        tk.Radiobutton(filter_frame, text="Download Everything", variable=self.date_filter_mode,
            value="all", font=("TkDefaultFont", 12), command=self.toggle_date_fields).pack(side=tk.LEFT, padx=10)
        tk.Radiobutton(filter_frame, text="From Date Forward", variable=self.date_filter_mode,
            value="from_date", font=("TkDefaultFont", 12), command=self.toggle_date_fields).pack(side=tk.LEFT, padx=10)
        tk.Radiobutton(filter_frame, text="Date Range", variable=self.date_filter_mode,
            value="date_range", font=("TkDefaultFont", 12), command=self.toggle_date_fields).pack(side=tk.LEFT, padx=10)

        date_fields_frame = ttk.Frame(main_frame)
        date_fields_frame.pack(fill=tk.X, pady=(0, 10))

        self.lbl_from = ttk.Label(date_fields_frame, text="From (YYYY-MM-DD):", font=("TkDefaultFont", 12))
        self.lbl_from.pack(side=tk.LEFT, padx=(0, 5))
        self.entry_from = ttk.Entry(date_fields_frame, textvariable=self.date_filter_from, width=14, font=("TkDefaultFont", 12))
        self.entry_from.pack(side=tk.LEFT, padx=(0, 20))

        self.lbl_to = ttk.Label(date_fields_frame, text="To (YYYY-MM-DD):", font=("TkDefaultFont", 12))
        self.lbl_to.pack(side=tk.LEFT, padx=(0, 5))
        self.entry_to = ttk.Entry(date_fields_frame, textvariable=self.date_filter_to, width=14, font=("TkDefaultFont", 12))
        self.entry_to.pack(side=tk.LEFT)

        self.toggle_date_fields()

        # 6. Start Button
        self.btn_toggle = ttk.Button(main_frame, text="START DOWNLOADER", command=self.toggle_agent)
        self.btn_toggle.pack(pady=25)

        # 7. Activity Log
        ttk.Label(main_frame, text="Activity Log:", font=("TkDefaultFont", 12, "bold")).pack(anchor=tk.W)
        self.log_text = tk.Text(main_frame, height=30, width=120, state='disabled', font=("Courier New", 12), bg="white", fg="black")
        self.log_text.pack(pady=5, fill=tk.BOTH, expand=True)

    def toggle_date_fields(self):
        mode = self.date_filter_mode.get()
        if mode == "all":
            self.lbl_from.config(foreground="grey")
            self.entry_from.config(state="disabled")
            self.lbl_to.config(foreground="grey")
            self.entry_to.config(state="disabled")
        elif mode == "from_date":
            self.lbl_from.config(foreground="black")
            self.entry_from.config(state="normal")
            self.lbl_to.config(foreground="grey")
            self.entry_to.config(state="disabled")
        elif mode == "date_range":
            self.lbl_from.config(foreground="black")
            self.entry_from.config(state="normal")
            self.lbl_to.config(foreground="black")
            self.entry_to.config(state="normal")

    def is_in_date_filter(self, transcript):
        mode = self.date_filter_mode.get()
        if mode == "all":
            return True
        raw = transcript.get("startTime", "")
        if not raw:
            return True  # no date on record, let it through
        try:
            t_date = datetime.strptime(raw[:10], "%Y-%m-%d").date()
        except ValueError:
            return True
        if mode == "from_date":
            from_str = self.date_filter_from.get().strip()
            if not from_str:
                return True
            try:
                from_date = datetime.strptime(from_str, "%Y-%m-%d").date()
                return t_date >= from_date
            except ValueError:
                self.log("⚠️ Invalid 'From' date format. Use YYYY-MM-DD.")
                return True
        if mode == "date_range":
            from_str = self.date_filter_from.get().strip()
            to_str = self.date_filter_to.get().strip()
            if not from_str or not to_str:
                return True
            try:
                from_date = datetime.strptime(from_str, "%Y-%m-%d").date()
                to_date = datetime.strptime(to_str, "%Y-%m-%d").date()
                return from_date <= t_date <= to_date
            except ValueError:
                self.log("⚠️ Invalid date range format. Use YYYY-MM-DD.")
                return True
        return True

    def on_closing(self):
        if self.is_running:
            if messagebox.askokcancel("Quit", "Downloader is currently active. Are you sure you want to stop and exit?"):
                self.root.destroy()
        else:
            self.root.destroy()

    def browse_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.download_path.set(folder)
            self.save_settings()

    def log(self, message):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_text.config(state='normal')
        self.log_text.insert(tk.END, f"[{ts}] {message}\n")
        self.log_text.see(tk.END)
        self.log_text.config(state='disabled')

    def load_settings(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r') as f:
                    data = json.load(f)
                    self.api_key.set(data.get("api_key", ""))
                    self.download_path.set(data.get("download_path", self.download_path.get()))
                    self.sync_interval.set(data.get("sync_interval", "1"))
                    self.date_filter_mode.set(data.get("date_filter_mode", "all"))
                    self.date_filter_from.set(data.get("date_filter_from", ""))
                    self.date_filter_to.set(data.get("date_filter_to", ""))
            except: pass

    def save_settings(self):
        with open(CONFIG_FILE, 'w') as f:
            json.dump({
                "api_key": self.api_key.get().strip(),
                "download_path": self.download_path.get(),
                "sync_interval": self.sync_interval.get(),
                "date_filter_mode": self.date_filter_mode.get(),
                "date_filter_from": self.date_filter_from.get(),
                "date_filter_to": self.date_filter_to.get()
            }, f)

    def toggle_agent(self):
        if not self.is_running:
            raw_key = self.api_key.get().strip()
            if not raw_key:
                messagebox.showerror("Error", "Enter API Key.")
                return
            self.save_settings()
            self.is_running = True
            self.btn_toggle.config(text="STOP DOWNLOADER")
            self.log(f"🚀 v{VERSION} active...")
            threading.Thread(target=self.agent_loop, args=(raw_key,), daemon=True).start()
        else:
            self.is_running = False
            self.log("🛑 Stop requested...")

    def agent_loop(self, api_key):
        headers = {"x-wordly-api-key": api_key}
        if os.path.exists(INVENTORY_FILE):
            with open(INVENTORY_FILE, 'r') as f:
                self.processed_ids = json.load(f)
            self.log(f"📦 Inventory loaded: {len(self.processed_ids)} items.")
        else:
            if not self.run_paginated_baseline(headers):
                self.is_running = False
                self.root.after(0, lambda: self.btn_toggle.config(text="START DOWNLOADER"))
                return

        while self.is_running:
            try:
                res = requests.get(f"{BASE_URL}/transcripts?limit=20", headers=headers, timeout=15)
                if res.status_code == 200:
                    transcripts = res.json().get("transcripts", [])
                    for t in transcripts:
                        if not self.is_running: break
                        if t['transcriptId'] not in self.processed_ids:
                            if self.is_in_date_filter(t):
                                self.process_new_transcript(t, headers)
                            else:
                                self.processed_ids[t['transcriptId']] = "skipped_date_filter"
                else:
                    self.log(f"⚠️ API Error {res.status_code}")
            except Exception as e:
                self.log(f"⚠️ Network check failed: {str(e)}")
            
            try:
                wait_time = int(self.sync_interval.get()) * 60
            except:
                wait_time = 60
                
            for _ in range(wait_time):
                if not self.is_running: break
                time.sleep(1)
        
        self.root.after(0, lambda: self.btn_toggle.config(text="START DOWNLOADER"))

    def run_paginated_baseline(self, headers):
        self.log("📡 Building historical baseline...")
        current_page = 1
        limit = 100
        while self.is_running:
            try:
                url = f"{BASE_URL}/transcripts?page={current_page}&limit={limit}"
                res = requests.get(url, headers=headers, timeout=20)
                if res.status_code == 200:
                    data = res.json()
                    transcripts = data.get("transcripts", [])
                    if not transcripts: break
                    for t in transcripts:
                        self.processed_ids[t['transcriptId']] = "historical_baseline"
                    total_captured = len(self.processed_ids)
                    self.log(f"   ✅ Page {current_page}: {len(transcripts)} items.")
                    if total_captured >= data.get("total", 0): break
                    current_page += 1
                else:
                    self.log(f"❌ Baseline Failed (Code {res.status_code})")
                    return False
            except Exception as e:
                self.log(f"❌ Baseline Error: {str(e)}")
                return False
        with open(INVENTORY_FILE, 'w') as f:
            json.dump(self.processed_ids, f)
        self.log(f"✅ Baseline complete. {len(self.processed_ids)} items archived.")
        return True

    def sanitize(self, text):
        return re.sub(r'[\\/*?:"<>|]', "_", text)

    def process_new_transcript(self, t, headers):
        t_id = t['transcriptId']
        s_id = t.get('sessionId', 'NoID')
        now = datetime.now()
        date_folder = f"Wordly_Transcripts_{now.strftime('%d-%m-%Y')}"
        master_folder = os.path.join(self.download_path.get(), date_folder)
        os.makedirs(master_folder, exist_ok=True)
        
        clean_title = self.sanitize(t['title'])
        base_name = f"{t['startTime'][:10]}_{now.strftime('%H-%M-%S')}_{clean_title}_{s_id}"
        self.log(f"✨ NEW: {t['title']}")
        
        success = True
        if self.want_txt.get():
            url = f"{BASE_URL}/transcripts/{t_id}/original?format=txt&speaker_names=true"
            if not self.verified_download(url, headers, master_folder, base_name, "txt"):
                success = False
        if self.want_srt.get():
            url = f"{BASE_URL}/transcripts/{t_id}/original?format=srt&speaker_names=true"
            self.verified_download(url, headers, master_folder, base_name, "srt")
        if self.want_xml.get() and self.want_txt.get():
            self.create_xml_wrapper(master_folder, base_name, t)

        if success:
            self.processed_ids[t_id] = "downloaded"
            with open(INVENTORY_FILE, 'w') as f:
                json.dump(self.processed_ids, f)
            self.log(f"✅ Finished: {base_name}")

    def create_xml_wrapper(self, folder, name, t):
        txt_file = os.path.join(folder, f"{name}.txt")
        if os.path.exists(txt_file):
            with open(txt_file, 'r', encoding='utf-8') as f:
                txt_content = f.read()
            xml_data = f"<?xml version='1.0' encoding='UTF-8'?>\n<transcript>\n  <session_id>{t.get('sessionId')}</session_id>\n  <title>{t.get('title')}</title>\n  <content>{txt_content}</content>\n</transcript>"
            with open(os.path.join(folder, f"{name}.xml"), 'w', encoding='utf-8') as f:
                f.write(xml_data)

    def verified_download(self, url, headers, folder, base_name, ext):
        suffix = ""
        alpha = "abcdefghijklmnopqrstuvwxyz"
        idx = 0
        while os.path.exists(os.path.join(folder, f"{base_name}{suffix}.{ext}")):
            suffix = f"_{alpha[idx]}"
            idx += 1
            if idx >= len(alpha): break
        target_path = os.path.join(folder, f"{base_name}{suffix}.{ext}")
        for i in range(3):
            try:
                res = requests.get(url, headers=headers, stream=True, timeout=20)
                if res.status_code == 200:
                    with open(target_path, 'w', encoding='utf-8') as f:
                        f.write(res.text)
                    return True
                else: return False
            except: continue
        return False

if __name__ == "__main__":
    root = tk.Tk()
    app = WordlyDownloaderApp(root)
    root.mainloop()