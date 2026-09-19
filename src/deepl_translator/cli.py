"""CLI: deepl-translate input.pdf -s EN -o out.txt"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .chunker import DEFAULT_MAX_CHARS, DEFAULT_MAX_REQUEST_BYTES, build_batches, split_into_chunks
from .extract import extract_text
from .shaper import deepl_web_url, shape_text
from .translator import DEFAULT_CONTEXT_CHARS, SOURCE_LANGS, DeepLError, DeepLTranslator


def shape_main(argv: list[str] | None = None) -> int:
    """deepl-shape: 標準入力（またはファイル）の改行・ハイフネーションを整形して出力。"""
    p = argparse.ArgumentParser(description="PDF からコピーした英文/独文の改行・ハイフネーションを除去します")
    p.add_argument("input", nargs="?", type=Path, help="入力ファイル（省略時は標準入力）")
    p.add_argument("--flat", action="store_true", help="段落区切りも除去して 1 行にする")
    p.add_argument("--url", action="store_true", help="DeepL Web 翻訳の URL を出力する")
    args = p.parse_args(argv)
    raw = extract_text(args.input) if args.input and args.input.suffix.lower() != ".txt" else (
        args.input.read_text(encoding="utf-8") if args.input else sys.stdin.read()
    )
    shaped = shape_text(raw, keep_paragraphs=not args.flat)
    print(deepl_web_url(shaped) if args.url else shaped)
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="txt/docx/pdf を DeepL で日本語に翻訳します")
    p.add_argument("input", type=Path, help="入力ファイル (.txt / .docx / .pdf)。'-' で標準入力")
    p.add_argument("-s", "--source", choices=list(SOURCE_LANGS), default="auto", help="原文言語 (既定: auto)")
    p.add_argument("-o", "--output", type=Path, help="出力ファイル（省略時は標準出力）")
    p.add_argument("--max-chars", type=int, default=DEFAULT_MAX_CHARS, help="1 チャンクの最大文字数")
    p.add_argument("--max-request-bytes", type=int, default=DEFAULT_MAX_REQUEST_BYTES)
    p.add_argument("--formality", choices=["default", "more", "less", "prefer_more", "prefer_less"])
    p.add_argument("--context", help="翻訳の文脈ヒント（課金対象外）")
    p.add_argument("--no-auto-context", action="store_true", help="直前チャンクの自動 context 付与を無効化（複数チャンクをまとめて送信）")
    p.add_argument("--context-chars", type=int, default=DEFAULT_CONTEXT_CHARS, help="自動 context の最大文字数")
    p.add_argument("--bilingual", action="store_true", help="原文と訳文を交互に出力")
    p.add_argument("--dry-run", action="store_true", help="API を呼ばずに抽出・分割結果だけ表示")
    p.add_argument("--dump-chunks", type=Path, help="分割結果をこのファイルに書き出す")
    args = p.parse_args(argv)

    try:
        text = shape_text(sys.stdin.read()) if str(args.input) == "-" else extract_text(args.input)
    except (ValueError, OSError) as e:
        print(f"抽出エラー: {e}", file=sys.stderr)
        return 1

    chunks = split_into_chunks(text, max_chars=args.max_chars)
    n_requests = len(chunks) if not args.no_auto_context else len(
        build_batches(chunks, max_request_bytes=args.max_request_bytes)
    )
    print(
        f"抽出 {len(text):,} 文字 → {len(chunks)} チャンク → {n_requests} リクエスト",
        file=sys.stderr,
    )
    if args.dump_chunks:
        args.dump_chunks.write_text(
            "\n".join(f"===== chunk {i} ({len(c)} chars) =====\n{c}\n" for i, c in enumerate(chunks)),
            encoding="utf-8",
        )
    if args.dry_run:
        for i, c in enumerate(chunks):
            print(f"[{i}] {len(c):>5} chars | {c[:70]!r}")
        return 0

    try:
        tr = DeepLTranslator()
        result = tr.translate_document_text(
            text,
            source_lang=SOURCE_LANGS[args.source],
            max_chars=args.max_chars,
            max_request_bytes=args.max_request_bytes,
            formality=args.formality,
            context=args.context,
            auto_context=not args.no_auto_context,
            context_chars=args.context_chars,
            progress=lambda n, t: print(f"  翻訳中 {n}/{t}", file=sys.stderr),
        )
    except DeepLError as e:
        print(e, file=sys.stderr)
        return 2

    out = result.bilingual() if args.bilingual else result.text
    if args.output:
        args.output.write_text(out + "\n", encoding="utf-8")
        print(f"書き出し: {args.output}", file=sys.stderr)
    else:
        print(out)
    print(f"課金文字数: {result.billed_characters:,}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
