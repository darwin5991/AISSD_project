# Phase 8 후속 — Legacy GEMM 실행 제어 재사용 및 Timing 개선

2026-11-24 KST. 기준 HEAD 1192f3f4f7b6c7e2b34e8b09ab4f0f885d5b65d5, 현재 브랜치 유지. **최종: G0~G5 기능 PASS / 합성·배치배선 완료 / 100MHz OOC Timing Gate FAIL.** 기존 20번 보고서는 변경하지 않았다.

## 1. 변경 및 보존

RTL 변경은 gemm_controller 한 파일이다. 기존 pipeline_control/read_issue_control/counter_en/pipeline_event_control/delay_line을 그대로 인스턴스화했다. 원본 CSR Snapshot·외부 포트와 ISA/CSR 번호는 유지했다.

설정/Region/전체 끝 주소/Runtime Bounds 및 공통 오류 Enable 차단, 중복 지연선을 제거했다. gemm_config.py에서 M=1, N=1~512, K>=8/4의 배수, 주소 역할/정렬/전체 깊이, Shift/ACT를 검사한다. K=4는 생성 전에 거부한다. 잘못된 GEMM 설정의 하드웨어 동작은 보장하지 않는다. 다른 명령어와 next-PC 오류 처리는 변경하지 않았다.

FSM은 control_state_t의 IDLE/PREP/RUN/DRAIN이다. Layer=0, Input 8bit/Group 7bit Counter, Layer Counter 없음. S 설정 저장/PREP, S+1 RUN, S+2 Read, 최종 Write 이후 Done/IDLE다. Input/Bias/Output은 Base+기존 Counter/지연 Group이고 Weight만 Read마다 증가하는 Cursor다. 그룹 공백에는 Cursor를 유지한다.

MAC/Accumulator/Postprocess, SRAM 7개, Owner MUX, BRAM 추론, Reset Wrapper, 1clk Read와 R→R+6, Timer 규칙은 보존했다. 새 RTL 포트/메모리/Pipeline Stage는 없다.

## 2. 실제 기능 Gate

| Gate | 실제 결과 | 로그 Run |
|---|---|---|
| G1 | 기본 K=8/N=4, 15,019 RTL checks PASS | npu_phase5_20261124_040545_577422Z |
| G2 | 4사례, 681,270 RTL checks/32,426 Python 비교 PASS | npu_phase5_20261124_041636_447456Z |
| G3 | debug 1 + 주 118 + 16MiB 1, 주 suite 37,172,572 RTL checks, FC 출력 326word PASS | npu_phase5_20261124_041846_604771Z |
| G4 | 원본 첫 200장 Golden 200/200, Label 200/200, 6,404,806cycles PASS | npu_phase7_20261124_042248_186193Z |
| G5 | Scalar/Python/Legacy 5종, 정상 Scalar/Block, GEMM→ARGMAX 양방향/연속 ARGMAX PASS | npu_gemm_reuse_regression_20261124_045004_381117Z |

G3는 K/N/방향/유효 경계 72개와 Shift/INT32 wrap, Snapshot, no-reset 연속 실행, Timer를 포함한다. 주 118개 중 정상 설정의 next-PC 거부 1개를 포함하며 제거한 GEMM Fault는 포함하지 않는다. G2의 A Word>=128 GEMM Write 70개는 기존 실제 요청 scoreboard가 주소/데이터/에지를 비교했다.

작은 실제 VCD 감사는 450 sampled edges/449 Cursor checks, 6 Read/3그룹/2공백에서 S+2/R+1/R+4/R+5/R+6와 Bias/Done을 확인했다. G3 Run의 wave_audit.json/timing.vcd/timing.wdb를 따른다.

Application은 모델 LOAD 5회+Input 200회, GEMM 600회, ARGMAX/Prediction 200회, 12,449명령, 중간 Layer STORE 0word, Timer/Waveform OFF다. Golden 불일치 0, 정상 END/Fault·timeout 없음. 기존 Phase 7 runner의 전체 Gate 표시는 PARTIAL이며 이번 요청의 G4 200장 PASS와 구분한다. Label 100%는 첫 200장 표본 실측이며 전체 MNIST 정확도가 아니다. Python Application/생성기 unit 19개도 PASS다.

## 3. G6 — 실제 FPGA 결과 및 최종 판정

FPGA는 xc7a100tcsg324-1, Clock은 10.000ns다. 기존 XDC 및 합성/Implementation Tcl의 내용과 설정을 보존했다. opt_design/place_design/phys_opt_design/route_design 모두 완료, 도구 return code=0이다. 실행기는 Timing 위반을 TIMING_FAIL/exit 1로 구분했다.

