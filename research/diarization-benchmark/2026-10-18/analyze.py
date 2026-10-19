"""Compare machine outputs without treating any model as human-labelled truth."""
import collections
import json
from pathlib import Path

import numpy as np
from scipy.optimize import linear_sum_assignment
from pipeline.local_diarizer import LocalDiarizer
from pipeline.speaker_evidence import has_temporal_support, label_key

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
STEP = .1


def read(path):
    return json.loads(path.read_text())


def enrollment(segments, references):
    chosen, evidence = {}, []
    for ref in references:
        counts = collections.Counter()
        for s in segments:
            overlap = max(0, min(s['end'], ref['prefix_end']-.1)-max(s['start'], ref['prefix_start']+.1))
            counts[s['speaker']] += overlap
        if not sum(counts.values()):
            evidence.append(dict(person_id=ref['person_id'],reason='no reference speech detected'))
            continue
        label, seconds = counts.most_common(1)[0]
        share = seconds/sum(counts.values())
        evidence.append(dict(person_id=ref['person_id'],label=label,seconds=seconds,share=share))
        if seconds >= 1 and share >= .5:
            chosen[ref['person_id']] = label
    repeated = {label for label in chosen.values() if list(chosen.values()).count(label)>1}
    # Even a weaker second reference is a collision signal. Do not count its
    # shared cluster as confident speech from the stronger reference's person.
    accepted = {e['person_id'] for e in evidence if e.get('share',0)>=.8}
    for e in evidence:
        if e.get('label') in repeated:e['reference_collision']=True
    return {label:pid for pid,label in chosen.items() if label not in repeated and pid in accepted}, evidence


def frame(segments, duration, prefix):
    labels = sorted({s['speaker'] for s in segments})
    lookup = {label:i for i,label in enumerate(labels)}
    values = np.full(int(np.ceil(duration/STEP)), -1, dtype=np.int32)
    for s in segments:
        lo=max(0,int(np.ceil((s['start']-prefix)/STEP)))
        hi=min(len(values),int(np.ceil((s['end']-prefix)/STEP)))
        if hi<=lo:continue
        active=values[lo:hi]
        code=lookup[s['speaker']]
        conflict=(active>=0)&(active!=code)
        empty=active==-1
        active[empty]=code
        active[conflict]=-2
    return values, labels


def compare(a,b):
    good=(a>=0)&(b>=0)
    common=int(good.sum())
    a_speech=a!=-1;b_speech=b!=-1
    union=int((a_speech|b_speech).sum())
    if not common:return dict(common_speech_seconds=0)
    matrix=np.zeros((int(a[good].max())+1,int(b[good].max())+1),dtype=np.int64)
    np.add.at(matrix,(a[good],b[good]),1)
    row,col=linear_sum_assignment(matrix,maximize=True)
    matched=int(matrix[row,col].sum())
    return dict(common_speech_seconds=round(common*STEP,1),
        optimally_matched_speaker_agreement=matched/common,
        speech_activity_agreement_on_union=float((a_speech&b_speech).sum())/union if union else None,
        unresolved_overlap_a_seconds=int((a==-2).sum())*STEP,
        unresolved_overlap_b_seconds=int((b==-2).sum())*STEP)


