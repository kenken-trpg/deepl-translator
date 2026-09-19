"""DeepL API クライアント（/v2/translate）。"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Callable

import requests

from .chunker import (
    DEFAULT_MAX_CHARS,
    DEFAULT_MAX_REQUEST_BYTES,
    _split_sentences,
    build_batches,
    split_into_chunks,
)

FREE_URL = "https://api-free.deepl.com/v2/translate"
PRO_URL = "https://api.deepl.com/v2/translate"

SOURCE_LANGS = {"auto": None, "EN": "EN", "DE": "DE"}
TARGET_LANG = "JA"
# 自動付与する context（直前チャンク末尾）の最大文字数
DEFAULT_CONTEXT_CHARS = 1000


class DeepLError(RuntimeError):
    pass


@dataclass
class TranslationResult:
    chunks: list[str]
    translations: list[str]
    detected_source_langs: list[str]
    billed_characters: int

    @property
    def text(self) -> str:
        return "\n\n".join(self.translations)

    def bilingual(self) -> str:
        return "\n\n".join(f"{s}\n\n{t}\n\n---" for s, t in zip(self.chunks, self.translations))


def get_auth_key() -> str:
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass
    key = os.environ.get("DEEPL_AUTH_KEY")
    if not key:
        raise DeepLError("環境変数 DEEPL_AUTH_KEY が設定されていません（.env でも可）")
    return key


def endpoint_for(key: str) -> str:
    return os.environ.get("DEEPL_API_URL") or (FREE_URL if key.endswith(":fx") else PRO_URL)


class DeepLTranslator:
    def __init__(self, auth_key: str | None = None, max_retries: int = 5, timeout: float = 60):
        self.auth_key = auth_key or get_auth_key()
        self.url = endpoint_for(self.auth_key)
        self.max_retries = max_retries
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"DeepL-Auth-Key {self.auth_key}",
                "Content-Type": "application/json",
                "User-Agent": "deepl-translator/0.1",
            }
        )

    def _post(self, body: dict) -> dict:
        delay = 1.0
        for attempt in range(self.max_retries + 1):
            try:
                resp = self.session.post(self.url, json=body, timeout=self.timeout)
            except requests.RequestException as e:
                if attempt == self.max_retries:
                    raise DeepLError(f"通信エラー: {e}") from e
            else:
                if resp.status_code == 200:
                    return resp.json()
                # 429: レート制限 / 5xx: 一時障害 → 指数バックオフで再試行
                if resp.status_code not in (429, 500, 502, 503, 504) or attempt == self.max_retries:
                    raise DeepLError(_error_message(resp))
            time.sleep(delay)
            delay = min(delay * 2, 30)
        raise DeepLError("再試行回数を超えました")

    def translate_texts(self, texts: list[str], source_lang: str | None, **opts) -> list[dict]:
        body = {"text": texts, "target_lang": TARGET_LANG, **opts}
        if source_lang:
            body["source_lang"] = source_lang
        data = self._post(body)
        return data["translations"]

    def translate_document_text(
        self,
        text: str,
        source_lang: str | None = None,
        max_chars: int = DEFAULT_MAX_CHARS,
        max_request_bytes: int = DEFAULT_MAX_REQUEST_BYTES,
        formality: str | None = None,
        context: str | None = None,
        auto_context: bool = True,
        context_chars: int = DEFAULT_CONTEXT_CHARS,
        progress: Callable[[int, int], None] | None = None,
    ) -> TranslationResult:
        """auto_context=True なら、直前チャンク末尾の数文を context として各チャンクに付ける。

        DeepL の context はリクエスト単位なので、auto_context 有効時は 1 チャンク = 1 リクエストになる
        （課金文字数は変わらない。context は課金対象外）。
        """
        chunks = split_into_chunks(text, max_chars=max_chars)
        base: dict = {"show_billed_characters": True}
        if formality:
            base["formality"] = formality

        # (送信テキスト群, 追加パラメータ) のリスト
        requests_: list[tuple[list[str], dict]] = []
        if auto_context:
            for i, chunk in enumerate(chunks):
                ctx = build_context(context, chunks[i - 1] if i else None, context_chars)
                extra = {**base, **({"context": ctx} if ctx else {})}
                requests_.append(([chunk], extra))
        else:
            extra = {**base, **({"context": context} if context else {})}
            size_params = {"target_lang": TARGET_LANG, "source_lang": source_lang or "", **extra}
            for batch in build_batches(chunks, max_request_bytes=max_request_bytes, extra_params=size_params):
                requests_.append((batch.texts, extra))

        translations: list[str] = []
        detected: list[str] = []
        billed = 0
        for n, (texts, extra) in enumerate(requests_, 1):
            results = self.translate_texts(texts, source_lang, **extra)
            for r in results:
                translations.append(r["text"])
                detected.append(r.get("detected_source_language", ""))
                billed += r.get("billed_characters", 0)
            if progress:
                progress(n, len(requests_))
        return TranslationResult(chunks, translations, detected, billed)

    def usage(self) -> dict:
        url = self.url.rsplit("/", 1)[0] + "/usage"
        resp = self.session.get(url, timeout=self.timeout)
        if resp.status_code != 200:
            raise DeepLError(_error_message(resp))
        return resp.json()


def build_context(user_context: str | None, previous_chunk: str | None, max_chars: int) -> str | None:
    """ユーザー指定の context と、直前チャンク末尾の数文（文の途中から始めない）を結合する。"""
    parts: list[str] = []
    if user_context:
        parts.append(user_context.strip())
    if previous_chunk and max_chars > 0:
        tail: list[str] = []
        length = 0
        for sent in reversed(_split_sentences(previous_chunk.replace("\n\n", " "))):
            if tail and length + len(sent) + 1 > max_chars:
                break
            tail.insert(0, sent)
            length += len(sent) + 1
        joined = " ".join(tail)
        parts.append(joined[-max_chars:])  # 1 文が長すぎる場合の保険
    return "\n\n".join(parts) or None


def _error_message(resp: requests.Response) -> str:
    hints = {
        403: "認証失敗（キーまたは Free/Pro エンドポイントを確認）",
        413: "リクエストが大きすぎます（max_request_bytes を小さく）",
        429: "リクエストが多すぎます",
        456: "翻訳文字数の上限（クォータ）に達しました",
    }
    try:
        detail = resp.json().get("message", resp.text)
    except ValueError:
        detail = resp.text
    return f"DeepL API エラー {resp.status_code}: {hints.get(resp.status_code, '')} {detail}".strip()
