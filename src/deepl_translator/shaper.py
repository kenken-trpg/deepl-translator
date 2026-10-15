"""PDF 等からコピーしたテキストの整形（改行・ハイフネーションの除去）。

- 行末ハイフネーションの除去: "trans-\\nlation" → "translation"
  次の行が大文字で始まる場合（独語の複合語 "Max-\\nPlanck" 等）と数字の範囲（"1990-\\n2000"）は
  ハイフンを残して結合する。
- 段落内の改行をスペースに置換
- 空行は段落区切りとして残す（keep_paragraphs=False で 1 行に平坦化）
"""
from __future__ import annotations

import re
from urllib.parse import quote

DEEPL_WEB_URL = "https://www.deepl.com/translator#{src}/ja/{text}"

_HYPHEN_BREAK = re.compile(r"(\w)[-­]\s*\n\s*(\w)")
_SOFT_HYPHEN = "­"


def shape_text(text: str, keep_paragraphs: bool = True) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace(" ", " ")
    text = _HYPHEN_BREAK.sub(_join_hyphen, text)
    text = text.replace(_SOFT_HYPHEN, "")
    paragraphs = re.split(r"\n\s*\n", text)
    joined = [re.sub(r"\s+", " ", p).strip() for p in paragraphs]
    joined = [p for p in joined if p]
    return ("\n\n" if keep_paragraphs else " ").join(joined)


def _join_hyphen(m: re.Match[str]) -> str:
    before, after = m.group(1), m.group(2)
    # 大文字始まり（独語の複合語）と数字の範囲 "1990-\n2000" はハイフンを残す
    if after.isupper() or (before.isdigit() and after.isdigit()):
        return f"{before}-{after}"
    return f"{before}{after}"


def deepl_web_url(text: str, source_lang: str | None = None) -> str:
    """DeepL Web 翻訳を開く URL。"#" 以降のフラグメント内で壊れる記号は全角化してから URL エンコードする。"""
    safe = text.translate(str.maketrans({"/": "／", "|": "｜", "#": "＃", "\\": "＼"}))
    src = (source_lang or "auto").lower()
    return DEEPL_WEB_URL.format(src=src if src in ("en", "de") else "auto", text=quote(safe, safe=""))
