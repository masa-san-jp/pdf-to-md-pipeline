"""Document AI OCR 処理。

≤15 ページは同期 API、>15 ページはバッチ API を自動選択する。
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
  from google.cloud import documentai

__all__ = ["process_single", "process_folder"]

logger = logging.getLogger(__name__)

# Document AI 同期処理の上限ページ数
_SYNC_PAGE_LIMIT = 15


def _make_client(location: str) -> "documentai.DocumentProcessorServiceClient":
  from google.api_core.client_options import ClientOptions
  from google.cloud import documentai

  opts = ClientOptions(api_endpoint=f"{location}-documentai.googleapis.com")
  return documentai.DocumentProcessorServiceClient(client_options=opts)


def _page_count(gcs_uri: str, bucket_name: str) -> int:
  """GCS 上の PDF のページ数を概算する（ファイルサイズで閾値判定）。

  正確なページ数取得は高コストなため、5MB 超を >15 ページと見なす。
  """
  from google.cloud import storage

  client = storage.Client()
  key = gcs_uri.removeprefix(f"gs://{bucket_name}/")
  blob = client.bucket(bucket_name).get_blob(key)
  if blob is None:
    return 0
  # 5MB ≈ 100ページ相当として閾値を設定
  return 99 if blob.size and blob.size > 5 * 1024 * 1024 else 1


def _process_sync(
  client: "documentai.DocumentProcessorServiceClient",
  processor_name: str,
  gcs_uri: str,
  process_options: "documentai.ProcessOptions",
) -> "documentai.Document":
  from google.cloud import documentai

  request = documentai.ProcessRequest(
    name=processor_name,
    gcs_document=documentai.GcsDocument(
      gcs_uri=gcs_uri,
      mime_type="application/pdf",
    ),
    process_options=process_options,
  )
  response = client.process_document(request=request)
  return response.document


def _process_batch(
  client: "documentai.DocumentProcessorServiceClient",
  processor_name: str,
  gcs_input_uri: str,
  gcs_output_prefix: str,
  process_options: "documentai.ProcessOptions",
) -> "documentai.Document":
  """バッチ処理を実行し、出力 JSON を結合した Document を返す。"""
  from google.cloud import documentai, storage

  request = documentai.BatchProcessRequest(
    name=processor_name,
    input_documents=documentai.BatchDocumentsInputConfig(
      gcs_documents=documentai.GcsDocuments(
        documents=[
          documentai.GcsDocument(
            gcs_uri=gcs_input_uri,
            mime_type="application/pdf",
          )
        ]
      )
    ),
    document_output_config=documentai.DocumentOutputConfig(
      gcs_output_config=documentai.DocumentOutputConfig.GcsOutputConfig(
        gcs_uri=gcs_output_prefix,
      )
    ),
    process_options=process_options,
  )
  operation = client.batch_process_documents(request=request)
  logger.info("バッチ処理開始: %s", gcs_input_uri)
  operation.result(timeout=600)

  # 出力 JSON を読み込んで Document に復元
  bucket_name = gcs_output_prefix.removeprefix("gs://").split("/")[0]
  prefix = "/".join(gcs_output_prefix.removeprefix(f"gs://{bucket_name}/").rstrip("/").split("/"))
  gcs_client = storage.Client()
  blobs = list(gcs_client.list_blobs(bucket_name, prefix=prefix))
  json_blobs = [b for b in blobs if b.name.endswith(".json")]
  if not json_blobs:
    raise RuntimeError(f"バッチ処理の出力 JSON が見つかりません: {gcs_output_prefix}")

  import json
  from google.protobuf import json_format

  pages: list[dict] = []
  for blob in sorted(json_blobs, key=lambda b: b.name):
    data = json.loads(blob.download_as_text(encoding="utf-8"))
    pages.append(data)

  # 複数 JSON を先頭ドキュメントにページ合成
  merged = documentai.Document()
  json_format.Parse(json.dumps(pages[0]), merged)
  for extra in pages[1:]:
    extra_doc = documentai.Document()
    json_format.Parse(json.dumps(extra), extra_doc)
    merged.pages.extend(extra_doc.pages)

  return merged


def _build_process_options(location: str) -> "documentai.ProcessOptions":
  from google.cloud import documentai

  return documentai.ProcessOptions(
    ocr_config=documentai.OcrConfig(
      enable_native_pdf_parsing=True,
      language_hints=["ja", "en"],
    )
  )


def process_single(
  gcs_input_uri: str,
  processor_name: str,
  location: str,
  *,
  gcs_batch_output_prefix: str = "",
) -> "documentai.Document":
  """単体 PDF を OCR 処理し Document を返す。

  ページ数に応じて同期/バッチを自動選択する。
  バッチ時は gcs_batch_output_prefix に一時出力先を指定すること。
  """
  bucket_name = gcs_input_uri.removeprefix("gs://").split("/")[0]
  pages = _page_count(gcs_input_uri, bucket_name)
  client = _make_client(location)
  opts = _build_process_options(location)

  if pages <= _SYNC_PAGE_LIMIT:
    logger.info("同期処理: %s", gcs_input_uri)
    return _process_sync(client, processor_name, gcs_input_uri, opts)

  if not gcs_batch_output_prefix:
    raise ValueError("バッチ処理には gcs_batch_output_prefix が必要です")
  logger.info("バッチ処理: %s", gcs_input_uri)
  return _process_batch(client, processor_name, gcs_input_uri, gcs_batch_output_prefix, opts)


def process_folder(
  gcs_input_uris: list[str],
  processor_name: str,
  location: str,
  *,
  gcs_batch_output_prefix: str = "",
) -> list["documentai.Document"]:
  """フォルダ内 PDF をファイル名昇順で OCR 処理し Document リストを返す。"""
  uris_sorted = sorted(gcs_input_uris, key=lambda u: u.rsplit("/", 1)[-1])
  docs: list = []
  for uri in uris_sorted:
    doc = process_single(
      uri,
      processor_name,
      location,
      gcs_batch_output_prefix=gcs_batch_output_prefix,
    )
    docs.append(doc)
  return docs
