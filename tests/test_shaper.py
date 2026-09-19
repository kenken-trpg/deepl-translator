from urllib.parse import unquote

from deepl_translator.shaper import deepl_web_url, shape_text


def test_removes_line_breaks_and_hyphenation():
    raw = "Machine trans-\nlation has im-\n proved\nrapidly.\n\nSecond para-\ngraph."
    assert shape_text(raw) == "Machine translation has improved rapidly.\n\nSecond paragraph."
    assert shape_text(raw, keep_paragraphs=False) == "Machine translation has improved rapidly. Second paragraph."


def test_keeps_hyphen_before_capital_and_inline_hyphens():
    raw = "Das Max-\nPlanck-Institut und state-of-the-art\nmodels."
    assert shape_text(raw) == "Das Max-Planck-Institut und state-of-the-art models."


def test_soft_hyphen_removed():
    assert shape_text("Über­setzung") == "Übersetzung"


def test_deepl_url_escapes_fragment_breakers():
    url = deepl_web_url("a/b #1 | 50%", "DE")
    assert url.startswith("https://www.deepl.com/translator#de/ja/")
    assert unquote(url.split("/ja/", 1)[1]) == "a／b ＃1 ｜ 50%"
