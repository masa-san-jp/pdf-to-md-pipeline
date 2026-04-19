# 開発ログ

`CLAUDE.md` の方針に従い、「なぜそう実装したか」を時系列で残す。実装の事実関係は `README.md` と `docs/` を正とする。

---

## 2026-04-17 — ローカル版（vol.1）の初期実装

### 実装したもの

- `core/converter.py`: `convert_single` / `convert_folder` / `move_to_done` を公開
- `local/run.py`: `input/` を走査して `output/`・`done/` に振り分けるエントリーポイント
- `local/config.yaml`, `local/requirements.txt`, `local/.gitignore`
- `tests/test_converter.py`: `opendataloader_pdf.convert` をスタブ化した単体テスト
- `local/README.md`, ルート `README.md` に「クローン→即使用」の導線を追加

### 意思決定のメモ

**hybrid（OCR）バックエンドをデフォルトで無効化した**  
仕様書では `hybrid: "docling-fast"` が既定だが、そのままでは `opendataloader-pdf-hybrid` の常駐なしでは実行時エラーになる。「クローンしてすぐ動く」状態を優先し、`config.yaml` でコメントアウトしたテンプレートを用意して、スキャンPDFが必要な利用者だけが明示的に有効化する方針にした。

**`convert_folder` は一時ディレクトリ経由で一括変換→連結**  
`opendataloader_pdf.convert` が複数の `input_path` を一度に受け取れる前提で、個別ファイルごとに再起動せず1コールで処理。最終成果物名 `{folder_name}.md` と途中ファイル名 `{stem}.md` の衝突を避けるため、中間出力は `tempfile.TemporaryDirectory` に逃がしてから連結する。

**Python インデント2スペース**  
`CLAUDE.md` の「Python: 2スペースインデント」に合わせた。一般的な PEP8 の 4 スペースと異なるので、同リポジトリ内では本方針で統一する。

**`run.py` からの `core` インポート**  
`local/` 配下から `core/` を参照するため、`run.py` の先頭でプロジェクトルートを `sys.path` に挿入する。パッケージ化（`pip install -e .`）は今の段階では過剰なので見送り。`noqa: E402` だけ付けて許容。

**テストは外部依存ゼロで走る**  
`opendataloader_pdf` が未インストール・Java 不在でも CI / 開発者が走らせられるよう、テストは `monkeypatch` で `sys.modules` にスタブを挿入している。hybrid / docling の実挙動は手動テストに任せる。

**エラーは 1 アイテム単位で握る**  
`process_input_dir` は各 PDF/サブフォルダの例外をログに出しつつ次の項目へ進む。1 本の壊れた PDF で全体のバッチが落ちるのを避けるため。

### 未確定事項の扱い

`docs/Spec-local.md` 末尾の `[ ]` リストのうち、

- 出力 Markdown のファイル名規則 → **元ファイル名そのまま** を採用（タイムスタンプは `done/` 側でのみ付与）
- OCR 言語 → `config.yaml` コメント内で `ja,en` をデフォルト表記
- 実行環境（systemd / launchd / タスクスケジューラ）→ `local/README.md` に 3 OS 分の例を併記し、ユーザー選択とした

最大処理ファイル数（タイムアウト）は未対応。必要になったら `config.yaml` に `max_items_per_run` などを追加する。

### 動作確認

- `pytest tests/ -v` → 4/4 PASS
- `python run.py`（`opendataloader_pdf` をスタブ化した状態）で `input/ → output/ + done/` のファイル移動を確認

---

## 2026-04-19 — Colab版（vol.2）の実装

### 実装したもの

- `colab/pdf_to_markdown.ipynb`: セル1〜4で構成されるColabノートブック

### 意思決定のメモ

**`core/converter.py` のロジックをノートブック内にインライン展開した**  
Colab環境では `sys.path` 操作なしにローカルの `core/` をインポートできない。ノートブックは自己完結していることが「開いてすぐ実行できる」という vol.2 の設計原則に合うため、`core/` の関数と同等のロジック（`_convert_single` / `_convert_folder` / `_move_to_done`）をセル3内に定義した。命名を `core/` と揃えることで、将来的にGitHub経由でインポートに切り替える際の差分を最小化している。

**`threading.Thread` + `Popen` でhybridバックエンドを起動**  
仕様書の `subprocess.run` はブロッキングのため、プロセスをバックグラウンドで保持するために `subprocess.Popen` に変更。`daemon=True` にすることでColabセッション終了時に自動終了する。

