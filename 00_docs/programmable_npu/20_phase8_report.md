# Phase 8 — Direct RTL Synthesis & Implementation 보고서

작성: 2026-11-24 KST. **최종 판정: Timing Gate FAIL / 후속 승인 대기.**

BRAM Inference/용량, Reset Wrapper 기능과 요청된 회귀는 PASS다. Synthesis 및 Opt/Place/PhysOpt/Route 명령도 완료했다. 100MHz OOC 결과는 **WNS -7.202ns, TNS -14911.218ns, WHS +0.134ns, THS 0.000ns**로 Setup 미충족이다. 도구 실행 완료와 Timing 통과를 구분하며 Phase 8 전체 PASS로 표시하지 않는다. 클럭/예외 완화와 기존 RTL 수정 없이 중단한다.

## 1. 기준선 및 환경

- 시작 HEAD/Phase 7 보존 커밋: 94bb214843d154e5ab830986b1b3c1e7801a14b9. 시작 작업 트리 clean.
- 새 브랜치: phase8/direct-bram-inference-20261124. 기존 브랜치 덮어쓰기 및 Commit/Push 없음.
- Target: xc7a100tcsg324-1 / Artix-7 / CSG324 / speed -1, BRAM 135×36Kb.
- Vivado 2025.2 win64 Build 6299465, D:/AMDDesignTools/2025.2/Vivado/bin.
- conda aissd Python 3.11.16, PyTorch 2.11.0+cu128 / torchvision 0.26.0+cu128 / numpy 2.4.6 import 확인. 패키지 설치·모델 변경 없음.
- 기존 Legacy XPR: 99_build/vivado_mlp_top_ooc/mlp_top_ooc.xpr. 기존 XPR/XDC/RTL은 SHA256 보호 및 불변 확인.
- 첫 합성 Top은 **npu_top 그대로**, Reset 적용 후 최종 Top은 **npu_fpga_top → u_npu:npu_top**이다. Legacy mlp_top을 새 합성 대상으로 선택하지 않았다.
- create_project -in_memory 및 Non-Project Tcl Flow로 실행했다. 기존 프로젝트 수정, BMG IP 생성, .xci 추가 없음.

Phase 7 전체 G0~G4 기준선 [npu_phase7_20261123_220156_054531Z](../../07_runs/npu_phase7_20261123_220156_054531Z/metrics.json)를 보존했다. 이번 Application 재실행은 G0/G1/G4이며, 5/100장은 이전 PASS를 보존하고 10,000장은 보류했다.

## 2. 신규·수정 파일 및 포트

| 신규 파일 | 역할 |
|---|---|
| 06_fpga/rtl/npu_reset_sync.sv | ASYNC_REG 2FF, Async Assert / Sync Deassert, SRL 변환 방지 |
| 06_fpga/rtl/npu_fpga_top.sv | 기존 npu_top 인스턴스, Reset 전달과 Reset 중 start 차단 |
| 06_fpga/constraints/npu_direct_ooc.xdc | clk의 10.000ns create_clock 하나 |
| 06_fpga/tcl/npu_direct_synth.tcl | OOC 합성, DCP/Netlist, 은행별 BRAM/자원/Timing/DRC |
| 06_fpga/tcl/npu_direct_impl.tcl | 검토된 DCP의 Opt/Place/PhysOpt/Route 및 보고 |
| 90_scripts/npu/run_phase8_synth.py | 명시적 RTL 목록, 원본 Hash 보호, 소스 Snapshot/Manifest |
| 90_scripts/npu/run_phase8_impl.py | Memory Gate 선행 확인, Checkpoint Hash, 실제 Timing 판정 |
| 90_scripts/npu/run_phase8_verify.py | Reset unit / Wrapper RTL / 합성 Netlist Application 실행 |
| 90_scripts/npu/run_phase8_regressions.py | 기존 실행기 호출 및 회귀 결과 수집 |
| 05_tb/npu/tb_npu_reset_sync.sv | Reset/SRAM 경계 검사 |
| 05_tb/npu/tb_npu_fpga_application.sv | 포트 기반 IMEM/DMEM 모델과 Prediction/Layer Scoreboard, RTL/Netlist 공용 |

