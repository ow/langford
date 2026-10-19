"""Tests for pipeline.ingestion.embed module.

Covers: MAX_EMBED_CHARS, TABLE_CONFIG. Embedding calls themselves go through
pipeline.ai (see tests/ai/test_client.py).
"""

import pytest
from unittest.mock import patch, MagicMock

from pipeline.ingestion.embed import (
    TABLE_CONFIG,
    MAX_EMBED_CHARS,
    API_BATCH_SIZE,
    DEFAULT_MIN_WORDS,
)


# --- Constants ---


class TestEmbedConstants:
    def test_max_embed_chars(self):
        assert MAX_EMBED_CHARS == 8000

    def test_api_batch_size(self):
        assert API_BATCH_SIZE == 128

    def test_table_config_has_expected_tables(self):
        expected_tables = {
            "agenda_items", "motions", "matters", "meetings",
            "bylaws", "bylaw_chunks", "documents", "key_statements",
            "document_sections",
        }
        assert set(TABLE_CONFIG.keys()) == expected_tables

    def test_each_table_has_select_and_text_fn(self):
        for table, config in TABLE_CONFIG.items():
            assert "select" in config, f"{table} missing 'select'"
            assert "text_fn" in config, f"{table} missing 'text_fn'"

    def test_default_min_words_covers_all_tables(self):
        for table in TABLE_CONFIG:
            assert table in DEFAULT_MIN_WORDS, f"{table} missing from DEFAULT_MIN_WORDS"


# --- TABLE_CONFIG text functions ---


class TestTableConfigTextFns:
    def test_motions_text_fn(self):
        fn = TABLE_CONFIG["motions"]["text_fn"]
        row = (1, "THAT Council approve the application")
        assert fn(row) == "THAT Council approve the application"

    def test_motions_text_fn_none(self):
        fn = TABLE_CONFIG["motions"]["text_fn"]
        row = (1, None)
        assert fn(row) == ""

    def test_matters_text_fn_prefers_summary(self):
        fn = TABLE_CONFIG["matters"]["text_fn"]
        row = (1, "Summary text", "Title text")
        assert fn(row) == "Summary text"

    def test_matters_text_fn_falls_back_to_title(self):
        fn = TABLE_CONFIG["matters"]["text_fn"]
        row = (1, None, "Title text")
        assert fn(row) == "Title text"

    def test_meetings_text_fn(self):
        fn = TABLE_CONFIG["meetings"]["text_fn"]
        row = (1, "Council discussed zoning changes")
        assert fn(row) == "Council discussed zoning changes"

    def test_documents_text_fn(self):
        fn = TABLE_CONFIG["documents"]["text_fn"]
        row = (1, "Staff Report", "Full text of the report")
        result = fn(row)
        assert "Staff Report" in result
        assert "Full text of the report" in result

    def test_key_statements_text_fn(self):
        fn = TABLE_CONFIG["key_statements"]["text_fn"]
        row = (1, "Traffic increased 40%", "During rezoning debate")
        result = fn(row)
        assert "Traffic increased" in result
        assert "rezoning debate" in result

    def test_document_sections_text_fn(self):
        fn = TABLE_CONFIG["document_sections"]["text_fn"]
        row = (1, "Background", "This section provides background information.")
        result = fn(row)
        assert "Background" in result
        assert "background information" in result

    def test_bylaws_text_fn(self):
        fn = TABLE_CONFIG["bylaws"]["text_fn"]
        row = (1, "Noise Control Bylaw", "Controls noise levels in View Royal")
        result = fn(row)
        assert "Noise Control Bylaw" in result

    def test_bylaw_chunks_text_fn(self):
        fn = TABLE_CONFIG["bylaw_chunks"]["text_fn"]
        row = (1, "Section 3.1 noise levels shall not exceed...")
        assert fn(row) == "Section 3.1 noise levels shall not exceed..."
