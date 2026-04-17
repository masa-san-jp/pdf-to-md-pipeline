# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## プロジェクト概要

PDFをMarkdownに変換するパイプライン。3つの実装バリアントがある：

| バリアント | 仕様書 | 概要 |
|---|---|---|
| **vol.1 ローカル版** | `docs/Spec-local.md` | `run.py` + `opendataloader-pdf` をローカル実行。systemd/launchd/タスクスケジューラで定期起動 |
| **vol.2 Colab版** | `docs/spec-colab.md` | Google Colabノートブック + Google Drive。ブラウザのみで動作。チーム共有可 |
| **vol.3 クラウド版** | `docs/spec-cloud.md` | GCS + Document AI + Cloud Run + Cloud Scheduler のフルサーバーレス構成 |

## 開発ルール

### 仕様書ベースの開発
実装前に必ず対応する `docs/spec-*.md` を確認する。未確定事項（各仕様書末尾の `[ ]` リスト）は実装を進めながら確定次第チェックを入れる。

### 開発ログ（logs.md）
`logs.md` を随時更新し、進捗・意思決定の経緯を記録する。他のコラボレーターが経緯を追えるよう、「なぜその実装を選んだか」を残す。

### README更新
実装後に変更・追加した機能はすぐ `README.md` に反映する。ユーザー目線で書く（セットアップ手順・使い方を中心に）。

### スキル化
同じ処理パターン（例：GCS操作、Document AI呼び出し、ファイル移動+ログ）が繰り返し現れたら、`.claude/commands/` 配下にカスタムスラッシュコマンドとして切り出す。

## リポジトリ構成

```
pdf-to-md-pipeline/
├── local/        # vol.1 ローカル版（run.py, config.yaml）
├── colab/        # vol.2 Google Colab版（.ipynb ノートブック）
├── cloud/        # vol.3 クラウド版（main.py, Dockerfile）
├── core/         # vol.1・vol.2 共通ロジック（converter.py）
├── docs/         # 設計仕様書（spec-local, spec-colab, spec-cloud）
├── CLAUDE.md
└── README.md
```

`core/` は `local/` と `colab/` が共有する変換ロジック（`convert_single`, `convert_folder`, `move_to_done`）を置く場所。`cloud/` は Document AI ベースで実装が独立しているため `core/` を使わない。

## アーキテクチャ・処理フロー

全バリアント共通の処理ロジック：

```
input/ を走査
├── 単体PDF → 変換 → output/{stem}.md → done/{stem}_{timestamp}.pdf
└── サブフォルダ → フォルダ内PDFをファイル名昇順でソート → 連結 → output/{folder}.md → done/{folder}_{timestamp}/
```

変換エンジンの使い分け：
- **vol.1・vol.2**：`opendataloader-pdf`（hybrid モードで OCR対応、Java 11+ 必須）
- **vol.3**：Google Cloud Document AI（OCR結果JSON → Markdown後処理が必要）

Document AIのMarkdown変換マッピング（vol.3 実装時の参照）：
- `HEADING_1/2` → `# ` / `## `
- `PARAGRAPH` → テキスト段落
- `TABLE` → Markdownテーブル
- `LIST_ITEM` → `- `
- 改ページ → `---`

## セットアップ（ローカル版）

```bash
java -version    # Java 11+ 必須
python --version # Python 3.10+ 必須

pip install opendataloader-pdf[hybrid] PyYAML

mkdir -p input output done logs

# hybrid バックエンド起動（スキャンPDF対応、初回のみ）
opendataloader-pdf-hybrid --port 5002 --ocr-lang "ja,en" &

python run.py
python run.py --log-level DEBUG
```

## コミット前チェック

```bash
# lint
ruff check .        # またはプロジェクトで採用したlinter

# type check
mypy .

# test
pytest              # 単一テスト: pytest tests/test_converter.py::test_single_pdf
```

## コーディング規約

- Python: 2スペースインデント、型ヒント必須、`async/await` を使う箇所では非同期一貫性を保つ
- 関数・変数は named export 相当の明示的な命名（モジュール内で `__all__` 定義）
- 過度な抽象化を避ける。`local/` と `colab/` で共通化できる処理のみ `core/converter.py` に切り出す（`cloud/` は別エンジンのため共有しない）
- テストは実装と同時（または先）に書く

## セキュリティ・パフォーマンス

- GCP認証はService Account + IAM最小権限。credentials をコードやログに含めない
- `done/` 移動はタイムスタンプ付きのため同名ファイルの上書きは起きないが、並列実行時のレース条件に注意
- スキャンPDF（hybridモード）は大量ページでメモリを大量消費する（目安: 100ページ/秒、CPU only）。バッチサイズ制限を設ける
- Document AI同期処理は最大15ページ制限があるため、それ超えるPDFはバッチAPI（非同期）を使う
- Cloud版のGCSバケットはバリアントごとに適切なIAMを設定し、公開アクセスを禁止する