수정 문서는 Programmable NPU README, 02 Architecture, 03 Implementation Plan, 04 Verification Plan 및 06_fpga/README다. 본 20번 보고서를 추가했다. 01 ISA 기능 계약 변경은 없다.

**기존 04_rtl 전체, 기존 TB/Python/Golden/모델, SRAM/MUX/Decoder, MAC/Accumulator/Postprocess, ISA/CSR·외부 메모리 프로토콜을 변경하지 않았다.** 회귀 종료 시 보호 소스 146개 변경 0개였다. 현재 문서 수정은 해당 보호 검사 이후 수행했다.

FPGA Wrapper의 외부 포트는 clk/rst_n/start, busy/done/fault, imem_en/addr/rdata, dmem_en/we/addr/wdata/rdata로 기존 npu_top과 같다. 외부 저장소·Ready/Valid·새 명령·CSR/GPR 추가 없음.

## 3. SRAM별 실제 BRAM 추론

| 메모리 | Width | 논리 Depth(words) | 유효 Word 주소 폭 | 논리 Bits | RAMB36 | RAMB18 |
|---|---:|---:|---:|---:|---:|---:|
| Buffer A | 32 | 196 | 8 | 6,272 | 0 | 1 |
| Buffer B | 32 | 128 | 7 | 4,096 | 0 | 1 |
| Weight 0 | 32 | 29,280 | 15 | 936,960 | 26 | 2 |
| Weight 1 | 32 | 29,280 | 15 | 936,960 | 26 | 2 |
| Weight 2 | 32 | 29,280 | 15 | 936,960 | 26 | 2 |
| Weight 3 | 32 | 29,280 | 15 | 936,960 | 26 | 2 |
| Bias | 32 | 163 | 8 | 5,216 | 0 | 1 |
| 합계 | | 117,607 | | 3,763,424 | 104 | 11 |

논리 용량은 **470,428bytes**다. 실제 할당은 **109.5×36Kb = 4,036,608bits(504,576bytes)**로, FPGA 135타일 중 **81.11%**, 잔여 **25.5타일(940,032bits)**이다. 논리/물리 차이 273,184bits는 구성·패딩 비용이다. 주변 시스템이 추가되면 잔여 자원을 별도로 계산해야 한다.

- Weight 각 Bank: 논리 29,280×32, 보고서 RAM_SP, 26×RAMB36+2×RAMB18 = 27타일.
- A/B/Bias: 각 1×RAMB18. 물리 표시 형상은 **RAM_SDP / 512×32**, 논리 Array Size는 각각 196×32/128×32/163×32로 일치한다.
- 물리 RAM_SDP가 논리 듀얼 포트 추가를 뜻하지 않는다. 기존 en/we의 Read/Write 배타성 및 Decoder/Bounds가 유지되어 패딩 Word를 노출하지 않는다.
- primitive 115개의 DOA_REG/DOB_REG는 모두 0이다. WRITE_MODE에는 READ_FIRST/WRITE_FIRST 조합도 있으므로 일괄 NO_CHANGE라고 보고하지 않는다. 기존 Read/Write gating과 외부 출력 Hold 계약을 기준으로 확인했다.
- **LUT as Distributed RAM 0**. LUT as Memory 10개는 SRL 10개로, SRAM의 LUTRAM fallback이 아니다.
- 은행별 FF는 작은 메모리 1개/Weight 6개 수준의 제어·출력 Mask이며 대규모 FF 배열 대체 없음.
- 요청 에지 R의 동기 Read 및 다음 에지 소비, 상승 에지 Write, Write/EN=0 출력 Hold, 비동기 출력 Zero Reset과 내용 유지 계약을 보존한다. 추가 Output Register/Read Latency 없음.
- 합성 입력에서 TB 및 외부 IMEM/DMEM initial/readmemh 저장소를 제외했다. 16MiB DMEM은 호스트 시뮬레이션 모델이며 위 BRAM에 포함되지 않는다.

근거: [RAM 상세](../../07_runs/npu_phase8_synth_20261123_230658_788545Z/ram_utilization.rpt), [primitive 속성](../../07_runs/npu_phase8_synth_20261123_230658_788545Z/bram_cells.tsv), [은행별 집계](../../07_runs/npu_phase8_synth_20261123_230658_788545Z/banks.tsv), [Memory Gate PASS 검토](../../07_runs/npu_phase8_synth_20261123_230658_788545Z/memory_gate_review.json).

