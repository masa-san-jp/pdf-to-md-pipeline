# pdf-to-md-pipeline

PDFをMarkdownに変換するパイプライン。環境・用途に応じて3つのバリアントから選べます。

---

## どれを使う？

```
データを社外に出したくない／オフライン環境？
    → YES → local/（ローカル版）

PCを選ばずブラウザだけで使いたい、またはチームで手軽に共同作業したい？
    → YES → colab/（Google Colab版）

完全自動化・大量処理・サーバー管理不要にしたい？（GCPアカウント必須）
    → YES → cloud/（クラウド版）
```

---

## バリアント比較

| | [local/](./local/) | [colab/](./colab/) | [cloud/](./cloud/) |
|---|---|---|---|
| **実行環境** | Linux / macOS / Windows | ブラウザ（Google Colab） | Google Cloud Platform |
| **セットアップ** | Python + Java のインストール | Googleアカウントのみ | GCPプロジェクト + IAM設定 |
| **スキャンPDF対応** | ✅ ローカルOCR | ✅ ローカルOCR（Colabランタイム） | ✅ Document AI OCR |
| **定期自動実行** | ✅ systemd / タスクスケジューラ | △ Colab Pro+ のみ | ✅ Cloud Scheduler |
| **共同作業** | ❌（ローカル完結） | ✅ Google Drive共有 | ✅ GCS共有 |
| **コスト** | 無料（電気代のみ） | 無料（Pro+は月約2,700円） | 約$2/月〜 |
| **データ保管場所** | ローカルマシン | Google Drive | Google Cloud Storage |

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

## 仕様書

詳細な設計仕様は `docs/` を参照してください：

- [`docs/Spec-local.md`](./docs/Spec-local.md) — ローカル版
- [`docs/spec-colab.md`](./docs/spec-colab.md) — Google Colab版
- [`docs/spec-cloud.md`](./docs/spec-cloud.md) — クラウド版
