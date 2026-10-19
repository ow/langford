-- Proposal: atomic service-only, source-bound spoken statements. No legacy rewrite.
BEGIN;
CREATE FUNCTION public.publish_source_bound_key_statement(
    p_input_canonical_json text, p_input_sha256 text
) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER
SET search_path = pg_catalog, public SET timezone = 'UTC' AS $$
DECLARE
    v jsonb;
    s jsonb;
    raw jsonb;
    expected jsonb;
    projected jsonb;
    proof jsonb;
    prior jsonb;
    allproofs jsonb;
    v_meta jsonb;
    source_ids jsonb := '[]'::jsonb;
    receipt_ids jsonb;
    receipt_hashes jsonb := '[]'::jsonb;
    item public.transcript_segments%ROWTYPE;
    receipt public.transcript_identity_evidence%ROWTYPE;
    v_statement public.key_statements%ROWTYPE;
    v_meeting public.meetings%ROWTYPE;
    v_agenda public.agenda_items%ROWTYPE;
    v_meeting_id bigint;
    v_agenda_id bigint;
    v_person_id bigint;
    v_name text;
    raw_label text;
    source_sha text;
    quote_sha text;
    identity_key text;
    joined text := '';
    normalized_source text;
    normalized_quote text;
    first_start double precision;
    last_index bigint;
    idx bigint;
    starts double precision;
    ends double precision;
    sid bigint;
    rid uuid;
    canonical_count integer;
    matched boolean;
    ids bigint[] := '{}';
