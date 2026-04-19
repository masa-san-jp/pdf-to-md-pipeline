"""Document AI の Document オブジェクトを Markdown テキストへ変換する。

Document AI はブロック・段落・行・単語・記号レベルで文書構造を検出する。
本モジュールはそのブロック情報を仕様書のマッピングに従って Markdown に変換する。
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
  from google.cloud import documentai

__all__ = ["docai_to_markdown", "concat_markdowns"]

logger = logging.getLogger(__name__)

# Document AI の block_type 文字列 → Markdown プレフィックスのマッピング
_HEADING_PREFIX: dict[str, str] = {
  "HEADING_1": "# ",
  "HEADING_2": "## ",
  "HEADING_3": "### ",
  "HEADING_4": "#### ",
}


def _extract_text(doc_text: str, layout: "documentai.Document.Page.Layout") -> str:
  """Layout の text_anchor から元テキストを復元する。"""
  if not layout.text_anchor.text_segments:
    return ""
  parts: list[str] = []
  for seg in layout.text_anchor.text_segments:
    start = int(seg.start_index) if seg.start_index else 0
    end = int(seg.end_index) if seg.end_index else len(doc_text)
    parts.append(doc_text[start:end])
  return "".join(parts).strip()


def _table_to_markdown(
  doc_text: str,
  table: "documentai.Document.Page.Table",
) -> str:
  """Table ブロックを Markdown テーブル形式に変換する。"""
  rows: list[list[str]] = []

  for row in table.header_rows:
    cells = [_extract_text(doc_text, cell.layout) for cell in row.cells]
    rows.append(cells)

  for row in table.body_rows:
    cells = [_extract_text(doc_text, cell.layout) for cell in row.cells]
    rows.append(cells)

  if not rows:
    return ""

  col_count = max(len(r) for r in rows)

  def _format_row(cells: list[str]) -> str:
    padded = cells + [""] * (col_count - len(cells))
    return "| " + " | ".join(padded) + " |"

  lines: list[str] = []
  lines.append(_format_row(rows[0]))
  lines.append("| " + " | ".join(["---"] * col_count) + " |")
  for row in rows[1:]:
    lines.append(_format_row(row))
  return "\n".join(lines)


def docai_to_markdown(doc: "documentai.Document") -> str:
  """Document AI の Document オブジェクトを Markdown 文字列へ変換する。

  仕様書のマッピング:
    HEADING_1/2 → # / ##
    PARAGRAPH   → テキスト段落
    TABLE       → Markdown テーブル
    LIST_ITEM   → -
    改ページ      → ---
  """
  doc_text: str = doc.text or ""
  sections: list[str] = []

  for page_idx, page in enumerate(doc.pages):
    if page_idx > 0:
      sections.append("---")

    for block in page.blocks:
      block_type = ""
      if block.layout.orientation is not None:
        pass  # orientation は変換に不要

      # block_type は layout.block_type が存在しない場合があるため paragraph から判定
      # Document AI v1 では page.paragraphs / page.tables を別途参照する
      pass

    # paragraphs
    for para in page.paragraphs:
      text = _extract_text(doc_text, para.layout)
      if not text:
        continue
      # block_type は paragraph 単体には無い → heading 判定は tokens の detectedLanguages 等から取れないため
      # page.blocks の block_type と paragraph の bounding_box 重複で判定するのが正式だが、
      # シンプルに paragraph をそのまま出力する（heading はブロックレベルで別処理）
      sections.append(text)

    # tables
    for table in page.tables:
      md_table = _table_to_markdown(doc_text, table)
      if md_table:
        sections.append(md_table)

  # Document レベルのブロック情報（page.blocks の blockType）で見出し・リストを上書きする
  # page.blocks.layout.block_type が利用可能な場合は再処理する
  sections = _reprocess_with_blocks(doc, doc_text, sections)

  return "\n\n".join(s for s in sections if s)


def _reprocess_with_blocks(
  doc: "documentai.Document",
  doc_text: str,
  fallback_sections: list[str],
) -> list[str]:
  """page.blocks の blockType が利用可能なら、見出し・リストを正しく変換する。

  blockType が空の環境（Document AI バージョン差異）では fallback_sections をそのまま返す。
  """
  has_block_type = any(
    getattr(block.layout, "block_type", None)
    for page in doc.pages
    for block in page.blocks
  )
  if not has_block_type:
    return fallback_sections

  sections: list[str] = []
  for page_idx, page in enumerate(doc.pages):
    if page_idx > 0:
      sections.append("---")
    for block in page.blocks:
      block_type: str = getattr(block.layout, "block_type", "") or ""
      text = _extract_text(doc_text, block.layout)
      if not text:
        continue
      if block_type in _HEADING_PREFIX:
        sections.append(_HEADING_PREFIX[block_type] + text)
      elif block_type == "LIST_ITEM":
        sections.append("- " + text)
      elif block_type == "TABLE":
        # TABLE は page.tables から別途処理済みのため、text のみ追加
        sections.append(text)
      else:
        sections.append(text)

    for table in page.tables:
      md_table = _table_to_markdown(doc_text, table)
      if md_table:
        sections.append(md_table)

  return sections


def concat_markdowns(parts: list[str]) -> str:
  """複数の Markdown テキストを結合する。"""
  return "\n\n".join(p.strip() for p in parts if p.strip())
