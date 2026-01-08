"""
シンプル動画ダウンローダー
Lulustream等の動画サイトからmp4形式で動画をダウンロードするGUIアプリ
"""

import os
import threading
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext
from datetime import datetime

try:
    import yt_dlp
except ImportError:
    print("yt-dlpがインストールされていません。以下のコマンドを実行してください:")
    print("pip install yt-dlp")
    exit(1)


class VideoDownloaderApp:
    def __init__(self, root):
        self.root = root
        self.root.title("動画ダウンローダー")
        self.root.geometry("700x550")
        self.root.minsize(600, 450)
        
        # デフォルトの保存先
        self.save_path = tk.StringVar(value=os.getcwd())
        
        # ダウンロード中フラグ
        self.is_downloading = False
        # 中止フラグ
        self.cancel_requested = False
        # 現在のyt-dlpプロセス
        self.current_ydl = None
        
        self._setup_ui()
    
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
        
        self.url_entry = ttk.Entry(url_frame, font=("", 10))
        self.url_entry.pack(fill=tk.X, pady=5)
        self.url_entry.insert(0, "ここに動画のURLを貼り付け...")
        self.url_entry.bind("<FocusIn>", self._on_url_focus_in)
        self.url_entry.bind("<FocusOut>", self._on_url_focus_out)
        
        # 保存先セクション
        save_frame = ttk.LabelFrame(main_frame, text="保存先フォルダ", padding="10")
        save_frame.pack(fill=tk.X, pady=(0, 10))
        
        save_inner = ttk.Frame(save_frame)
        save_inner.pack(fill=tk.X, pady=5)
        
        self.path_entry = ttk.Entry(save_inner, textvariable=self.save_path, font=("", 10))
        self.path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        
        browse_btn = ttk.Button(save_inner, text="参照...", command=self._browse_folder)
        browse_btn.pack(side=tk.RIGHT)
        
        # ボタンセクション
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(pady=15)
        
        # ダウンロードボタン
        self.download_btn = ttk.Button(
            btn_frame, 
            text="▶ ダウンロード開始", 
            command=self._start_download,
            style="Accent.TButton"
        )
        self.download_btn.pack(side=tk.LEFT, ipadx=20, ipady=5, padx=(0, 10))
        
        # 中止ボタン
        self.cancel_btn = ttk.Button(
            btn_frame, 
            text="⏹ 中止", 
            command=self._cancel_download,
            state=tk.DISABLED
        )
        self.cancel_btn.pack(side=tk.LEFT, ipadx=15, ipady=5)
        
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
            height=10, 
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
        
        self._log("アプリケーションを起動しました。動画URLを入力してダウンロードを開始してください。")
    
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
    
    def _set_downloading_state(self, is_downloading):
        """ダウンロード中の状態を設定"""
        self.is_downloading = is_downloading
        if is_downloading:
            self.download_btn.config(state=tk.DISABLED)
            self.cancel_btn.config(state=tk.NORMAL)
        else:
            self.download_btn.config(state=tk.NORMAL)
            self.cancel_btn.config(state=tk.DISABLED)
    
    def _cancel_download(self):
        """ダウンロードを中止"""
        if self.is_downloading:
            self.cancel_requested = True
            self._log("⚠ 中止をリクエストしました。処理を停止しています...")
            self._update_status("中止中...")
    
    def _start_download(self):
        """ダウンロードを開始（別スレッドで実行）"""
        url = self.url_entry.get().strip()
        
        # バリデーション
        if not url or url == "ここに動画のURLを貼り付け...":
            self._log("❌ エラー: URLを入力してください。")
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
        self._reset_progress()
        self._set_downloading_state(True)
        self._update_status("ダウンロード中...")
        
        thread = threading.Thread(target=self._download_video, args=(url, save_dir), daemon=True)
        thread.start()
    
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
            
            if total > 0:
                percent = (downloaded / total) * 100
                speed_str = f"{speed / 1024 / 1024:.1f} MB/s" if speed else "計算中..."
                self.root.after(0, lambda p=percent: self._update_progress(p))
                self.root.after(0, lambda: self._update_status(
                    f"ダウンロード中: {percent:.1f}% ({speed_str})"
                ))
            else:
                downloaded_mb = downloaded / 1024 / 1024
                self.root.after(0, lambda: self._update_status(
                    f"ダウンロード中: {downloaded_mb:.1f} MB"
                ))
        
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
                self.root.after(0, lambda: self._update_status("完了"))
        
        except yt_dlp.utils.DownloadCancelled:
            self.root.after(0, lambda: self._log("🛑 ダウンロードが中止されました"))
            self.root.after(0, lambda: self._update_status("中止"))
            self.root.after(0, lambda: self._reset_progress())
        except yt_dlp.utils.DownloadError as e:
            error_msg = str(e)
            self.root.after(0, lambda: self._log(f"❌ ダウンロードエラー: {error_msg}"))
            self.root.after(0, lambda: self._update_status("エラー"))
        except Exception as e:
            error_msg = str(e)
            if "中止" not in error_msg and "cancel" not in error_msg.lower():
                self.root.after(0, lambda: self._log(f"❌ 予期せぬエラー: {error_msg}"))
                self.root.after(0, lambda: self._update_status("エラー"))
            else:
                self.root.after(0, lambda: self._log("🛑 ダウンロードが中止されました"))
                self.root.after(0, lambda: self._update_status("中止"))
        finally:
            self.current_ydl = None
            self.cancel_requested = False
            self.root.after(0, lambda: self._set_downloading_state(False))


def main():
    root = tk.Tk()
    
    # スタイル設定
    style = ttk.Style()
    style.configure("Accent.TButton", font=("", 11, "bold"))
    
    app = VideoDownloaderApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
