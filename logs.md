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

## 2026-05-18 — クラウド版（vol.3）の実装

### 実装したもの

- `cloud/__init__.py`：Python パッケージ化
- `cloud/main.py`：Cloud Run ジョブのエントリポイント（GCS 走査 → Document AI OCR → Markdown 保存 → done/ 移動）
- `cloud/requirements.txt`：`google-cloud-documentai` / `google-cloud-storage`
- `cloud/Dockerfile`：`python:3.11-slim` ベースの Cloud Run イメージ
- `cloud/setup.sh`：GCP リソース一括セットアップスクリプト（API 有効化・バケット・SA・Cloud Run・Scheduler）
- `tests/test_cloud_main.py`：GCP 依存なしのユニットテスト 18 件（全パス）

### 意思決定のメモ

**`os.environ.get()` でモジュールレベル定数を読む**
`os.environ["KEY"]`（KeyError 即時）にすると pytest でのモジュールインポート自体が失敗する。`get()` にして `main()` 入口でのみ必須バリデーションを行う設計にすることで、テストが外部依存なしに動く。

**Layout Parser 優先 / Enterprise OCR フォールバックの二段構え**
`document.document_layout.blocks` が存在する場合（Layout Parser プロセッサ）は見出し・段落・リスト・テーブルの意味的なブロックをそのまま Markdown に変換する。存在しない場合（Enterprise Document OCR）は `pages[].blocks[]` と `pages[].tables[]` を y 座標順に並べて変換するフォールバックに切り替える。これにより利用者がプロセッサタイプを切り替えても動作する。

**`heading-1` と `heading_1` 両形式を正規化**
Document AI の実際の API レスポンスでハイフン・アンダースコアどちらが返るか実環境で確認できないため、`type_.replace("-", "_")` で正規化してから判定する。

**同期 API（≤15 ページ）/ バッチ API（>15 ページ）の自動切り替え**
先頭 64KB の `/Type /Page` カウントでページ数を推定し同期 API を試みる。推定が外れて `InvalidArgument` が返った場合はバッチ API に自動フォールバックする。バッチ処理の一時 JSON 出力（`tmp/docai/{ts}/`）は処理後に削除する。

**`copy_blob` + `delete` で GCS 上の「移動」を実現**
GCS にはネイティブの移動操作がないため、コピー→元削除のパターンを使う。タイムスタンプ付き宛先名（`done/{stem}_{ts}.pdf`）で競合を回避する設計は vol.1/2 と共通。

**テストは sys.modules スタブ注入で GCP 依存ゼロ**
`autouse` フィクスチャで `google.cloud.*` の最小スタブを `sys.modules` に注入してから `cloud.main` のキャッシュを `monkeypatch.delitem` で破棄し、各テスト関数内でフレッシュインポートさせる。GCP 認証・ネットワーク不要で CI でも動く。

### 未確定事項の扱い

`docs/spec-cloud.md` 末尾の `[ ]` のうち実装に影響するものの扱い：

- GCS バケット名規則 → `{PROJECT_ID}-pdf-converter` を `setup.sh` のデフォルトに採用
- Document AI リージョン → デフォルト `us`、環境変数 `DOCUMENT_AI_REGION` で上書き可能
- Drive↔GCS 連携パターン → 今回は GCS 単独の実装とし、Drive 連携は `setup.sh` のコメントに誘導を記載
- ページ数上限の実挙動 → 同期 API の `InvalidArgument` をキャッチしてバッチに自動切り替えする安全網を実装

### 動作確認

- `pytest tests/ -v` → 22/22 PASS（クラウド版 18 件 + 既存 4 件）
