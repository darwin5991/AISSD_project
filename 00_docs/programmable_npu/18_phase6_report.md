# Phase 6 — ARGMAX 독립 실행 구현 및 검증 보고서

작성일: 2026-11-24 (Asia/Seoul). **Phase 6 Gate: PASS.**
작업 브랜치: `feat/phase6-argmax-20261124`. 기준 HEAD: `414fd57b56adbeeee8a4542d6fd66120efc179a3`, 부모 Phase 5: `5be9059844bcf536ef160bee3a4c4ce9e4bf9b6f`.

## 1. 승인 범위와 시작 상태

사용자 첨부 Phase 6 RTL Implementation 요청으로 독립 ARGMAX 및 검증을 승인받았다. AGENTS.md, ISA/Architecture/Implementation/Verification, [17번 P6-D-01/D-02](17_phase6_decisions.md), 기존 MAC/MLP 및 Phase 1~5/16 보고서와 실제 RTL을 대조했다.

시작 시 미커밋 변경은 직전 문서 작업의 01/02/03/04/README와 신규 17번 결정 문서뿐이었다. 이 6개를 보존했고 무관한 변경은 없었다. 기존 브랜치 존재 여부를 확인한 뒤 요청한 새 브랜치를 생성했다. **커밋·Push는 수행하지 않았고 HEAD는 414fd57 그대로다.**

17번의 확정 결정 본문은 변경하지 않았다. 문서 작성 당시 상태와 후속 구현 승인/결과를 구분하는 상태 설명만 보완했다. 새로운 Opcode·CSR·오류 코드·메모리 프로토콜은 추가하지 않았다. Phase 7/8, 합성/FPGA, MNIST 10,000장은 수행하지 않았다.

## 2. 생성·수정 파일

기준 HEAD 대비 문서 7개와 기능/검증 13개, 총 20개 파일이다. 문서 6개는 시작 시 이미 미커밋 상태였던 변경을 포함한다.

| 파일 | 역할/변경 |
|---|---|
| `04_rtl/controller/argmax_engine.sv` 신규 | 원본 64bit 범위 검사, 가변 Read/Compare, 기존 비교 Datapath, 완료/Fault |
| `04_rtl/isa/npu_isa_pkg.sv` | 내부 OP_ARGMAX 추가, 기존 operation 값 유지 |
| `04_rtl/isa/instruction_decoder.sv` | 기존 EXEC ARGMAX 인코딩·예약 필드·rd 검사 |
| `04_rtl/isa/csr_file.sv` | 원본 ARG_SRC/LEN 병렬 출력 2개 |
| `04_rtl/isa/instruction_controller.sv` | 원자적 Snapshot·오류 병합·CHECK/START/WAIT·지연 Writeback, FSM 5bit 확장 |
| `04_rtl/controller/npu_top.sv` | 실제 ARGMAX Engine·기존 Wrapper 포트·OWNER_ARGMAX 연결 |
| `05_tb/npu/tb_npu_phase6.sv` 신규 | 실제 bus/상태/비교 결과/Timer scoreboard, Snapshot·Reset·runtime TB 주입, 관측 dump |
| `90_scripts/npu/phase6_vectors.py` 신규 | 독립 Python 주소/ISA/수치 Golden 및 정상·Fault 시나리오 |
| `90_scripts/npu/run_phase6.py` 신규 | XSim·unit·관측 dump 비교, 테스트 ID/종료/timeout·hash·파형 기록 |
| `90_scripts/npu/run_phase1.py` | 기존 비교 Datapath와 신규 Engine compile 의존 목록 추가 |
| `05_tb/npu/tb_npu_phase2_units.sv` | 새 CSR 병렬 출력의 wildcard 연결 선언 |
| `05_tb/npu/tb_npu_phase2_active.sv` | 새 Controller 내부 포트의 wildcard 연결 선언 |
| `90_scripts/npu/phase5_vectors.py` | 기존 합법 ARGMAX,r0를 불법 사례로 쓰지 않도록 실제 예약 funct7 사례로 교체 |
| `00_docs/programmable_npu/01_isa_spec.md` | P6-D-01/D-02 기능 계약과 실제 구현 상태 |
| `02_architecture.md` | Snapshot 책임·실제 Engine/메모리/완료 구조 |
| `03_implementation_plan.md` | 구현 파일·순서·Gate 실제 결과 |
| `04_verification_plan.md` | A-01~16 및 A-B/A-P 기대값·실행 결과 구분 |
| `17_phase6_decisions.md` | D-01/D-02 확정 본문 보존, 후속 승인/실행 상태 연결 |
| `README.md`, `18_phase6_report.md` (보고서 신규) | 색인·진행 상태 및 본 보고서 |

