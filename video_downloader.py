"""
シンプル動画ダウンローダー
Lulustream等の動画サイトからmp4形式で動画をダウンロードするGUIアプリ
"""

import os
import json
import threading
import tkinter as tk
from tkinter import ttk, filedialog
from datetime import datetime
from collections import deque
from concurrent.futures import ThreadPoolExecutor

try:
    import yt_dlp
except ImportError:
    print("yt-dlpがインストールされていません。以下のコマンドを実行してください:")
    print("pip install yt-dlp")
    exit(1)

# 設定ファイルのパス
SETTINGS_DIR = os.path.join(os.path.expanduser("~"), ".video_downloader")
SETTINGS_FILE = os.path.join(SETTINGS_DIR, "settings.json")
HISTORY_FILE = os.path.join(SETTINGS_DIR, "history.json")

# デフォルトの同時ダウンロード数
DEFAULT_CONCURRENT_DOWNLOADS = 2
MAX_CONCURRENT_DOWNLOADS = 5


class DownloadTask:
    """個別のダウンロードタスクを管理するクラス"""
    def __init__(self, url, task_id):
        self.url = url
        self.task_id = task_id
        self.progress = 0.0
        self.status = "待機中"
        self.cancel_requested = False
        self.title = ""
        self.speed = ""
        self.current_ydl = None


