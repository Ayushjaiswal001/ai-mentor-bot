from app.bot.formatting import chunk, md_to_html


def test_bold_and_inline_code():
    assert md_to_html("a **bold** and `code` here") == "a <b>bold</b> and <code>code</code> here"


def test_code_fence_becomes_pre_and_is_escaped():
    out = md_to_html("```python\nprint('<hi>')\n```")
    assert out == "<pre>print('&lt;hi&gt;')</pre>"


def test_html_outside_fences_is_escaped():
    out = md_to_html("evil <script> tag")
    assert "<script>" not in out
    assert "&lt;script&gt;" in out


def test_chunk_short_text_is_single():
    assert chunk("hello", limit=100) == ["hello"]


def test_chunk_splits_on_paragraphs_within_limit():
    text = "\n\n".join(f"para {i} " + "x" * 50 for i in range(10))
    parts = chunk(text, limit=120)
    assert all(len(p) <= 120 for p in parts)
    assert "".join(parts).replace("\n\n", "") == text.replace("\n\n", "")


def test_chunk_hard_splits_oversized_paragraph():
    text = "y" * 500
    parts = chunk(text, limit=120)
    assert all(len(p) <= 120 for p in parts)
    assert "".join(parts) == text
