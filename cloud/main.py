"""Cloud Run ジョブ。GCS input/ を走査し Document AI で PDF → Markdown 変換する。"""
from __future__ import annotations

__all__ = [
  "list_input_items",
  "convert_docai_document_to_markdown",
  "process_pdf_to_markdown",
  "process_folder_to_markdown",
  "save_markdown",
  "move_to_done",
  "main",
]

import json
import logging
import os
from datetime import datetime, timezone

from google.api_core.exceptions import InvalidArgument
from google.cloud import documentai_v1 as documentai
from google.cloud import storage

PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", "")
PROCESSOR_ID = os.environ.get("DOCUMENT_AI_PROCESSOR_ID", "")
PROCESSOR_REGION = os.environ.get("DOCUMENT_AI_REGION", "us")
BUCKET_NAME = os.environ.get("GCS_BUCKET_NAME", "")

PROCESSOR_NAME = (
  f"projects/{PROJECT_ID}/locations/{PROCESSOR_REGION}/processors/{PROCESSOR_ID}"
)
DOCAI_ENDPOINT = f"{PROCESSOR_REGION}-documentai.googleapis.com"

# Document AI 同期 API のページ上限
_SYNC_PAGE_LIMIT = 15

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


# ─── GCS helpers ─────────────────────────────────────────────────────────────

def list_input_items(bucket: storage.Bucket) -> dict[str, list[storage.Blob]]:
  """input/ を走査して {gcs_key: [blob, ...]} を返す。

  直下 .pdf → キー = "input/name.pdf"（blob 1 個）
  サブフォルダ → キー = "input/folder/"（内部 PDF を名前昇順）
  """
  items: dict[str, list[storage.Blob]] = {}
  folders: dict[str, list[storage.Blob]] = {}

  for blob in bucket.list_blobs(prefix="input/"):
    if blob.name == "input/" or not blob.name.endswith(".pdf"):
      continue
    relative = blob.name[len("input/"):]
    parts = relative.split("/")
    if len(parts) == 1:
      items[blob.name] = [blob]
    elif len(parts) == 2:
      key = f"input/{parts[0]}/"
      folders.setdefault(key, []).append(blob)

  for key, blobs in folders.items():
    items[key] = sorted(blobs, key=lambda b: b.name)

  return items


def _timestamp() -> str:
  return datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")


def move_to_done(bucket: storage.Bucket, source_key: str) -> None:
  """source_key を done/ にタイムスタンプ付きでコピーしてから元を削除する。"""
  ts = _timestamp()

  if source_key.endswith("/"):
    stem = source_key.rstrip("/").split("/")[-1]
    for blob in bucket.list_blobs(prefix=source_key):
      rel = blob.name[len(source_key):]
      bucket.copy_blob(blob, bucket, new_name=f"done/{stem}_{ts}/{rel}")
      blob.delete()
  else:
    blob = bucket.blob(source_key)
    filename = source_key.rsplit("/", 1)[-1]
    if "." in filename:
      stem, ext = filename.rsplit(".", 1)
      dest = f"done/{stem}_{ts}.{ext}"
    else:
      dest = f"done/{filename}_{ts}"
    bucket.copy_blob(blob, bucket, new_name=dest)
    blob.delete()


def save_markdown(bucket: storage.Bucket, source_key: str, content: str) -> str:
  """Markdown を output/ に保存し保存先パスを返す。"""
  if source_key.endswith("/"):
    stem = source_key.rstrip("/").split("/")[-1]
  else:
    filename = source_key.rsplit("/", 1)[-1]
    stem = filename.rsplit(".", 1)[0] if "." in filename else filename
  dest = f"output/{stem}.md"
  bucket.blob(dest).upload_from_string(content, content_type="text/markdown; charset=utf-8")
  logger.info("保存: %s", dest)
  return dest


# ─── Document AI → Markdown ──────────────────────────────────────────────────

def _extract_text(document: documentai.Document, anchor: documentai.Document.TextAnchor) -> str:
  return "".join(
    document.text[s.start_index:s.end_index] for s in anchor.text_segments
  )


def _table_to_md(document: documentai.Document, table: documentai.Document.Page.Table) -> str:
  """pages[] 内の Table → Markdown テーブル。"""
  def row_to_cells(row) -> list[str]:
    return [
      _extract_text(document, cell.layout.text_anchor).strip().replace("\n", " ")
      for cell in row.cells
    ]

  rows: list[str] = []
  if table.header_rows:
    headers = row_to_cells(table.header_rows[0])
    rows.append("| " + " | ".join(headers) + " |")
    rows.append("|" + "|".join(["---"] * len(headers)) + "|")
  for body_row in table.body_rows:
    rows.append("| " + " | ".join(row_to_cells(body_row)) + " |")
  return "\n".join(rows)


