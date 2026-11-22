import pytest

from app.rag.splitter import hash_content, split_text


def test_empty_text_produces_no_chunks():
    assert split_text("", 100, 10) == []
    assert split_text("   \n\n  ", 100, 10) == []


def test_short_document_produces_single_chunk():
    chunks = split_text("Python developer with FastAPI experience.", 200, 20)

    assert len(chunks) == 1
    assert chunks[0].index == 0
    assert chunks[0].content == "Python developer with FastAPI experience."


def test_chunks_never_exceed_chunk_size():
    text = " ".join(f"Sentence number {index} about recruitment." for index in range(120))
    chunks = split_text(text, 200, 40)

    assert len(chunks) > 1
    assert all(len(chunk.content) <= 200 for chunk in chunks)


def test_consecutive_chunks_overlap():
    text = " ".join(f"Requirement {index} for the role." for index in range(80))
    chunks = split_text(text, 200, 60)

    assert len(chunks) > 1
    assert chunks[1].char_start < chunks[0].char_end


def test_chunk_offsets_are_consistent():
    text = "\n\n".join(
        f"Paragraph {index} describing the hiring process in detail." for index in range(10)
    )
    chunks = split_text(text, 180, 30)

    for chunk in chunks:
        assert 0 <= chunk.char_start < chunk.char_end
        assert chunk.content_hash == hash_content(chunk.content)


def test_chunk_indexes_are_sequential():
    text = " ".join(f"Word {index}" for index in range(400))
    chunks = split_text(text, 150, 30)

    assert [chunk.index for chunk in chunks] == list(range(len(chunks)))


def test_identical_chunks_are_deduplicated():
    paragraph = "a" * 100
    text = "\n\n".join([paragraph] * 5)
    chunks = split_text(text, 100, 0)

    assert len(chunks) == 1


def test_hash_content_ignores_case_and_whitespace():
    assert hash_content("Python   Developer") == hash_content("python developer")


def test_invalid_chunk_settings_are_rejected():
    with pytest.raises(ValueError):
        split_text("text", 0, 0)
    with pytest.raises(ValueError):
        split_text("text", 100, -1)
    with pytest.raises(ValueError):
        split_text("text", 100, 100)
    with pytest.raises(ValueError):
        split_text("text", 100, 200)


def test_long_unbroken_text_is_split():
    text = " ".join(f"token{index}" for index in range(400))
    chunks = split_text(text, 200, 50)

    assert len(chunks) >= 5
    assert all(len(chunk.content) <= 200 for chunk in chunks)