class VideoDownloaderApp:
    def __init__(self, root):
        self.root = root
        self.root.title("動画ダウンローダー")
        self.root.geometry("700x500")
        self.root.minsize(600, 400)
        
        # 設定を読み込む
        self.settings = self._load_settings()
        
        # 保存先
        default_save_path = self.settings.get("save_path", os.getcwd())
        if not os.path.isdir(default_save_path):
            default_save_path = os.getcwd()
        self.save_path = tk.StringVar(value=default_save_path)
        
        # 同時ダウンロード数
        default_concurrent = self.settings.get("concurrent_downloads", DEFAULT_CONCURRENT_DOWNLOADS)
        self.concurrent_downloads = tk.IntVar(value=default_concurrent)
        
        # 設定パネル表示フラグ
        self.settings_visible = tk.BooleanVar(value=False)
        
        # ダウンロード状態
        self.is_downloading = False
        self.cancel_all_requested = False
        self.download_queue = deque()
        self.active_tasks = {}
        self.completed_count = 0
        self.total_count = 0
        self.task_id_counter = 0
        self.queue_lock = threading.Lock()
        self.executor = None
        
        # 履歴データ
        self.history_data = self._load_history()
        
        self._setup_ui()
        
        # 履歴をUIに反映
        self._restore_history_to_ui()
    
    def _load_settings(self):
        try:
            if os.path.exists(SETTINGS_FILE):
                with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
        return {}
    
    def _save_settings(self, new_settings):
        try:
            if not os.path.exists(SETTINGS_DIR):
                os.makedirs(SETTINGS_DIR)
            self.settings.update(new_settings)
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, ensure_ascii=False, indent=2)
        except IOError:
            pass
    
    def _load_history(self):
        """履歴ファイルを読み込む"""
        try:
            if os.path.exists(HISTORY_FILE):
                with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
        return []
    
    def _save_history(self):
        """履歴ファイルを保存する"""
        try:
            if not os.path.exists(SETTINGS_DIR):
                os.makedirs(SETTINGS_DIR)
            with open(HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump(self.history_data, f, ensure_ascii=False, indent=2)
        except IOError:
            pass
    
    def _restore_history_to_ui(self):
        """保存された履歴をUIに反映"""
        for item in self.history_data:
            self.history_tree.insert("", tk.END, values=(
                item.get("time", ""),
                item.get("status", ""),
                item.get("title", "")
            ))
        self._update_tab_counts()
    
    def _setup_ui(self):
        """UIコンポーネントをセットアップ"""
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # === URL入力 + ボタン ===
        input_frame = ttk.Frame(main_frame)
        input_frame.pack(fill=tk.X, pady=(0, 8))
        
        self.url_entry = ttk.Entry(input_frame, font=("", 10))
        self.url_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        self.url_entry.insert(0, "URLを貼り付け...")
        self.url_entry.bind("<FocusIn>", self._on_url_focus_in)
        self.url_entry.bind("<FocusOut>", self._on_url_focus_out)
        self.url_entry.bind("<Return>", lambda e: self._add_to_queue())
        
        ttk.Button(input_frame, text="➕", width=3, command=self._add_to_queue).pack(side=tk.LEFT, padx=2)
        
        self.download_btn = ttk.Button(input_frame, text="▶", width=3, command=self._start_queue_download)
        self.download_btn.pack(side=tk.LEFT, padx=2)
        
        self.cancel_btn = ttk.Button(input_frame, text="⏹", width=3, command=self._cancel_all_downloads, state=tk.DISABLED)
        self.cancel_btn.pack(side=tk.LEFT, padx=2)
        
        ttk.Button(input_frame, text="⚙", width=3, command=self._toggle_settings).pack(side=tk.LEFT, padx=2)
        
        # === 設定パネル（折りたたみ） ===
        self.settings_frame = ttk.LabelFrame(main_frame, text="設定", padding="8")
        
        settings_row1 = ttk.Frame(self.settings_frame)
        settings_row1.pack(fill=tk.X, pady=2)
        
        ttk.Label(settings_row1, text="保存先:").pack(side=tk.LEFT)
        ttk.Entry(settings_row1, textvariable=self.save_path, width=50).pack(side=tk.LEFT, padx=5)
        ttk.Button(settings_row1, text="...", width=3, command=self._browse_folder).pack(side=tk.LEFT)
        
        settings_row2 = ttk.Frame(self.settings_frame)
        settings_row2.pack(fill=tk.X, pady=2)
        
        ttk.Label(settings_row2, text="同時DL:").pack(side=tk.LEFT)
        ttk.Spinbox(settings_row2, from_=1, to=MAX_CONCURRENT_DOWNLOADS, 
                    textvariable=self.concurrent_downloads, width=5,
                    command=lambda: self._save_settings({"concurrent_downloads": self.concurrent_downloads.get()})
        ).pack(side=tk.LEFT, padx=5)
        
        # === 進捗バー ===
        progress_frame = ttk.Frame(main_frame)
        progress_frame.pack(fill=tk.X, pady=(0, 8))
        
        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(progress_frame, variable=self.progress_var, maximum=100)
        self.progress_bar.pack(fill=tk.X)
        
        # === タブ：キュー / 履歴 ===
        self.notebook = ttk.Notebook(main_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)
        
        # キュータブ
        queue_tab = ttk.Frame(self.notebook, padding="5")
        self.notebook.add(queue_tab, text="キュー (0)")
        
        queue_frame = ttk.Frame(queue_tab)
        queue_frame.pack(fill=tk.BOTH, expand=True)
        
        self.queue_tree = ttk.Treeview(
            queue_frame,
            columns=("status", "progress", "title"),
            show="headings",
            height=8
        )
        self.queue_tree.heading("status", text="状態")
        self.queue_tree.heading("progress", text="進捗")
        self.queue_tree.heading("title", text="タイトル/URL")
        self.queue_tree.column("status", width=80, anchor="center")
        self.queue_tree.column("progress", width=60, anchor="center")
        self.queue_tree.column("title", width=450)
        
        queue_scroll = ttk.Scrollbar(queue_frame, orient=tk.VERTICAL, command=self.queue_tree.yview)
        self.queue_tree.configure(yscrollcommand=queue_scroll.set)
        self.queue_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        queue_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        # キュー操作
        queue_btn = ttk.Frame(queue_tab)
        queue_btn.pack(fill=tk.X, pady=(5, 0))
        ttk.Button(queue_btn, text="🗑 削除", command=self._remove_from_queue).pack(side=tk.LEFT, padx=2)
        ttk.Button(queue_btn, text="🧹 クリア", command=self._clear_queue).pack(side=tk.LEFT, padx=2)
        
        # 履歴タブ
        history_tab = ttk.Frame(self.notebook, padding="5")
        self.notebook.add(history_tab, text="履歴 (0)")
        
        history_frame = ttk.Frame(history_tab)
        history_frame.pack(fill=tk.BOTH, expand=True)
        
        self.history_tree = ttk.Treeview(
            history_frame,
            columns=("time", "status", "title"),
            show="headings",
            height=8
        )
        self.history_tree.heading("time", text="時刻")
        self.history_tree.heading("status", text="結果")
        self.history_tree.heading("title", text="タイトル")
        self.history_tree.column("time", width=70, anchor="center")
        self.history_tree.column("status", width=60, anchor="center")
        self.history_tree.column("title", width=460)
        
        history_scroll = ttk.Scrollbar(history_frame, orient=tk.VERTICAL, command=self.history_tree.yview)
        self.history_tree.configure(yscrollcommand=history_scroll.set)
        self.history_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        history_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 履歴操作
        history_btn = ttk.Frame(history_tab)
        history_btn.pack(fill=tk.X, pady=(5, 0))
        ttk.Button(history_btn, text="🧹 クリア", command=self._clear_history).pack(side=tk.LEFT, padx=2)
        
        # === ステータスバー ===
        self.status_var = tk.StringVar(value="準備完了")
        ttk.Label(main_frame, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W, padding="3"
        ).pack(fill=tk.X, pady=(8, 0))
    
    def _toggle_settings(self):
        """設定パネルの表示切り替え"""
        if self.settings_visible.get():
            self.settings_frame.pack_forget()
            self.settings_visible.set(False)
        else:
            self.settings_frame.pack(fill=tk.X, pady=(0, 8), after=self.root.winfo_children()[0].winfo_children()[0])
            self.settings_visible.set(True)
    
    def _on_url_focus_in(self, event):
        if self.url_entry.get() == "URLを貼り付け...":
            self.url_entry.delete(0, tk.END)
    
    def _on_url_focus_out(self, event):
        if not self.url_entry.get():
            self.url_entry.insert(0, "URLを貼り付け...")
    
    def _browse_folder(self):
        folder = filedialog.askdirectory(initialdir=self.save_path.get())
        if folder:
            self.save_path.set(folder)
            self._save_settings({"save_path": folder})
    
    def _update_status(self, msg):
        self.status_var.set(msg)
    
    def _update_tab_counts(self):
        queue_count = len(self.queue_tree.get_children())
        history_count = len(self.history_tree.get_children())
        self.notebook.tab(0, text=f"キュー ({queue_count})")
        self.notebook.tab(1, text=f"履歴 ({history_count})")
    
    def _add_to_queue(self):
        url = self.url_entry.get().strip()
        if not url or url == "URLを貼り付け...":
            self._update_status("❌ URLを入力してください")
            return
        
        with self.queue_lock:
            all_urls = list(self.download_queue) + [t.url for t in self.active_tasks.values()]
            if url in all_urls:
                self._update_status("⚠ 既にキューに存在します")
                return
            self.download_queue.append(url)
        
        self.queue_tree.insert("", tk.END, values=("待機中", "0%", url[:60]))
        self._update_tab_counts()
        self._update_status(f"📋 追加: {url[:40]}...")
        
        self.url_entry.delete(0, tk.END)
        self.url_entry.insert(0, "URLを貼り付け...")
    
    def _remove_from_queue(self):
        selected = self.queue_tree.selection()
        if not selected:
            return
        for item in selected:
            values = self.queue_tree.item(item, "values")
            if values[0] != "DL中":
                self.queue_tree.delete(item)
        self._update_tab_counts()
    
    def _clear_queue(self):
        for item in self.queue_tree.get_children():
            values = self.queue_tree.item(item, "values")
            if values[0] != "DL中":
                self.queue_tree.delete(item)
        with self.queue_lock:
            self.download_queue.clear()
        self._update_tab_counts()
    
    def _clear_history(self):
        for item in self.history_tree.get_children():
            self.history_tree.delete(item)
        self.history_data = []
        self._save_history()
        self._update_tab_counts()
    
    def _add_to_history(self, status, title, url):
        timestamp = datetime.now().strftime("%H:%M")
        display = title if title else url[:50]
        self.history_tree.insert("", 0, values=(timestamp, status, display))
        
        # 履歴データに追加して保存
        self.history_data.insert(0, {
            "time": timestamp,
            "status": status,
            "title": display,
            "url": url
        })
        # 履歴は最大100件に制限
        if len(self.history_data) > 100:
            self.history_data = self.history_data[:100]
        self._save_history()
        self._update_tab_counts()
    
    def _set_downloading_state(self, is_downloading):
        self.is_downloading = is_downloading
        self.download_btn.config(state=tk.DISABLED if is_downloading else tk.NORMAL)
        self.cancel_btn.config(state=tk.NORMAL if is_downloading else tk.DISABLED)
    
    def _cancel_all_downloads(self):
        self.cancel_all_requested = True
        with self.queue_lock:
            for task in self.active_tasks.values():
                task.cancel_requested = True
        self._update_status("⏹ 中止中...")
    
    def _update_queue_item(self, url, status, progress=None):
        for item in self.queue_tree.get_children():
            values = self.queue_tree.item(item, "values")
            if url in values[2]:
                progress_str = f"{progress:.0f}%" if progress is not None else values[1]
                self.queue_tree.item(item, values=(status, progress_str, values[2]))
                break
    
    def _remove_queue_item(self, url):
        for item in self.queue_tree.get_children():
            values = self.queue_tree.item(item, "values")
            if url in values[2]:
                self.queue_tree.delete(item)
                break
        self._update_tab_counts()
    
    def _start_queue_download(self):
        with self.queue_lock:
            if not self.download_queue:
                self._update_status("⚠ キューが空です")
                return
        
        if self.is_downloading:
            return
        
        save_dir = self.save_path.get()
        if not os.path.isdir(save_dir):
            self._update_status("❌ 保存先が存在しません")
            return
        
        self.cancel_all_requested = False
        self.completed_count = 0
        with self.queue_lock:
            self.total_count = len(self.download_queue)
        self.progress_var.set(0)
        self._set_downloading_state(True)
        
        thread = threading.Thread(target=self._process_queue, args=(save_dir,), daemon=True)
        thread.start()
    
    def _process_queue(self, save_dir):
        concurrent = self.concurrent_downloads.get()
        self.executor = ThreadPoolExecutor(max_workers=concurrent)
        futures = []
        
        try:
            while True:
                if self.cancel_all_requested:
                    break
                
                with self.queue_lock:
                    active_count = len(self.active_tasks)
                    queue_empty = len(self.download_queue) == 0
                
                while active_count < concurrent and not queue_empty and not self.cancel_all_requested:
                    with self.queue_lock:
                        if not self.download_queue:
                            break
                        url = self.download_queue.popleft()
                        self.task_id_counter += 1
                        task = DownloadTask(url, self.task_id_counter)
                        self.active_tasks[task.task_id] = task
                        active_count = len(self.active_tasks)
                        queue_empty = len(self.download_queue) == 0
                    
                    self.root.after(0, lambda u=url: self._update_queue_item(u, "DL中", 0))
                    future = self.executor.submit(self._download_video, task, save_dir)
                    futures.append((future, task))
                
                completed_futures = []
                for future, task in futures:
                    if future.done():
                        completed_futures.append((future, task))
                        
                        with self.queue_lock:
                            if task.task_id in self.active_tasks:
                                del self.active_tasks[task.task_id]
                        
                        try:
                            success = future.result()
                            status = "✅" if success else ("⏹" if task.cancel_requested else "❌")
                            self.root.after(0, lambda u=task.url: self._remove_queue_item(u))
                            self.root.after(0, lambda s=status, t=task.title, u=task.url: self._add_to_history(s, t, u))
                        except:
                            self.root.after(0, lambda u=task.url: self._remove_queue_item(u))
                            self.root.after(0, lambda u=task.url: self._add_to_history("❌", "", u))
                        
                        self.completed_count += 1
                        if self.total_count > 0:
                            self.root.after(0, lambda: self.progress_var.set((self.completed_count / self.total_count) * 100))
                
                for cf in completed_futures:
                    futures.remove(cf)
                
                with self.queue_lock:
                    if not self.download_queue and not self.active_tasks:
                        break
                
                threading.Event().wait(0.1)
            
        finally:
            self.executor.shutdown(wait=True)
            self.executor = None
            self.root.after(0, lambda: self._set_downloading_state(False))
            self.root.after(0, lambda: self._update_status("✅ 完了" if not self.cancel_all_requested else "⏹ 中止"))
            self.cancel_all_requested = False
    
    def _progress_hook(self, task, d):
        if task.cancel_requested:
            raise yt_dlp.utils.DownloadCancelled("中止")
        
        status = d.get('status', '')
        if status == 'downloading':
            downloaded = d.get('downloaded_bytes', 0)
            total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
            fragment_index = d.get('fragment_index')
            fragment_count = d.get('fragment_count')
            
            percent = None
            if total > 0:
                percent = (downloaded / total) * 100
            elif fragment_index and fragment_count and fragment_count > 0:
                percent = (fragment_index / fragment_count) * 100
            elif '_percent_str' in d:
                try:
                    percent = float(d.get('_percent_str', '0').strip().replace('%', ''))
                except:
                    pass
            
            if percent is not None:
                task.progress = percent
                self.root.after(0, lambda u=task.url, p=percent: self._update_queue_item(u, "DL中", p))
        
        elif status == 'finished':
            task.progress = 100
            self.root.after(0, lambda u=task.url: self._update_queue_item(u, "変換中", 100))
    
    def _download_video(self, task, save_dir):
        self.root.after(0, lambda: self._update_status(f"⬇ {task.url[:50]}..."))
        
        ydl_opts = {
            'format': 'bestvideo+bestaudio/best',
            'merge_output_format': 'mp4',
            'outtmpl': os.path.join(save_dir, '%(title)s.%(ext)s'),
            'progress_hooks': [lambda d: self._progress_hook(task, d)],
            'overwrites': True,
            'quiet': True,
            'no_warnings': True,
            'hls_prefer_native': False,
            'fragment_retries': 10,
            'retries': 10,
            'socket_timeout': 30,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            },
            'postprocessors': [{'key': 'FFmpegVideoConvertor', 'preferedformat': 'mp4'}],
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                task.current_ydl = ydl
                if task.cancel_requested:
                    raise yt_dlp.utils.DownloadCancelled("中止")
                
                info = ydl.extract_info(task.url, download=False)
                task.title = info.get('title', '不明')
                
                if task.cancel_requested:
                    raise yt_dlp.utils.DownloadCancelled("中止")
                
                ydl.download([task.url])
            
            if not task.cancel_requested:
                self.root.after(0, lambda t=task.title: self._update_status(f"✅ {t[:40]}"))
                return True
        
        except yt_dlp.utils.DownloadCancelled:
            return False
        except Exception as e:
            self.root.after(0, lambda: self._update_status(f"❌ エラー: {str(e)[:40]}"))
            return False
        finally:
            task.current_ydl = None
        
        return False


def main():
    root = tk.Tk()
    style = ttk.Style()
    style.configure("Accent.TButton", font=("", 11, "bold"))
    app = VideoDownloaderApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
