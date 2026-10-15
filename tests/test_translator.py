from deepl_translator.translator import DeepLTranslator, endpoint_for


def test_endpoint_selection(monkeypatch):
    monkeypatch.delenv("DEEPL_API_URL", raising=False)
    assert "api-free" in endpoint_for("abc:fx")
    assert "api-free" not in endpoint_for("abc")


def test_translate_document_preserves_order(monkeypatch):
    tr = DeepLTranslator(auth_key="dummy:fx")
    calls = []

    def fake(texts, source_lang, **opts):
        calls.append(texts)
        return [{"text": f"JA({t[:3]})", "detected_source_language": "EN", "billed_characters": len(t)} for t in texts]

    monkeypatch.setattr(tr, "translate_texts", fake)
    text = "\n\n".join(f"Paragraph {i}. " + "x" * 900 for i in range(120))
    res = tr.translate_document_text(text, source_lang="EN", max_chars=1200, auto_context=False)
    assert len(res.translations) == len(res.chunks) == 120
    assert len(calls) >= 3  # 50 件/リクエスト上限で分割される
    assert res.translations[0] == "JA(Par)"
    assert res.billed_characters == sum(len(c) for c in res.chunks)


def test_auto_context_uses_previous_chunk_tail(monkeypatch):
    tr = DeepLTranslator(auth_key="dummy:fx")
    calls = []

    def fake(texts, source_lang, **opts):
        calls.append((texts, opts.get("context")))
        return [{"text": "JA", "billed_characters": len(t)} for t in texts]

    monkeypatch.setattr(tr, "translate_texts", fake)
    paras = [f"Para {i} first. Para {i} last sentence." + " filler." * 10 for i in range(3)]
    tr.translate_document_text("\n\n".join(paras), max_chars=200, context="Fantasy novel.", context_chars=40)
    assert len(calls) == 3 and all(len(t) == 1 for t, _ in calls)
    assert calls[0][1] == "Fantasy novel."
    assert calls[1][1].startswith("Fantasy novel.\n\n")
    assert calls[1][1].endswith("filler.") and len(calls[1][1]) <= len("Fantasy novel.\n\n") + 40


def test_build_context_starts_at_sentence_boundary():
    from deepl_translator.translator import build_context

    ctx = build_context(None, "One here. Two here. Three here.", 22)
    assert ctx == "Two here. Three here."


def test_retry_honors_retry_after(monkeypatch):
    import requests

    from deepl_translator import translator as mod

    tr = DeepLTranslator(auth_key="dummy:fx")
    sleeps = []
    monkeypatch.setattr(mod.time, "sleep", sleeps.append)

    def response(status, headers=None, body=b'{"translations": [{"text": "JA"}]}'):
        r = requests.Response()
        r.status_code = status
        r.headers.update(headers or {})
        r._content = body
        return r

    responses = [response(429, {"Retry-After": "7"}), response(503), response(200)]
    monkeypatch.setattr(tr.session, "post", lambda *a, **k: responses.pop(0))
    assert tr.translate_texts(["Hi"], None) == [{"text": "JA"}]
    assert sleeps == [7.0, 2.0]  # 1 回目は Retry-After、2 回目は指数バックオフ（1→2 秒）


def test_user_agent_uses_package_version():
    import tomllib
    from pathlib import Path

    expected = tomllib.loads((Path(__file__).parents[1] / "pyproject.toml").read_text())["project"]["version"]
    tr = DeepLTranslator(auth_key="dummy:fx")
    assert tr.session.headers["User-Agent"] == f"deepl-translator/{expected}"