기존 소스·모델·TB·설정 129개를 시작 전 hash로 기록했다. 승인된 기존 파일 9개만 달라졌고 나머지 **120개는 SHA-256 동일**하다. 이 9개는 위 기존 RTL 5개, Phase 2 TB 2개, Python 2개다. 신규 기능/검증 파일 4개를 별도로 추가했다.

Legacy MLP/ARGMAX 제어·비교 모듈, SRAM Wrapper/MUX/decoder/single_port_bram, Block/GEMM Engine, MAC·Multiplier·Adder Tree·Accumulator/Postprocess RTL 및 기존 헤더는 변경하지 않았다. SRAM 7개 깊이·폭·Single-Port·1clk Read와 MAC R→R+6/Bias 계약을 보존했다.

## 3. 모듈·Snapshot·오류 검사

### Engine 및 포트

Engine은 IDLE/READ/PROCESS/COMPLETE/FAILED의 독립 FSM이다. 기존 argmax_unit → byte_select4/signed_compare8/argmax_tracker/argmax_update/register_en을 그대로 인스턴스화한다.

입력은 start, config_words[0:1] (ARG_SRC/LEN 원본), sram_rdata/error다. 출력은 config_error[7:0], active/done/fault, error_code[7:0], result_index[3:0], sram_en/address[31:0]다. SRAM Write 포트는 없다.

Top 외부 IMEM/DMEM 포트와 프로토콜은 그대로다. 기존 Wrapper의 argmax_en/address/rdata/error 및 OWNER_ARGMAX를 연결했고, active는 SRAM 소유권에만 사용한다. Timer에는 추가 연결하지 않았다.

### Decode와 원자적 Snapshot

`EXEC ARGMAX,r5=0x020022AB`를 유지한다. rs1/rs2 등 예약 필드를 먼저 검사하여 0x08, 유효 형식의 rd=r8~r31은 0x02다. r0~r7은 정상이다.

CSR file은 기존 settings[10]/[11]의 원본을 argmax_settings[0:1]로 병렬 출력한다. Instruction Controller가 EXEC 수락 에지에 두 값, 원본 rd, next-PC 및 PC 오류를 함께 래치한다. ARG_CHECK에서 검사하고 성공해야 ARG_START를 1회 발생시킨다. ARG_WAIT에서 완료를 기다린 뒤 저장된 rd/next-PC로 끝낸다. Snapshot 전에 GPR을 쓰는 일반 instruction_commit 경로에서 ARGMAX를 제외했다.

Snapshot TB에서는 live ARG_SRC=0x80040001, ARG_LEN=0xFFFFFFFF 변경을 실제 관찰했지만 Snapshot은 0x80000040/10으로 유지돼 정상 완료했다. TB 전용 register deposit이며 일반 프로그램의 동시 CSR 쓰기 기능을 추가하지 않았다.

### P6-D-01/D-02

원본 unsigned 32bit L에서 **먼저 64bit로 확장한 뒤** W=(L+3)>>2, B=W×4, E=SRC+B를 계산한다. Alignment → A/B Region/역할 → 시작/끝 및 next-PC Bounds → 원본 LEN 1~10 Configuration 순서다. invalid 길이도 전체 Bounds를 검사한다. LEN=0은 시작 Bounds를 검사하고 W−1 underflow를 만들지 않는다. 실행 주소의 축소는 검사 뒤에만 소비한다.

