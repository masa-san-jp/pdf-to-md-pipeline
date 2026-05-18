"""`cloud/main.py` のユニットテスト。

google.cloud.* 依存をすべてモック化して変換ロジックと GCS 操作を検証する。
"""
from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock

import pytest


# ─── Google stubs ─────────────────────────────────────────────────────────────

class _MockDocumentLayout:
  def __init__(self) -> None:
    self.blocks: list = []


class _MockDocument:
  def __init__(self) -> None:
    self.text = ""
    self.pages: list = []
    self.document_layout = _MockDocumentLayout()

  @staticmethod
  def from_json(s: str) -> "_MockDocument":
    return _MockDocument()


def _install_stubs(monkeypatch) -> None:
  """google.cloud.* の最小スタブを sys.modules に注入する。"""

  class _InvalidArgument(Exception):
    pass

  docai = types.ModuleType("google.cloud.documentai_v1")
  docai.Document = _MockDocument  # type: ignore[attr-defined]
  for name in (
    "DocumentProcessorServiceClient",
    "ProcessRequest",
    "ProcessOptions",
    "OcrConfig",
    "GcsDocument",
    "BatchProcessRequest",
    "BatchDocumentsInputConfig",
    "GcsDocuments",
    "DocumentOutputConfig",
  ):
    setattr(docai, name, MagicMock)

  storage = types.ModuleType("google.cloud.storage")
  storage.Client = MagicMock  # type: ignore[attr-defined]

  exc_mod = types.ModuleType("google.api_core.exceptions")
  exc_mod.InvalidArgument = _InvalidArgument  # type: ignore[attr-defined]

  google = types.ModuleType("google")
  google_cloud = types.ModuleType("google.cloud")
  google_api_core = types.ModuleType("google.api_core")
  google.cloud = google_cloud  # type: ignore[attr-defined]
  google.api_core = google_api_core  # type: ignore[attr-defined]
  google_cloud.documentai_v1 = docai  # type: ignore[attr-defined]
  google_cloud.storage = storage  # type: ignore[attr-defined]
  google_api_core.exceptions = exc_mod  # type: ignore[attr-defined]

  for mod_name, mod in [
    ("google", google),
    ("google.cloud", google_cloud),
    ("google.cloud.documentai_v1", docai),
    ("google.cloud.storage", storage),
    ("google.api_core", google_api_core),
    ("google.api_core.exceptions", exc_mod),
  ]:
    monkeypatch.setitem(sys.modules, mod_name, mod)

  monkeypatch.delitem(sys.modules, "cloud.main", raising=False)


@pytest.fixture(autouse=True)
def _stubs(monkeypatch):
  _install_stubs(monkeypatch)
  monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "test-project")
  monkeypatch.setenv("DOCUMENT_AI_PROCESSOR_ID", "test-processor")
  monkeypatch.setenv("GCS_BUCKET_NAME", "test-bucket")


# ─── helpers ─────────────────────────────────────────────────────────────────

def _blob(name: str) -> MagicMock:
  b = MagicMock()
  b.name = name
  return b


# ─── list_input_items ─────────────────────────────────────────────────────────

def test_list_input_items_direct_pdf():
  from cloud.main import list_input_items

  bucket = MagicMock()
  bucket.list_blobs.return_value = [_blob("input/report.pdf")]

  result = list_input_items(bucket)

  assert "input/report.pdf" in result
  assert len(result["input/report.pdf"]) == 1


def test_list_input_items_groups_folder_and_sorts():
  from cloud.main import list_input_items

  bucket = MagicMock()
  bucket.list_blobs.return_value = [
    _blob("input/bundle/02_body.pdf"),
    _blob("input/bundle/01_intro.pdf"),
  ]

  result = list_input_items(bucket)

  assert "input/bundle/" in result
  names = [b.name for b in result["input/bundle/"]]
  assert names == ["input/bundle/01_intro.pdf", "input/bundle/02_body.pdf"]


def test_list_input_items_skips_prefix_blob():
  from cloud.main import list_input_items

  bucket = MagicMock()
  bucket.list_blobs.return_value = [_blob("input/"), _blob("input/doc.pdf")]

  result = list_input_items(bucket)

  assert "input/" not in result
  assert "input/doc.pdf" in result


def test_list_input_items_empty():
  from cloud.main import list_input_items

  bucket = MagicMock()
  bucket.list_blobs.return_value = []

  assert list_input_items(bucket) == {}


# ─── save_markdown ────────────────────────────────────────────────────────────

def test_save_markdown_single_pdf():
  from cloud.main import save_markdown

  bucket = MagicMock()
  dest = save_markdown(bucket, "input/report.pdf", "# Hello")

  assert dest == "output/report.md"


