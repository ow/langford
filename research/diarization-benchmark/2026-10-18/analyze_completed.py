"""Aggregate full-output consistency; never grade aliases as identity truth."""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import sys
os.environ.setdefault('OPENBLAS_NUM_THREADS', '1')
import numpy as np
from scipy.optimize import linear_sum_assignment

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
PRIVATE=ROOT/'.private/research/diarization-benchmark/2026-10-19'
sys.path.insert(0,str(ROOT/'apps/pipeline'))
from pipeline.ingestion.transcript_links import temporal_evidence
STEP=.1


def read(path):return json.loads(path.read_text())


def frames(turns, duration, prefix):
    labels=sorted({turn['speaker']for turn in turns})
    lookup={label:index for index,label in enumerate(labels)}
    grid=np.full(int(np.ceil(duration/STEP)),-1,dtype=np.int32)
    for turn in turns:
        low=max(0,int(np.ceil((turn['start']-prefix)/STEP)))
        high=min(len(grid),int(np.ceil((turn['end']-prefix)/STEP)))
        if high<=low:continue
        current=grid[low:high];code=lookup[turn['speaker']]
        conflicts=(current>=0)&(current!=code)
        current[current==-1]=code;current[conflicts]=-2
    return grid


def agreement(a,b):
    common=(a>=0)&(b>=0);count=int(common.sum())
    if not count:return {'common_single_voice_seconds':0,'agreement':None}
    matrix=np.zeros((int(a[common].max())+1,int(b[common].max())+1),dtype=np.int64)
    np.add.at(matrix,(a[common],b[common]),1)
    left,right=linear_sum_assignment(matrix,maximize=True)
    return {'common_single_voice_seconds':count*STEP,'agreement':float(matrix[left,right].sum())/count}


def sentence_support(sentences,turns,prefix):
    counts=Counter();seconds=Counter()
    for row in sentences:
        start,end=row.get('start',row.get('start_time')),row.get('end',row.get('end_time'))
        if not isinstance(start,(int,float))or not isinstance(end,(int,float))or not 0<=start<end:
            counts['invalid_source_timing']+=1;continue
        start+=prefix;end+=prefix
        nearby=[turn for turn in turns if turn['start']<end and turn['end']>start]
        labels={turn['speaker']for turn in nearby}
        evidence=[temporal_evidence(start,end,label,nearby)for label in labels]
        supported=any(value['status']=='supported'for value in evidence)
        status='model_internal_temporal_support'if supported else'model_internal_temporal_hold'
        counts[status]+=1;seconds[status]+=end-start
    return {'rows':dict(counts),'source_sentence_seconds':dict(seconds),
            'identity_validated_rows':0,'meaning':'Drop-in compatibility with shared cached ASR sentence times, not intrinsic temporal precision or validated identity; new cloud ASR may use different boundaries'}


