"""CLI: deepl-translate input.pdf -s EN -o out.txt"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .chunker import DEFAULT_MAX_CHARS, DEFAULT_MAX_REQUEST_BYTES, build_batches, split_into_chunks
from .extract import extract_text
from .translator import DEFAULT_CONTEXT_CHARS, SOURCE_LANGS, DeepLError, DeepLTranslator


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="txt/docx/pdf を DeepL で日本語に翻訳します")
    p.add_argument("input", type=Path, help="入力ファイル (.txt / .docx / .pdf)")
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
        text = extract_text(args.input)
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
