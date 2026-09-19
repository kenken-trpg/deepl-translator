"""Streamlit Web GUI:  uv run --extra web streamlit run app.py"""
from __future__ import annotations

import io

import streamlit as st

from deepl_translator.chunker import build_batches, split_into_chunks
from deepl_translator.extract import extract_text
from deepl_translator.translator import SOURCE_LANGS, DeepLError, DeepLTranslator

st.set_page_config(page_title="DeepL 翻訳 (EN/DE → JA)", layout="wide")
st.title("DeepL 翻訳  EN / DE → 日本語")

with st.sidebar:
    source = st.selectbox("原文言語", list(SOURCE_LANGS), index=0)
    max_chars = st.slider("チャンク最大文字数", 500, 10000, 4000, step=500)
    formality = st.selectbox("文体", ["(指定なし)", "prefer_more", "prefer_less"])
    context = st.text_area("文脈ヒント（任意・課金対象外）", height=80)
    auto_context = st.checkbox("直前チャンクを context として自動付与", value=True)
    bilingual = st.checkbox("対訳形式で出力")

uploaded = st.file_uploader("ファイルを選択", type=["txt", "docx", "pdf"])
if not uploaded:
    st.stop()

try:
    text = extract_text(io.BytesIO(uploaded.getvalue()), filename=uploaded.name)
except ValueError as e:
    st.error(str(e))
    st.stop()

chunks = split_into_chunks(text, max_chars=max_chars)
n_requests = len(chunks) if auto_context else len(build_batches(chunks))
c1, c2, c3 = st.columns(3)
c1.metric("抽出文字数", f"{len(text):,}")
c2.metric("チャンク数", len(chunks))
c3.metric("API リクエスト数", n_requests)

with st.expander("分割プレビュー"):
    for i, c in enumerate(chunks):
        st.caption(f"chunk {i} — {len(c)} 文字")
        st.text(c)

if st.button("翻訳する", type="primary"):
    bar = st.progress(0.0, text="翻訳中…")
    try:
        result = DeepLTranslator().translate_document_text(
            text,
            source_lang=SOURCE_LANGS[source],
            max_chars=max_chars,
            formality=None if formality.startswith("(") else formality,
            context=context or None,
            auto_context=auto_context,
            progress=lambda n, t: bar.progress(n / t, text=f"翻訳中 {n}/{t}"),
        )
    except DeepLError as e:
        st.error(str(e))
        st.stop()
    bar.empty()
    st.session_state["result"] = result.bilingual() if bilingual else result.text
    st.success(f"完了（課金文字数 {result.billed_characters:,}）")

if "result" in st.session_state:
    out = st.session_state["result"]
    st.text_area("翻訳結果", out, height=500)
    st.download_button(
        "ダウンロード (.txt)",
        out.encode("utf-8"),
        file_name=uploaded.name.rsplit(".", 1)[0] + "_ja.txt",
        mime="text/plain",
    )