def _layout_text_to_md(text_block) -> str:
  """LayoutTextBlock → Markdown テキスト。heading-1 と heading_1 の両形式を受け付ける。"""
  t = (text_block.type_ or "paragraph").lower().replace("-", "_")
  text = (text_block.text or "").strip()

  if t == "heading_1":
    return f"# {text}"
  if t == "heading_2":
    return f"## {text}"
  if t == "heading_3":
    return f"### {text}"
  if t == "list":
    return "\n".join(
      f"- {(b.text or '').strip()}"
      for b in text_block.blocks
      if (b.text or "").strip()
    )
  if t == "list_item":
    return f"- {text}"
  return text


def _layout_table_to_md(table_block) -> str:
  """LayoutTableBlock → Markdown テーブル。"""
  def cell_text(cell) -> str:
    return " ".join(
      (b.text or "").strip().replace("\n", " ")
      for b in cell.blocks
      if (b.text or "").strip()
    )

  rows: list[str] = []
  if table_block.header_rows:
    headers = [cell_text(c) for c in table_block.header_rows[0].cells]
    rows.append("| " + " | ".join(headers) + " |")
    rows.append("|" + "|".join(["---"] * len(headers)) + "|")
  for body_row in table_block.body_rows:
    rows.append("| " + " | ".join(cell_text(c) for c in body_row.cells) + " |")
  return "\n".join(rows)


def convert_docai_document_to_markdown(document: documentai.Document) -> str:
  """Document AI Document → Markdown。

  document_layout.blocks（Layout Parser）があれば優先使用。
  なければ pages[] ベースのフォールバックを使う。
  """
  if document.document_layout.blocks:
    return _from_layout_blocks(document)
  return _from_pages(document)


def _from_layout_blocks(document: documentai.Document) -> str:
  parts: list[str] = []
  prev_page_end = 0

  for block in document.document_layout.blocks:
    page_start = block.page_span.page_start if block.page_span else 0
    if page_start > prev_page_end and prev_page_end > 0:
      parts.append("---")
    if block.page_span:
      prev_page_end = block.page_span.page_end

    if block.table_block:
      md = _layout_table_to_md(block.table_block)
    elif block.text_block:
      md = _layout_text_to_md(block.text_block)
    else:
      continue
    if md:
      parts.append(md)

  return "\n\n".join(parts).strip()


def _from_pages(document: documentai.Document) -> str:
  parts: list[str] = []

  for page_num, page in enumerate(document.pages):
    if page_num > 0:
      parts.append("---")

    # テーブルの text range を収集して blocks と重複しないようにする
    table_ranges: set[str] = set()
    table_items: list[tuple[float, str]] = []
    for table in page.tables:
      y = (
        table.layout.bounding_poly.normalized_vertices[0].y
        if table.layout.bounding_poly.normalized_vertices else 0.0
      )
      table_items.append((y, _table_to_md(document, table)))
      for row in list(table.header_rows) + list(table.body_rows):
        for cell in row.cells:
          for s in cell.layout.text_anchor.text_segments:
            table_ranges.add(f"{s.start_index}:{s.end_index}")

    block_items: list[tuple[float, str]] = []
    for block in page.blocks:
      if any(
        f"{s.start_index}:{s.end_index}" in table_ranges
        for s in block.layout.text_anchor.text_segments
      ):
        continue
      text = _extract_text(document, block.layout.text_anchor).strip()
      if not text:
        continue
      y = (
        block.layout.bounding_poly.normalized_vertices[0].y
        if block.layout.bounding_poly.normalized_vertices else 0.0
      )
      block_items.append((y, text))

    for _, content in sorted(table_items + block_items):
      parts.append(content)

  return "\n\n".join(parts).strip()


# ─── Document AI 処理 ─────────────────────────────────────────────────────────

def _docai_client() -> documentai.DocumentProcessorServiceClient:
  return documentai.DocumentProcessorServiceClient(
    client_options={"api_endpoint": DOCAI_ENDPOINT}
  )


def _estimate_pages(blob: storage.Blob) -> int:
  """先頭 64KB から /Type /Page の出現数でページ数を推定する（ヒューリスティック）。"""
  end = min(65536, blob.size or 65536)
  data = blob.download_as_bytes(end=end)
  count = data.count(b"/Type /Page") + data.count(b"/Type/Page")
  return max(count, 1)


def _process_sync(
  client: documentai.DocumentProcessorServiceClient, gcs_uri: str
) -> str:
  result = client.process_document(
    request=documentai.ProcessRequest(
      name=PROCESSOR_NAME,
      gcs_document=documentai.GcsDocument(gcs_uri=gcs_uri, mime_type="application/pdf"),
      process_options=documentai.ProcessOptions(
        ocr_config=documentai.OcrConfig(
          enable_native_pdf_parsing=True,
          language_hints=["ja", "en"],
        )
      ),
    )
  )
  return convert_docai_document_to_markdown(result.document)


