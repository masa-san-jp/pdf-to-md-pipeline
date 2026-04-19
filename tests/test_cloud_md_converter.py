"""`cloud.md_converter` のユニットテスト。

google-cloud-documentai を直接インポートせずに動作するよう、
Document・Page・Layout などのデータクラスをシンプルなスタブで代替する。
"""
from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock


# ──────────────────────────────────────────────────────────────────────────────
# google.cloud.documentai スタブ
# ──────────────────────────────────────────────────────────────────────────────

def _make_text_segment(start: int, end: int):
  seg = MagicMock()
  seg.start_index = start
  seg.end_index = end
  return seg


def _make_layout(text: str, full_text: str, block_type: str = ""):
  """full_text 中の text に対応する Layout を作る。"""
  layout = MagicMock()
  start = full_text.index(text)
  end = start + len(text)
  seg = _make_text_segment(start, end)
  layout.text_anchor.text_segments = [seg]
  layout.block_type = block_type
  return layout


def _stub_documentai():
  """google.cloud.documentai を最小限のスタブモジュールに差し替える。"""
  mod = types.ModuleType("google.cloud.documentai")

  class Document:
    def __init__(self, text="", pages=None):
      self.text = text
      self.pages = pages or []

  class Page:
    def __init__(self, paragraphs=None, tables=None, blocks=None):
      self.paragraphs = paragraphs or []
      self.tables = tables or []
      self.blocks = blocks or []

  class Paragraph:
    def __init__(self, layout):
      self.layout = layout

  class Block:
    def __init__(self, layout):
      self.layout = layout

  class Table:
    def __init__(self, header_rows=None, body_rows=None):
      self.header_rows = header_rows or []
      self.body_rows = body_rows or []

  class TableRow:
    def __init__(self, cells):
      self.cells = cells

  class TableCell:
    def __init__(self, layout):
      self.layout = layout

  mod.Document = Document
  mod.Page = Page
  mod.Paragraph = Paragraph
  mod.Block = Block
  mod.Table = Table
  mod.TableRow = TableRow
  mod.TableCell = TableCell

  # google / google.cloud パッケージも登録
  google_mod = sys.modules.get("google") or types.ModuleType("google")
  google_cloud = sys.modules.get("google.cloud") or types.ModuleType("google.cloud")
  google_mod.cloud = google_cloud
  google_cloud.documentai = mod
  sys.modules.setdefault("google", google_mod)
  sys.modules.setdefault("google.cloud", google_cloud)
  sys.modules["google.cloud.documentai"] = mod
  return mod


_stub_documentai()

from cloud.md_converter import concat_markdowns, docai_to_markdown  # noqa: E402


# ──────────────────────────────────────────────────────────────────────────────
# ヘルパー
# ──────────────────────────────────────────────────────────────────────────────

def _doc_with_paragraphs(texts: list[str]):
  """複数段落を持つ Document を生成する。"""
  import sys
  docai = sys.modules["google.cloud.documentai"]
  full_text = "\n".join(texts)

  paragraphs = []
  for t in texts:
    layout = _make_layout(t, full_text)
    paragraphs.append(docai.Paragraph(layout))

  page = docai.Page(paragraphs=paragraphs)
  return docai.Document(text=full_text, pages=[page])


def _doc_with_table(headers: list[str], rows: list[list[str]]):
  """テーブルを持つ Document を生成する。"""
  import sys
  docai = sys.modules["google.cloud.documentai"]

  all_cells = headers + [c for row in rows for c in row]
  full_text = "\t".join(all_cells)

  def make_cell(text: str):
    layout = _make_layout(text, full_text)
    return docai.TableCell(layout)

  header_row = docai.TableRow([make_cell(h) for h in headers])
  body_rows = [docai.TableRow([make_cell(c) for c in row]) for row in rows]
  table = docai.Table(header_rows=[header_row], body_rows=body_rows)
  page = docai.Page(tables=[table])
  return docai.Document(text=full_text, pages=[page])


# ──────────────────────────────────────────────────────────────────────────────
# テスト
# ──────────────────────────────────────────────────────────────────────────────

def test_single_paragraph():
  doc = _doc_with_paragraphs(["Hello world"])
  md = docai_to_markdown(doc)
  assert "Hello world" in md


def test_multiple_paragraphs_separated():
  doc = _doc_with_paragraphs(["First paragraph", "Second paragraph"])
  md = docai_to_markdown(doc)
  assert "First paragraph" in md
  assert "Second paragraph" in md


def test_page_break_inserts_horizontal_rule():
  import sys
  docai = sys.modules["google.cloud.documentai"]
  full = "Page one\nPage two"

  def make_para(text):
    layout = _make_layout(text, full)
    return docai.Paragraph(layout)

  pages = [
    docai.Page(paragraphs=[make_para("Page one")]),
    docai.Page(paragraphs=[make_para("Page two")]),
  ]
  doc = docai.Document(text=full, pages=pages)
  md = docai_to_markdown(doc)
  assert "---" in md
  assert "Page one" in md
  assert "Page two" in md


def test_table_converted_to_markdown_table():
  doc = _doc_with_table(["Name", "Age"], [["Alice", "30"], ["Bob", "25"]])
  md = docai_to_markdown(doc)
  assert "| Name | Age |" in md
  assert "| --- | --- |" in md
  assert "| Alice | 30 |" in md
  assert "| Bob | 25 |" in md


def test_block_type_heading_1():
  import sys
  docai = sys.modules["google.cloud.documentai"]
  full = "Introduction"
  layout = _make_layout("Introduction", full, block_type="HEADING_1")
  block = docai.Block(layout)
  page = docai.Page(blocks=[block])
  doc = docai.Document(text=full, pages=[page])
  md = docai_to_markdown(doc)
  assert "# Introduction" in md


def test_block_type_heading_2():
  import sys
  docai = sys.modules["google.cloud.documentai"]
  full = "Section"
  layout = _make_layout("Section", full, block_type="HEADING_2")
  block = docai.Block(layout)
  page = docai.Page(blocks=[block])
  doc = docai.Document(text=full, pages=[page])
  md = docai_to_markdown(doc)
  assert "## Section" in md


def test_block_type_list_item():
  import sys
  docai = sys.modules["google.cloud.documentai"]
  full = "Item one"
  layout = _make_layout("Item one", full, block_type="LIST_ITEM")
  block = docai.Block(layout)
  page = docai.Page(blocks=[block])
  doc = docai.Document(text=full, pages=[page])
  md = docai_to_markdown(doc)
  assert "- Item one" in md


def test_empty_document():
  import sys
  docai = sys.modules["google.cloud.documentai"]
  doc = docai.Document(text="", pages=[])
  md = docai_to_markdown(doc)
  assert md == ""


def test_concat_markdowns_joins_with_double_newline():
  parts = ["# Title", "Body text", "## Section"]
  result = concat_markdowns(parts)
  assert result == "# Title\n\nBody text\n\n## Section"


def test_concat_markdowns_skips_empty():
  parts = ["First", "", "   ", "Last"]
  result = concat_markdowns(parts)
  assert result == "First\n\nLast"
