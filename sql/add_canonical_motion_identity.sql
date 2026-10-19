-- Guard source-backed ordinary ingestion against concurrent duplicate inserts.
-- Existing unbound legacy records stay untouched; preflight rejects duplicate
-- nonempty keys instead of choosing or deleting a record automatically.
BEGIN;
LOCK TABLE public.motions IN SHARE ROW EXCLUSIVE MODE;
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM public.motions
    WHERE nullif(meta->'canonical_source_motion'->>'key', '') IS NOT NULL
    GROUP BY meeting_id, (meta->'canonical_source_motion'->>'key')
    HAVING count(*) > 1
  ) THEN
    RAISE EXCEPTION 'Duplicate canonical source keys: review motion identities before applying index';
  END IF;
END $$;
CREATE UNIQUE INDEX IF NOT EXISTS motions_canonical_source_identity
ON public.motions (meeting_id, (meta->'canonical_source_motion'->>'key'))
WHERE nullif(meta->'canonical_source_motion'->>'key', '') IS NOT NULL;
COMMIT;
