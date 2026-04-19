"""Cloud Run ジョブ エントリポイント。

環境変数:
  BUCKET_NAME        GCS バケット名（必須）
  PROCESSOR_NAME     Document AI プロセッサのフルリソース名（必須）
                     例: projects/123/locations/us/processors/abc
  DOCAI_LOCATION     Document AI エンドポイントリージョン（デフォルト: us）
  BATCH_OUTPUT_GCS   バッチ処理の一時出力先プレフィックス（>15ページ対応時に必要）
"""
from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timezone

from cloud.docai import process_folder, process_single
from cloud.gcs_ops import (
  list_input_items,
  log_result,
  move_folder_to_done,
  move_to_done,
  save_markdown,
)
from cloud.md_converter import concat_markdowns, docai_to_markdown

__all__ = ["main"]

logging.basicConfig(
  level=logging.INFO,
  format="%(asctime)s %(levelname)s %(name)s: %(message)s",
  stream=sys.stdout,
)
logger = logging.getLogger(__name__)


def _require_env(name: str) -> str:
  val = os.environ.get(name, "").strip()
  if not val:
    raise EnvironmentError(f"環境変数 {name} が設定されていません")
  return val


def _is_folder_prefix(key: str) -> bool:
  return key.endswith("/")


def _list_folder_pdfs(bucket, folder_prefix: str) -> list[str]:
  """フォルダ内の PDF キーをファイル名昇順で返す。"""
  blobs = list(bucket.client.list_blobs(bucket, prefix=folder_prefix))
  keys = sorted(
    [b.name for b in blobs if b.name.lower().endswith(".pdf")],
    key=lambda k: k.rsplit("/", 1)[-1],
  )
  return keys


def main() -> None:
  bucket_name = _require_env("BUCKET_NAME")
  processor_name = _require_env("PROCESSOR_NAME")
  location = os.environ.get("DOCAI_LOCATION", "us").strip()
  batch_output = os.environ.get("BATCH_OUTPUT_GCS", "").strip()

  from google.cloud import storage  # noqa: PLC0415

  gcs = storage.Client()
  bucket = gcs.bucket(bucket_name)

  items = list_input_items(bucket, "input/")
  if not items:
    logger.info("input/ に処理対象ファイルがありません")
    return

  results: list[dict] = []

  for item in items:
    ts_start = datetime.now(timezone.utc).isoformat()
    try:
      if _is_folder_prefix(item):
        # ── フォルダ処理 ──────────────────────────────────────────
        pdf_keys = _list_folder_pdfs(bucket, item)
        if not pdf_keys:
          logger.warning("フォルダ内にPDFが見つかりません: %s", item)
          continue

        gcs_uris = [f"gs://{bucket_name}/{k}" for k in pdf_keys]
        docs = process_folder(
          gcs_uris,
          processor_name,
          location,
          gcs_batch_output_prefix=batch_output,
        )
        md_parts = [docai_to_markdown(d) for d in docs]
        md_text = concat_markdowns(md_parts)

        folder_name = item.strip("/").rsplit("/", 1)[-1]
        dest_key = save_markdown(bucket, folder_name, md_text, "output/")
        done_prefix = move_folder_to_done(bucket, item, "done/")

        results.append({
          "type": "folder",
          "source": item,
          "output": dest_key,
          "done": done_prefix,
          "pdf_count": len(pdf_keys),
          "status": "ok",
          "timestamp": ts_start,
        })
        logger.info("完了: %s → %s", item, dest_key)

      else:
        # ── 単体 PDF 処理 ─────────────────────────────────────────
        gcs_uri = f"gs://{bucket_name}/{item}"
        doc = process_single(
          gcs_uri,
          processor_name,
          location,
          gcs_batch_output_prefix=batch_output,
        )
        md_text = docai_to_markdown(doc)
        dest_key = save_markdown(bucket, item, md_text, "output/")
        done_key = move_to_done(bucket, item, "done/")

        results.append({
          "type": "file",
          "source": item,
          "output": dest_key,
          "done": done_key,
          "status": "ok",
          "timestamp": ts_start,
        })
        logger.info("完了: %s → %s", item, dest_key)

    except Exception as exc:
      logger.exception("処理失敗: %s", item)
      results.append({
        "type": "folder" if _is_folder_prefix(item) else "file",
        "source": item,
        "status": "error",
        "error": str(exc),
        "timestamp": ts_start,
      })

  ok = sum(1 for r in results if r["status"] == "ok")
  ng = len(results) - ok
  logger.info("処理完了: 成功=%d 失敗=%d", ok, ng)

  for entry in results:
    log_result(bucket, entry)


if __name__ == "__main__":
  main()