## 4. 합성 및 자원

| 항목 | 무수정 npu_top | Reset Wrapper 합성 | 최종 배치·배선 |
|---|---:|---:|---:|
| LUT | 6,424 | 6,420 | 6,567 |
| FF | 2,422 | 2,424 | 2,443 |
| DSP | 4 | 4 | 4 |
| RAMB36 / RAMB18 | 104 / 11 | 104 / 11 | 104 / 11 |
| BRAM 타일 | 109.5 | 109.5 | 109.5 |
| Distributed RAM | 0 | 0 | 0 |
| 도구 실행 | COMPLETED | COMPLETED | COMPLETED |

첫 합성 [npu_phase8_synth_20261123_225336_491606Z](../../07_runs/npu_phase8_synth_20261123_225336_491606Z/metrics.json)는 124.015s, Wrapper 합성 [npu_phase8_synth_20261123_230658_788545Z](../../07_runs/npu_phase8_synth_20261123_230658_788545Z/metrics.json)는 120.407s, Implementation [npu_phase8_impl_20261123_231841_766407Z](../../07_runs/npu_phase8_impl_20261123_231841_766407Z/metrics.json)는 233.953s다. Python 실행기가 도구 실행/보고 단계를 측정한 경과 시간이다.

첫 합성의 synthesis_status.txt에 top=design_1이 기록된 것은 Vivado current_design NAME을 쓴 메타데이터 실수다. 실제 보고서 Design/Netlist/Manifest의 Top은 npu_top이다. 후속 Tcl은 명시적 Top 인자를 기록하도록 보완했다. 기존 RTL 변경은 없다.

합성 Setup 추정치 WNS -11.154ns도 실패로 기록했다. 실제 배선 지연과 구분하기 위해 클럭을 바꾸지 않고 Placement/Route를 진행했다.

## 5. Placement / Routing / Timing

[단계 로그](../../07_runs/npu_phase8_impl_20261123_231841_766407Z/stages.txt)에 opt_design/place_design/phys_opt_design/route_design 완료가 기록돼 있다. 도구 return code는 0이며, Python 실행기는 실제 Setup 미충족을 TIMING_FAIL/exit 1로 반환했다. Bitstream 없음.

| 항목 | 실제 OOC Post-route | 목표 | 판정 |
|---|---:|---:|---|
| Clock | 10.000ns | 100MHz | 유지 |
| WNS | -7.202ns | ≥0 | FAIL |
| TNS | -14911.218ns | 0 | FAIL |
| WHS | +0.134ns | ≥0 | 모델 내 PASS |
| THS | 0.000ns | 0 | 모델 내 PASS |

Worst 내부 Setup 경로의 실제 리포트 발췌:

~~~text
Slack (VIOLATED) :        -7.202ns  (required time - arrival time)
  Source:                 u_npu/u_instruction_controller/gemm_config_reg[6][5]_replica_2/C
                            (rising edge-triggered cell FDCE clocked by npu_clk  {rise@0.000ns fall@5.000ns period=10.000ns})
  Destination:            u_npu/u_memory/g_banks[2].u_ram/memory_reg__24/ENBWREN
                            (rising edge-triggered cell RAMB36E1 clocked by npu_clk  {rise@0.000ns fall@5.000ns period=10.000ns})
  Path Group:             npu_clk
  Path Type:              Setup (Max at Slow Process Corner)
  Requirement:            10.000ns  (npu_clk rise@10.000ns - npu_clk rise@0.000ns)
  Data Path Delay:        16.675ns  (logic 6.444ns (38.645%)  route 10.231ns (61.355%))
  Logic Levels:           27  (CARRY4=16 LUT3=2 LUT4=2 LUT5=2 LUT6=5)
  Clock Path Skew:        -0.049ns (DCD - SCD + CPR)
    Destination Clock Delay (DCD):    0.924ns = ( 10.924 - 10.000 )
    Source Clock Delay      (SCD):    0.973ns
    Clock Pessimism Removal (CPR):    0.000ns
~~~

Worst 내부 Hold 경로:

~~~text
Slack (MET) :             0.134ns  (arrival time - required time)
  Source:                 u_npu/u_instruction_controller/u_csr/settings_reg[7][11]/C
                            (rising edge-triggered cell FDCE clocked by npu_clk  {rise@0.000ns fall@5.000ns period=10.000ns})
  Destination:            u_npu/u_instruction_controller/gemm_config_reg[7][11]/D
                            (rising edge-triggered cell FDCE clocked by npu_clk  {rise@0.000ns fall@5.000ns period=10.000ns})
  Path Group:             npu_clk
  Path Type:              Hold (Min at Fast Process Corner)
  Requirement:            0.000ns  (npu_clk rise@0.000ns - npu_clk rise@0.000ns)
  Data Path Delay:        0.240ns  (logic 0.141ns (58.692%)  route 0.099ns (41.308%))
  Logic Levels:           0
  Clock Path Skew:        0.022ns (DCD - SCD - CPR)
    Destination Clock Delay (DCD):    0.432ns
    Source Clock Delay      (SCD):    0.410ns
    Clock Pessimism Removal (CPR):    -0.000ns
~~~

합성 추정 최악 경로는 GEMM N → ceil(N/4)·K 곱셈/범위·오류 병합 → error_code CE였고 DSP cascade를 포함했다. 실제 배치·배선 최악 경로는 **GEMM K Snapshot bit → 주소/범위·제어 조합 논리 → SRAM 접근 선택 → Weight 0 BRAM ENBWREN**이다. 27 logic levels(CARRY4 16개 등), Data Delay 16.675ns 중 Logic 6.444ns / Route 10.231ns, Skew -0.049ns다. 실제 RTL의 config_words[6]는 input_words에도 연결되고, 실행 중 address_full의 Weight 주소 계산 및 모든 Bank의 runtime_error 검사 결과가 같은 사이클 ram_en을 제어한다. 따라서 수락 시 config_error 경로뿐 아니라 실행 중 주소 산술/Bounds→Enable 경로도 후속 분석 대상이다. 이 경로는 MAC 산술 R→R+6 파이프라인과 구분한다. 평탄화된 모든 중간 Net의 의미를 이름만으로 확정하지 않으며 실제 cell/pin 경로를 근거로 삼는다.

Routing 보고:

~~~text
# of logical nets.......................... :       14809 :
# of nets not needing routing.......... :        4440 :
# of implicitly routed ports....... :         137 :
# of routable nets..................... :       10369 :
# of fully routed nets............. :       10369 :
# of nets with routing errors.......... :           0 :
~~~

10,369개 routable net은 모두 fully routed, routing error 0이다. 이는 OOC의 경계/클럭 모델 범위에서의 완료이며 보드 전체 배선 완료는 아니다.

상세: [Timing 요약](../../07_runs/npu_phase8_impl_20261123_231841_766407Z/timing_summary.rpt), [내부 Setup](../../07_runs/npu_phase8_impl_20261123_231841_766407Z/internal_setup_paths.rpt), [내부 Hold](../../07_runs/npu_phase8_impl_20261123_231841_766407Z/internal_hold_paths.rpt), [Routing](../../07_runs/npu_phase8_impl_20261123_231841_766407Z/route_status.rpt), [Routed DCP](../../07_runs/npu_phase8_impl_20261123_231841_766407Z/routed.dcp).

## 6. OOC 제약·Clock 및 DRC 한계

XDC는 create_clock -name npu_clk -period 10.000 [get_ports clk] 하나다. 보드 핀/전압/IOSTANDARD/Input·Output Delay/가상 I/O 위치/HD.PARTPIN_LOCS/False·Multicycle Path를 임의로 정하지 않았다. exceptions.rpt도 No valid timing exceptions found다.

**Clock 모델의 실제 한계:** 이 OOC Netlist에는 BUFG/MMCM/PLL이 0개이며 clock_utilization의 Global Clock Resource 목록도 비어 있다. Worst Path의 clk net은 unset 상태이고 Source/Destination clock delay는 0.973/0.924ns의 도구 모델이다. 따라서 위 Hold PASS 및 Skew는 실제 보드의 전역 Clock Tree 구축/배선 완료 증명이 아니다. 외부 Parent/보드 Wrapper의 Clock Source/Buffer 통합은 미구현이다. 이를 숨기기 위한 Clock LOC/지연/예외는 추가하지 않았다. 데이터 경로의 큰 Setup 위반을 확인한 상태에서 이 모델을 최종 실물 Fmax 보장으로 해석하지 않는다.

