"""`cloud.gcs_ops` のユニットテスト。

google-cloud-storage をモック化し、GCS API 呼び出し不要でテストする。
"""
from __future__ import annotations

import json
import sys
import types
from unittest.mock import MagicMock, call, patch


# ──────────────────────────────────────────────────────────────────────────────
# google.cloud.storage スタブ（最小限）
# ──────────────────────────────────────────────────────────────────────────────

def _stub_storage():
  mod = types.ModuleType("google.cloud.storage")
  mod.Client = MagicMock
  google_mod = sys.modules.get("google") or types.ModuleType("google")
  google_cloud = sys.modules.get("google.cloud") or types.ModuleType("google.cloud")
  google_mod.cloud = google_cloud
  google_cloud.storage = mod
  sys.modules.setdefault("google", google_mod)
  sys.modules.setdefault("google.cloud", google_cloud)
  sys.modules["google.cloud.storage"] = mod
  return mod


_stub_storage()

from cloud.gcs_ops import (  # noqa: E402
  log_result,
  move_folder_to_done,
  move_to_done,
  save_markdown,
)


# ──────────────────────────────────────────────────────────────────────────────
# ヘルパー
# ──────────────────────────────────────────────────────────────────────────────

def _make_bucket():
  bucket = MagicMock()
  return bucket


# ──────────────────────────────────────────────────────────────────────────────
# save_markdown
# ──────────────────────────────────────────────────────────────────────────────

def test_save_markdown_single_pdf():
  bucket = _make_bucket()
  dest = save_markdown(bucket, "input/sample.pdf", "# Hello", "output/")
  assert dest == "output/sample.md"
  bucket.blob.assert_called_with("output/sample.md")
  bucket.blob.return_value.upload_from_string.assert_called_once()


def test_save_markdown_folder_name():
  bucket = _make_bucket()
  dest = save_markdown(bucket, "my_folder", "# Content", "output/")
  assert dest == "output/my_folder.md"


def test_save_markdown_strips_trailing_slash():
  bucket = _make_bucket()
  dest = save_markdown(bucket, "input/doc.pdf", "text", "output")
  assert dest == "output/doc.md"


# ──────────────────────────────────────────────────────────────────────────────
# move_to_done
# ──────────────────────────────────────────────────────────────────────────────

def test_move_to_done_renames_with_timestamp():
  bucket = _make_bucket()
  dest = move_to_done(bucket, "input/doc.pdf", "done/")
  # done/doc_<timestamp>.pdf の形式
  assert dest.startswith("done/doc_")
  assert dest.endswith(".pdf")
  bucket.blob.return_value.delete.assert_called_once()


def test_move_to_done_no_timestamp():
  bucket = _make_bucket()
  dest = move_to_done(bucket, "input/doc.pdf", "done/", add_timestamp=False)
  assert dest == "done/doc.pdf"


def test_move_to_done_copies_then_deletes():
  bucket = _make_bucket()
  move_to_done(bucket, "input/doc.pdf", "done/")
  bucket.copy_blob.assert_called_once()
  bucket.blob.return_value.delete.assert_called_once()


# ──────────────────────────────────────────────────────────────────────────────
# move_folder_to_done
# ──────────────────────────────────────────────────────────────────────────────

def test_move_folder_to_done_moves_all_blobs():
  bucket = _make_bucket()
  blob1 = MagicMock()
  blob1.name = "input/bundle/01.pdf"
  blob2 = MagicMock()
  blob2.name = "input/bundle/02.pdf"
  bucket.client.list_blobs.return_value = [blob1, blob2]

  dest_prefix = move_folder_to_done(bucket, "input/bundle/", "done/")

  assert "bundle_" in dest_prefix
  assert dest_prefix.endswith("/")
  assert bucket.copy_blob.call_count == 2
  assert blob1.delete.call_count == 1
  assert blob2.delete.call_count == 1


def test_move_folder_to_done_no_timestamp():
  bucket = _make_bucket()
  bucket.client.list_blobs.return_value = []
  dest_prefix = move_folder_to_done(bucket, "input/bundle/", "done/", add_timestamp=False)
  assert dest_prefix == "done/bundle/"


# ──────────────────────────────────────────────────────────────────────────────
# log_result
# ──────────────────────────────────────────────────────────────────────────────

def test_log_result_creates_jsonl_entry():
  bucket = _make_bucket()
  blob = MagicMock()
  blob.exists.return_value = False
  bucket.blob.return_value = blob

  entry = {"source": "input/doc.pdf", "status": "ok"}
  log_result(bucket, entry, "logs/")

  blob.upload_from_string.assert_called_once()
  uploaded = blob.upload_from_string.call_args[0][0]
  line = json.loads(uploaded.strip())
  assert line["source"] == "input/doc.pdf"
  assert line["status"] == "ok"


def test_log_result_appends_to_existing():
  bucket = _make_bucket()
  blob = MagicMock()
  blob.exists.return_value = True
  blob.download_as_text.return_value = '{"previous": true}\n'
  bucket.blob.return_value = blob

  log_result(bucket, {"new": True}, "logs/")

  uploaded = blob.upload_from_string.call_args[0][0]
  lines = [l for l in uploaded.strip().splitlines() if l]
  assert len(lines) == 2
  assert json.loads(lines[0]) == {"previous": True}
  assert json.loads(lines[1]) == {"new": True}
