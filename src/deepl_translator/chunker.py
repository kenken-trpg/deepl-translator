"""意味の切れ目でテキストをチャンク分割し、DeepL のリクエスト単位にまとめる。

2 段階:
1. split_into_chunks: 段落 > 文 > 節 > 単語 の優先順位で、max_chars（既定 4000）以下のチャンクを作る。
   段落の途中で切ると文脈が壊れるため、次の段落が入り切らない場合は
   max_chars に達していなくてもそこでチャンクを閉じる。
2. build_batches: チャンクを DeepL の 1 リクエスト（JSON ボディ ≦ 約128KB、text ≦ 50 件）に詰める。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

DEFAULT_MAX_CHARS = 4000
# DeepL のリクエストボディ上限は 128 KiB。ヘッダ等の余裕を見て少し小さく。
DEFAULT_MAX_REQUEST_BYTES = 120 * 1024
MAX_TEXTS_PER_REQUEST = 50

# 文末にピリオドが付くが文の終わりではない略語（英・独）
_ABBREVIATIONS = {
    # English
    "mr", "mrs", "ms", "dr", "prof", "sr", "jr", "st", "vs", "etc", "e.g", "i.e",
    "fig", "no", "vol", "p", "pp", "ch", "cf", "approx", "inc", "ltd", "co", "jan",
    "feb", "mar", "apr", "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec",
    # German
    "z.b", "d.h", "u.a", "usw", "bzw", "ca", "vgl", "nr", "s", "hr", "fr", "str",
    "bspw", "ggf", "evtl", "inkl", "zzgl", "abs", "art", "bd", "hrsg", "u.ä", "o.ä",
    "sog", "etc", "z.t", "u.u", "v.a", "dt", "jh", "mio", "mrd",
}

# 文末候補: . ! ? (… も) の後に閉じ引用符/括弧があってもよく、その後に空白
_SENTENCE_END = re.compile(r"[.!?…]+[\"'”’»)\]]*\s+")
_CLAUSE_END = re.compile(r"[;:,—–]\s+")


def split_into_chunks(text: str, max_chars: int = DEFAULT_MAX_CHARS) -> list[str]:
    if max_chars < 50:
        raise ValueError("max_chars は 50 以上にしてください")
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]

    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    def flush() -> None:
        nonlocal current, current_len
        if current:
            chunks.append("\n\n".join(current))
            current, current_len = [], 0

    for para in paragraphs:
        if len(para) > max_chars:
            # 長い段落は単独で文単位に分割（前の段落とは混ぜない）
            flush()
            chunks.extend(_pack(_split_sentences(para), max_chars, sep=" "))
            continue
        added = len(para) + (2 if current else 0)
        if current_len + added > max_chars:
            flush()
            added = len(para)
        current.append(para)
        current_len += added
    flush()
    return chunks


def _pack(units: list[str], max_chars: int, sep: str) -> list[str]:
    """units を順に max_chars 以下で貪欲に詰める。単体で超える unit はさらに細かく割る。"""
    out: list[str] = []
    buf = ""
    for u in units:
        if len(u) > max_chars:
            if buf:
                out.append(buf)
                buf = ""
            out.extend(_split_oversized(u, max_chars))
            continue
        candidate = f"{buf}{sep}{u}" if buf else u
        if len(candidate) > max_chars:
            out.append(buf)
            buf = u
        else:
            buf = candidate
    if buf:
        out.append(buf)
    return out


def _split_oversized(sentence: str, max_chars: int) -> list[str]:
    """1 文が max_chars を超える場合: 節（; : ,）→ 空白 → 強制切断 の順で割る。"""
    clauses = _split_keep(sentence, _CLAUSE_END)
    if len(clauses) > 1:
        return _pack(clauses, max_chars, sep=" ")
    words = sentence.split(" ")
    if len(words) > 1:
        return _pack(words, max_chars, sep=" ")
    return [sentence[i : i + max_chars] for i in range(0, len(sentence), max_chars)]


def _split_keep(text: str, pattern: re.Pattern[str]) -> list[str]:
    parts: list[str] = []
    start = 0
    for m in pattern.finditer(text):
        parts.append(text[start : m.end()].strip())
        start = m.end()
    if start < len(text):
        parts.append(text[start:].strip())
    return [p for p in parts if p]


def _split_sentences(text: str) -> list[str]:
    sentences: list[str] = []
    start = 0
    for m in _SENTENCE_END.finditer(text):
        end = m.end()
        before = text[start : m.start() + 1]
        after = text[end:]
        if not _is_sentence_boundary(before, after):
            continue
        sentences.append(text[start:end].strip())
        start = end
    if start < len(text):
        sentences.append(text[start:].strip())
    return [s for s in sentences if s]


def _is_sentence_boundary(before: str, after: str) -> bool:
    if not after:
        return True
    # 次が小文字始まりなら文の途中（英独とも。独の名詞は大文字なので誤結合は少ない）
    if after[0].islower():
        return False
    if not before.endswith("."):
        return True
    last_token = before.rstrip(".").rsplit(None, 1)[-1] if before.strip(". ") else ""
    token = last_token.lower().lstrip("(\"'„“")
    if token in _ABBREVIATIONS:
        return False
    # 単一の大文字イニシャル (J. R. R. Tolkien)
    if len(token) == 1 and token.isalpha():
        return False
    # ドイツ語の序数 "3. Mai" / 箇条番号
    if token.isdigit() and len(token) <= 3:
        return False
    return True


@dataclass
class Batch:
    texts: list[str] = field(default_factory=list)
    start_index: int = 0


def request_body_size(texts: list[str], extra: dict | None = None) -> int:
    """DeepL に送る JSON ボディのバイト数を計算する。"""
    body = {"text": texts, **(extra or {})}
    return len(json.dumps(body, ensure_ascii=False).encode("utf-8"))


def build_batches(
    chunks: list[str],
    max_request_bytes: int = DEFAULT_MAX_REQUEST_BYTES,
    max_texts: int = MAX_TEXTS_PER_REQUEST,
    extra_params: dict | None = None,
) -> list[Batch]:
    batches: list[Batch] = []
    cur = Batch(start_index=0)
    for i, chunk in enumerate(chunks):
        trial = cur.texts + [chunk]
        too_big = request_body_size(trial, extra_params) > max_request_bytes
        if cur.texts and (too_big or len(trial) > max_texts):
            batches.append(cur)
            cur = Batch(start_index=i)
            trial = [chunk]
        if request_body_size(trial, extra_params) > max_request_bytes:
            raise ValueError(f"チャンク {i} 単体でリクエスト上限を超えています。max_chars を小さくしてください")
        cur.texts = trial
    if cur.texts:
        batches.append(cur)
    return batches