check_timing 집계:

~~~text
1. checking no_clock (0)
2. checking constant_clock (0)
3. checking pulse_width_clock (0)
4. checking unconstrained_internal_endpoints (0)
5. checking no_input_delay (66)
6. checking no_output_delay (102)
7. checking multiple_clock (0)
8. checking generated_clocks (0)
9. checking loops (0)
10. checking partial_input_delay (0)
11. checking partial_output_delay (0)
12. checking latch_loops (0)
1. checking no_clock (0)
2. checking constant_clock (0)
3. checking pulse_width_clock (0)
4. checking unconstrained_internal_endpoints (0)
5. checking no_input_delay (66)
6. checking no_output_delay (102)
7. checking multiple_clock (0)
8. checking generated_clocks (0)
9. checking loops (0)
10. checking partial_input_delay (0)
11. checking partial_output_delay (0)
12. checking latch_loops (0)
~~~

내부 no_clock/unconstrained endpoint는 0이지만 입출력 경계는 no_input_delay=66/no_output_delay=102다. Route 35-198의 HD.PARTPIN_LOCS 미지정 경고도 있어 경계 partial routing/Timing은 미검증이다. OOC 평가와 외부 메모리/보드 Timing 보장을 분리한다. [Clock 자원](../../07_runs/npu_phase8_impl_20261123_231841_766407Z/clock_utilization.rpt), [제약 점검](../../07_runs/npu_phase8_impl_20261123_231841_766407Z/check_timing.rpt), [예외](../../07_runs/npu_phase8_impl_20261123_231841_766407Z/exceptions.rpt) 참조.

최종 DRC 집계:

~~~text
| Rule      | Severity | Description                                         | Checks |
| CFGBVS-1  | Warning  | Missing CFGBVS and CONFIG_VOLTAGE Design Properties | 1      |
| CHECK-3   | Warning  | Report rule limit reached                           | 2      |
| DPIP-1    | Warning  | Input pipelining                                    | 8      |
| DPOP-1    | Warning  | PREG Output pipelining                              | 4      |
| DPOP-2    | Warning  | MREG Output pipelining                              | 4      |
| REQP-1839 | Warning  | RAMB36 async control check                          | 20     |
| REQP-1840 | Warning  | RAMB18 async control check                          | 20     |
~~~

주요 경고는 REQP-1839/1840(BRAM async controls), DPIP/DPOP(비파이프라인 DSP), CFGBVS(보드 설정 미정)다. Synth 8-3332의 미사용 FF 제거, optional output register merge 관련 정보도 보존했다. 반복 메시지 100회 및 DRC 규칙 20개 제한에 도달한 수를 전체 발생 건수로 간주하지 않는다. 경고를 waive/강등하지 않았다. [DRC](../../07_runs/npu_phase8_impl_20261123_231841_766407Z/drc.rpt), [Methodology](../../07_runs/npu_phase8_impl_20261123_231841_766407Z/methodology.rpt), [전체 실행 로그](../../07_runs/npu_phase8_impl_20261123_231841_766407Z/process.log) 참조.

## 7. Reset 및 기능 검증

Reset Synchronizer는 Async Assert / 2edge Sync Release다. core_rst_n은 두 번째 상승 에지 직후 올라가므로 start는 그 이후 코어가 수락 가능한 상승 에지에 제공한다. Reset 중 start는 차단하며 조기 pulse를 저장/재생하는 기능은 없다. 기존 SRAM Reset은 출력만 0으로 만들고 내용을 지우지 않는다.

신규 단위 검사 **17/17 PASS**: 비동기 Assert/EN=0 출력 Clear, 두 에지 Release, Reset 중 쓰기 차단, 내용 유지, 해제 후 첫 Read, Write/Disable 시 출력 Hold. 디지털 검증은 metastability나 클럭 인접 비동기 전이의 아날로그 안전성을 증명하지 않으며 위 BRAM 경고도 남는다.