| 실측 사례 | ERROR_CODE |
|---|---|
| A/B base, LEN=0 또는 11 | 07 |
| 실제 Buffer 끝, LEN=0 | 06 |
| 끝에서 8byte 남음, LEN=11 | 06 |
| base, LEN=0x10000001/0xFFFFFFFC/FD/FFFFFFFF | 06 |
| 비정렬 SRC와 다른 오류 | 05 |
| 정렬된 Weight/Bias/DMEM 등과 Bounds/Config | 04 |
| 정상 주소/길이 + next-PC Bounds | 06 |
| Alignment/Region + next-PC Bounds | 각각 05/04 |
| Config + next-PC Bounds | 06 |

사전 오류는 Engine start, DMEM/SRAM 요청, GPR Writeback 및 PC 전진 없이 Error Halt한다. PC/GPR/RW CSR 및 Timer는 보존하고 STATUS=2/최초 ERROR_CODE만 기록한다. 이후 Halt sticky 및 Reset 재시작을 확인했다.

실행 중 오류 경로는 첫 요소 초기화 뒤 TB에서 index=15를 주입했다. 잘못된 다음 처리를 차단하고 Engine FAILED → Controller Error Halt(06), PC/GPR/RW CSR 보존, 추가 Read/Writeback 없음으로 완료했다. 외부 bus/ECC 오류 응답 기능을 추가하거나 검증한 것은 아니다.

## 4. SRAM·비교·완료·Timer 타이밍

주소는 ARG_SRC+4×floor(i/4), lane=i[1:0]이다. READ R의 데이터는 R 직후 RAM에서 갱신되고 PROCESS R+1에서 소비한다. 같은 Word의 나머지 바이트는 RAM rdata hold를 사용하며 index=4/8 경계에서만 다음 Read를 낸다. 첫 값은 무조건 초기화, 이후 signed strict greater에서만 갱신한다. padding은 비교하지 않는다.

Fetch 요청 F 기준 Snapshot F+2, CHECK F+3, start F+4, 첫 Read F+5다. 정상 완료 age는 L+ceil(L/4)+5, 사전 설정/PC Fault는 3, Decode/GPR Fault는 2다. 이 일정은 실제 scoreboard와 일치했다.

| LEN | Read 수 | 첫 Read R 기준 최종 비교 | GPR Writeback |
|---:|---:|---|---|
| 1 | 1 | R+1 | R+2 |
| 3 | 1 | R+3 | R+4 |
| 4 | 1 | R+4 | R+5 |
| 9 | 3 | R+11 | R+12 |
| 10 | 3 | R+12 | R+13 |

마지막 비교 에지 직후 tracker 결과와 내부 done이 유효해지고, 다음 에지에 GPR이 안정된 결과를 zero-extend하여 기록한다. rd=r0도 전체 실행·Fault 검사를 수행하고 쓰기만 생략한다. Top done은 ARGMAX에서 발생하지 않으며 END에서만 1클럭이다. GEMM 자동 ARGMAX도 없다.

최종 Debug VCD 실측:

| 시각 | 실제 동작 |
|---:|---|
| 1845ns | A:0x80000040 Read, RAM/argmax rdata=0xF8F7F680 |
| 1855ns | 요소 0, signed −128로 초기화 |
| 1895ns / 1905ns | 두 번째 Read / 요소 4 소비 |
| 1945ns / 1955ns | 세 번째 Read / 요소 8 소비 |
| 1965ns | 요소 9=126 비교 후 결과 9, 내부 done=1 |
| 1975ns | r5에 9 Writeback, PC+4 |

마지막 Word=0x7F7F7EFD의 padding +127 두 개는 후보로 소비하지 않았다. 물리 A/B read probe와 argmax_rdata가 같은 요청 에지 직후 일치함을 확인했다. ARGMAX 동안 Count=6 유지, 별도 T-04 구간 Count=0 및 TB에서 seed한 Count=0xFFFFFFFE/overflow=1 보존도 PASS다. armed/unarmed 및 기존 TSTART/TSTOP/Overflow unit 회귀를 유지했다.

## 5. 실행 명령 및 실제 결과

저장소 루트, Python 3.14.5 / Vivado XSim 2025.2. 실행 ID는 UTC, 문서 날짜는 KST다.