def main(allow_incomplete=False):
    manifest=read(PRIVATE/'legacy-protocol-manifest.json');prefix=manifest['prefix_seconds'];meetings=[];complete=True
    for meeting in manifest['meetings']:
        mid=meeting['id'];duration=meeting['duration_seconds'];providers={};grids={}
        for kind in ('senko','community'):
            path=HERE/'results'/f'{mid}-{kind}.json'
            if path.exists():providers[kind]=read(path)
            else:complete=False
        chunk_files=sorted((HERE/'results/openai-chunks').glob(f'{mid}-*.json'))
        chunks=[read(path)for path in chunk_files]
        expected=int(np.ceil((duration+prefix)/600))
        if len(chunks)!=expected:raise RuntimeError('Incomplete cached cloud material; no new API requests are sent')
        cloud=[]
        for chunk in chunks:
            for turn in chunk['response']['segments']:
                label=turn['speaker']
                if not label.startswith('person_'):label=f"chunk_{chunk['chunk']}:{label}"
                cloud.append({'start':turn['start']+chunk['offset'],'end':turn['end']+chunk['offset'],'speaker':label})
        providers['openai']={'segments':cloud,'raw_segments':cloud,
          'seconds':sum(chunk['elapsed_seconds']for chunk in chunks),
          'wall_seconds':max(chunk.get('api_finished_at',path.stat().st_mtime)for chunk,path in zip(chunks,chunk_files))
                         -min(chunk.get('api_started_at',path.stat().st_mtime-chunk['elapsed_seconds'])for chunk,path in zip(chunks,chunk_files)),
          'timing_basis':('recorded_request_timestamps'if all('api_started_at'in chunk and'api_finished_at'in chunk for chunk in chunks)
                          else'early_request_times_estimated_from_recorded_elapsed_and_response_file_mtime'),
          'runtime_scope':'remote_transcription_and_diarization_request_span',
          'estimated_usd':sum((chunk['response']['usage']['input_tokens']*2.5+chunk['response']['usage']['output_tokens']*10)/1e6 for chunk in chunks)}
        raw_path=(ROOT/meeting['audio']).with_name(Path(meeting['audio']).stem+'_raw_transcript.json')
        raw=read(raw_path);sentences=raw.get('segments',raw.get('sentences',[]))if isinstance(raw,dict)else raw
        result={'meeting_id':mid,'recording_seconds':duration,'providers':{},'pairwise':{}}
        for kind,output in providers.items():
            grid=frames(output['segments'],duration,prefix);grids[kind]=grid
            turns=output.get('overlap_segments',output.get('raw_segments',output['segments']))
            stats={'speech_union_seconds':int((grid!=-1).sum())*STEP,
                   'speaker_labels':len({turn['speaker']for turn in output['segments']}),
                   'label_scope':('request_local_anonymous_labels_plus_unvalidated_reference_names'if kind=='openai'
                                  else'whole_recording_cluster_labels'),
                   'runtime_seconds':output['seconds'],
                   'runtime_scope':output.get('runtime_scope','acoustic_only_single_complete_meeting_attempt'),
                   'sentence_alignment':sentence_support(sentences,turns,prefix)}
            if kind=='openai':stats.update(wall_seconds=output['wall_seconds'],timing_basis=output['timing_basis'],estimated_usd=output['estimated_usd'])
            if kind=='community':stats.update(embedding_batches_reused=output.get('embedding_batches_reused',0),
                  process_peak_rss_bytes=output.get('process_peak_rss_bytes'))
            result['providers'][kind]=stats
        for left in providers:
            for right in providers:
                if left>=right:continue
                parts=[agreement(grids[left][i:i+6000],grids[right][i:i+6000])for i in range(0,len(grids[left]),6000)]
                common=sum(part['common_single_voice_seconds']for part in parts)
                result['pairwise'][left+'/'+right]={'common_single_voice_seconds':common,
                  'anonymous_agreement':sum(part['common_single_voice_seconds']*(part['agreement']or 0)for part in parts)/common if common else None,
                  'is_accuracy_or_DER':False}
        meetings.append(result)
    if not complete and not allow_incomplete:raise RuntimeError('Community-1 full comparison is not complete')
    result={'status':'complete_three_engine_outputs'if complete else'incomplete_community_pending',
      'meetings':meetings,'new_paid_calls':0,'production_writes':0,
      'legacy_reference_bank_is_identity_ground_truth':False,
      'evaluation_notes':['100ms frames, optimally matched anonymous labels separately within ten-minute intervals',
        'Model-internal interval support is not independent acoustic or named identity truth',
        'Shared cached-ASR alignment measures drop-in compatibility; cloud native ASR boundaries may differ',
        'Cloud anonymous labels reset by request; label counts are not directly comparable to whole-recording local cluster counts',
        'Local timings exclude fresh ASR; cloud includes ASR; resumed elapsed excludes earlier completed cached work',
        'Old alias/consensus enrollment cannot establish named precision/recall',
        'Cost uses cached token usage and published rates, not a billing receipt']}
    PRIVATE.mkdir(parents=True,exist_ok=True)
    output=PRIVATE/('comparison-complete.json'if complete else'comparison-provisional.json')
    output.write_text(json.dumps(result,indent=2)+'\n')
    if complete:(HERE/'comparison-v2-aggregate.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'status':result['status'],'new_paid_calls':0,'meetings':len(meetings)}))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--allow-incomplete',action='store_true')
    main(parser.parse_args().allow_incomplete)
