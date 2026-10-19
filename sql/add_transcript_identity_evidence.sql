-- Version: 2026-10-19.3. Additive PRIVATE machine-identity ledger.
-- Proposal only until reviewed/applied. Does not rewrite existing transcript rows.
BEGIN;

CREATE TABLE public.transcript_identity_evidence (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    segment_id bigint NOT NULL REFERENCES public.transcript_segments(id) ON DELETE RESTRICT,
    meeting_id bigint NOT NULL REFERENCES public.meetings(id) ON DELETE RESTRICT,
    person_id bigint NOT NULL REFERENCES public.people(id) ON DELETE RESTRICT,
    validator_version text NOT NULL CHECK (length(validator_version) > 0),
    validator_sha256 text NOT NULL CHECK (validator_sha256 ~ '^[0-9a-f]{64}$'),
    identity_evidence_sha256 text NOT NULL CHECK (identity_evidence_sha256 ~ '^[0-9a-f]{64}$'),
    input_sha256 text NOT NULL CHECK (input_sha256 ~ '^[0-9a-f]{64}$'),
    source_run jsonb NOT NULL CHECK (
        jsonb_typeof(source_run) = 'object'
        AND coalesce(trim(source_run->>'recording_id') <> '', false)
        AND coalesce(source_run->>'meeting_id' ~ '^[0-9]+$', false)
        AND coalesce(source_run->>'recording_sha256' ~ '^[0-9a-f]{64}$', false)
        AND coalesce(source_run->>'transcript_sha256' ~ '^[0-9a-f]{64}$', false)
        AND coalesce(source_run->>'diarization_run_sha256' ~ '^[0-9a-f]{64}$', false)
    ),
    evidence jsonb NOT NULL CHECK (jsonb_typeof(evidence) = 'object'),
    before_row jsonb NOT NULL CHECK (jsonb_typeof(before_row) = 'object'),
    after_row jsonb NOT NULL CHECK (jsonb_typeof(after_row) = 'object'),
    status text NOT NULL DEFAULT 'applied' CHECK (status IN ('applied', 'reverted')),
    created_at timestamptz NOT NULL DEFAULT now(),
    reverted_at timestamptz,
    reverted_row jsonb,
    UNIQUE (segment_id, input_sha256),
    UNIQUE (segment_id, validator_sha256, identity_evidence_sha256, source_run),
    CHECK ((status = 'applied' AND reverted_at IS NULL AND reverted_row IS NULL)
        OR (status = 'reverted' AND reverted_at IS NOT NULL AND reverted_row IS NOT NULL AND jsonb_typeof(reverted_row) = 'object'))
);
CREATE INDEX transcript_identity_evidence_meeting_idx ON public.transcript_identity_evidence(meeting_id, created_at);
ALTER TABLE public.transcript_identity_evidence ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.transcript_identity_evidence FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE ON public.transcript_identity_evidence TO service_role;
COMMENT ON TABLE public.transcript_identity_evidence IS 'Private source/run-bound machine identity proofs and full before/after rollback. No public read policy.';

-- SECURITY INVOKER and no public execution: only the service-role pipeline may
-- submit a fully recomputed admission; SQL enforces atomicity and immutable rows.
CREATE FUNCTION public.apply_transcript_identity_evidence(
    p_segment_id bigint,
    p_expected jsonb,
    p_person_id bigint,
    p_speaker_name text,
    p_validator_version text,
    p_validator_sha256 text,
    p_input_sha256 text,
    p_source_run jsonb,
    p_evidence jsonb,
    p_input_canonical_json text
) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path = pg_catalog, public AS $$
DECLARE
    v_before public.transcript_segments%ROWTYPE;
    v_expected public.transcript_segments%ROWTYPE;
    v_after public.transcript_segments%ROWTYPE;
    v_existing public.transcript_identity_evidence%ROWTYPE;
    v_canonical_name text;
    v_input jsonb;
    v_envelope jsonb := '{}'::jsonb;
    v_key text;
    v_identity_sha text;
    v_id uuid;
