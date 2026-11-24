"""Audit actual debug VCD edges independently of the DUT control implementation."""
from pathlib import Path
import argparse,json,re

def audit(run):
    lines=(run/"timing.vcd").read_text().splitlines()
    ids={};scope=[];values={};blocks=[];stamp=0;changes=[]
    for line in lines:
        fields=line.split()
        if line.startswith("$scope"):scope.append(fields[2])
        elif line.startswith("$upscope"):scope.pop()
        elif line.startswith("$var"):ids["/".join(scope+[fields[4]])]=fields[3]
        elif line.startswith("#"):
            blocks.append((stamp,changes));stamp=int(line[1:]);changes=[]
        elif line and not line.startswith("$"):
            changes.append(line)
    blocks.append((stamp,changes))
    def key(name):
        found=[v for k,v in ids.items() if k.endswith("/"+name)]
        assert len(found)==1,(name,found)
        return found[0]
    keys={s:key(s) for s in ("clk","rst_n","gemm_start","gemm_active","gemm_done","read_issue",
                           "input_word","output_group","weight_cursor","gemm_en","gemm_we",
                           "mac_input_valid","psum_valid","bias_load","result_load")}
    rows=[];cursor_checks=0
    for time,updates in blocks:
        old=values.copy()
        for line in updates:
            if line[0] in "bB":bits,identifier=line[1:].split()
            elif line[0] in "01xXzZ":bits,identifier=line[0],line[1:]
            else:continue
            values[identifier]=int(bits,2) if re.fullmatch("[01]+",bits) else None
        if old.get(keys["clk"])==0 and values.get(keys["clk"])==1:
            before={s:old.get(k) for s,k in keys.items()}
            if before["rst_n"]==1:
                assert all(v is not None for v in before.values()),"unknown sampled signal"
                if not before["gemm_start"]:
                    expected=before["weight_cursor"]+before["read_issue"]
                    assert values[keys["weight_cursor"]]==expected,"cursor must advance only on actual Read"
                    cursor_checks+=1
                rows.append((time,before))
    reads=[t for t,v in rows if v["read_issue"]]
    assert len(reads)>=4,"insufficient Read coverage"
    period=min(b-a for a,b in zip(reads,reads[1:]))
    groups={}
    for time,v in rows:
        enabled=(v["gemm_en"]>>2)&15
        assert enabled==(15 if v["read_issue"] else 0),"Weight bank Read enables"
        if v["read_issue"]:groups.setdefault(v["output_group"],[]).append(time)
    group_reads=list(groups.values());assert len(group_reads)>=2,"group gap not exercised"
    for left,right in zip(group_reads,group_reads[1:]):
        assert right[0]-left[-1]==2*period,"group gap must be one Read-free cycle"
    def edges(name):return {t for t,v in rows if v[name]}
    last=[g[-1] for g in group_reads]
    assert edges("mac_input_valid")=={r+period for r in reads},"MAC input R+1"
    assert edges("psum_valid")=={r+4*period for r in reads},"accumulate R+4"
    assert edges("result_load")=={r+5*period for r in last},"result R+5"
    assert edges("gemm_we")=={r+6*period for r in last},"Write R+6"
    assert edges("bias_load")=={reads[0]+period,*[r+5*period for r in last[:-1]]},"first/next Bias"
    starts=edges("gemm_start");assert len(starts)==1
    assert reads[0]-next(iter(starts))==2*period,"Start S to first Read S+2"
    done=edges("gemm_done");assert len(done)==1
    assert next(iter(done))==last[-1]+7*period,"Done sampled after final committed Write"
    return dict(status="PASS",sampled_rising_edges=len(rows),cursor_checks=cursor_checks,reads=len(reads),
                groups=len(groups),group_gaps=len(groups)-1,period_ps=period,read_edges_ps=reads,
                result_edges_ps=sorted(edges("result_load")),write_edges_ps=sorted(edges("gemm_we")),
                bias_edges_ps=sorted(edges("bias_load")),done_sample_edges_ps=sorted(done),
                contracts=["S+2 first Read","R+1 operands","R+4 accumulate","R+5 result/bias","R+6 Write","one-cycle gap","cursor Read-only advance"])

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("run",type=Path);a=p.parse_args()
    result=audit(a.run)
    (a.run/"wave_audit.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result,indent=2))
if __name__=="__main__":main()
