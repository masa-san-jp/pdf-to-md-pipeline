# 設計仕様書 vol.2：Google Colab版（共同作業用）

**作成日**: 2026-04-17  
**対象環境**: Google Colaboratory + Google Drive  
**スキャンPDF対応**: ✅ hybridモード（Colabランタイム上でOCR）  
**共同作業**: ✅ Driveフォルダ共有で複数人が使用可能

-----

## 1. 概要

Google DriveをストレージとしてColabノートブックで変換処理を実行する構成。
PC環境を選ばずブラウザのみで動作し、チームメンバー全員がDriveフォルダを通じて協働できる。
スクリプトのインストール不要。「ノートブックを開いて実行する」だけで使える。

**制約**: 定期自動実行は原則不可（Colabセッションは手動起動が前提）。
ただしColab Pro+ の「スケジュール実行」機能を利用すれば定期実行も可能。

-----

## 2. Googleドライブフォルダ構成

```
マイドライブ/
└── pdf-to-markdown/           # 共有ドライブフォルダ（チームで共有）
    ├── input/                 # 作業フォルダ：PDFをアップロードする
    │   ├── single.pdf
    │   └── 001_まとめフォルダ/
    │       ├── 01_intro.pdf
    │       └── 02_body.pdf
    ├── output/                # 成果物フォルダ：変換済みMarkdown
    ├── done/                  # 作業済みフォルダ
    ├── logs/                  # 処理ログ
    └── pdf_to_markdown.ipynb  # ← 実行ノートブック（このファイルを開く）
```

-----

## 3. 処理フロー

```
[ユーザー] ブラウザでノートブックを開く
    │
    ▼
セル1: 初期セットアップ
    ├─ Java + opendataloader-pdf インストール（Colabランタイムに）
    └─ hybridバックエンド起動（OCR用）
    │
    ▼
セル2: Googleドライブのマウント
    └─ /content/drive/ に Drive をマウント
    │
    ▼
セル3: 変換実行
    ├─ input/ を走査
    ├─ PDF → Markdown変換（テキスト/スキャン自動判定）
    ├─ output/ に保存
    └─ done/ に移動
    │
    ▼
セル4: 完了サマリー表示
    └─ 処理件数・失敗件数・出力ファイル一覧
```

-----

## 4. ノートブック仕様（pdf_to_markdown.ipynb）

### セル1：セットアップ（初回・ランタイム再起動後に実行）

```python
# ① Java インストール
import subprocess
subprocess.run(["apt-get", "install", "-y", "default-jdk"], check=True)

# ② opendataloader-pdf インストール
subprocess.run(
    ["pip", "install", "opendataloader-pdf[hybrid]", "-q"],
    check=True
)

# ③ hybridバックエンド起動（OCR用）
import threading, time

def start_hybrid():
    subprocess.run([
        "opendataloader-pdf-hybrid",
        "--port", "5002",
        "--ocr-lang", "ja,en"
    ])

t = threading.Thread(target=start_hybrid, daemon=True)
t.start()
time.sleep(10)  # バックエンド起動待機
print("✅ セットアップ完了")
```

### セル2：Googleドライブのマウント

```python
from google.colab import drive
drive.mount("/content/drive")

# フォルダパス設定（Drive上のフォルダ名に合わせて変更）
BASE_DIR = "/content/drive/MyDrive/pdf-to-markdown"
INPUT_DIR  = f"{BASE_DIR}/input"
OUTPUT_DIR = f"{BASE_DIR}/output"
DONE_DIR   = f"{BASE_DIR}/done"
LOG_DIR    = f"{BASE_DIR}/logs"

import os
for d in [OUTPUT_DIR, DONE_DIR, LOG_DIR]:
    os.makedirs(d, exist_ok=True)

print("✅ Driveマウント完了")
```

### セル3：変換実行