| 항목 | 이전 Post-route | 이번 Post-route | 변화/판정 |
|---|---:|---:|---|
| WNS | -7.202ns | **-4.097ns** | +3.105ns 개선, FAIL |
| TNS | -14911.218ns | **-5159.014ns** | 위반 감소, FAIL |
| WHS | +0.134ns | +0.111ns | 현재 OOC 모델 내 PASS |
| THS | 0ns | 0ns | 현재 OOC 모델 내 PASS |
| 최악 Data Path | 16.675ns | 13.808ns | -2.867ns |
| 최악 Logic Delay | 6.444ns | 4.462ns | 감소 |
| 최악 Routing Delay | 10.231ns | 9.345ns | 감소 |
| Logic Levels | 27 | 20 | CARRY4 16→6 |
| LUT | 6567 | **5768** | -799 |
| FF | 2443 | **2245** | -198 |
| DSP | 4 | **0** | GEMM 설정/주소 곱셈 제거 |
| RAMB36 / RAMB18 | 104 / 11 | **104 / 11** | 보존 |
| BRAM Tiles | 109.5/135 | 109.5/135 | 81.11%, 잔여 25.5 |
| LUTRAM | 0 | 0 | 보존 |

위 Logic/Route 비교는 각 설계의 최악 경로이며 서로 다른 경로를 비교한 것이다. 동일한 Weight Enable 경로의 전후 지연을 격리한 측정으로 해석하지 않는다.

### 합성·Memory Gate·기능 근거

- [새 합성 metrics](../../07_runs/npu_phase8_synth_20261124_055413_162591Z/metrics.json): LUT 5623, FF 2238, DSP 0, BRAM 104/11. 합성 추정 WNS -4.210ns는 Post-route와 구분한다.
- [새 Memory Gate 검토](../../07_runs/npu_phase8_synth_20261124_055413_162591Z/memory_gate_review.json): 7개 논리 깊이/Array Bits, Bank별 BRAM, primitive 115개의 DOA_REG/DOB_REG=0, LUTRAM 0, 보존 파일 대조 및 새 기능 근거를 직접 검토했다. 과거 PASS JSON을 복사하지 않았다.
- [Reset/Wrapper G1](../../07_runs/npu_phase8_verify_20261124_055536_804656Z/metrics.json): Reset/SRAM 17검사, Prediction 1/1 및 FC 163word PASS.
- [새 합성 Netlist G1](../../07_runs/npu_phase8_verify_20261124_055908_322128Z/metrics.json): Prediction 1/1, FC1/2/3 총 163word PASS.
- [최종 Implementation metrics](../../07_runs/npu_phase8_impl_20261124_060345_477678Z/metrics.json), [Setup](../../07_runs/npu_phase8_impl_20261124_060345_477678Z/internal_setup_paths.rpt), [Hold](../../07_runs/npu_phase8_impl_20261124_060345_477678Z/internal_hold_paths.rpt), [전체 로그](../../07_runs/npu_phase8_impl_20261124_060345_477678Z/process.log).

논리 SRAM 용량은 3,763,424bits이며 기존과 같다. Weight Bank마다 RAM_SP/26 RAMB36+2 RAMB18, A/B/Bias는 RAM_SDP/각 1 RAMB18이다. 작은 RAM의 물리 512word는 지원 주소를 늘리지 않는다. GEMM은 SW 배치 검사로 유효 접근을 보장하고 XFER/ARGMAX는 기존 HW 검사를 유지한다.

Routing은 routable 9090개 중 9090개 fully routed, routing error 0이다. 배선 완료와 Setup 통과를 구분한다.

### 새 Critical Path

Source: u_npu/u_instruction_controller/FSM_sequential_state_reg[2]/C

Destination: u_npu/u_instruction_controller/error_code_reg[1]/CE

Data Path 13.808ns = Logic 4.462ns + Route 9.345ns(반올림 오차 포함), 20 levels(CARRY4=6, LUT3=1, LUT4=2, LUT5=4, LUT6=7)다. error_code[2]/[3] CE도 같은 -4.097ns이며 후속 상위 경로는 GPR Write Enable이다.

