from deepl_translator.chunker import (
    _split_sentences,
    build_batches,
    request_body_size,
    split_into_chunks,
)


def test_short_paragraphs_are_merged_without_splitting():
    text = "Para one.\n\nPara two.\n\nPara three."
    assert split_into_chunks(text, 1200) == ["Para one.\n\nPara two.\n\nPara three."]


def test_paragraph_not_cut_when_next_does_not_fit():
    a, b = "A" * 700 + ".", "B" * 700 + "."
    chunks = split_into_chunks(f"{a}\n\n{b}", 1200)
    assert chunks == [a, b]  # 1200 未満でも段落境界で閉じる


def test_long_paragraph_split_at_sentences():
    sent = "This is a sentence with some words in it. "
    para = (sent * 60).strip()
    chunks = split_into_chunks(para, 1200)
    assert all(len(c) <= 1200 for c in chunks)
    assert all(c.endswith(".") for c in chunks)
    assert " ".join(chunks) == para


def test_abbreviations_do_not_split():
    en = "Dr. Smith met Mr. Jones, e.g. at 5 p.m. yesterday. Then he left."
    assert _split_sentences(en) == ["Dr. Smith met Mr. Jones, e.g. at 5 p.m. yesterday.", "Then he left."]
    de = "Am 3. Mai kam z.B. Herr Müller usw. Danach ging er. Das war's."
    assert _split_sentences(de) == ["Am 3. Mai kam z.B. Herr Müller usw. Danach ging er.", "Das war's."]


def test_oversized_sentence_falls_back_to_clauses_and_words():
    s = ", ".join(["word " * 20] * 20)
    chunks = split_into_chunks(s, 300)
    assert all(len(c) <= 300 for c in chunks)
    assert "".join(chunks).replace(" ", "") == s.replace(" ", "")


def test_batches_respect_byte_limit_and_count():
    chunks = ["ä" * 1000] * 200  # 2 bytes/char in UTF-8
    batches = build_batches(chunks, max_request_bytes=20_000)
    assert sum(len(b.texts) for b in batches) == 200
    for b in batches:
        assert request_body_size(b.texts) <= 20_000
        assert len(b.texts) <= 50
    assert [b.start_index for b in batches] == [sum(len(x.texts) for x in batches[:i]) for i in range(len(batches))]
