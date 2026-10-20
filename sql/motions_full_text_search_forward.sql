-- Guarded by research/data-integrity/2026-10-19/motion_search_migration.py.
-- PostgreSQL 17; changes generated values only. Run with bounded transaction timeouts.
ALTER TABLE public.motions ALTER COLUMN text_search SET EXPRESSION AS (
  to_tsvector('english'::regconfig,
    COALESCE(text_content, ''::text) || ' '::text || COALESCE(plain_english_summary, ''::text))
);