```powershell
python -X utf8 -B 90_scripts/npu/run_phase6.py --vivado-bin D:/AMDDesignTools/2025.2/Vivado/bin
python -X utf8 -B 90_scripts/npu/run_phase6.py --case runtime_index_abort --vivado-bin D:/AMDDesignTools/2025.2/Vivado/bin
python -X utf8 -B 90_scripts/npu/run_phase1.py --legacy --vivado-bin D:/AMDDesignTools/2025.2/Vivado/bin
python -X utf8 -B 90_scripts/npu/run_phase2.py --vivado-bin D:/AMDDesignTools/2025.2/Vivado/bin
python -X utf8 -B 90_scripts/npu/run_phase3.py --vivado-bin D:/AMDDesignTools/2025.2/Vivado/bin
python -X utf8 -B 90_scripts/npu/run_phase4.py --vivado-bin D:/AMDDesignTools/2025.2/Vivado/bin
python -X utf8 -B 90_scripts/npu/run_phase5.py --vivado-bin D:/AMDDesignTools/2025.2/Vivado/bin
python -X utf8 -B 90_scripts/npu/run_fault_priority.py --vivado-bin D:/AMDDesignTools/2025.2/Vivado/bin
```

| Phase 6 최종 profile | Cases | RTL checks | Python dump words |
|---|---:|---:|---:|
| Debug, IMEM 4KiB/DMEM 16KiB | 1 | 11,684 | 1,853 |
| Main, IMEM 4KiB/DMEM 64KiB | 301 | 2,258,254 | 388,110 |
| PC Fault, IMEM 64KiB/DMEM 64KiB | 108 | 701,461 | 125,442 |
| Default DMEM 16MiB/IMEM 64KiB | 1 | 11,684 | 1,853 |
| **합계 PASS** | **411** | **2,983,083** | **517,258** |

17,344 instruction records, 4,789 memory events, 실제 ARGMAX 비교 상태 599개, GEMM control 24개/numeric update 20개도 일치했다. 독립 Golden unit 118 checks는 별도다. A-01~A-16, A-B01~18, A-P01~07의 41개 ID를 모두 실행했다. A-B 경계 38회, 마지막 PC Fault는 두 IMEM 용량 합계 216회다. 주 301사례는 정상 79, Fault 222(07=8, 06=83, 05=37, 04=51, 02=32, 08=7, 03=4)다.

signed 음/양수·동점·최대 첫/중간/마지막, 길이·padding, A/B·offset/경계, 전체 rd·r0, 모든 invalid rd, CSR/예약 필드, Snapshot, 연속 실행, 양방향 GEMM 뒤 독립 ARGMAX, 실행 중 Reset/오류, Timer 및 매 에지 PC/GPR/RW CSR 유지가 포함된다. SRAM은 LOAD로 준비했고 결과는 SW/STORE 및 실제 관측 dump로 비교했다. 대량 Waveform은 OFF, 작은 Debug만 WDB/VCD를 남겼다.

| 기존 회귀 | 실제 결과 / metrics |
|---|---|
| Phase 1 | 64KiB/256B 각각 61 cases·25,100 checks PASS — [결과](../../07_runs/npu_phase1_20261123_212012_145526Z/metrics.json) |
| Phase 2 | 각각 98 cases·75,116 checks, CSR/Timer unit 8,752·synthetic 114 PASS — [결과](../../07_runs/npu_phase2_20261123_212131_419524Z/metrics.json) |
| Phase 3 | 87+7 cases, 6,711,905+9,107 checks·owner 53 PASS — [결과](../../07_runs/npu_phase3_20261123_212131_372567Z/metrics.json) |
| Phase 4 | main 315, small/default 각 11, debug 1 PASS — [결과](../../07_runs/npu_phase4_20261123_212131_096244Z/metrics.json) |
| Phase 5 | main 173·37,451,392 checks·Legacy FC 326words, debug/default PASS — [결과](../../07_runs/npu_phase5_20261123_212129_569334Z/metrics.json) |
| 16번 Memory Fault | 1+74+16 cases·492,453 checks PASS — [결과](../../07_runs/npu_fault_priority_20261123_212116_288360Z/metrics.json) |
| Python unit | runner 15 + Golden 12 = 27 PASS — [runner](../../07_runs/npu_phase1_20261123_212012_145526Z/runner_unit.log), [Golden](../../07_runs/npu_phase1_20261123_212012_145526Z/golden_unit.log) |
| Legacy control_unit | 442,054 checks·errors=0 PASS — [결과](../../07_runs/control_unit_xsim_20261123_212031_995162Z/metrics.json) |
| Legacy memory_wrapper | 1,708,039 checks·errors=0 PASS — [결과](../../07_runs/memory_wrapper_xsim_20261123_212049_504762Z/metrics.json) |
| Legacy mac_array | 1,325,105 checks·errors=0 PASS — [결과](../../07_runs/mac_array_xsim_20261123_212303_073692Z/metrics.json) |
| Legacy accumulator_postprocess | 265,019 checks·errors=0 PASS — [결과](../../07_runs/accumulator_postprocess_xsim_20261123_212512_246215Z/metrics.json) |
| Legacy mlp_top | 913,476 checks·errors=0 PASS — [결과](../../07_runs/mlp_top_xsim_20261123_212542_040907Z/metrics.json) |

