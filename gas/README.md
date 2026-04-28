# gas/ — Google Apps Script 版

Google Drive に置いたファイル（PDF・画像）を Gemini API で OCR し、
**Markdown 形式の Google Doc** として自動生成するパイプライン。

他バリアントとの最大の違いは、**画像ファイルも対応**し、
**出力先が Google Doc**（Drive 内でそのまま閲覧・編集可能）である点です。

---

## 対応ファイル形式

| 形式 | 対応 |
|---|---|
| PDF | ✅ |
| JPEG / PNG / TIFF | ✅ |
| HEIC / HEIF / WebP | ✅ |

---

## 動作フロー

```
ocr-input/ に任意のファイルを置く
  ↓ 10分ごとに自動実行（タイムドリガー）
  Gemini API: OCR → Markdown 再構築 + ファイル名提案
  ↓
ocr-output/  → Google Doc「20260428_請求書_ABC社_4月分」
ocr-processed/ → 入力ファイルも同名にリネーム（Doc との紐付け用）
ocr-error/   → OCR 失敗ファイルの退避先
```

---

## セットアップ

### 1. Google Drive にフォルダを4つ作成する

| フォルダ名（任意） | 用途 |
|---|---|
| `ocr-input` | 処理したいファイルを置く |
| `ocr-processed` | 処理済みファイルの保管先 |
| `ocr-error` | OCR 失敗ファイルの退避先 |
| `ocr-output` | 生成された Google Doc の保存先 |

各フォルダの URL から **フォルダ ID**（`/folders/` 以降の文字列）をメモしておく。

### 2. GAS プロジェクトを作成する

1. [script.google.com](https://script.google.com) を開く
2. 「新しいプロジェクト」を作成
3. `src/` 以下の4ファイルをそれぞれ貼り付ける（ファイル名を揃える）

| GAS ファイル | 対応ソース |
|---|---|
| `Config.gs` | `src/Config.gs` |
| `GeminiService.gs` | `src/GeminiService.gs` |
| `DocService.gs` | `src/DocService.gs` |
| `main.gs` | `src/main.gs` |

4. 「プロジェクトの設定」→「appsscript.json を表示」を有効化し、`src/appsscript.json` の内容で上書きする

### 3. スクリプトプロパティを設定する

「プロジェクトの設定」→「スクリプト プロパティ」から追加：

| プロパティ名 | 値 |
|---|---|
| `GEMINI_API_KEY` | [Google AI Studio](https://aistudio.google.com/) で取得した API キー |
| `FOLDER_ID_INPUT` | `ocr-input` フォルダの ID |
| `FOLDER_ID_PROCESSED` | `ocr-processed` フォルダの ID |
| `FOLDER_ID_ERROR` | `ocr-error` フォルダの ID |
| `FOLDER_ID_OUTPUT` | `ocr-output` フォルダの ID |

### 4. トリガーを設定する

「トリガー」→「トリガーを追加」

| 設定項目 | 値 |
|---|---|
| 実行する関数 | `processDocuments` |
| イベントのソース | 時間主導型 |
| タイプ | 分ベースのタイマー |
| 間隔 | 10分おき |

---

## ファイル名の命名ルール

```
yyyymmdd_文書種別_キーワード
例: 20260428_請求書_ABC株式会社_4月分
    20260428_契約書_業務委託_XYZ社
    20260428_議事録_経営会議
```

- `yyyymmdd` は処理実行日
- 文書種別・キーワードは Gemini が内容から自動生成
- Google Doc と入力ファイルが同名になるため、対応関係を追跡しやすい

---

## テスト実行

```bash
cd gas/
npm install
npm test
```

21 ユニットテスト（Jest）が通ることを確認してください。
