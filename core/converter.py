"""PDF → Markdown 変換の共通ロジック。

`opendataloader_pdf.convert` を呼び出して単体PDF・フォルダ単位の変換と、
処理済みファイルの `done/` への移動（タイムスタンプ付与）を行う。
`local/` と `colab/` 両バリアントから参照される。
"""
from __future__ import annotations

import logging
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

__all__ = ["convert_single", "convert_folder", "move_to_done"]

logger = logging.getLogger(__name__)


def _timestamp() -> str:
  return datetime.now().strftime("%Y%m%d_%H%M%S")


def _build_kwargs(
  input_paths: list[str],
  output_dir: Path,
  hybrid: Optional[str],
  use_struct_tree: bool,
) -> dict:
  kwargs: dict = {
    "input_path": input_paths,
    "output_dir": str(output_dir),
    "format": "markdown",
    "use_struct_tree": use_struct_tree,
  }
  if hybrid:
    kwargs["hybrid"] = hybrid
  return kwargs


def convert_single(
  pdf: Path,
  output_dir: Path,
  *,
  hybrid: Optional[str] = None,
  use_struct_tree: bool = True,
) -> Path:
  """単体PDFを変換し、`output_dir/{stem}.md` を返す。"""
  import opendataloader_pdf

  output_dir.mkdir(parents=True, exist_ok=True)
  opendataloader_pdf.convert(
    **_build_kwargs([str(pdf)], output_dir, hybrid, use_struct_tree)
  )
  result = output_dir / f"{pdf.stem}.md"
  logger.info("変換: %s → %s", pdf, result)
  return result


def convert_folder(
  pdfs: Iterable[Path],
  folder_name: str,
  output_dir: Path,
  *,
  hybrid: Optional[str] = None,
  use_struct_tree: bool = True,
) -> Path:
  """フォルダ内のPDFをファイル名昇順で変換し、単一Markdownへ連結する。"""
  import opendataloader_pdf

  pdfs = list(pdfs)
  if not pdfs:
    raise ValueError(f"変換対象のPDFが空です: {folder_name}")

  output_dir.mkdir(parents=True, exist_ok=True)
  final = output_dir / f"{folder_name}.md"

  with tempfile.TemporaryDirectory() as tmp:
    tmp_dir = Path(tmp)
    opendataloader_pdf.convert(
      **_build_kwargs([str(p) for p in pdfs], tmp_dir, hybrid, use_struct_tree)
    )
    parts: list[str] = []
    missing_results: list[Path] = []
    for pdf in pdfs:
      md = tmp_dir / f"{pdf.stem}.md"
      if md.exists():
        parts.append(md.read_text(encoding="utf-8"))
      else:
        logger.warning("変換結果が見つかりません: %s", md)
        missing_results.append(md)

    if missing_results:
      missing_list = ", ".join(str(path) for path in missing_results)
      raise FileNotFoundError(
        f"変換結果が不足しているため連結Markdownを生成できません: "
        f"{folder_name} ({len(missing_results)}件欠落: {missing_list})"
      )
    final.write_text("\n\n".join(parts), encoding="utf-8")

  logger.info("変換: %s (%d件) → %s", folder_name, len(pdfs), final)
  return final


def move_to_done(src: Path, done_dir: Path, *, add_timestamp: bool = True) -> Path:
  """ファイル/ディレクトリを `done_dir` へ移動。既定でタイムスタンプを付与して衝突を回避する。"""
  done_dir.mkdir(parents=True, exist_ok=True)
  if add_timestamp:
    stamp = _timestamp()
    if src.is_file():
      dst = done_dir / f"{src.stem}_{stamp}{src.suffix}"
    else:
      dst = done_dir / f"{src.name}_{stamp}"
  else:
    dst = done_dir / src.name
  shutil.move(str(src), str(dst))
  logger.info("移動: %s → %s", src, dst)
  return dst