```python
import opendataloader_pdf
import shutil
from pathlib import Path
from datetime import datetime

def convert_and_move(input_path, output_dir, done_dir, is_folder=False):
    stem = Path(input_path).stem
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    if is_folder:
        pdfs = sorted(Path(input_path).glob("*.pdf"))
        # フォルダ内PDFを一括変換して結合
        tmp_dir = f"/content/tmp_{stem}"
        os.makedirs(tmp_dir, exist_ok=True)
        opendataloader_pdf.convert(
            input_path=[str(p) for p in pdfs],
            output_dir=tmp_dir,
            format="markdown",
            hybrid="docling-fast",
            use_struct_tree=True,
        )
        # Markdown結合
        combined = ""
        for p in sorted(Path(tmp_dir).glob("*.md")):
            combined += p.read_text() + "\n\n---\n\n"
        Path(output_dir, f"{stem}.md").write_text(combined)
        shutil.rmtree(tmp_dir)
        shutil.move(input_path, f"{done_dir}/{stem}_{timestamp}")
    else:
        opendataloader_pdf.convert(
            input_path=[input_path],
            output_dir=output_dir,
            format="markdown",
            hybrid="docling-fast",
            use_struct_tree=True,
        )
        shutil.move(input_path, f"{done_dir}/{stem}_{timestamp}.pdf")

# 実行
results = {"success": [], "error": []}
for item in sorted(Path(INPUT_DIR).iterdir()):
    try:
        if item.is_file() and item.suffix == ".pdf":
            convert_and_move(str(item), OUTPUT_DIR, DONE_DIR)
            results["success"].append(item.name)
        elif item.is_dir():
            convert_and_move(str(item), OUTPUT_DIR, DONE_DIR, is_folder=True)
            results["success"].append(item.name + "/")
    except Exception as e:
        results["error"].append(f"{item.name}: {e}")

print(f"✅ 成功: {len(results['success'])}件")
for f in results["success"]:
    print(f"  - {f}")
if results["error"]:
    print(f"❌ 失敗: {len(results['error'])}件")
    for e in results["error"]:
        print(f"  - {e}")
```

### セル4：出力ファイル一覧確認

```python
for f in sorted(Path(OUTPUT_DIR).glob("*.md")):
    size = f.stat().st_size // 1024
    print(f"📄 {f.name}  ({size} KB)")
```

-----

## 5. 共同作業の使い方

```
チームメンバー全員の操作フロー:

1. 変換したいPDFを Drive の input/ にアップロード
   └─ ブラウザのDriveページからドラッグ＆ドロップ

2. ノートブックを開く（pdf_to_markdown.ipynb をダブルクリック）

3. 「ランタイム」→「すべてのセルを実行」

4. セル3の完了サマリーを確認

5. output/ フォルダにMarkdownファイルが生成されていることを確認
```

-----

## 6. Colab Pro+ での定期実行（オプション）

Colab Pro+（月額約2,700円）では「スケジュール実行」が利用可能。

- ノートブック上部の「スケジュール」ボタンから設定
- 例: 毎日9時に自動実行
- Colabがセッションを起動し、全セルを順番に実行して終了

無料プランでは手動実行のみ。

-----

## 7. セットアップ手順

1. [Google Drive](https://drive.google.com) で `pdf-to-markdown` フォルダを作成
1. `input/`, `output/`, `done/`, `logs/` サブフォルダを作成
1. ノートブックファイル `pdf_to_markdown.ipynb` を当フォルダに配置
1. フォルダをチームメンバーと共有（「共有」→「編集者」権限）
1. Colabでノートブックを開いて動作確認

-----

## 8. 制約・注意事項

|項目      |内容                            |
|--------|------------------------------|
|セッション時間 |無料: 最大12時間 / Pro: 24時間        |
|ストレージ   |Driveの容量に依存（無料: 15GB）         |
|実行速度    |テキストPDF: 高速 / スキャンPDF: 中速（CPU）|
|セットアップ時間|セル1実行に約2〜3分（初回のみ）             |
|定期実行    |Colab Pro+でのみ対応、無料版は手動        |
|データ保管場所 |すべてGoogleドライブ上（Googleのサーバー）   |

-----

## 9. 未確定事項

- [ ] Driveの共有方法（個人MyDrive共有 / 共有ドライブ（旧チームドライブ））
- [ ] Colab Proの契約有無（定期実行の要否）
- [ ] ノートブックのバージョン管理方法（DriveのみorGitHub連携）