| 실행 | 실제 결과 | 근거 |
|---|---|---|
| 합성 npu_top Netlist G1 | Prediction 1/1 + FC1/2/3 합계 163word PASS | [npu_phase8_verify_20261123_225919_642678Z](../../07_runs/npu_phase8_verify_20261123_225919_642678Z/metrics.json) |
| Reset unit + FPGA Wrapper RTL G1/G4 | 17검사, Prediction 1/1·200/200 PASS | [npu_phase8_verify_20261123_230700_330640Z](../../07_runs/npu_phase8_verify_20261123_230700_330640Z/metrics.json) |
| 기존 회귀 | 모두 PASS | [npu_phase8_regression_20261123_230830_395556Z](../../07_runs/npu_phase8_regression_20261123_230830_395556Z/metrics.json) |

Wrapper G4: Load=205(모델 5+Input 200), GEMM=600, ARGMAX=200, Prediction=200, cycles=6,404,806으로 Phase 7과 일치한다. 기존 Application 재실행도 Golden 불일치 0/Label 200/200(100%)다. 이는 **원본 첫 200장 표본 실측**이며 전체 MNIST 정확도가 아니다. G1만 Layer STORE(163word)를 사용하고 G4는 Timer/Waveform/중간 Layer STORE OFF다.

200장 Netlist, Post-route/SDF 시뮬레이션과 신규 파형 저장은 수행하지 않았다. 기존 Phase 5/6 R→R+6/R→R+1 파형 근거와 이번 기능 로그를 구분한다.

## 8. 기존 회귀 결과

| 기존 실행기 | 결과 | 실제 근거 |
|---|---|---|
| phase1 | PASS | [metrics](../../07_runs/npu_phase1_20261123_230830_623848Z/metrics.json) |
| phase2 | PASS | [metrics](../../07_runs/npu_phase2_20261123_231417_937259Z/metrics.json) |
| phase3 | PASS | [metrics](../../07_runs/npu_phase3_20261123_231443_385664Z/metrics.json) |
| phase4 | PASS | [metrics](../../07_runs/npu_phase4_20261123_231516_637579Z/metrics.json) |
| phase5 | PASS | [metrics](../../07_runs/npu_phase5_20261123_231550_467594Z/metrics.json) |
| phase6 | PASS | [metrics](../../07_runs/npu_phase6_20261123_231650_217984Z/metrics.json) |
| fault_priority | PASS | [metrics](../../07_runs/npu_fault_priority_20261123_231722_776716Z/metrics.json) |
| scenario | PASS | [metrics](../../07_runs/npu_phase7_20261123_231746_209167Z/metrics.json) |

phase1 --legacy 안에서 runner/golden Python unit와 control_unit/memory_wrapper/mac_array/accumulator_postprocess/mlp_top 5종을 전부 실행했다. 기존 Application 실행은 G0(unit 9개 포함)와 G1/G4를 선택한 부분 실행이므로 phase7_gate=PARTIAL을 유지했다. 이전 전체 G0~G4 PASS 기준선을 새 전체 실행으로 둔갑시키지 않았다.

기존 Application 재실행 G4는 131.437s, 0.1s 표본의 Python+시뮬레이터 프로세스 트리 RSS 최대 908,906,496bytes다. 호스트 전체/동시 Vivado 전체의 절대 최대 메모리가 아니다. FPGA Wrapper G4 XSim kernel 로그는 별도로 보존했다.

## 9. 실패·수정 및 검토 이력

1. 최초 Reset 단위 [npu_phase8_verify_20261123_230405_216684Z](../../07_runs/npu_phase8_verify_20261123_230405_216684Z/metrics.json)는 timescale 없는 재사용 RTL과 TB 조합으로 XSIM 43-4099 elaboration 실패였다. 신규 실행기 xelab에 -timescale 1ns/1ps를 지정해 후속 실행 PASS. 기존 RTL/TB 수정 없음. 실패 로그 보존.
2. 초기 Memory Gate 검토는 모든 은행에 RAM_SP/논리와 같은 표시 Depth를 요구해 assertion이 실패했다. 작은 RAM의 RAM_SDP/512word 물리 구성과 논리 Array Bits/Bounds를 구분하도록 검토를 정정했다. SRAM/주소 범위 변경은 없으며 memory_gate_review.json에 기록했다.
3. 첫 합성 top=design_1 메타데이터는 4절과 같이 보완했다.
4. 최종 Timing FAIL을 숨기거나 Clock/예외/설계 변경으로 우회하지 않았다.