실제 리포트는 FSM → rs2_read_address → GPR read data → 산술/next-PC 오류 논리 → commit/error CE를 통과한다. RTL 연결 근거는 instruction_controller.sv:174의 XFER_ARGS/일반 rs2 주소 선택, register_file.sv:12의 비동기 읽기, scalar_alu.sv:15~21의 분기/next-PC, instruction_controller.sv:103~110/183~200/236~268의 PC 검사·commit·오류 기록이다. 평탄화된 scalar_next_pc/gemm_next_pc_error Cell 이름을 원래 모듈 의미와 일대일로 단정하지 않으며, 공유·최적화된 각 LUT의 세부 역할은 추가 Netlist Query 없이는 추정 범위다.

기존 GEMM K → 그룹 곱셈 → 64bit 주소 → Runtime Bounds → Weight BRAM Enable 경로는 RTL에서 제거했다. 기존 GEMM N → 설정 곱셈/끝 주소 검증도 제거했고 DSP 0이 이를 뒷받침한다. 새 상위 10 Setup 경로는 Instruction Controller 쪽이다. Weight Enable은 Read Issue/active/reset/Owner 선택으로 구성되며 주소 산술/Bounds와 직렬 연결되지 않는다. 개별 Weight Enable 경로의 정량 보고는 별도 추출하지 않았다.

### 남은 한계와 다음 후보

100MHz Setup은 여전히 FAIL이다. 사용자 지시에 따라 이 결과 이후 RTL 수정·재합성·추가 구조 변경을 하지 않았다.

다음 별도 승인 후보는 Instruction Controller의 상태 의존 GPR 읽기 선택과 분기/next-PC/commit 경로 분석이다. 권장 순서는 실제 Cell 대응 확인 → Operand/선택된 next-PC의 순차 경계 또는 동등한 조합 구조 분리 검토다. 다른 명령어의 오류 처리, 선택된 target만 검사하는 규칙, Fault 시 GPR/PC 보존 및 Timer를 유지해야 한다. 이번에는 구현하지 않았다.

Clock 모델은 기존처럼 BUFG/MMCM/PLL 0개, no_input_delay 66/no_output_delay 102다. 내부 no_clock/unconstrained endpoint/loop는 0이며 Timing Exception은 없다. 보드 Clock Tree/I/O/실물 Fmax/Bitstream/Power/SDF는 검증하지 않았다.

DRC에는 CFGBVS-1과 REQP-1839/1840이 남았다. 각 BRAM 경고 20개는 보고 제한에 도달한 수치다. 기존 DSP Pipeline 경고는 DSP가 제거되어 사라졌다. SRAM/Reset 의미를 바꾸거나 경고를 waive하지 않았다.

## 4. 재현 명령

저장소 루트에서 conda aissd Python을 사용한다.

- python -X utf8 -B 90_scripts/npu/run_phase5.py --reuse-gate g2 --vivado-bin D:/AMDDesignTools/2025.2/Vivado/bin
- python -X utf8 -B 90_scripts/npu/run_phase5.py --reuse-gate g3 --vivado-bin D:/AMDDesignTools/2025.2/Vivado/bin
- python -X utf8 -B 90_scripts/npu/audit_gemm_reuse_wave.py 07_runs/npu_phase5_20261124_041846_604771Z
- python -X utf8 -B 90_scripts/npu/run_scenario.py --counts 200 --no-regressions --vivado-bin D:/AMDDesignTools/2025.2/Vivado/bin
- python -X utf8 -B 90_scripts/npu/run_gemm_reuse_regressions.py --vivado-bin D:/AMDDesignTools/2025.2/Vivado/bin

각 Run의 metrics/manifest/source_snapshot 및 data/log를 보존한다. G0 새 문서의 한글 stdin 인코딩 문제를 발견해 회귀 소스 불변 검사 종료 뒤 UTF-8로 수정했다. RTL/시뮬레이션 실패는 없었다. Commit/Push/10,000장 실행 없음.


추가 G6 실제 명령:

- python -X utf8 -B 90_scripts/npu/run_phase8_synth.py D:/AMDDesignTools/2025.2/Vivado/bin --fpga-wrapper
- python -X utf8 -B 90_scripts/npu/run_phase8_verify.py --counts 1 --vivado-bin D:/AMDDesignTools/2025.2/Vivado/bin
- python -X utf8 -B 90_scripts/npu/run_phase8_verify.py --synth-run 07_runs/npu_phase8_synth_20261124_055413_162591Z --counts 1 --vivado-bin D:/AMDDesignTools/2025.2/Vivado/bin
- 새 합성 보고서/기능/보존 파일을 검토해 해당 Run의 memory_gate_review.json을 기록한 뒤:
- python -X utf8 -B 90_scripts/npu/run_phase8_impl.py 07_runs/npu_phase8_synth_20261124_055413_162591Z D:/AMDDesignTools/2025.2/Vivado/bin