**ログをDriveの `logs/` に保存する**  
仕様書のフォルダ構成に `logs/` があるため、実行ごとにタイムスタンプ付きログファイルを生成する。`StreamHandler` も同時設定してセル出力にも表示。

**`tempfile.TemporaryDirectory` で中間ファイルを管理**  
仕様書の実装例では `/content/tmp_{stem}` に直接書き出していたが、`with` ブロックで自動削除される `tempfile.TemporaryDirectory` に変更した。Colabの `/content` は揮発性なので残留ゴミを防ぐ。

**`input/` が空の場合を明示的にハンドリング**  
空ディレクトリで `sorted(INPUT_DIR.iterdir())` を実行しても無害だが、ユーザーへの通知として `⚠️` メッセージを表示する。

### 未確定事項の扱い

`docs/spec-colab.md` 末尾の `[ ]` リストは未解決のまま（Driveの共有方法、Colab Pro契約有無、バージョン管理方法）。ノートブック自体はどちらの構成でも動作するため、今回は判断を求めない実装とした。

---

## 2026-04-19 — クラウド版（vol.3）の実装

### 実装したもの

- `cloud/__init__.py`: パッケージ宣言
- `cloud/gcs_ops.py`: GCS 操作（input/ 走査・Markdown 保存・done/ 移動・JSON Lines ログ）
- `cloud/docai.py`: Document AI OCR 処理（≤15ページ: 同期 / >15ページ: バッチ 自動選択）
- `cloud/md_converter.py`: Document AI Document → Markdown 変換（見出し・段落・テーブル・リスト・改ページ対応）
- `cloud/main.py`: Cloud Run ジョブ エントリポイント
- `cloud/requirements.txt`: `google-cloud-documentai`, `google-cloud-storage`
- `cloud/Dockerfile`: `python:3.11-slim` ベース、`python -m cloud.main` で起動
- `tests/test_cloud_md_converter.py`: md_converter のユニットテスト（10件）
- `tests/test_cloud_gcs_ops.py`: gcs_ops のユニットテスト（10件）

### 意思決定のメモ

**`cloud/` を独立したパッケージとして実装した**  
Document AI は `opendataloader_pdf` と異なる変換エンジンであり、`core/converter.py` を共有することでかえって複雑になる。`CLAUDE.md` の方針（cloud/ は core/ を使わない）に従い、cloud/ パッケージ内で完結する実装とした。

**同期/バッチ処理を自動選択するヒューリスティック**  
Document AI の同期処理上限は15ページ。正確なページ数取得はコストがかかるため、5MB 超のファイルを「15ページ超」とみなすヒューリスティックを採用した。精度よりもシンプルさを優先した判断で、正確さが必要になった場合は実際のページ数カウントに切り替えられる。

**Markdown 変換は page.blocks の blockType 有無でフォールバック**  
Document AI のバージョン・プロセッサ種別によって `block_type` フィールドが存在しない場合がある。`_reprocess_with_blocks` でブロックタイプが利用可能か確認し、無ければ `page.paragraphs` / `page.tables` だけを使うフォールバックを実装した。実環境でのプロセッサバージョン確認後に整理できる。

**GCS の JSON Lines ログは上書き戦略**  
GCS は追記書き込みが不可能なため、既存内容を読み込んで再アップロードする方式を採用した。並列実行時のレース条件が生じる可能性があるが、Cloud Run ジョブは単一インスタンス実行が基本のため現時点では許容とした。

**Dockerfile は project root をビルドコンテキストとして想定**  
`COPY cloud/ ./cloud/` は project root からのビルドを前提とする。ビルドコマンドは `docker build -f cloud/Dockerfile .`。

**Drive 連携は今回のスコープ外**  
`spec-cloud.md` の「パターン A: Drive API 連携」は未確定事項（GCPプロジェクト有無・連携方針）が多く、GCS 直接操作のみ実装して Drive 連携は別タスクとした。

### 未確定事項の扱い

仕様書の `[ ]` リストのうち、コード実装に影響するものはすべて環境変数（`BUCKET_NAME`, `PROCESSOR_NAME`, `DOCAI_LOCATION`, `BATCH_OUTPUT_GCS`）として外出しにした。GCP プロジェクト作成・Document AI プロセッサ作成・Cloud Scheduler 設定は運用者がセットアップ手順に従って行う。

### 動作確認

- `pytest tests/test_cloud_md_converter.py tests/test_cloud_gcs_ops.py -v` → 20/20 PASS
