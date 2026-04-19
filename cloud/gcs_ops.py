"""GCS 操作ユーティリティ。

input/ の走査・Markdown 保存・done/ への移動・ログ記録を担う。
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
  from google.cloud import storage

__all__ = [
  "list_input_items",
  "save_markdown",
  "move_to_done",
  "move_folder_to_done",
  "log_result",
]

logger = logging.getLogger(__name__)

_TIMESTAMP_FMT = "%Y%m%d_%H%M%S"


def _timestamp() -> str:
  return datetime.utcnow().strftime(_TIMESTAMP_FMT)


def list_input_items(bucket: "storage.Bucket", prefix: str = "input/") -> list[str]:
  """input/ 直下の PDF ファイルキーとサブフォルダプレフィックスを返す。

  直下の .pdf と、直下サブフォルダ（1階層のみ）を列挙する。
  深いネストは対象外とし、フォルダは末尾 "/" で区別する。
  """
  blobs = list(bucket.client.list_blobs(bucket, prefix=prefix, delimiter="/"))

  # list_blobs の delimiter 動作: blobs にファイル、prefixes にフォルダが入る
  # google-cloud-storage は iterator に prefixes 属性を持つ
  from google.cloud.storage.blob import Blob  # noqa: PLC0415

  pdf_keys: list[str] = [
    b.name for b in blobs if isinstance(b, Blob) and b.name.lower().endswith(".pdf")
  ]
  folder_prefixes: list[str] = list(blobs.prefixes) if hasattr(blobs, "prefixes") else []

  items = pdf_keys + folder_prefixes
  logger.info("input/ アイテム数: %d (PDF=%d, フォルダ=%d)", len(items), len(pdf_keys), len(folder_prefixes))
  return items


def save_markdown(
  bucket: "storage.Bucket",
  source_key: str,
  md_text: str,
  output_prefix: str = "output/",
) -> str:
  """Markdown テキストを output/ に保存し、保存先キーを返す。"""
  stem = source_key.rstrip("/").rsplit("/", 1)[-1]
  if stem.lower().endswith(".pdf"):
    stem = stem[:-4]
  dest_key = f"{output_prefix.rstrip('/')}/{stem}.md"
  blob = bucket.blob(dest_key)
  blob.upload_from_string(md_text, content_type="text/markdown; charset=utf-8")
  logger.info("保存: %s", dest_key)
  return dest_key


def move_to_done(
  bucket: "storage.Bucket",
  source_key: str,
  done_prefix: str = "done/",
  *,
  add_timestamp: bool = True,
) -> str:
  """GCS 上の単体 PDF を done/ へコピー後に元を削除し、移動先キーを返す。"""
  stem = source_key.rsplit("/", 1)[-1]
  if stem.lower().endswith(".pdf"):
    name = stem[:-4]
    suffix = ".pdf"
  else:
    name, suffix = stem, ""

  if add_timestamp:
    dest_key = f"{done_prefix.rstrip('/')}/{name}_{_timestamp()}{suffix}"
  else:
    dest_key = f"{done_prefix.rstrip('/')}/{stem}"

  src_blob = bucket.blob(source_key)
  bucket.copy_blob(src_blob, bucket, dest_key)
  src_blob.delete()
  logger.info("移動: %s → %s", source_key, dest_key)
  return dest_key


def move_folder_to_done(
  bucket: "storage.Bucket",
  folder_prefix: str,
  done_prefix: str = "done/",
  *,
  add_timestamp: bool = True,
) -> str:
  """GCS 上のフォルダ（プレフィックス）配下を done/ へ移動し、移動先プレフィックスを返す。"""
  folder_name = folder_prefix.strip("/").rsplit("/", 1)[-1]
  if add_timestamp:
    dest_folder = f"{done_prefix.rstrip('/')}/{folder_name}_{_timestamp()}/"
  else:
    dest_folder = f"{done_prefix.rstrip('/')}/{folder_name}/"

  blobs = list(bucket.client.list_blobs(bucket, prefix=folder_prefix))
  for blob in blobs:
    rel = blob.name[len(folder_prefix):]
    dest_key = dest_folder + rel
    bucket.copy_blob(blob, bucket, dest_key)
    blob.delete()

  logger.info("フォルダ移動: %s → %s (%d件)", folder_prefix, dest_folder, len(blobs))
  return dest_folder


def log_result(
  bucket: "storage.Bucket",
  entry: dict,
  logs_prefix: str = "logs/",
) -> None:
  """処理結果エントリを logs/ に JSON Lines 形式で追記する。

  既存ファイルへのアトミック追記が GCS では不可能なため、
  エントリごとに日付別ファイルへ上書きする戦略を取る。
  """
  date_str = datetime.utcnow().strftime("%Y%m%d")
  log_key = f"{logs_prefix.rstrip('/')}/{date_str}.jsonl"

  blob = bucket.blob(log_key)
  existing = ""
  if blob.exists():
    existing = blob.download_as_text(encoding="utf-8")

  line = json.dumps(entry, ensure_ascii=False)
  blob.upload_from_string(
    existing + line + "\n",
    content_type="application/x-ndjson; charset=utf-8",
  )