BEGIN
    SELECT * INTO v_before FROM public.transcript_segments WHERE id=p_segment_id FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'transcript segment unavailable'; END IF;
    IF jsonb_typeof(p_expected) IS DISTINCT FROM 'object'
        OR EXISTS(SELECT 1 FROM jsonb_object_keys(to_jsonb(v_before)) AS k(name) WHERE NOT (p_expected ? k.name))
        OR EXISTS(SELECT 1 FROM jsonb_object_keys(p_expected) AS k(name) WHERE NOT (to_jsonb(v_before) ? k.name)) THEN
        RAISE EXCEPTION 'complete before-row required';
    END IF;
    SELECT * INTO v_expected FROM jsonb_populate_record(NULL::public.transcript_segments,p_expected);
    SELECT name INTO v_canonical_name FROM public.people WHERE id=p_person_id FOR SHARE;
    IF NOT FOUND OR p_speaker_name IS DISTINCT FROM v_canonical_name THEN
        RAISE EXCEPTION 'canonical person and exact canonical name required';
    END IF;
    IF p_evidence #>> '{link,status}' IS DISTINCT FROM 'link_candidate'
        OR (p_evidence #>> '{link,person_id}')::bigint IS DISTINCT FROM p_person_id
        OR (p_evidence #>> '{link,segment_id}')::bigint IS DISTINCT FROM p_segment_id
        OR p_evidence #>> '{admission,status}' IS DISTINCT FROM 'identity_admitted'
        OR (p_evidence #>> '{admission,person_id}')::bigint IS DISTINCT FROM p_person_id
        OR p_evidence #>> '{link,speaker_name}' IS DISTINCT FROM p_speaker_name THEN
        RAISE EXCEPTION 'machine admission and exact link candidate required';
    END IF;
    FOREACH v_key IN ARRAY ARRAY['meeting_id','recording_id','recording_sha256','transcript_sha256','diarization_run_sha256','validator_version','validator_sha256','identity_evidence_sha256'] LOOP
        IF coalesce(p_evidence->'link'->>v_key,'')=''
            OR p_evidence->'link'->v_key IS DISTINCT FROM p_evidence->'admission'->v_key THEN
            RAISE EXCEPTION 'identity/link envelope mismatch: %',v_key;
        END IF;
        v_envelope := v_envelope || jsonb_build_object(v_key,p_evidence->'link'->v_key);
    END LOOP;
    FOREACH v_key IN ARRAY ARRAY['meeting_id','recording_id','recording_sha256','transcript_sha256','diarization_run_sha256'] LOOP
        IF p_evidence->'link'->v_key IS DISTINCT FROM p_source_run->v_key THEN
            RAISE EXCEPTION 'source run mismatch: %',v_key;
        END IF;
    END LOOP;
    IF (p_source_run->>'meeting_id')::bigint IS DISTINCT FROM v_before.meeting_id
        OR p_evidence #>> '{link,validator_version}' IS DISTINCT FROM p_validator_version
        OR p_evidence #>> '{link,validator_sha256}' IS DISTINCT FROM p_validator_sha256 THEN
        RAISE EXCEPTION 'meeting or validator version mismatch';
    END IF;
    v_identity_sha := p_evidence #>> '{link,identity_evidence_sha256}';
    v_input := p_input_canonical_json::jsonb;
    IF p_input_sha256 IS DISTINCT FROM encode(sha256(convert_to(p_input_canonical_json,'UTF8')),'hex')
        OR p_evidence #>> '{link,input_sha256}' IS DISTINCT FROM p_input_sha256
        OR p_evidence #>> '{link,input_canonical_json}' IS DISTINCT FROM p_input_canonical_json
        OR p_evidence->'link'->'expected_row' IS DISTINCT FROM p_expected
        OR v_input IS DISTINCT FROM jsonb_build_object(
            'source_run',p_source_run,'envelope',v_envelope,'expected_row',p_expected,
            'person_id',p_person_id,'speaker_name',p_speaker_name,
            'operation',p_evidence->'link'->'operation','evidence',p_evidence->'link'->'evidence') THEN
        RAISE EXCEPTION 'candidate whole-input fingerprint mismatch';
    END IF;
    SELECT * INTO v_existing FROM public.transcript_identity_evidence
        WHERE segment_id=p_segment_id AND input_sha256=p_input_sha256;
    IF FOUND THEN
        IF v_existing.status='applied' AND to_jsonb(v_before)=v_existing.after_row
            AND v_existing.before_row=to_jsonb(v_expected) AND v_existing.person_id=p_person_id
            AND v_existing.validator_version=p_validator_version AND v_existing.validator_sha256=p_validator_sha256
            AND v_existing.source_run=p_source_run AND v_existing.evidence=p_evidence
            AND v_existing.after_row->>'speaker_name'=p_speaker_name THEN
            RETURN jsonb_build_object('status','already_applied','evidence_id',v_existing.id,'segment_id',p_segment_id);
        END IF;
        RAISE EXCEPTION 'identity receipt exists but current row or request differs';
    END IF;
    IF to_jsonb(v_before) IS DISTINCT FROM to_jsonb(v_expected) THEN
        RAISE EXCEPTION USING ERRCODE='40001', MESSAGE='transcript identity compare-and-swap failed';
    END IF;
    IF v_before.is_verified IS TRUE THEN RAISE EXCEPTION 'protected verified transcript row'; END IF;
    IF v_before.person_id IS NOT NULL AND v_before.person_id IS DISTINCT FROM p_person_id THEN
        RAISE EXCEPTION 'existing different identity requires separate source-reviewed correction';
    END IF;
    IF (v_before.person_id IS NULL AND p_evidence #>> '{link,operation}' IS DISTINCT FROM 'fill_null')
        OR (v_before.person_id IS NOT NULL AND p_evidence #>> '{link,operation}' IS DISTINCT FROM 'retain_supported') THEN
        RAISE EXCEPTION 'identity operation does not match current row';
    END IF;
    -- Re-preparing the same source proof against its already-applied after-row
    -- is a no-op, not an unbounded new receipt/timestamp on every worker run.
    SELECT * INTO v_existing FROM public.transcript_identity_evidence
        WHERE segment_id=p_segment_id AND validator_sha256=p_validator_sha256
        AND identity_evidence_sha256=v_identity_sha AND source_run=p_source_run;
    IF FOUND THEN
        IF v_existing.status='applied' AND to_jsonb(v_before)=v_existing.after_row
            AND v_existing.person_id=p_person_id AND v_existing.after_row->>'speaker_name'=p_speaker_name THEN
            RETURN jsonb_build_object('status','already_applied','evidence_id',v_existing.id,'segment_id',p_segment_id);
        END IF;
        RAISE EXCEPTION 'source identity scope already has a different or reverted receipt';
    END IF;
    UPDATE public.transcript_segments SET person_id=p_person_id,speaker_name=p_speaker_name,
        attribution_source='SOURCE_VALIDATED_DIARIZATION'
        WHERE id=p_segment_id RETURNING * INTO v_after;
    INSERT INTO public.transcript_identity_evidence (
        segment_id,meeting_id,person_id,validator_version,validator_sha256,identity_evidence_sha256,input_sha256,
        source_run,evidence,before_row,after_row
    ) VALUES (
        p_segment_id,v_before.meeting_id,p_person_id,p_validator_version,p_validator_sha256,v_identity_sha,p_input_sha256,
        p_source_run,p_evidence,to_jsonb(v_before),to_jsonb(v_after)
    ) RETURNING id INTO v_id;
    RETURN jsonb_build_object('status','applied','evidence_id',v_id,'segment_id',p_segment_id);
END;
$$;
REVOKE ALL ON FUNCTION public.apply_transcript_identity_evidence(bigint,jsonb,bigint,text,text,text,text,jsonb,jsonb,text) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.apply_transcript_identity_evidence(bigint,jsonb,bigint,text,text,text,text,jsonb,jsonb,text) TO service_role;

CREATE FUNCTION public.rollback_transcript_identity_evidence(p_evidence_id uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path = pg_catalog, public AS $$
DECLARE
    v_receipt public.transcript_identity_evidence%ROWTYPE;
    v_current public.transcript_segments%ROWTYPE;
    v_after public.transcript_segments%ROWTYPE;
BEGIN
    -- Same lock order as apply (segment first) avoids cross-operation deadlocks.
    SELECT * INTO v_receipt FROM public.transcript_identity_evidence WHERE id=p_evidence_id;
    IF NOT FOUND THEN RAISE EXCEPTION 'identity evidence unavailable'; END IF;
    SELECT * INTO v_current FROM public.transcript_segments WHERE id=v_receipt.segment_id FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'transcript segment unavailable'; END IF;
    SELECT * INTO v_receipt FROM public.transcript_identity_evidence WHERE id=p_evidence_id FOR UPDATE;
    IF v_receipt.status='reverted' AND to_jsonb(v_current)=v_receipt.reverted_row THEN
        RETURN jsonb_build_object('status','already_reverted','evidence_id',p_evidence_id);
    END IF;
    IF v_receipt.status IS DISTINCT FROM 'applied' OR to_jsonb(v_current) IS DISTINCT FROM v_receipt.after_row THEN
        RAISE EXCEPTION USING ERRCODE='40001', MESSAGE='transcript rollback compare-and-swap failed';
    END IF;
    UPDATE public.transcript_segments SET
        person_id=(v_receipt.before_row->>'person_id')::bigint,
        speaker_name=v_receipt.before_row->>'speaker_name',
        attribution_source=v_receipt.before_row->>'attribution_source'
        WHERE id=v_receipt.segment_id RETURNING * INTO v_after;
    UPDATE public.transcript_identity_evidence SET status='reverted',reverted_at=now(),reverted_row=to_jsonb(v_after)
        WHERE id=p_evidence_id;
    RETURN jsonb_build_object('status','reverted','evidence_id',p_evidence_id,'segment_id',v_receipt.segment_id);
END;
$$;
REVOKE ALL ON FUNCTION public.rollback_transcript_identity_evidence(uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.rollback_transcript_identity_evidence(uuid) TO service_role;

COMMIT;
