"""Phase 8 port-level RTL/netlist regression using the preserved Phase 7 G1/G4 data."""
from datetime import datetime,timezone
from pathlib import Path
import argparse,ast,hashlib,json,re,shutil,subprocess,sys
sys.dont_write_bytecode=True
import run_phase1 as scalar
ROOT=scalar.ROOT
legacy=scalar.legacy
BASELINE=ROOT/"07_runs/npu_phase7_20261123_220156_054531Z"

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,obj):p.write_text(json.dumps(obj,indent=2)+"\n",encoding="utf-8")

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--vivado-bin",type=Path,required=True)
    p.add_argument("--synth-run",type=Path)
    p.add_argument("--counts",type=int,nargs="+",default=[1])
    a=p.parse_args()
    if any(n not in (1,200) for n in a.counts):p.error("only G1/G4")
    rid="npu_phase8_verify_"+datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%fZ")
    out=ROOT/"07_runs"/rid;out.mkdir()
    build=ROOT/"99_build"/rid;build.mkdir()
    print("[RUN] "+str(out),flush=True)
    stages=[];result=dict(status="FAIL",profiles=[],kind="netlist" if a.synth_run else "rtl_wrapper")
    manifest=dict(stages=stages,sources_sha256={},baseline=str(BASELINE))
    try:
        tools=legacy.find_tools(a.vivado_bin)
        if not a.synth_run:
            work=build/"reset";work.mkdir()
            logs=out/"logs/reset";logs.mkdir(parents=True)
            names=["06_fpga/rtl/npu_reset_sync.sv","04_rtl/memory/single_port_bram.sv",
                   "05_tb/npu/tb_npu_reset_sync.sv"]
            unit_sources=[]
            for name in names:
                target=out/"reset_source_snapshot"/name
                target.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(ROOT/name,target);unit_sources.append(target.as_posix())
                manifest["sources_sha256"][str(ROOT/name)]=sha(ROOT/name)
            unit_commands=[
                ("compile","xvlog",["-sv",*unit_sources,"-log","xvlog.log"]),
                ("elaborate","xelab",["work.tb_npu_reset_sync","-s","reset_unit","-debug","off","-timescale","1ns/1ps","-log","xelab.log"]),
                ("simulate","xsim",["reset_unit","-R","-onerror","quit","-onfinish","quit","-log","xsim.log"])]
            for stage,tool,args in unit_commands:
                rc,text=legacy.run_stage("reset_"+stage,tools[tool],args,work,logs,180,stages)
                if rc or legacy.ERROR_LINE.search(text):
                    raise RuntimeError("Reset/SRAM unit failed "+stage)
                if stage=="simulate" and not re.search(r"^\[RESET_SRAM\] result=PASS checks=\d+$",text,re.M):
                    raise RuntimeError("Reset/SRAM unit missing PASS")
            result["reset_unit"]="PASS"
        if a.synth_run:
            net=a.synth_run/"synthesized_funcsim.v"
            module=re.search(r"^module\s+(\w+)\b",net.read_text(),re.M).group(1)
            # Exported child modules may precede the top in a flattened netlist.
            body=net.read_text()
            module="npu_fpga_top" if re.search(r"^module npu_fpga_top\b",body,re.M) else "npu_top"
            sources=[net,a.vivado_bin.parent/"data/verilog/src/glbl.v"]
        else:
            module="npu_fpga_top"
            sources=[ROOT/f for f in scalar.SOURCES[:-1]]+[
                ROOT/"06_fpga/rtl/npu_reset_sync.sv",ROOT/"06_fpga/rtl/npu_fpga_top.sv"]
        sources+=[ROOT/"05_tb/npu/tb_npu_fpga_application.sv"]
        snap=out/"source_snapshot";snap.mkdir()
        copied=[]
        for i,source in enumerate(sources):
            target=snap/f"{i:02d}_{source.name}";shutil.copyfile(source,target)
            copied.append(target)
            manifest["sources_sha256"][str(source)]=sha(source)
        manifest["top"]=module
        for n in a.counts:
            name="G1" if n==1 else "G4"
            source=BASELINE/"data"/name
            saved=json.loads((source/"manifest.json").read_text())
            for f,h in saved["files_sha256"].items():
                if sha(source/f)!=h:raise RuntimeError("Phase 7 baseline hash changed: "+f)
            data=out/"data"/name;data.mkdir(parents=True)
            for f in ("imem.hex","dmem.hex","golden_prediction.hex","golden_layers.hex","npu_application_profile.vh"):
                shutil.copyfile(source/f,data/f)
            work=build/name;work.mkdir()
            logs=out/"logs"/name;logs.mkdir(parents=True)
            commands=[
                ("compile","xvlog",["-sv","-i",str(data),"-d","DUT_TOP="+module,*map(str,copied),"-log","xvlog.log"]),
                ("elaborate","xelab",["work.tb_npu_fpga_application",*(["work.glbl"] if a.synth_run else []),
                 "-L","unisims_ver","-L","unimacro_ver","-L","secureip","-s","fpga_app","-debug","off","-timescale","1ns/1ps","-log","xelab.log"]),
                ("simulate","xsim",["fpga_app","-onerror","quit","-onfinish","quit","-R",
                                   "-testplusarg","DATA_DIR="+data.as_posix(),"-log","xsim.log"])]
            for stage,tool,args in commands:
                rc,text=legacy.run_stage(name+"_"+stage,tools[tool],args,work,logs,1800,stages)
                if rc or legacy.ERROR_LINE.search(text):raise RuntimeError(name+" "+stage+" failed")
                if stage=="simulate" and len(re.findall(r"^\[FPGA_APP\] result=PASS ",text,re.M))!=1:
                    raise RuntimeError(name+" missing PASS summary")
            rows=[line.split() for line in (data/"observed_prediction.txt").read_text().splitlines()]
            expected=[line.split() for line in (source/"observed_prediction.txt").read_text().splitlines()]
            if rows!=expected:raise RuntimeError("Prediction differs from Phase 7")
            result["profiles"].append(dict(name=name,images=n,status="PASS",prediction_sha256=sha(data/"observed_prediction.txt")))
            print("[VERIFY] "+name+" PASS",flush=True)
        result["status"]="PASS"
    except Exception as error:
        result["reason"]=repr(error);print("[STOP] "+repr(error),flush=True)
    finally:
        save(out/"metrics.json",result);save(out/"manifest.json",manifest)
    print("[PHASE8_VERIFY] "+result["status"],flush=True)
    return int(result["status"]!="PASS")
if __name__=="__main__":raise SystemExit(main())