def _process_batch(
  client: documentai.DocumentProcessorServiceClient,
  source_name: str,
  bucket: storage.Bucket,
) -> str:
  ts = _timestamp()
  gcs_in = f"gs://{BUCKET_NAME}/{source_name}"
  gcs_out_prefix = f"tmp/docai/{ts}/"
  gcs_out = f"gs://{BUCKET_NAME}/{gcs_out_prefix}"

  operation = client.batch_process_documents(
    request=documentai.BatchProcessRequest(
      name=PROCESSOR_NAME,
      input_documents=documentai.BatchDocumentsInputConfig(
        gcs_documents=documentai.GcsDocuments(
          documents=[documentai.GcsDocument(gcs_uri=gcs_in, mime_type="application/pdf")]
        )
      ),
      document_output_config=documentai.DocumentOutputConfig(
        gcs_output_config=documentai.DocumentOutputConfig.GcsOutputConfig(gcs_uri=gcs_out)
      ),
    )
  )
  logger.info("バッチ処理開始: %s", gcs_in)
  operation.result()

  json_blobs = sorted(
    [b for b in bucket.list_blobs(prefix=gcs_out_prefix) if b.name.endswith(".json")],
    key=lambda b: b.name,
  )
  if not json_blobs:
    raise RuntimeError(f"バッチ処理出力が空です: {gcs_out}")

  parts = [
    convert_docai_document_to_markdown(
      documentai.Document.from_json(b.download_as_bytes().decode())
    )
    for b in json_blobs
  ]
  for b in json_blobs:
    b.delete()

  return "\n\n---\n\n".join(parts)


def process_pdf_to_markdown(blob: storage.Blob, bucket: storage.Bucket) -> str:
  """単体 PDF blob を Document AI で処理し Markdown を返す。"""
  client = _docai_client()
  gcs_uri = f"gs://{BUCKET_NAME}/{blob.name}"

  if _estimate_pages(blob) <= _SYNC_PAGE_LIMIT:
    try:
      return _process_sync(client, gcs_uri)
    except InvalidArgument as exc:
      # ページ数推定が外れて同期 API の上限を超えた場合はバッチに切り替える
      if "page" not in str(exc).lower():
        raise
      logger.info("同期 API 上限超過のためバッチに切り替え: %s", blob.name)

  return _process_batch(client, blob.name, bucket)


def process_folder_to_markdown(
  bucket: storage.Bucket, pdf_blobs: list[storage.Blob]
) -> str:
  """フォルダ内 PDF を昇順で処理して結合した Markdown を返す。"""
  parts = [process_pdf_to_markdown(b, bucket) for b in pdf_blobs]
  return "\n\n".join(parts)


# ─── ログ・エントリポイント ───────────────────────────────────────────────────

def _save_log(bucket: storage.Bucket, results: list[dict]) -> None:
  ts = _timestamp()
  content = "\n".join(json.dumps(r, ensure_ascii=False) for r in results) + "\n"
  bucket.blob(f"logs/{ts}.jsonl").upload_from_string(
    content, content_type="application/x-ndjson; charset=utf-8"
  )


def main() -> None:
  for var in ("GOOGLE_CLOUD_PROJECT", "DOCUMENT_AI_PROCESSOR_ID", "GCS_BUCKET_NAME"):
    if not os.environ.get(var):
      raise SystemExit(f"環境変数 {var} が未設定です")

  gcs = storage.Client()
  bucket = gcs.bucket(BUCKET_NAME)

  items = list_input_items(bucket)
  logger.info("処理対象: %d 件", len(items))
  if not items:
    logger.info("input/ に処理対象がありません")
    return

  results: list[dict] = []
  for key, blobs in items.items():
    try:
      md = (
        process_folder_to_markdown(bucket, blobs)
        if key.endswith("/")
        else process_pdf_to_markdown(blobs[0], bucket)
      )
      out = save_markdown(bucket, key, md)
      move_to_done(bucket, key)
      results.append({"source": key, "output": out, "status": "ok"})
      logger.info("完了: %s → %s", key, out)
    except Exception as exc:
      logger.error("エラー: %s — %s", key, exc, exc_info=True)
      results.append({"source": key, "status": "error", "error": str(exc)})

  _save_log(bucket, results)
  errors = [r for r in results if r["status"] == "error"]
  if errors:
    raise SystemExit(f"{len(errors)} 件のエラーが発生しました")


if __name__ == "__main__":
  main()
