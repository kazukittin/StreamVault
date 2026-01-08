# 🎬 動画ダウンローダー

Lulustream等の動画サイトからMP4形式で動画をダウンロードするシンプルなGUIアプリケーション。

## 📋 必要条件

- Python 3.8以上
- FFmpeg（mp4への変換に必要）

## 🚀 インストール

### 1. 依存パッケージのインストール

```bash
pip install yt-dlp
```

### 2. FFmpegのインストール（Windowsの場合）

以下のいずれかの方法でインストール:

**方法A: wingetを使用（推奨）**
```bash
winget install FFmpeg
```

**方法B: Chocolateyを使用**
```bash
choco install ffmpeg
```

**方法C: 手動インストール**
1. [FFmpeg公式サイト](https://ffmpeg.org/download.html)からダウンロード
2. 解凍してPATHを通す

## 💡 使い方

1. アプリを起動:
   ```bash
   python video_downloader.py
   ```

2. **URL入力欄**に動画のURLを貼り付け

3. **参照ボタン**で保存先フォルダを選択（オプション）

4. **ダウンロード開始**ボタンをクリック

5. ログエリアで進捗を確認

## ✨ 機能

- 🎥 最高画質でダウンロード（bestvideo+bestaudio）
- 📁 保存先フォルダの選択
- 📊 リアルタイム進捗表示
- 🔄 HLS/m3u8ストリーム対応
- 🎭 MP4形式への自動変換
- 🖥️ GUIがフリーズしない非同期処理

## 🛠️ 対応サイト

yt-dlpがサポートする1000以上のサイトに対応（一部例）:
- Lulustream
- YouTube
- Vimeo
- Dailymotion
- その他多数

## ⚠️ 注意事項

- 著作権法を遵守してご使用ください
- 個人利用の範囲内でお使いください
- 一部のサイトでは地域制限やアクセス制限がある場合があります