def main():
    manifest=read(HERE/'manifest.json');prefix=manifest['prefix_seconds']
    result=dict(method='100ms frames; per-ten-minute optimal anonymous-label matching; agreement is not accuracy',meetings=[])
    for m in manifest['meetings']:
        mid=m['id'];duration=m['duration_seconds']
        providers={}
        for kind in ['senko','community']:
            path=HERE/'results'/f'{mid}-{kind}.json'
            if path.exists():providers[kind]=read(path)
        chunks=sorted((HERE/'results'/'openai-chunks').glob(f'{mid}-*.json'))
        expected=int(np.ceil((duration+prefix)/600))
        if len(chunks)==expected:
            responses=[read(p) for p in chunks]
            segments=[]
            for chunk in responses:
                for s in chunk['response'].get('segments',[]):
                    label=s['speaker']
                    if not label.startswith('person_'):label=f"chunk_{chunk['chunk']}:{label}"
                    segments.append(dict(start=s['start']+chunk['offset'],end=s['end']+chunk['offset'],speaker=label,text=s.get('text','')))
            providers['openai']=dict(segments=segments,seconds=sum(c['elapsed_seconds'] for c in responses),
                wall_seconds=max(c.get('api_finished_at',p.stat().st_mtime) for c,p in zip(responses,chunks))-min(c.get('api_started_at',p.stat().st_mtime-c['elapsed_seconds']) for c,p in zip(responses,chunks)),
                chunks=len(chunks),usage=[c['response'].get('usage') for c in responses])
        entry=dict(meeting_id=mid,date=m['date'],duration_seconds=duration,providers={},pairwise={},challenge_windows=[])
        grids={};names={}
        for provider,data in providers.items():
            segments=data['segments']
            mapping,evidence=enrollment(segments,manifest['references'])
            if provider=='openai':
                mapping={f"person_{r['person_id']}":r['person_id'] for r in manifest['references']}
            grid,labels=frame(segments,duration,prefix);grids[provider]=grid
            named=np.full(len(grid),-1,dtype=np.int32)
            for i,label in enumerate(labels):
                if label in mapping:named[grid==i]=mapping[label]
            names[provider]=named
            counts=collections.Counter({pid:int((named==pid).sum())*STEP for pid in mapping.values()})
            stats=dict(runtime_seconds=data['seconds'],speech_seconds=int((grid!=-1).sum())*STEP,
                local_speaker_labels=len(labels),named_seconds=dict(counts),reference_evidence=evidence,
                reference_conflicts=[e for e in evidence if e.get('label') not in mapping],
                completed_openai_chunks=len(chunks) if provider=='openai' else None,
                incomplete_openai_chunks=expected-len(chunks) if provider=='openai' else None)
            if provider=='openai':
                stats['usage']=data['usage']
                stats['wall_seconds']=data['wall_seconds']
                stats['estimated_usd_at_published_token_rates']=sum((u.get('input_tokens',0)*2.5+u.get('output_tokens',0)*10)/1e6 for u in data['usage'] if u)
                stats['cost_basis']='Published model-card input $2.50/M and output $10/M token rates; usage-based estimate, not a billing receipt'
            else:
                # Compare local engines using identical cached ASR sentences.
                raw_path=(ROOT/m['audio']).with_name(Path(m['audio']).stem+'_raw_transcript.json')
                raw=read(raw_path)
                raw=raw.get('segments',raw.get('sentences',[])) if isinstance(raw,dict) else raw
                asr=[dict(start=s.get('start',s.get('start_time'))+prefix,
                          end=s.get('end',s.get('end_time'))+prefix,text=s.get('text','')) for s in raw]
                merged=LocalDiarizer()._merge_results(asr,segments,{})
                accepted=collections.Counter();rejected=0.
                for s in merged:
                    # Match the normalized output label back to this engine's key.
                    candidates=[label for label in mapping if (label_key(label) or label)==(label_key(s['speaker']) or s['speaker'])]
                    seconds=s['end']-s['start']
                    if has_temporal_support(s) and len(candidates)==1:accepted[mapping[candidates[0]]]+=seconds
                    elif candidates:rejected+=seconds
                stats['cached_asr_accepted_named_seconds']=dict(accepted)
                stats['cached_asr_named_candidate_timing_rejected_seconds']=rejected
                stats['cached_asr_sentences']=len(asr)
            entry['providers'][provider]=stats
        for a in providers:
            for b in providers:
                if a>=b:continue
                blocks=[]
                for offset in range(0,len(grids[a]),6000):
                    blocks.append(compare(grids[a][offset:offset+6000],grids[b][offset:offset+6000]))
                common=sum(v['common_speech_seconds'] for v in blocks)
                agree=sum(v['common_speech_seconds']*v.get('optimally_matched_speaker_agreement',0) for v in blocks)
                entry['pairwise'][f'{a}/{b}']=dict(common_speech_seconds=common,
                    per_chunk_speaker_agreement=agree/common if common else None,
                    colby_both_seconds=int(((names[a]==21)&(names[b]==21)).sum())*STEP,
                    colby_only_a_seconds=int(((names[a]==21)&(names[b]!=21)).sum())*STEP,
                    colby_only_b_seconds=int(((names[b]==21)&(names[a]!=21)).sum())*STEP)
        windows=[(8615.24,8830.16,'long cached Colby candidate')] if mid==219 else [(3550,3820,'Lisa/preceding speaker/chair service-check window')]
        for start,end,label in windows:
            w=dict(start=start,end=end,label=label,providers={})
            for provider,named in names.items():
                lo=int(start/STEP);hi=int(end/STEP)
                w['providers'][provider]={str(pid):int((named[lo:hi]==pid).sum())*STEP for pid in [1,21,23,353]}
            entry['challenge_windows'].append(w)
        result['meetings'].append(entry)
    (HERE/'comparison.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