실제 실행 Python: C:/Users/darwi/.conda/envs/aissd/python.exe (3.11), Vivado 2025.2. Source List는 공통 run_phase1.py의 명시 목록을 FPGA 실행기도 읽는다. 합성/Implementation 중 RTL 변경 0개, Legacy 프로젝트 변경 0개다.

## 5. 변경 파일과 포트

| 구분 | 파일 | 변경 |
|---|---|---|
| 기존 RTL | [gemm_controller.sv](../../04_rtl/controller/gemm_controller.sv) | Legacy Pipeline/Counter, 최소 Adapter/FSM, Weight Cursor, GEMM 검사 제거 |
| 기존 Python | [run_phase1.py](../../90_scripts/npu/run_phase1.py) | Legacy 제어 RTL 5개 의존성 |
| 기존 Python | [assembler.py](../../90_scripts/npu/assembler.py) | Layer 전체 설정을 생성 전에 검사 |
| 기존 Python | [phase5_vectors.py](../../90_scripts/npu/phase5_vectors.py), [run_phase5.py](../../90_scripts/npu/run_phase5.py) | 정상 계약 선택 Gate, SW 설정 검사, Cursor 파형 |
| 기존 Python | [run_scenario.py](../../90_scripts/npu/run_scenario.py) | 새 검사 모듈의 Source Snapshot 포함 |
| 기존 FPGA 실행기 | [run_phase8_synth.py](../../90_scripts/npu/run_phase8_synth.py) | 새 합성 목적에 맞는 메타데이터; XDC/Tcl/설정은 동일 |
| 신규 Python | [gemm_config.py](../../90_scripts/npu/gemm_config.py) | 정상 GEMM 소프트웨어 검사 |
| 신규 Python | [test_gemm_config.py](../../90_scripts/npu/tests/test_gemm_config.py) | K=4/상위 비트/역할/깊이/Shift와 정상 생성 검사 |
| 신규 Python | [audit_gemm_reuse_wave.py](../../90_scripts/npu/audit_gemm_reuse_wave.py) | 실제 VCD의 Pipeline/Cursor 감사 |
| 신규 Python | [run_gemm_reuse_regressions.py](../../90_scripts/npu/run_gemm_reuse_regressions.py) | 승인된 선택 회귀와 로그 수집 |
| 문서 | 01/02/03/04/README, 신규 21번·22번 | 최신 GEMM 계약, 실행 구조, 검증 및 실측 결과 |

총 18개 변경/신규 파일이며 RTL 변경은 gemm_controller 한 파일이다. 새 외부 포트·CSR·Opcode·GPR·메모리 프로토콜은 없다. 내부에 Base/파생 설정/Weight Cursor 레지스터와 기존 Pipeline/Counter 연결 신호를 사용했다.

기존 MAC/Accumulator/Postprocess, Legacy 제어 모듈, npu_memory_wrapper/sram_port_mux/single_port_bram, Reset Wrapper, gemm_engine/npu_top/instruction_controller는 변경하지 않았다. 기존 20번 보고서와 모델/Golden/Legacy TB도 보존했다.

## 6. 근거 색인과 종료 상태

- [G1](../../07_runs/npu_phase5_20261124_040545_577422Z/metrics.json)
- [G2](../../07_runs/npu_phase5_20261124_041636_447456Z/metrics.json)
- [G3](../../07_runs/npu_phase5_20261124_041846_604771Z/metrics.json), [실제 파형 감사](../../07_runs/npu_phase5_20261124_041846_604771Z/wave_audit.json)
- [G4 200장](../../07_runs/npu_phase7_20261124_042248_186193Z/metrics.json), [Python 19개 로그](../../07_runs/npu_phase7_20261124_042248_186193Z/application_unit.log)
- [G5 선택 회귀](../../07_runs/npu_gemm_reuse_regression_20261124_045004_381117Z/metrics.json)
- [완료 감사](../../07_runs/npu_phase8_impl_20261124_060345_477678Z/completion_audit.json)

기능·BRAM·도구 실행 완료와 100MHz Timing FAIL을 구분해 보고한다. 검증되지 않은 항목을 PASS로 표시하지 않았다. 요청된 구현/측정 범위 종료, 추가 설계 변경 승인 대기. 현재 Branch/HEAD 유지, Commit/Push와 10,000장 실행 없음.
