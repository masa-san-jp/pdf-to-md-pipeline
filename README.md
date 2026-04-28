# pdf-to-md-pipeline

PDFや画像をMarkdownに変換するパイプライン。環境・用途に応じて4つのバリアントから選べます。

---

## どれを使う？

```
データを社外に出したくない／オフライン環境？
    → YES → local/（ローカル版）

PCを選ばずブラウザだけで使いたい、またはチームで手軽に共同作業したい？
    → YES → colab/（Google Colab版）

完全自動化・大量処理・サーバー管理不要にしたい？（GCPアカウント必須）
    → YES → cloud/（クラウド版）

Google Drive にファイルを置くだけで自動変換したい？画像も扱いたい？
    → YES → gas/（Google Apps Script版）
```

---

## バリアント比較

| | [local/](./local/) | [colab/](./colab/) | [cloud/](./cloud/) | [gas/](./gas/) |
|---|---|---|---|---|
| **実行環境** | Linux / macOS / Windows | ブラウザ（Google Colab） | Google Cloud Platform | Google Apps Script |
| **セットアップ** | Python + Java のインストール | Googleアカウントのみ | GCPプロジェクト + IAM設定 | Googleアカウント + Gemini APIキー |
| **対応形式** | PDF | PDF | PDF | PDF + 画像（JPEG / PNG / HEIC 等） |
| **スキャンPDF対応** | ✅ ローカルOCR | ✅ ローカルOCR（Colabランタイム） | ✅ Document AI OCR | ✅ Gemini Vision OCR |
| **出力形式** | Markdown ファイル | Markdown ファイル | Markdown ファイル | Google Doc（Markdown本文） |
| **定期自動実行** | ✅ systemd / タスクスケジューラ | △ Colab Pro+ のみ | ✅ Cloud Scheduler | ✅ タイムドリガー（10分ごと） |
| **共同作業** | ❌（ローカル完結） | ✅ Google Drive共有 | ✅ GCS共有 | ✅ Google Drive共有 |
| **コスト** | 無料（電気代のみ） | 無料（Pro+は月約2,700円） | 約$2/月〜 | 無料枠内〜（Gemini API従量） |
| **データ保管場所** | ローカルマシン | Google Drive | Google Cloud Storage | Google Drive |

---

## 共通の処理フロー

全バリアントとも同じ処理ロジックで動きます：

```
input/ を走査
├── 単体PDF  →  output/{ファイル名}.md  →  done/{ファイル名}_{timestamp}.pdf
└── サブフォルダ  →  フォルダ内PDFをファイル名昇順で変換・結合
                →  output/{フォルダ名}.md  →  done/{フォルダ名}_{timestamp}/
```

---

## クイックスタート（ローカル版）

```bash
git clone https://github.com/masa-san-jp/pdf-to-md-pipeline.git
cd pdf-to-md-pipeline/local
python -m venv .venv && source .venv/bin/activate   # Windows は .venv\Scripts\activate
pip install -r requirements.txt
cp ~/Downloads/sample.pdf input/
python run.py
# → output/sample.md が生成され、input/sample.pdf は done/ へ退避
```

詳細・systemdサービス化・OCR有効化などは [`local/README.md`](./local/README.md) を参照。

---

## クイックスタート（Colab版）

1. Google Drive に `pdf-to-markdown/` フォルダを作成し、`input/` サブフォルダを追加
2. `colab/pdf_to_markdown.ipynb` をそのフォルダにアップロード
3. ノートブックをダブルクリックして Colab で開く
4. 「ランタイム」→「すべてのセルを実行」
5. `output/` フォルダに Markdown ファイルが生成されます

チームで使う場合は `pdf-to-markdown/` フォルダを「共有」→「編集者」権限でメンバーに共有してください。

---

## クイックスタート（クラウド版）

GCP プロジェクト・Document AI プロセッサ・GCS バケットが作成済みであることを前提とします。  
詳細は [`docs/spec-cloud.md`](./docs/spec-cloud.md) のセットアップ手順を参照してください。

```bash
# Docker イメージをビルド（project root から実行）
docker build -f cloud/Dockerfile -t pdf-converter .

# ローカル動作確認（実 GCP 認証が必要）
docker run \
  -e BUCKET_NAME=my-project-pdf-converter \
  -e PROCESSOR_NAME="projects/123/locations/us/processors/abc" \
  -e DOCAI_LOCATION=us \
  -v ~/.config/gcloud:/root/.config/gcloud \
  pdf-converter

# Cloud Run ジョブとしてデプロイ
gcloud builds submit --tag gcr.io/[PROJECT]/pdf-converter .
gcloud run jobs create pdf-converter \
  --image gcr.io/[PROJECT]/pdf-converter \
  --region asia-northeast1 \
  --set-env-vars BUCKET_NAME=[BUCKET],PROCESSOR_NAME=[PROCESSOR],DOCAI_LOCATION=us
```

---

## 実装状況

| バリアント | 状態 |
|---|---|
| vol.1 ローカル版 | ✅ 実装済み（`local/`） |
| vol.2 Colab版 | ✅ 実装済み（`colab/`） |
| vol.3 クラウド版 | ✅ 実装済み（`cloud/`） |
| vol.4 GAS版 | ✅ 実装済み（`gas/`） |

---

## クイックスタート（GAS版）

1. Google Drive に `ocr-input` / `ocr-processed` / `ocr-error` / `ocr-output` フォルダを作成
2. [script.google.com](https://script.google.com) で新プロジェクトを作成し、`gas/src/` の4ファイルを貼り付け
3. スクリプトプロパティに `GEMINI_API_KEY` と4つのフォルダ ID を設定
4. `processDocuments` 関数に10分ごとのタイムドリガーを設定
5. `ocr-input/` にファイルを置くと `ocr-output/` に Google Doc が自動生成されます

詳細は [`gas/README.md`](./gas/README.md) を参照してください。

---

## 仕様書

詳細な設計仕様は `docs/` を参照してください：

- [`docs/Spec-local.md`](./docs/Spec-local.md) — ローカル版
- [`docs/spec-colab.md`](./docs/spec-colab.md) — Google Colab版
- [`docs/spec-cloud.md`](./docs/spec-cloud.md) — クラウド版
