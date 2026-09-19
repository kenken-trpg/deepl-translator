"""Streamlit Web GUI:  uv run streamlit run app.py"""
from __future__ import annotations

import io

import streamlit as st

from deepl_translator.chunker import build_batches, split_into_chunks
from deepl_translator.extract import extract_text
from deepl_translator.shaper import deepl_web_url, shape_text
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


def translate_and_show(text: str, key: str, download_name: str) -> None:
    """分割プレビュー → 翻訳ボタン → 結果表示・ダウンロード。"""
    chunks = split_into_chunks(text, max_chars=max_chars)
    n_requests = len(chunks) if auto_context else len(build_batches(chunks))
    c1, c2, c3 = st.columns(3)
    c1.metric("文字数", f"{len(text):,}")
    c2.metric("チャンク数", len(chunks))
    c3.metric("API リクエスト数", n_requests)

    with st.expander("分割プレビュー"):
        for i, c in enumerate(chunks):
            st.caption(f"chunk {i} — {len(c)} 文字")
            st.text(c)

    if st.button("DeepL API で翻訳", type="primary", key=f"{key}_btn"):
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
            bar.empty()
            st.error(str(e))
            return
        bar.empty()
        st.session_state[key] = result.bilingual() if bilingual else result.text
        st.success(f"完了（課金文字数 {result.billed_characters:,}）")

    if key in st.session_state:
        out = st.session_state[key]
        st.text_area("翻訳結果", out, height=400, key=f"{key}_out")
        st.download_button("ダウンロード (.txt)", out.encode("utf-8"), file_name=download_name, mime="text/plain", key=f"{key}_dl")


tab_file, tab_shaper = st.tabs(["📄 ファイル翻訳", "✂️ 貼り付け整形（Shaper）"])

with tab_file:
    uploaded = st.file_uploader("ファイルを選択", type=["txt", "docx", "pdf"])
    if uploaded:
        try:
            text = extract_text(io.BytesIO(uploaded.getvalue()), filename=uploaded.name)
        except ValueError as e:
            st.error(str(e))
        else:
            translate_and_show(text, "file_result", uploaded.name.rsplit(".", 1)[0] + "_ja.txt")

with tab_shaper:
    st.caption("PDF からコピーした英文・独文の不要な改行と行末ハイフネーションを除去します。")
    raw = st.text_area("ここに原文を貼り付け", height=220, key="shaper_in")
    flat = st.checkbox("段落区切りも除去して 1 行にする", value=False)
    if raw.strip():
        shaped = shape_text(raw, keep_paragraphs=not flat)
        st.markdown("**整形後のテキスト**（右上のアイコンでクリップボードにコピー）")
        st.code(shaped, language=None, wrap_lines=True)
        url = deepl_web_url(shaped, SOURCE_LANGS[source])
        if len(url) > 8000:
            st.caption("テキストが長いため DeepL Web へのリンクは省略しました（API 翻訳を使ってください）")
        else:
            st.link_button("DeepL Web で開く", url)
        translate_and_show(shaped, "shaper_result", "pasted_ja.txt")