모두 실제 실행한 최종 결과이며 timeout/FAIL은 없다. Phase 6 TB/probe/runtime 사례 보강 이후 기존 회귀 소스는 변경하지 않았고, 모든 실행의 compile source snapshot/header와 현재 파일의 해시를 대조했다.

## 6. 실패 기록·근거·남은 범위

- [첫 컴파일](../../07_runs/npu_phase6_20261123_211850_397841Z/logs/debug/compile.log): rd 선언 전 참조 ERROR. 주소 선택 assign을 선언 뒤로 옮겨 수정했다.
- [첫 전체 PASS](../../07_runs/npu_phase6_20261123_212014_466052Z/metrics.json): 기능 PASS였지만 XSim 배열 인스턴스 2개 파형 경로가 기록되지 않는 경고가 있었다. TB 직접 physical A/B probe로 보완했다.
- [probe 보완 전체 PASS](../../07_runs/npu_phase6_20261123_212325_717048Z/metrics.json) 이후 실행 중 오류 사례를 추가했고, [단독 runtime PASS](../../07_runs/npu_phase6_20261123_212747_110022Z/metrics.json)와 최종 전체 실행을 수행했다. 이 과정에서 RTL은 추가 변경하지 않았다.

최종 판정 근거:

- [Phase 6 metrics](../../07_runs/npu_phase6_20261123_212833_429949Z/metrics.json), [소스/명령/data manifest](../../07_runs/npu_phase6_20261123_212833_429949Z/manifest.json).
- [주 suite scoreboard 로그](../../07_runs/npu_phase6_20261123_212833_429949Z/logs/65536/simulate.log), [64KiB PC Fault](../../07_runs/npu_phase6_20261123_212833_429949Z/logs/imem65536/simulate.log).
- [실제 관측 coverage](../../07_runs/npu_phase6_20261123_212833_429949Z/coverage.json), [coverage 감사 스크립트](../../07_runs/npu_phase6_20261123_212833_429949Z/coverage_audit.py).
- [Debug VCD](../../07_runs/npu_phase6_20261123_212833_429949Z/timing.vcd), [WDB](../../07_runs/npu_phase6_20261123_212833_429949Z/timing.wdb), [파형 대조](../../07_runs/npu_phase6_20261123_212833_429949Z/wave_audit.json), [감사 스크립트](../../07_runs/npu_phase6_20261123_212833_429949Z/wave_audit.py).
- [회귀·소스 보존·문서 완료 감사](../../07_runs/npu_phase6_20261123_212833_429949Z/completion.json).

승인된 Phase 6 범위에서 미해결 기능 결함이나 설계 결정 대기 항목은 없다. 구현/시뮬레이션 Gate PASS이며 모든 가능한 프로그램·내부 고장/ECC를 exhaustive하게 검증했다는 뜻은 아니다. 합성/FPGA/대규모 정확도는 미실행이다.

로그·HEX·빌드·파형은 기존 gitignore에 따라 로컬 보존한다. 커밋·Push는 수행하지 않는다. **Phase 6에서 중단하며 Phase 7/8은 사용자 별도 승인 전 시작하지 않는다.**
