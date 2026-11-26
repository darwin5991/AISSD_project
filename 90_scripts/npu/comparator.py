"""Strict dense external dump comparison. No tolerance/masking or DUT reference."""
import json,re
from pathlib import Path
import numpy as np
from model_loader import sha
def compare(run):
    run=Path(run);m=json.loads((run/'manifest.json').read_text())
    for name,digest in m['files_sha256'].items():
        if sha(run/name)!=digest:raise ValueError('immutable artifact changed '+name)
    lines=(run/m['dump']['file']).read_text().splitlines()
    if len(lines)!=m['dump']['words'] or any(not re.fullmatch('[0-9a-fA-F]{8}',x) for x in lines):raise ValueError('dump length/unknown/format')
    words=np.array([int(x,16) for x in lines],dtype='<u4')
    records=words.view(np.uint8).reshape(len(m['sample_ids']),m['record_stride'])
    report=dict(passed=True,fields={},sample_ids=m['sample_ids'],mismatching_sample_ids=[],output_sha256=sha(run/m['dump']['file']))
    failed=set()
    with np.load(run/'reference.npz',allow_pickle=False) as ref:
        for key,f in m['fields'].items():
            raw=records[:,f['offset']:f['offset']+f['bytes']].copy()
            actual=raw.view(np.int8) if f['dtype']=='int8' else raw.view('<u4').reshape(-1)
            expected=ref[key]; bad=np.argwhere(actual!=expected)
            field=dict(total=int(expected.size),matches=int(expected.size-len(bad)),mismatches=int(len(bad)),first=[])
            for coord in bad:
                row=int(coord[0]);failed.add(m['sample_ids'][row])
                col=int(coord[1]) if len(coord)>1 else 0
                if len(field['first'])<10:
                    unit=1 if f['dtype']=='int8' else 4
                    field['first'].append(dict(sample_id=m['sample_ids'][row],index=col,address=f'{m["dump"]["base"]+row*m["record_stride"]+f["offset"]+unit*col:08x}',expected=int(expected[tuple(coord)]),actual=int(actual[tuple(coord)]),raw_word=f'{int(words[(row*m["record_stride"]+f["offset"]+unit*col)//4]):08x}'))
            report['fields'][key]=field
        if 'argmax' in ref:
            report['reference_label_matches']=int(np.sum(ref['argmax']==ref['labels']))
            report['label_count']=len(m['sample_ids'])
    report['passed']=not failed;report['mismatching_sample_ids']=sorted(failed)
    (run/'comparison.json').write_text(json.dumps(report,indent=2)+'\n')
    (run/'summary.md').write_text(f"{m['scenario']['name']}: {'PASS' if report['passed'] else 'FAIL'}\n\n"+json.dumps(report,indent=2)+'\n')
    return report