BEGIN
    IF p_input_sha256 IS DISTINCT FROM encode(sha256(convert_to(p_input_canonical_json,'UTF8')),'hex') THEN
        RAISE EXCEPTION 'statement canonical input hash mismatch';
    END IF;
    v := p_input_canonical_json::jsonb;
    IF jsonb_typeof(v) IS DISTINCT FROM 'object'
        OR v->>'validator_version' IS DISTINCT FROM 'source-bound-key-statements-v2'
        OR NOT coalesce(v->>'validator_sha256' ~ '^[0-9a-f]{64}$',false) THEN
        RAISE EXCEPTION 'versioned machine validator input required';
    END IF;
    v_meeting_id := (v->>'meeting_id')::bigint;
    v_agenda_id := (v->>'agenda_item_id')::bigint;
    SELECT * INTO v_meeting FROM public.meetings WHERE id=v_meeting_id FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'statement meeting unavailable'; END IF;
    SELECT * INTO v_agenda FROM public.agenda_items WHERE id=v_agenda_id FOR SHARE;
    IF NOT FOUND OR v_agenda.meeting_id IS DISTINCT FROM v_meeting_id THEN
        RAISE EXCEPTION 'statement agenda/meeting mismatch';
    END IF;
    s := v->'statement';
    source_sha := v->>'transcript_source_sha256';
    v_person_id := (s->>'person_id')::bigint;
    IF jsonb_typeof(s) IS DISTINCT FROM 'object'
        OR NOT coalesce(source_sha ~ '^[0-9a-f]{64}$',false)
        OR jsonb_typeof(s->'statement_text')IS DISTINCT FROM'string'
        OR coalesce(trim(s->>'statement_text'),'')=''
        OR coalesce(s->>'statement_type','') NOT IN ('claim','proposal','objection','recommendation','financial','public_input')
        OR NOT coalesce((v->>'source_segment_count')::bigint>0,false)
        OR jsonb_typeof(v->'raw_segments') IS DISTINCT FROM 'array'
        OR jsonb_array_length(v->'raw_segments')=0
        OR jsonb_typeof(v->'expected_segments') IS DISTINCT FROM 'array'
        OR jsonb_array_length(v->'expected_segments')=0 THEN
        RAISE EXCEPTION 'bounded original speech and expected row tuples required';
    END IF;
    -- Bound source-array indexes explicitly; DB row IDs are never array indexes.
    FOR raw IN SELECT value FROM jsonb_array_elements(v->'raw_segments') LOOP
        idx := (raw->>'source_index')::bigint;
        starts := (raw->>'start')::double precision;
        ends := (raw->>'end')::double precision;
        sid := (raw->>'segment_id')::bigint;
        IF idx IS NULL OR starts IS NULL OR ends IS NULL OR sid IS NULL OR idx<0 OR idx>=(v->>'source_segment_count')::bigint OR (last_index IS NOT NULL AND idx<>last_index+1)
            OR starts<0 OR NOT starts<ends OR starts IN ('Infinity'::float8,'-Infinity'::float8,'NaN'::float8)
            OR ends IN ('Infinity'::float8,'-Infinity'::float8,'NaN'::float8)
            OR coalesce(trim(raw->>'text'),'')=''
            OR jsonb_typeof(raw->'speaker') IS DISTINCT FROM 'string' THEN
            RAISE EXCEPTION 'invalid/noncontiguous original speech tuple';
        END IF;
        IF last_index IS NULL THEN raw_label:=raw->>'speaker'; first_start:=starts; END IF;
        IF raw->>'speaker' IS DISTINCT FROM raw_label THEN RAISE EXCEPTION 'quote crosses raw speakers'; END IF;
        SELECT * INTO item FROM public.transcript_segments WHERE id=sid FOR SHARE;
        IF NOT FOUND OR item.meeting_id IS DISTINCT FROM v_meeting_id
            OR NOT(item.start_time<=starts AND starts<ends AND ends<=item.end_time)
            OR strpos(regexp_replace(item.text_content,'\s+',' ','g'),regexp_replace(raw->>'text','\s+',' ','g'))=0 THEN
            RAISE EXCEPTION USING ERRCODE='40001',MESSAGE='statement current source tuple changed';
        END IF;
        SELECT value INTO expected FROM jsonb_array_elements(v->'expected_segments') WHERE (value->>'id')::bigint=sid;
        IF NOT FOUND OR (SELECT count(*)FROM jsonb_array_elements(v->'expected_segments')WHERE(value->>'id')::bigint=sid)<>1 THEN
            RAISE EXCEPTION 'unique complete expected source tuple required';
        END IF;
        projected := jsonb_build_object('id',item.id,'meeting_id',item.meeting_id,'person_id',item.person_id,
            'speaker_name',item.speaker_name,'start_time',item.start_time,'end_time',item.end_time,'text_content',item.text_content);
        IF projected IS DISTINCT FROM expected THEN
            RAISE EXCEPTION USING ERRCODE='40001',MESSAGE='statement source row compare-and-swap failed';
        END IF;
        -- A caller cannot choose the first of several matching persisted tuples.
        IF (SELECT count(*)FROM public.transcript_segments t WHERE t.meeting_id=v_meeting_id
            AND t.start_time<=starts AND ends<=t.end_time
            AND strpos(regexp_replace(t.text_content,'\s+',' ','g'),regexp_replace(raw->>'text','\s+',' ','g'))>0)<>1 THEN
            RAISE EXCEPTION 'ambiguous persisted source tuple';
        END IF;
        IF NOT sid=ANY(ids) THEN ids:=array_append(ids,sid);source_ids:=source_ids||jsonb_build_array(sid); END IF;
        joined:=joined||' '||(raw->>'text');last_index:=idx;
    END LOOP;
    normalized_source:=trim(regexp_replace(joined,'\s+',' ','g'));
    normalized_quote:=trim(regexp_replace(s->>'statement_text','\s+',' ','g'));
    IF (SELECT count(*)FROM jsonb_array_elements(v->'expected_segments'))<>cardinality(ids)
        OR s->'source_segment_ids' IS DISTINCT FROM source_ids
        OR (s->>'start_time')::double precision IS DISTINCT FROM first_start
        OR s->>'statement_text'IS DISTINCT FROM normalized_quote
        OR NOT EXISTS(SELECT 1 FROM generate_series(1,length(normalized_source)-length(normalized_quote)+1)AS g(pos)
            WHERE substring(normalized_source FROM g.pos FOR length(normalized_quote))=normalized_quote
            AND(left(normalized_quote,1)!~'[[:alnum:]_]'OR g.pos=1 OR substring(normalized_source FROM g.pos-1 FOR 1)!~'[[:alnum:]_]')
            AND(right(normalized_quote,1)!~'[[:alnum:]_]'OR substring(normalized_source FROM g.pos+length(normalized_quote)FOR 1)!~'[[:alnum:]_]')) THEN
        RAISE EXCEPTION 'exact whole-word quote, measured start and bound source IDs required';
    END IF;
    receipt_ids:=coalesce(v->'identity_receipt_ids','[]'::jsonb);
    IF v_person_id IS NULL THEN
        IF s->>'speaker_name' IS DISTINCT FROM (CASE WHEN raw_label ~* '^speaker_[0-9]+$' THEN raw_label ELSE 'Unidentified speaker' END) OR jsonb_array_length(receipt_ids)<>0 THEN
            RAISE EXCEPTION 'unadmitted identity must remain generically labelled and NULL';
        END IF;
    ELSE
        SELECT p.name INTO v_name FROM public.people p WHERE p.id=v_person_id FOR SHARE;
        SELECT count(*)INTO canonical_count FROM public.people p WHERE lower(trim(regexp_replace(p.name,'\s+',' ','g')))=lower(trim(regexp_replace(v_name,'\s+',' ','g')));
        IF v_name IS NULL OR v_name IS DISTINCT FROM s->>'speaker_name'OR canonical_count<>1 THEN
            RAISE EXCEPTION 'unique exact canonical speaker required';
        END IF;
        FOREACH sid IN ARRAY ids LOOP
            SELECT * INTO item FROM public.transcript_segments WHERE id=sid FOR SHARE;
            matched:=false;
            FOR rid IN SELECT value::text::uuid FROM jsonb_array_elements_text(receipt_ids) LOOP
                SELECT * INTO receipt FROM public.transcript_identity_evidence WHERE id=rid FOR SHARE;
                IF FOUND AND receipt.segment_id=sid AND receipt.meeting_id=v_meeting_id
                    AND receipt.person_id=v_person_id AND item.person_id=v_person_id
                    AND receipt.status='applied'AND receipt.reverted_at IS NULL
                    AND receipt.source_run->>'transcript_sha256'=source_sha
                    AND (receipt.source_run->>'meeting_id')::bigint=v_meeting_id
                    AND receipt.after_row @> jsonb_build_object('id',item.id,'meeting_id',item.meeting_id,
                        'person_id',item.person_id,'speaker_name',item.speaker_name,'start_time',item.start_time,
                        'end_time',item.end_time,'text_content',item.text_content) THEN
                    matched:=true;
                    receipt_hashes:=receipt_hashes||jsonb_build_array(encode(sha256(convert_to(to_jsonb(receipt)::text,'UTF8')),'hex'));
                END IF;
            END LOOP;
            IF NOT matched THEN RAISE EXCEPTION 'active exact source/row identity admission required'; END IF;
        END LOOP;
    END IF;
    quote_sha:=encode(sha256(convert_to(s->>'statement_text','UTF8')),'hex');
    identity_key:=encode(sha256(convert_to(jsonb_build_object('meeting_id',v_meeting_id,'agenda_item_id',v_agenda_id,
        'source_segment_ids',source_ids,'quote_sha256',quote_sha)::text,'UTF8')),'hex');
    v_meta:=coalesce(v_meeting.meta,'{}'::jsonb);allproofs:=coalesce(v_meta->'key_statement_evidence','{}'::jsonb);
    IF jsonb_typeof(v_meta)IS DISTINCT FROM'object'OR jsonb_typeof(allproofs)IS DISTINCT FROM'object'THEN RAISE EXCEPTION 'statement proof metadata format held'; END IF;
    prior:=allproofs->identity_key;
    IF prior IS NOT NULL THEN
        SELECT * INTO v_statement FROM public.key_statements WHERE id=(prior->>'statement_id')::bigint FOR SHARE;
        IF NOT FOUND OR v_statement.meeting_id IS DISTINCT FROM v_meeting_id OR v_statement.agenda_item_id IS DISTINCT FROM v_agenda_id
            OR to_jsonb(v_statement.source_segment_ids)IS DISTINCT FROM source_ids
            OR v_statement.statement_text IS DISTINCT FROM s->>'statement_text'
            OR v_statement.person_id IS DISTINCT FROM v_person_id OR v_statement.speaker_name IS DISTINCT FROM s->>'speaker_name'
            OR prior->>'transcript_source_sha256'IS DISTINCT FROM source_sha THEN
            RAISE EXCEPTION 'existing source statement identity changed; reviewed reconciliation required';
        END IF;
        RETURN jsonb_build_object('status','already_published','statement_id',v_statement.id,'proof_digest',identity_key);
    END IF;
    -- Legacy rows are never adopted or overwritten merely because text matches.
    IF EXISTS(SELECT 1 FROM public.key_statements k WHERE k.meeting_id=v_meeting_id
        AND k.agenda_item_id=v_agenda_id AND to_jsonb(k.source_segment_ids)=source_ids
        AND k.statement_text=s->>'statement_text')THEN RAISE EXCEPTION 'unproved legacy statement collision held'; END IF;
    INSERT INTO public.key_statements("meeting_id","agenda_item_id","speaker_name","person_id","statement_type","statement_text","context","source_segment_ids","start_time","municipality_id")
        VALUES(v_meeting_id,v_agenda_id,s->>'speaker_name',v_person_id,s->>'statement_type',s->>'statement_text',s->>'context',ids,first_start,v_meeting.municipality_id)
        RETURNING * INTO v_statement;
    proof:=jsonb_build_object('statement_id',v_statement.id,'meeting_id',v_meeting_id,'agenda_item_id',v_agenda_id,
        'transcript_source_sha256',source_sha,'source_segment_indexes',(SELECT jsonb_agg(value->'source_index')FROM jsonb_array_elements(v->'raw_segments')),
        'source_segment_ids',source_ids,'source_quote_sha256',quote_sha,'person_id',v_person_id,
        'validator_version',v->>'validator_version','validator_sha256',v->>'validator_sha256',
        'input_sha256',p_input_sha256,'identity_receipt_sha256s',receipt_hashes,'receipt_hash_format','postgres-jsonb-text-sha256-v1');
    UPDATE public.meetings SET "meta"=v_meta||jsonb_build_object('key_statement_evidence',allproofs||jsonb_build_object(identity_key,proof))WHERE id=v_meeting_id;
    RETURN jsonb_build_object('status','published','statement_id',v_statement.id,'proof_digest',identity_key);
END;
$$;
REVOKE ALL ON FUNCTION public.publish_source_bound_key_statement(text,text)FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.publish_source_bound_key_statement(text,text)TO service_role;
COMMIT;
