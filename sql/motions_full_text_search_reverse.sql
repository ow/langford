-- Restore this expression before using historical whole-row content/ballot rollback receipts.
ALTER TABLE public.motions ALTER COLUMN text_search SET EXPRESSION AS (
  to_tsvector('english'::regconfig, COALESCE(plain_english_summary, text_content, ''::text))
);