## 10. 실제 재현 명령 및 산출물

저장소 루트 PowerShell:

~~~powershell
$phase8Python = 'C:/Users/darwi/.conda/envs/aissd/python.exe'
$phase8Vivado = 'D:/AMDDesignTools/2025.2/Vivado/bin'
& $phase8Python -X utf8 -B 90_scripts/npu/run_phase8_synth.py $phase8Vivado
& $phase8Python -X utf8 -B 90_scripts/npu/run_phase8_synth.py $phase8Vivado --fpga-wrapper
& $phase8Python -X utf8 -B 90_scripts/npu/run_phase8_verify.py --vivado-bin $phase8Vivado --counts 1 200
& $phase8Python -X utf8 -B 90_scripts/npu/run_phase8_verify.py --vivado-bin $phase8Vivado --synth-run 07_runs/npu_phase8_synth_20261123_225336_491606Z --counts 1
& $phase8Python -X utf8 -B 90_scripts/npu/run_phase8_regressions.py
& $phase8Python -X utf8 -B 90_scripts/npu/run_phase8_impl.py 07_runs/npu_phase8_synth_20261123_230658_788545Z $phase8Vivado
~~~

합성 실행기는 자동 매핑 검사 뒤에도 SYNTHESIS_REVIEW_REQUIRED/MAPPED_REVIEW_REQUIRED를 유지한다. 실제 memory_gate_review.json PASS와 기능 근거를 확인한 뒤 Implementation을 시작했다. 새 합성 Run도 새로 검토해야 하며 기존 PASS JSON을 무조건 복사하면 안 된다.

각 Run의 manifest.json에 실제 argv/cwd, 실행 소스 Snapshot/Hash, RTL·Legacy 프로젝트 보호 Hash가 있다. DCP/HEX/log/build는 07_runs/99_build에 분리해 Git에 추가하지 않았다. source Hash/최종 범위 점검은 [완료 Audit](../../07_runs/npu_phase8_impl_20261123_231841_766407Z/completion_audit.json)에 기록한다.

## 11. 남은 문제 및 승인 선택지

현재 Timing FAIL이므로 다음 설계 변경은 별도 승인 대상이다.

- **권장:** 수락 시 config_error와 실행 중 address_full/runtime_error→ram_en 두 경로를 나눠 분석하고, 검증/제어 FSM과 검증 후 Word Base/Stride 저장·주소 계산 구조를 검토한다. 수락 검증만 여러 사이클로 나눠도 실행 중 Bounds→Enable 병목은 남을 수 있다. Snapshot 원본 32bit/넓은 중간값, Alignment→Region→Bounds→Configuration 및 next-PC 우선순위, 검증 전 Start/메모리 접근 차단을 유지해야 한다. Timer에서 검증 구간을 계속 제외하고 MAC R→R+6/SRAM Latency는 보존한다. Controller·Engine 허가/owner 경로와 Fault/Timer TB를 함께 검증해야 한다.
- 대안은 산술/선택 논리의 동등한 조합식 최적화다. 상위 비트를 잘라 검사하거나 Bounds 이전에 Configuration으로 탈락시키는 방법은 기존 계약과 충돌한다. 등가 검증과 실제 재배치·배선이 필요하다.
- OOC Parent Clock Source/Buffer 모델을 명시하거나 별도 보드 Wrapper를 연결하는 후속 검증이 필요하다. 임의 핀/Clock LOC/예외로 처리하지 않았다.
- BRAM 비동기 EN/WE 경고의 물리 적합성은 별도 검토가 남는다. SRAM Reset/쓰기 의미 변경은 적용하지 않았다.
- 외부 메모리/핀/전압/Bitstream/실물 FPGA, Power 추정, SDF 및 10,000장은 이번 결과에 포함하지 않는다.

Commit/Push 없음. 후속 설계 수정 및 다음 Phase 작업을 진행하지 않는다.
