"""Selected G5 regressions; removed GEMM hardware Fault cases are not replayed."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,re,subprocess,sys
ROOT=Path(__file__).resolve().parents[2]
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--vivado-bin",required=True);a=p.parse_args()
    out=ROOT/"07_runs"/("npu_gemm_reuse_regression_"+datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%fZ"))
    out.mkdir();print("[RUN] "+str(out),flush=True)
    def cmd(phase,*args):return [sys.executable,"-X","utf8","-B",f"90_scripts/npu/run_{phase}.py","--vivado-bin",a.vivado_bin,*args]
    jobs=[("scalar_python_legacy5",cmd("phase1","--legacy")),
          ("scalar_block_normal",cmd("phase4","--debug-only")),
          ("gemm_argmax_A_B",cmd("phase6","--case","gemm_then_argmax_dir0")),
          ("gemm_argmax_B_A",cmd("phase6","--case","gemm_then_argmax_dir1")),
          ("argmax_consecutive",cmd("phase6","--case","consecutive_source_length_change"))]
    tracked=subprocess.check_output(["git","ls-files"],cwd=ROOT,text=True).splitlines()
    guard={s:hashlib.sha256((ROOT/s).read_bytes()).hexdigest() for s in tracked if (ROOT/s).is_file()}
    result=dict(status="FAIL",scope="selected normal execution + original Legacy five targets",jobs=[])
    try:
        for name,command in jobs:
            print("[G5] "+name,flush=True);log=out/(name+".log")
            with log.open("w",encoding="utf-8") as f:
                rc=subprocess.run(command,cwd=ROOT,stdout=f,stderr=subprocess.STDOUT,timeout=1800).returncode
            text=log.read_text(encoding="utf-8",errors="replace")
            paths=re.findall(r"^\[RUN\] (.+)$",text,re.M)
            item=dict(name=name,command=command,return_code=rc,log=str(log),status="FAIL");result["jobs"].append(item)
            if rc or not paths:raise RuntimeError(name+" failed; see "+str(log))
            child=Path(paths[-1].strip());metrics=json.loads((child/"metrics.json").read_text(encoding="utf-8"))
            if metrics["status"]!="PASS":raise RuntimeError(name+" incomplete")
            item.update(status="PASS",run=str(child));print("[G5_PASS] "+name,flush=True)
        result["status"]="PASS"
    except Exception as error:result["reason"]=repr(error);print("[STOP] "+repr(error),flush=True)
    finally:
        result["source_changed"]=[s for s,h in guard.items() if hashlib.sha256((ROOT/s).read_bytes()).hexdigest()!=h]
        if result["source_changed"]:result["status"]="FAIL"
        (out/"metrics.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    print("[G5_RESULT] "+result["status"]+" "+str(out),flush=True)
    return int(result["status"]!="PASS")
if __name__=="__main__":raise SystemExit(main())