def test_save_markdown_folder():
  from cloud.main import save_markdown

  bucket = MagicMock()
  dest = save_markdown(bucket, "input/bundle/", "# Bundled")

  assert dest == "output/bundle.md"


# ─── move_to_done ─────────────────────────────────────────────────────────────

def test_move_to_done_single_file_copies_then_deletes():
  from cloud.main import move_to_done

  blob = MagicMock()
  bucket = MagicMock()
  bucket.blob.return_value = blob

  move_to_done(bucket, "input/doc.pdf")

  bucket.copy_blob.assert_called_once()
  dest = bucket.copy_blob.call_args[1]["new_name"]
  assert dest.startswith("done/doc_")
  assert dest.endswith(".pdf")
  blob.delete.assert_called_once()


def test_move_to_done_folder_moves_all_blobs():
  from cloud.main import move_to_done

  inner = [_blob("input/bundle/01.pdf"), _blob("input/bundle/02.pdf")]
  bucket = MagicMock()
  bucket.list_blobs.return_value = inner

  move_to_done(bucket, "input/bundle/")

  assert bucket.copy_blob.call_count == 2
  dest_names = [call[1]["new_name"] for call in bucket.copy_blob.call_args_list]
  assert all(n.startswith("done/bundle_") for n in dest_names)
  for b in inner:
    b.delete.assert_called_once()


# ─── _layout_text_to_md ───────────────────────────────────────────────────────

@pytest.mark.parametrize("type_,text,expected", [
  ("heading_1", "はじめに", "# はじめに"),
  ("heading-1", "はじめに", "# はじめに"),
  ("heading_2", "背景", "## 背景"),
  ("heading_3", "詳細", "### 詳細"),
  ("paragraph", "本文テキスト", "本文テキスト"),
  ("list_item", "アイテム", "- アイテム"),
])
def test_layout_text_to_md_block_types(type_: str, text: str, expected: str):
  from cloud.main import _layout_text_to_md

  block = MagicMock()
  block.type_ = type_
  block.text = text
  block.blocks = []

  assert _layout_text_to_md(block) == expected


def test_layout_text_to_md_list_with_sub_blocks():
  from cloud.main import _layout_text_to_md

  sub1, sub2 = MagicMock(), MagicMock()
  sub1.text = "項目1"
  sub2.text = "項目2"

  block = MagicMock()
  block.type_ = "list"
  block.text = ""
  block.blocks = [sub1, sub2]

  assert _layout_text_to_md(block) == "- 項目1\n- 項目2"


# ─── convert_docai_document_to_markdown (layout path) ────────────────────────

def test_convert_layout_path_headings_and_paragraph():
  from cloud.main import convert_docai_document_to_markdown

  doc = _MockDocument()

  def _text_block(type_: str, text: str):
    tb = MagicMock()
    tb.type_ = type_
    tb.text = text
    tb.blocks = []
    blk = MagicMock()
    blk.page_span = None
    blk.table_block = None
    blk.text_block = tb
    return blk

  doc.document_layout.blocks = [
    _text_block("heading_1", "タイトル"),
    _text_block("paragraph", "本文です。"),
  ]

  result = convert_docai_document_to_markdown(doc)

  assert "# タイトル" in result
  assert "本文です。" in result


# ─── convert_docai_document_to_markdown (fallback path) ──────────────────────

def test_convert_fallback_extracts_block_text():
  from cloud.main import convert_docai_document_to_markdown

  doc = _MockDocument()
  doc.text = "Hello"
  doc.document_layout.blocks = []  # trigger fallback

  seg = MagicMock()
  seg.start_index = 0
  seg.end_index = 5

  block = MagicMock()
  block.layout.text_anchor.text_segments = [seg]
  block.layout.bounding_poly.normalized_vertices = [MagicMock(y=0.0)]

  page = MagicMock()
  page.tables = []
  page.blocks = [block]
  doc.pages = [page]

  assert convert_docai_document_to_markdown(doc) == "Hello"


def test_convert_fallback_adds_page_break_between_pages():
  from cloud.main import convert_docai_document_to_markdown

  doc = _MockDocument()
  doc.text = "Page1Page2"
  doc.document_layout.blocks = []

  def _page(start: int, end: int, y: float = 0.0):
    seg = MagicMock()
    seg.start_index = start
    seg.end_index = end
    block = MagicMock()
    block.layout.text_anchor.text_segments = [seg]
    block.layout.bounding_poly.normalized_vertices = [MagicMock(y=y)]
    page = MagicMock()
    page.tables = []
    page.blocks = [block]
    return page

  doc.pages = [_page(0, 5), _page(5, 10)]

  result = convert_docai_document_to_markdown(doc)

  assert "---" in result
  assert "Page1" in result
  assert "Page2" in result
