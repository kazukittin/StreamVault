"""
シンプル動画ダウンローダー
Lulustream等の動画サイトからmp4形式で動画をダウンロードするGUIアプリ
"""

import os
import json
import threading
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext
from datetime import datetime
from collections import deque

try:
    import yt_dlp
except ImportError:
    print("yt-dlpがインストールされていません。以下のコマンドを実行してください:")
    print("pip install yt-dlp")
    exit(1)

# 設定ファイルのパス
SETTINGS_DIR = os.path.join(os.path.expanduser("~"), ".video_downloader")
SETTINGS_FILE = os.path.join(SETTINGS_DIR, "settings.json")


class VideoDownloaderApp:
    def __init__(self, root):
        self.root = root
        self.root.title("動画ダウンローダー")
        self.root.geometry("750x700")
        self.root.minsize(650, 600)
        
        # 設定を読み込む
        self.settings = self._load_settings()
        
        # 保存先（設定から読み込み、なければ現在のディレクトリ）
        default_save_path = self.settings.get("save_path", os.getcwd())
        # 保存先が存在しない場合は現在のディレクトリにフォールバック
        if not os.path.isdir(default_save_path):
            default_save_path = os.getcwd()
        self.save_path = tk.StringVar(value=default_save_path)
        
        # ダウンロード中フラグ
        self.is_downloading = False
        # 中止フラグ
        self.cancel_requested = False
        # 全キャンセルフラグ
        self.cancel_all_requested = False
        # 現在のyt-dlpプロセス
        self.current_ydl = None
        
        # ダウンロードキュー
        self.download_queue = deque()
        # キューのロック（スレッドセーフ用）
        self.queue_lock = threading.Lock()
        
        self._setup_ui()
    
    def _load_settings(self):
        """設定ファイルを読み込む"""
        try:
            if os.path.exists(SETTINGS_FILE):
                with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"設定ファイルの読み込みに失敗しました: {e}")
        return {}
    
    def _save_settings(self, new_settings):
        """設定ファイルを保存する"""
        try:
            # 設定ディレクトリがなければ作成
            if not os.path.exists(SETTINGS_DIR):
                os.makedirs(SETTINGS_DIR)
            
            # 既存の設定を読み込んで更新
            self.settings.update(new_settings)
            
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, ensure_ascii=False, indent=2)
        except IOError as e:
            print(f"設定ファイルの保存に失敗しました: {e}")
    
    def _setup_ui(self):
        """UIコンポーネントをセットアップ"""
        # メインフレーム
        main_frame = ttk.Frame(self.root, padding="15")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # タイトル
        title_label = ttk.Label(
            main_frame, 
            text="🎬 動画ダウンローダー", 
            font=("", 16, "bold")
        )
        title_label.pack(pady=(0, 15))
        
        # URL入力セクション
        url_frame = ttk.LabelFrame(main_frame, text="動画URL", padding="10")
        url_frame.pack(fill=tk.X, pady=(0, 10))
        
        url_inner = ttk.Frame(url_frame)
        url_inner.pack(fill=tk.X, pady=5)
        
        self.url_entry = ttk.Entry(url_inner, font=("", 10))
        self.url_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        self.url_entry.insert(0, "ここに動画のURLを貼り付け...")
        self.url_entry.bind("<FocusIn>", self._on_url_focus_in)
        self.url_entry.bind("<FocusOut>", self._on_url_focus_out)
        self.url_entry.bind("<Return>", lambda e: self._add_to_queue())
        
        # キューに追加ボタン
        self.add_queue_btn = ttk.Button(
            url_inner,
            text="➕ キューに追加",
            command=self._add_to_queue
        )
        self.add_queue_btn.pack(side=tk.RIGHT)
        
        # 保存先セクション
        save_frame = ttk.LabelFrame(main_frame, text="保存先フォルダ", padding="10")
        save_frame.pack(fill=tk.X, pady=(0, 10))
        
        save_inner = ttk.Frame(save_frame)
        save_inner.pack(fill=tk.X, pady=5)
        
        self.path_entry = ttk.Entry(save_inner, textvariable=self.save_path, font=("", 10))
        self.path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        
        browse_btn = ttk.Button(save_inner, text="参照...", command=self._browse_folder)
        browse_btn.pack(side=tk.RIGHT)
        
        # ダウンロードキューセクション
        queue_frame = ttk.LabelFrame(main_frame, text="ダウンロードキュー", padding="10")
        queue_frame.pack(fill=tk.X, pady=(0, 10))
        
        # キューリスト
        queue_list_frame = ttk.Frame(queue_frame)
        queue_list_frame.pack(fill=tk.X, pady=5)
        
        # Treeview for queue
        self.queue_tree = ttk.Treeview(
            queue_list_frame,
            columns=("status", "url"),
            show="headings",
            height=4,
            selectmode="browse"
        )
        self.queue_tree.heading("status", text="状態")
        self.queue_tree.heading("url", text="URL")
        self.queue_tree.column("status", width=80, anchor="center")
        self.queue_tree.column("url", width=550)
        
        # スクロールバー
        queue_scrollbar = ttk.Scrollbar(queue_list_frame, orient=tk.VERTICAL, command=self.queue_tree.yview)
        self.queue_tree.configure(yscrollcommand=queue_scrollbar.set)
        
        self.queue_tree.pack(side=tk.LEFT, fill=tk.X, expand=True)
        queue_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # キュー操作ボタン
        queue_btn_frame = ttk.Frame(queue_frame)
        queue_btn_frame.pack(fill=tk.X, pady=(10, 0))
        
        self.remove_btn = ttk.Button(
            queue_btn_frame,
            text="🗑 選択を削除",
            command=self._remove_from_queue
        )
        self.remove_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        self.clear_queue_btn = ttk.Button(
            queue_btn_frame,
            text="🧹 キューをクリア",
            command=self._clear_queue
        )
        self.clear_queue_btn.pack(side=tk.LEFT)
        
        # キューカウンター
        self.queue_count_var = tk.StringVar(value="キュー: 0件")
        queue_count_label = ttk.Label(queue_btn_frame, textvariable=self.queue_count_var)
        queue_count_label.pack(side=tk.RIGHT)
        
        # ボタンセクション
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(pady=15)
        
        # ダウンロード開始ボタン
        self.download_btn = ttk.Button(
            btn_frame, 
            text="▶ ダウンロード開始", 
            command=self._start_queue_download,
            style="Accent.TButton"
        )
        self.download_btn.pack(side=tk.LEFT, ipadx=20, ipady=5, padx=(0, 10))
        
        # 中止ボタン
        self.cancel_btn = ttk.Button(
            btn_frame, 
            text="⏹ 現在のを中止", 
            command=self._cancel_download,
            state=tk.DISABLED
        )
        self.cancel_btn.pack(side=tk.LEFT, ipadx=15, ipady=5, padx=(0, 10))
        
        # 全て中止ボタン
        self.cancel_all_btn = ttk.Button(
            btn_frame, 
            text="⏹ 全て中止", 
            command=self._cancel_all_downloads,
            state=tk.DISABLED
        )
        self.cancel_all_btn.pack(side=tk.LEFT, ipadx=15, ipady=5)
        
        # プログレスバーセクション
        progress_frame = ttk.Frame(main_frame)
        progress_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(
            progress_frame, 
            variable=self.progress_var,
            maximum=100,
            mode='determinate',
            length=400
        )
        self.progress_bar.pack(fill=tk.X)
        
        self.progress_label = ttk.Label(progress_frame, text="0%", font=("", 9))
        self.progress_label.pack(pady=(5, 0))
        
        # ログ表示セクション
        log_frame = ttk.LabelFrame(main_frame, text="ログ", padding="10")
        log_frame.pack(fill=tk.BOTH, expand=True)
        
        self.log_area = scrolledtext.ScrolledText(
            log_frame, 
            height=8, 
            font=("Consolas", 9),
            state=tk.DISABLED,
            wrap=tk.WORD
        )
        self.log_area.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # ステータスバー
        self.status_var = tk.StringVar(value="準備完了")
        status_bar = ttk.Label(
            main_frame, 
            textvariable=self.status_var, 
            relief=tk.SUNKEN, 
            anchor=tk.W,
            padding="5"
        )
        status_bar.pack(fill=tk.X, pady=(10, 0))
        
        self._log("アプリケーションを起動しました。動画URLを入力してキューに追加してください。")
    
    def _on_url_focus_in(self, event):
        """URLエントリーにフォーカスが当たった時"""
        if self.url_entry.get() == "ここに動画のURLを貼り付け...":
            self.url_entry.delete(0, tk.END)
    
    def _on_url_focus_out(self, event):
        """URLエントリーからフォーカスが外れた時"""
        if not self.url_entry.get():
            self.url_entry.insert(0, "ここに動画のURLを貼り付け...")
    
    def _browse_folder(self):
        """フォルダ選択ダイアログを開く"""
        folder = filedialog.askdirectory(initialdir=self.save_path.get())
        if folder:
            self.save_path.set(folder)
            self._save_settings({"save_path": folder})
            self._log(f"保存先を変更: {folder}")
    
    def _log(self, message):
        """ログエリアにメッセージを追加"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_area.config(state=tk.NORMAL)
        self.log_area.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_area.see(tk.END)
        self.log_area.config(state=tk.DISABLED)
    
    def _update_status(self, status):
        """ステータスバーを更新"""
        self.status_var.set(status)
    
    def _update_progress(self, percent):
        """プログレスバーを更新"""
        self.progress_var.set(percent)
        self.progress_label.config(text=f"{percent:.1f}%")
    
    def _reset_progress(self):
        """プログレスバーをリセット"""
        self.progress_var.set(0)
        self.progress_label.config(text="0%")
    
    def _update_queue_count(self):
        """キューカウンターを更新"""
        with self.queue_lock:
            count = len(self.download_queue)
        self.queue_count_var.set(f"キュー: {count}件")
    
    def _add_to_queue(self):
        """URLをキューに追加"""
        url = self.url_entry.get().strip()
        
        # バリデーション
        if not url or url == "ここに動画のURLを貼り付け...":
            self._log("❌ エラー: URLを入力してください。")
            return
        
        # 重複チェック
        with self.queue_lock:
            if url in self.download_queue:
                self._log("⚠ このURLは既にキューに存在します。")
                return
            
            self.download_queue.append(url)
        
        # TreeViewに追加
        self.queue_tree.insert("", tk.END, values=("待機中", url))
        
        self._update_queue_count()
        self._log(f"📋 キューに追加: {url[:50]}...")
        
        # URL入力欄をクリア
        self.url_entry.delete(0, tk.END)
        self.url_entry.insert(0, "ここに動画のURLを貼り付け...")
    
    def _remove_from_queue(self):
        """選択されたアイテムをキューから削除"""
        selected = self.queue_tree.selection()
        if not selected:
            self._log("⚠ 削除するアイテムを選択してください。")
            return
        
        for item in selected:
            values = self.queue_tree.item(item, "values")
            url = values[1]
            status = values[0]
            
            # ダウンロード中のアイテムは削除できない
            if status == "ダウンロード中":
                self._log("⚠ ダウンロード中のアイテムは削除できません。")
                continue
            
            with self.queue_lock:
                if url in self.download_queue:
                    self.download_queue.remove(url)
            
            self.queue_tree.delete(item)
            self._log(f"🗑 キューから削除: {url[:50]}...")
        
        self._update_queue_count()
    
    def _clear_queue(self):
        """待機中のアイテムを全てクリア"""
        items_to_delete = []
        for item in self.queue_tree.get_children():
            values = self.queue_tree.item(item, "values")
            if values[0] != "ダウンロード中":
                items_to_delete.append((item, values[1]))
        
        with self.queue_lock:
            for item, url in items_to_delete:
                if url in self.download_queue:
                    self.download_queue.remove(url)
                self.queue_tree.delete(item)
        
        self._update_queue_count()
        self._log("🧹 待機中のキューをクリアしました。")
    
    def _set_downloading_state(self, is_downloading):
        """ダウンロード中の状態を設定"""
        self.is_downloading = is_downloading
        if is_downloading:
            self.download_btn.config(state=tk.DISABLED)
            self.cancel_btn.config(state=tk.NORMAL)
            self.cancel_all_btn.config(state=tk.NORMAL)
        else:
            self.download_btn.config(state=tk.NORMAL)
            self.cancel_btn.config(state=tk.DISABLED)
            self.cancel_all_btn.config(state=tk.DISABLED)
    
    def _cancel_download(self):
        """現在のダウンロードを中止"""
        if self.is_downloading:
            self.cancel_requested = True
            self._log("⚠ 現在のダウンロードを中止しています...")
            self._update_status("中止中...")
    
    def _cancel_all_downloads(self):
        """全てのダウンロードを中止"""
        if self.is_downloading:
            self.cancel_requested = True
            self.cancel_all_requested = True
            self._log("⚠ 全てのダウンロードを中止しています...")
            self._update_status("全て中止中...")
    
    def _update_queue_item_status(self, url, status):
        """キューアイテムの状態を更新"""
        for item in self.queue_tree.get_children():
            values = self.queue_tree.item(item, "values")
            if values[1] == url:
                self.queue_tree.item(item, values=(status, url))
                break
    
    def _remove_queue_item(self, url):
        """キューアイテムを削除"""
        for item in self.queue_tree.get_children():
            values = self.queue_tree.item(item, "values")
            if values[1] == url:
                self.queue_tree.delete(item)
                break
    
    def _start_queue_download(self):
        """キューのダウンロードを開始"""
        with self.queue_lock:
            if not self.download_queue:
                self._log("⚠ キューにダウンロードするアイテムがありません。")
                return
        
        if self.is_downloading:
            self._log("⚠ 現在ダウンロード中です。完了までお待ちください。")
            return
        
        save_dir = self.save_path.get()
        if not os.path.isdir(save_dir):
            self._log(f"❌ エラー: 保存先フォルダが存在しません: {save_dir}")
            return
        
        # 状態をリセット
        self.cancel_requested = False
        self.cancel_all_requested = False
        self._reset_progress()
        self._set_downloading_state(True)
        
        # ダウンロードスレッドを開始
        thread = threading.Thread(target=self._process_queue, args=(save_dir,), daemon=True)
        thread.start()
    
    def _process_queue(self, save_dir):
        """キューを順番に処理"""
        while True:
            # 全キャンセルがリクエストされた場合
            if self.cancel_all_requested:
                self.root.after(0, lambda: self._log("🛑 全てのダウンロードが中止されました。"))
                break
            
            # キューから次のURLを取得
            with self.queue_lock:
                if not self.download_queue:
                    break
                url = self.download_queue[0]
            
            # ダウンロード実行
            self.root.after(0, lambda u=url: self._update_queue_item_status(u, "ダウンロード中"))
            self.root.after(0, lambda: self._reset_progress())
            
            success = self._download_video(url, save_dir)
            
            # キューから削除
            with self.queue_lock:
                if url in self.download_queue:
                    self.download_queue.popleft()
            
            if success:
                self.root.after(0, lambda u=url: self._update_queue_item_status(u, "✅ 完了"))
            elif self.cancel_requested and not self.cancel_all_requested:
                self.root.after(0, lambda u=url: self._update_queue_item_status(u, "⏹ 中止"))
            else:
                self.root.after(0, lambda u=url: self._update_queue_item_status(u, "❌ エラー"))
            
            self.root.after(0, self._update_queue_count)
            
            # 次のダウンロードのためにリセット
            self.cancel_requested = False
            
            # キャンセルされた場合は終了
            if self.cancel_all_requested:
                break
        
        # すべて完了
        self.root.after(0, lambda: self._set_downloading_state(False))
        self.root.after(0, lambda: self._update_status("完了" if not self.cancel_all_requested else "中止"))
        self.root.after(0, lambda: self._log("📦 キューの処理が完了しました。"))
        self.cancel_all_requested = False
    
    def _progress_hook(self, d):
        """yt-dlpの進捗をハンドリング"""
        # 中止がリクエストされた場合
        if self.cancel_requested:
            raise yt_dlp.utils.DownloadCancelled("ユーザーによって中止されました")
        
        status = d.get('status', '')
        
        if status == 'downloading':
            downloaded = d.get('downloaded_bytes', 0)
            total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
            speed = d.get('speed', 0)
            speed_str = f"{speed / 1024 / 1024:.1f} MB/s" if speed else "計算中..."
            
            # フラグメント情報を取得（HLS/m3u8の場合）
            fragment_index = d.get('fragment_index')
            fragment_count = d.get('fragment_count')
            
            percent = None
            
            # 方法1: 通常のバイト単位での進捗計算
            if total > 0:
                percent = (downloaded / total) * 100
            
            # 方法2: フラグメント単位での進捗計算（HLS/m3u8）
            elif fragment_index is not None and fragment_count is not None and fragment_count > 0:
                percent = (fragment_index / fragment_count) * 100
            
            # 方法3: ダウンロード済みバイト数と推定進捗
            elif '_percent_str' in d:
                try:
                    percent_str = d.get('_percent_str', '0%').strip().replace('%', '')
                    percent = float(percent_str)
                except (ValueError, AttributeError):
                    pass
            
            # 進捗を更新
            if percent is not None:
                downloaded_mb = downloaded / 1024 / 1024
                if fragment_index is not None and fragment_count is not None:
                    status_text = f"ダウンロード中: {percent:.1f}% (フラグメント {fragment_index}/{fragment_count}) [{speed_str}]"
                else:
                    status_text = f"ダウンロード中: {percent:.1f}% ({downloaded_mb:.1f} MB) [{speed_str}]"
                
                self.root.after(0, lambda p=percent: self._update_progress(p))
                self.root.after(0, lambda s=status_text: self._update_status(s))
            else:
                # 進捗率が取得できない場合はダウンロード量のみ表示
                downloaded_mb = downloaded / 1024 / 1024
                if fragment_index is not None:
                    status_text = f"ダウンロード中: フラグメント {fragment_index} ({downloaded_mb:.1f} MB) [{speed_str}]"
                else:
                    status_text = f"ダウンロード中: {downloaded_mb:.1f} MB [{speed_str}]"
                self.root.after(0, lambda s=status_text: self._update_status(s))
        
        elif status == 'finished':
            filename = d.get('filename', '')
            self.root.after(0, lambda: self._update_progress(100))
            self.root.after(0, lambda: self._log(f"📥 ダウンロード完了: {os.path.basename(filename)}"))
            self.root.after(0, lambda: self._update_status("変換中..."))
        
        elif status == 'error':
            self.root.after(0, lambda: self._log("❌ ダウンロード中にエラーが発生しました"))
    
    def _download_video(self, url, save_dir):
        """動画をダウンロード（別スレッドで実行）"""
        self.root.after(0, lambda: self._log(f"🔗 URL: {url}"))
        self.root.after(0, lambda: self._log("📂 動画情報を取得中..."))
        
        # yt-dlpの設定
        ydl_opts = {
            # 最高画質で動画と音声を取得
            'format': 'bestvideo+bestaudio/best',
            # mp4形式で出力
            'merge_output_format': 'mp4',
            # 出力ファイル名テンプレート
            'outtmpl': os.path.join(save_dir, '%(title)s.%(ext)s'),
            # 進捗フック
            'progress_hooks': [self._progress_hook],
            # 既存ファイルの上書き確認なし
            'overwrites': True,
            # ログ出力を抑制
            'quiet': True,
            'no_warnings': True,
            # HLS/m3u8ストリーム対応
            'hls_prefer_native': False,
            # フラグメントのリトライ回数
            'fragment_retries': 10,
            # 接続リトライ回数
            'retries': 10,
            # ネットワークタイムアウト
            'socket_timeout': 30,
            # User-Agent設定（一部サイト対策）
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'ja,en-US;q=0.7,en;q=0.3',
            },
            # postprocessors（mp4への変換用）
            'postprocessors': [{
                'key': 'FFmpegVideoConvertor',
                'preferedformat': 'mp4',
            }],
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                self.current_ydl = ydl
                
                # 中止チェック
                if self.cancel_requested:
                    raise yt_dlp.utils.DownloadCancelled("ユーザーによって中止されました")
                
                # 動画情報を取得
                info = ydl.extract_info(url, download=False)
                title = info.get('title', '不明なタイトル')
                duration = info.get('duration', 0)
                duration_str = f"{duration // 60}分{duration % 60}秒" if duration else "不明"
                
                self.root.after(0, lambda: self._log(f"📹 タイトル: {title}"))
                self.root.after(0, lambda: self._log(f"⏱ 長さ: {duration_str}"))
                self.root.after(0, lambda: self._log("⬇ ダウンロードを開始します..."))
                
                # 中止チェック
                if self.cancel_requested:
                    raise yt_dlp.utils.DownloadCancelled("ユーザーによって中止されました")
                
                # ダウンロード実行
                ydl.download([url])
            
            if not self.cancel_requested:
                self.root.after(0, lambda: self._log("✅ ダウンロードが正常に完了しました！"))
                return True
        
        except yt_dlp.utils.DownloadCancelled:
            self.root.after(0, lambda: self._log("🛑 ダウンロードが中止されました"))
            self.root.after(0, lambda: self._reset_progress())
            return False
        except yt_dlp.utils.DownloadError as e:
            error_msg = str(e)
            self.root.after(0, lambda: self._log(f"❌ ダウンロードエラー: {error_msg}"))
            return False
        except Exception as e:
            error_msg = str(e)
            if "中止" not in error_msg and "cancel" not in error_msg.lower():
                self.root.after(0, lambda: self._log(f"❌ 予期せぬエラー: {error_msg}"))
            else:
                self.root.after(0, lambda: self._log("🛑 ダウンロードが中止されました"))
            return False
        finally:
            self.current_ydl = None
        
        return False


def main():
    root = tk.Tk()
    
    # スタイル設定
    style = ttk.Style()
    style.configure("Accent.TButton", font=("", 11, "bold"))
    
    app = VideoDownloaderApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
