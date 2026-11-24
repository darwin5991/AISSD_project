# Programmable NPU v1.0 — Codex 구현 계획

> 2026-11-24 결정 우선순위: [07_design_decisions_phase0.md](07_design_decisions_phase0.md)의 D-01~D-04와 후속 사용자 확정을 우선 적용한다.

**목표:** 기존 고정 3-Layer INT8 MLP RTL을 보존·재활용하면서 ISA v1.0에 따른 Programmable NPU Top, Python 통합 테스트 환경, FPGA 구현 경로를 단계적으로 완성. **현재 진행(Phase 5/6 이력):** Phase 4를 6efeec4에 보존한 뒤 사용자 승인에 따라 Phase 5 GEMM 구현·검증을 완료했다. [Phase 5 결과](15_phase5_report.md)의 Gate PASS와 정식 지원 하한 K=8 확정을 기록한다. Phase 6도 후속 승인에 따라 독립 ARGMAX 구현·검증 Gate PASS다. [18번 결과](18_phase6_report.md)를 따르며 당시 후속 Phase는 별도 승인 대상이었고, 현재 상태는 아래 후속 요약을 따른다.

**현재 후속 상태:** Phase 7은 94bb214에 보존했다. 새 Phase 8 브랜치에서 Direct BRAM 합성·배치배선과 기능 회귀를 완료했으며 Timing Gate는 FAIL이다. 아래 Phase 8과 20번 보고서를 따른다. 10,000장은 보류한다.

## 0. Codex에 전달할 공통 지시

1. `01_isa_spec.md`, `02_architecture.md`, `04_verification_plan.md` 및 현재 `00_docs/architecture.md`, `00_docs/mac_input_pipeline.md`를 순서대로 읽는다. 새 ISA 동작은 새 문서가 우선이고, 기존 MAC 및 Timing은 기존 소스 명세를 준수.
2. Git에서 작업용 브랜치를 만들고 기존 커밋/테스트를 보존. 원본 `mlp_top.sv`, `control_unit.sv`, `memory_wrapper.sv`를 한꺼번에 갈아엎지 말 것. 새 `npu_top.sv`, `gemm_controller.sv`, 신규 `npu_memory_wrapper.sv` 등으로 단계적 교체하는 방식을 우선.
3. **매 단계 첫 작업:** 실 코드와 명세를 비교해 필요한 포트/파일 목록 작성 → 최소 구현 → 테스트 실행 → 변경 diff/검증 결과 요약. 단계 완료 조건을 통과하지 못하면 다음 단계로 진행하지 않는다.
4. MAC array, `accumulator_postprocess` 연산/latency, signed8 Packing/Shift/Saturate 규칙, Input/Weight 3-stage pipeline은 비요청 수정 금지.
5. GPR 8개, 32bit ISA, CSR 번호, Opcode/funct 필드, Error Code, 외부 메모리 1clk, Timer Engine-only와 SRAM 1clk는 변경하지 않는다.
6. 모호한 경계 동작을 발견한 경우 **의사결정 항목과 구현 가능한 옵션을 보고**하고, 미승인 새 기능·성능 최적화·ISA 확장은 진행하지 않는다.
7. 지원하지 않는 Reserved Register/CSR/Opcode/Memory Access는 무시하거나 0으로 읽지 말고 명세상의 Fault로 처리.
8. 기능별 Pass/Fail 결과를 `07_runs/` 기록으로 남기되, 빌드 산출물과 대용량 메모리 HEX는 기존 `.gitignore`/저장소 정책에 맞게 관리.


## Phase 0 — 기존 RTL 기준선과 검증 방법 확인

**읽을 파일:**

- `04_rtl/controller/mlp_top.sv`, `control_unit.sv`, `control_fsm.sv`, `read_issue_control.sv`, `pipeline_control.sv`, `address_generator.sv`, `layer_config_lut.sv`
- `04_rtl/memory/memory_wrapper.sv`, `memory_port_mux.sv`, `buffer_router.sv`, `single_port_bram.sv`
- `04_rtl/mac_array/*`, `04_rtl/accumulator_postprocess/*`
- `05_tb/controller/tb_mlp_top.sv`, `mlp_top_tester.sv`, `90_scripts/sim_targets.json`

**수행:** 지금 커밋의 TB, Simulation Script, MAC 3-stage 데이터 포맷·클럭 계약을 점검. 이미 PASS했던 과거 검증과 최신 소스의 검증 상태를 구분하고, 최신 소스로 재실행 가능한 범위만 실행. 실패 시 기준선 실패와 신규 코드 실패를 구분할 기록 생성.

**완료 조건:** 재현 가능한 기존 시뮬레이션 호출/로그 확보, Legacy Top 수정 금지, MAC read(R)→Write(R+6) 추적 표 작성.

## Phase 1 — ISA Constants, Decoder, PC, GPR, ALU

**실행 상태 (2026-11-24): PASS.** 64KiB/256B 각 61 cases·432 steps·25100 checks, 기존 Python 27 tests 및 Legacy RTL 5종 PASS. 상세 명령·로그·범위는 [08_phase1_report.md](08_phase1_report.md).

**신규 후보:** `04_rtl/isa/npu_isa_pkg.sv`, `04_rtl/isa/instruction_decoder.sv`, `04_rtl/isa/register_file.sv`, `04_rtl/isa/scalar_alu.sv`, `04_rtl/isa/instruction_controller.sv`, `04_rtl/controller/npu_top.sv` (초기에는 Scalar-only skeleton).

**지원 명령:** `LUI`, `ADDI`, `ADD`, `BEQ`, `BNE`, `JAL`, `END`. PC+4, signed Immediate, Branch/JAL target, invalid GPR, illegal opcode 처리. D-03/D-04를 적용하고, 내부 최소 STATUS/ERROR 상태만 두며 CSR bank/Timer/DMEM 동작은 구현하지 않는다. Fetch 검증에 필요한 1clk IMEM TB와 Python machine-word/scoreboard fixture는 이 Phase에 별도로 추가한다. Legacy target/헤더는 보존한다.

**테스트:** Python이 만든 32bit machine-word IMEM에서 프로그램 로드; 카운터 증가 및 `BNE LOOP` 종료; LUI/ADDI를 통한 32bit 주소 상수 생성; `JAL r0,label`; 잘못된 PC와 invalid GPR Fault. `r0=0` invariant.

**완료 조건:** PC trace / GPR scoreboard와 bit-exact 일치, 완주 후 `done=1cycle`, Halt 뒤 추가 Fetch 없음. 기본 64KiB 및 별도 축소 IMEM 용량에서 zero fill, 마지막 word/용량 밖, taken/non-taken 잘못된 후보 target, JAL fault 시 link 불변, invalid GPR/encoding 우선순위, Reset 재시작을 확인한다. Phase 1 종료 후 보고하며 별도 승인 전 Phase 2로 진행하지 않는다.

## Phase 2 — CSR + SETI + Timer + Status/Error

**실행 상태 (2026-11-24): PASS.** 64KiB/256B 각 98 scenarios·763 steps·75116 checks. CSR 4096주소·Timer 156에지 unit 및 테스트용 active 통합 PASS. 기존 Scalar 두 용량/Python 27 tests/Legacy RTL 5종 PASS. 실제 엔진 active 경계 및 EXEC snapshot 검사는 후속 단계다. 상세는 [09_phase2_report.md](09_phase2_report.md).

**신규 후보:** `04_rtl/isa/csr_file.sv`, `04_rtl/isa/perf_timer.sv`, Fault Handling을 위한 `instruction_controller` 확장.

**지원 명령:** `SETI`, `CSRW`, `CSRR`, `TSTART`, `TSTOP`; STATUS/ERROR_CODE/PERF_COUNT/PERF_OVERFLOW RO 처리.

**테스트:** D-01의 RW 원본 보존 및 중간 invalid 값의 조기 Fault 금지, CSR 설정 유지, 음수 imm13 sign extend, `SETADDR` 확대 결과, 일반 CSR readback, Reserved/RO fault, Timer start/stop/reset/overflow 및 idle/Scalar 제외.

**완료 조건:** 모든 CSR ID와 기계어 인코딩이 문서·Python assembler·SV decoder에 공통으로 반영, Timer directed tests PASS.

## Phase 3 — 내부 SRAM MUX + Block LOAD/STORE

**실행 상태 (2026-11-24): PASS.** 256KiB 87 cases·2124 steps·6711895 checks, 기본 16MiB 7 cases·156 steps·9097 checks, SRAM owner 53 checks. Phase 1/2 및 Legacy 5종 회귀 PASS. [11_phase3_report.md](11_phase3_report.md).

**기존 파일 검토:** `04_rtl/memory/memory_wrapper.sv`, `memory_port_mux.sv`, `buffer_router.sv`, `tb_address_decoder.sv`, `tb_read_mux.sv`. **신규 후보:** `npu_memory_wrapper.sv`, `sram_address_decoder.sv`, `sram_port_mux.sv`, `block_transfer.sv`.

**수행:**

- 기존 SRAM 7개, 32bit Single-Port, 1clk registered read 동작 유지.
- Region/Alignment/Depth 검사, 내부 SRAM bank 선택, word offset decode.
- LOAD 외부→내부(Weight 4 bank 각각/Buffer/Bias), STORE 내부→외부. 기존 `memory_port_mux`의 busy 2-way 선택과 분리.
- GPR 세 개 source를 수락 시 래치하고 전송 도중 변경 금지. Read→Write 직렬 구현, 마지막 write 종료 후 done, `LOAD` Timer Active 정확히 정의.
- 메모리 복사 중 다른 명령/엔진 시작 차단.

**테스트:** 1word, 2word, full Buffer A/B, Weight Bank 0/1/2/3(각 29280word), Bias 163word; SRAM 깊이+1, 예약 창 구멍, misalign, zero length, read hold, 경계/32bit 주소 wrap, LOAD→STORE round-trip, 완료 이전 다음 Fetch 차단.

**완료 조건:** SRAM 모든 Bank bit-exact copy, 비정상 접근 Fault, 타이머 LOAD active count와 TB 실제 active edge 수 일치. 기존 RAM 1clk 계약 유지.

> 2026-11-24 사용자 승인: 블록 LOAD/STORE를 Phase 3으로 앞당기고 Scalar LW/SW는 후속 Phase 4 승인 범위로 남긴다. Phase 3 Gate PASS이며, 상세 결과는 [11_phase3_report.md](11_phase3_report.md)에 기록했다. 이후 사용자 승인으로 Phase 4 Scalar LW/SW를 진행했으며 아래 결과를 따른다.

## Phase 4 — 외부 IMEM/DMEM 모델, Scalar LW/SW, 주소 검증

**진행 승인 및 실행 상태 (2026-11-24): PASS.** LW/SW 각각 signed imm12 전체 4096개, 64KiB 315 cases, 4KiB/기본 16MiB 각각 11 cases 및 소규모 파형 1 case. Phase 1~3·Python 27개·Legacy 5종 회귀 PASS. [13_phase4_report.md](13_phase4_report.md). 이후 Phase 5 진행을 승인받았으며 아래 결과를 따른다.

**실제 구현:** 기존 instruction_controller/decoder/ISA package 확장, Controller 내부 Scalar/Block DMEM 선택. 별도 tb_npu_phase4.sv, phase4_vectors.py, run_phase4.py를 추가했다. Top/Block Transfer/SRAM Wrapper/BRAM은 수정하지 않았다.

**수행:** 동기식 고정 1-cycle IMEM/DMEM 32bit Single-Port TB. CPU `LW/SW`만 외부 DMEM 범위 지원; `S/B/I/U/J` Immediate decoding/Word Alignment, memory region+bounds faults.

**완료 조건:** Address+WriteData+ReadData를 waveform과 scoreboard로 검증; Read 요청 edge R와 소비 edge R+1 규칙 PASS.

## Phase 5 — GEMM 1회 실행 엔진 통합

**진행 승인 및 실행 상태 (2026-11-24): PASS.** 주 suite 173 cases / 37451392 RTL checks, K 경계 72 cases, 독립/연속 Legacy FC 출력 326words 일치. Snapshot/INT32 wrap/R→R+6/Timer/Fault 및 Phase 1~4·Python·Legacy 회귀 PASS. 최소 K=8은 사용자 승인으로 정식 지원 하한을 확정했다. [15_phase5_report.md](15_phase5_report.md). 이 Phase 5 시점의 Phase 6은 미시작이었으며 후속 결과는 18번 보고서를 따른다.

**기존 RTL 중 핵심 변경 후보:**

- `control_unit.sv`: 현재 고정 3 FC + ARGMAX 결합 해체. 가능하면 새로운 `gemm_controller.sv`로 분리.
- `layer_config_lut.sv`: 신규 경로 제거(레거시 경로는 그대로 유지).
- `control_fsm.sv`, `control_state_pkg.sv`: 단일 GEMM FSM으로 재구성(레거시 파일 직접 변경보다 별도 이름 권장).
- `mlp_counters.sv`: layer_index 제거, input_word 및 group counter 유지.
- `address_generator.sv`: CSR base/offset, `K_words=K/4`, `out_groups=ceil(N/4)`로 계산. (두 차원을 혼동하지 않을 것.)
- `read_issue_control.sv`, `pipeline_control.sv`: layer 종속 조건 제거, read/bias/result/write event 유지.
- `control_read_mux.sv`: SRAM owner 선택기와 역할 중복 확인.
- `mlp_top.sv`: 레거시 유지, 신규 `npu_top.sv`가 새 GEMM과 기존 MAC/Accumulator 연결.

**절대 보존:** `mac_array.sv`, 내부 input register, signed_multiplier, adder_tree, partial_sum register, accumulator/postprocess 산술, `bias_load` 및 `out_we` 에지 관계.

**테스트:** D-02에 따라 K=4는 INVALID_CONFIG/start·SRAM write 없음 확인. K=8/12/16/32 경계 분석·시뮬레이션 후 검증 후 최소 지원 K=8 확정 (현재 staging 추가 금지). 독립 FC1/2/3 각각 CSR 기반 GEMM, 입력/출력 버퍼 반대 선택, Packed INT8 Weight 4 Bank 동기 읽기, Bias shift, Out shift, ReLU, N=10 padding, `done` 최종 write 이후, 지원하지 않는 `M>1`/Overflow Config Fault. 기존 Python Golden과 layerwise bit-exact.

**완료 조건:** 3개 FC의 모든 출력 워드 Golden 일치; 전체 MLP도 3×`EXEC GEMM` 결과가 이전 베이스라인과 동일. Timer GEMM active count 일치.

## Phase 6 — ARGMAX 독립 실행, END/Halt 통합

**후속 구현 승인 및 실행 상태 (2026-11-24): Phase 6 Gate PASS.** 기준 HEAD는 `414fd57`, 브랜치는 `feat/phase6-argmax-20261124`다. [17번 결정](17_phase6_decisions.md)의 확정 본문을 유지했고 독립 ARGMAX를 구현·검증했다. 최종 411회 실행, 2,983,083 RTL checks, 517,258 Python 비교 및 Phase 1~5/Memory Fault/Python 27개/Legacy 5종 회귀 PASS다. [18번 보고서](18_phase6_report.md). 커밋·Push 및 Phase 7/8은 수행하지 않았다.

### 구현 구조와 적용 순서

독립 `argmax_engine.sv`를 추가하고 기존 비교 Datapath를 재사용했다. 아래 순서대로 구현·검증을 완료했다.

1. ISA package/Decoder에 기존 EXEC ARGMAX 형식을 연결한다. 예약 필드 → 원본 5bit rd 검사 순서를 유지한다. 새로운 Opcode/CSR/인코딩은 추가하지 않는다.
2. CSR file에서 ARG_SRC/LEN 병렬 출력을 제공하고 Controller가 EXEC 수락 에지에 두 원본 32bit, next-PC/오류, rd를 Snapshot한다.
3. 원본 L에서 넓은 W=ceil(L/4), B=4W, E=ARG_SRC+B를 계산한다. Alignment → A/B Region/역할 → 데이터/next-PC Bounds → Configuration 순서로 검증하며 **invalid ARG_LEN의 Bounds를 생략하지 않는다.**
4. 검증 성공 후 Engine start를 1회만 허용한다. 기존 Wrapper ARGMAX 포트와 OWNER_ARGMAX를 연결한다. 검증 실패는 Engine start·모든 SRAM 요청·GPR Writeback·PC 전진을 차단한다.
5. Read R → 소비 R+1, 워드별 직렬 byte 처리, 첫 값 initialize/후속 strict signed compare, 유효 L개만 비교를 구현한다. 다음 word는 i=4/8 경계에서만 읽는다.
6. 마지막 비교 결과가 갱신된 뒤 내부 argmax_done을 발생시키고 다음 에지에 결과 zero-extend/rd Writeback 및 PC 전진을 수행한다. rd=r0도 전체 검증·실행 후 결과 쓰기만 생략한다. 내부 완료를 Top done/END와 분리한다.
7. 연속 실행·Reset·Fault와 Timer 제외를 검증한다. ARGMAX active는 SRAM owner용이며 Timer에는 연결하지 않는다.
8. Python Golden과 실제 RTL dump/포트·상태 scoreboard 및 작은 waveform을 비교한다. Phase 1~5, 메모리 Fault 후속, Python unit, Legacy RTL 5종 회귀를 수행한다. 결과·실패·소스 해시를 향후 보고서에 기록한다.

구현된 Instruction FSM은 Snapshot → ARG_CHECK → ARG_START → ARG_WAIT → 명령 완료다. 현재 4bit/14개 상태에 CHECK/START/WAIT 3개를 추가하면 17개이므로 기존 값 유지 및 5bit로 확장했다. Engine은 IDLE/READ/PROCESS/COMPLETE/FAILED다. 실제 포트·FSM·타이밍은 18번 보고서와 소스를 따른다.

### 신규·수정 파일

| 구분 | 파일 | 적용 내용 |
|---|---|---|
| 신규 RTL | `04_rtl/controller/argmax_engine.sv` | 원본 설정 검사 출력, 가변 읽기/비교 FSM, 내부 완료·오류·결과 |
| 수정 RTL | `04_rtl/isa/npu_isa_pkg.sv` | 기존 ISA에 해당하는 내부 OP_ARGMAX/상수 |
| 수정 RTL | `04_rtl/isa/instruction_decoder.sv` | 기존 funct3/funct7/예약 필드 및 rd 유효성 |
| 수정 RTL | `04_rtl/isa/csr_file.sv` | ARG_SRC/LEN 원본 32bit 병렬 내부 출력; 저장/권한 규칙 보존 |
| 수정 RTL | `04_rtl/isa/instruction_controller.sv` | 원자적 Snapshot, 공통 오류 병합, start/Wait, 지연 GPR Writeback, FSM 폭 |
| 수정 RTL | `04_rtl/controller/npu_top.sv` | Engine과 기존 ARGMAX Wrapper 포트·owner 연결; 외부 포트 유지 |
| 신규 검증 | `05_tb/npu/tb_npu_phase6.sv` | 동기 메모리/상태·요청·결과·Timer·Fault scoreboard와 실제 dump |
| 신규 검증 | `90_scripts/npu/phase6_vectors.py` | 독립 signed Golden, 인코딩/CSR/주소·Fault·혼합 프로그램 시나리오 |
| 신규 검증 | `90_scripts/npu/run_phase6.py` | XSim 실행·timeout·실제 비교·hash·소규모 파형·로그 |
| 검증 연결 보완 | `90_scripts/npu/run_phase1.py` | 새 Engine/기존 비교 Datapath compile 의존 목록 |
| 검증 연결 보완 | `05_tb/npu/tb_npu_phase2_units.sv`, `tb_npu_phase2_active.sv` | wildcard 인스턴스의 추가 내부 포트 선언/연결; 기존 기대 동작 보존 |
| 기존 검증 보완 | `90_scripts/npu/phase5_vectors.py` | argmax_reserved가 기존 EXEC ARGMAX,r0이므로 실제 불법 형식으로 교체하고 불법 인코딩 커버리지 유지; 공유 Golden 확장 시 기존 GEMM 수치/기대값 보존 |
| 문서 | 01/02/03/04/README, `17_phase6_decisions.md`, `18_phase6_report.md` | 계약·계획·실제 수행 결과를 구분해 기록 |

재사용/보존 대상: argmax_unit/tracker/update, byte_select4, signed_compare8, common register_en, Legacy argmax_control/schedule/control_read_mux/LUT/MLP Top, 기존 SRAM Wrapper/MUX/BRAM/Block/GEMM/MAC/Accumulator. Wrapper는 준비된 포트를 사용하므로 기본 계획에 RTL 변경을 포함하지 않는다. 합성/FPGA/10,000장 정확도는 이번 Phase 6의 수행 범위가 아니다.

### 실행한 테스트와 완료 Gate

[Verification Plan 5.1절](04_verification_plan.md)의 A-01~A-16 및 경계/복합 오류 매트릭스를 구현·실행해 PASS했다. 특히 LEN=11의 0x07/0x06 구분, LEN=0의 시작 Bounds, 상위 비트/올림 산술, 마지막 IMEM의 데이터/next-PC 오류 병합을 검증한다.

완료 조건은 정상 결과/GPR zero-extend·r0 버림, Snapshot, 무부작용 Fault Halt/Reset, Timer 제외, R→R+1 실파형, 전체 회귀 PASS다. **Top done은 END에서만 1클럭**, argmax_done은 내부 완료다. 실제 근거는 18번 보고서/metrics/source snapshot/wave audit에 기록했다. 당시 후속 Phase는 별도 승인 대상이었고, 현재 상태는 아래 후속 요약을 따른다.

## Phase 7 — MNIST Application Verification (첫 200장 승인 범위)

**현재 상태: Gate PASS.** 사용자 후속 승인으로 이번 완료 범위를 G0 → 1장 → 5장 → 원본 첫 100장 → 첫 200장으로 확정했다. 기존 계획의 10,000장 정확도·별도 모델 전환은 이번 범위에서 제외하고 후속 승인으로 남긴다. 실제 근거는 [19번 보고서](19_phase7_report.md)와 [metrics](../../07_runs/npu_phase7_20261123_220156_054531Z/metrics.json)를 따른다.

### 구현 및 보존 범위

- 신규 Python: run_scenario.py(단일 진입점/Manifest/실행·회귀/자원 기록), assembler.py(기존 인코더·Label/LI/SETADDR 및 범위 검사), memory_allocator.py(4byte 정렬·중복·16MiB Bounds), weight_packer.py(기존 모델 로더/양자화/Packing), golden_compare.py(INT64 계산 후 INT32 wrap·shift/saturation·분류 비교).
- 신규 검증: 05_tb/npu/tb_npu_application.sv와 90_scripts/npu/tests/test_application.py.
- 기존 04_rtl 전체, Phase 1~6·Legacy TB/실행기, 모델·양자화·Golden 코드는 변경하지 않는다. 새 포트·Opcode·CSR·GPR·메모리 프로토콜을 추가하지 않는다.
- conda aissd Python 3.11, PyTorch/torchvision 실제 import 및 CUDA 인식을 확인했다. Golden은 CPU 정수 계산이다.

### 실행 프로그램과 메모리

모델은 Python에서 한 번 로드·양자화하고 W0~3/Bias를 프로그램 시작 때 총 5회 LOAD한다. 반복문은 Input LOAD → FC1/2/3 CSR 설정·EXEC GEMM → EXEC ARGMAX,r5 → SW → Pointer 증가 → BNE다. r1/r3/r6/r7은 loop-live, r2/r4/r5만 임시값이며 SETADDR는 r4를 사용한다. G1 debug STORE도 live register를 보존한다.

G2/G3/G4는 동일한 111word/444byte 코드 구조다. 100/200장의 기계어 차이는 Prediction Pointer와 Input End의 LI 확장 4word뿐이다. 기본 외부 IMEM 64KiB/DMEM 16MiB와 SRAM 7개·1clk Read·MAC R→R+6 계약은 보존한다. 모델+Input+Prediction은 100장 547,932B, 200장 626,732B다. 각 실행의 byte address/크기/HEX hash를 Manifest에 기록한다.

### 수행 순서 및 완료 Gate

| Gate | 실제 검증 | 결과 |
|---|---|---|
| G0 | Python unit 9개, 기존 IntegerMLP 200장 Layer 비교, Phase 5 packed kernel 0/7/199번, Legacy model 117,283words | PASS |
| G1 | 1장 Prediction 및 FC1/2/3 총 163word bit-exact, END | PASS |
| G2 | 5장 연속·모델 재LOAD 없음·BNE/Pointer·Prediction | PASS |
| G3 | 원본 첫 100장, Golden 100/100, Label 100/100 | PASS |
| G4 | 원본 첫 200장, Golden 200/200, Label 200/200 | PASS |
| 회귀 | Phase 1~6/Memory Fault/Python unit/Legacy 5종 및 기존 소스 보존 | PASS |

모든 Application은 TSTART/TSTOP와 Waveform을 사용하지 않는다. G1에만 Layer STORE를 넣고 G2/G3/G4는 Prediction만 외부 DMEM에 쓴다. TB cycle 통계는 PERF Timer 측정이 아니다. 시간·메모리는 실측값과 측정 범위를 19번에 기록했다. Label 정확도는 실측 보고이며 별도 최소 기준을 추가하지 않는다.

의존성 확인 중 읽기 전용 샌드박스의 임시 디렉터리 제한이 발생했고 승인된 권한에서 같은 aissd import가 성공했다. 패키지 설치·환경 변경이나 RTL 수정은 없었다. 기능/Golden/시뮬레이션 실패·timeout은 없었다. Phase 7 당시 커밋·Push와 10,000장·Phase 8은 수행하지 않았다. 이후 Phase 7을 94bb214에 보존했고, 별도 승인된 Phase 8 결과는 아래와 20번 보고서를 따른다.

## Phase 8 — Direct RTL BRAM Inference / OOC Synthesis & Implementation

**현재 상태: Timing Gate FAIL / 후속 승인 대기.** 기존 BMEM IP 전환 계획은 최신 사용자 승인에 따라 직접 RTL 추론 방식으로 대체한다. BMG IP/.xci를 만들지 않는다. 10,000장 정확도 검증은 보류하며 Phase 7 G0~G4의 기준선과 커밋 94bb214를 보존한다.

| 순서 | 수행 범위 | 완료 기준 / 실제 결과 |
|---|---|---|
| P8-0 | Phase 7 기준선·도구·별도 브랜치 / Non-Project Flow | phase8/direct-bram-inference-20261124, Vivado 2025.2, Legacy 프로젝트 보존 |
| P8-1 | npu_top 및 기존 SRAM 무수정 첫 합성 | 7개 논리 SRAM, BRAM 109.5/135타일, LUTRAM 0, mapped netlist G1 PASS |
| P8-2 | FPGA Reset 경계 및 기능 회귀 | 2FF Async Assert/Sync Deassert, Reset/SRAM 17개, Wrapper G1/G4 및 기존 회귀 PASS |
| P8-3 | 동일 100MHz에서 opt/place/phys_opt/route | 실제 도구 실행 완료, Timing과 구분 |
| P8-4 | Setup/Hold 및 경계·경고 분석 | WNS≥0, WHS≥0, TNS=THS=0 필요; 실제 판정 FAIL |
| P8-5 | 보고·승인 경계 | [20번 보고서](20_phase8_report.md). 실패 시 임의 RTL/주파수/예외 변경 없이 중단 |

변경은 신규 06_fpga Reset Wrapper·Tcl·XDC, 전용 TB와 Phase 8 실행기, 현재 계획/결과 문서에 한정한다. 기존 04_rtl 전체, SRAM 7개, MAC R→R+6, ISA/CSR/외부 메모리 프로토콜, 기존 TB/실행기와 Legacy 프로젝트는 보존한다. 외부 IMEM/DMEM의 TB 저장소는 합성 입력에 넣지 않는다.

아래 명령으로 각 Gate를 재현하며 출력은 새로운 07_runs/99_build 디렉터리에 분리한다. 구체적인 Checkpoint·Manifest·명령은 20번 보고서를 따른다. Power/보드 I/O/Bitstream/보드 실험/타이밍 시뮬레이션은 이번 완료 결과에 포함하지 않는다.

## 9. 구현 순서와 테스트 게이트 요약

| 단계 | 기능 | 다음 단계로 넘어가는 조건 |
|---|---|---|
| 0 | 기존 RTL 기준선 | 기존 시뮬레이션/현재 제한 확인 |
| 1 | Fetch/ALU/Branch | Branch loop·PC·GPR PASS |
| 2 | CSR/Timer/Error | CSR·Timer·Fault PASS |
| 3 | SRAM/Block XFER (사용자 범위 재정의) | 모든 Bank LOAD/STORE 및 Timer/Fault PASS |
| 4 | 외부 Scalar LW/SW (진행 승인) | DMEM 동기 1clk 동작 PASS |
| 5 | GEMM | FC1/2/3 Golden bit-exact PASS |
| 6 | ARGMAX/Halt | 유효/오류 경로 PASS |
| 7 | Python/Application TB | 승인된 G0~G4·첫 100/200장 Golden 및 전체 회귀 PASS; 10k 별도 |
| 8 | FPGA | BRAM·Timing·Report 확보 |

## 10. 예상되는 주요 오류와 방지책

| 위험 | 예방 / 테스트 |
|---|---|
| MAC 3-stage schedule 1cycle 어긋남 | 매 Read R 기준 R+1~R+6 신호 Trace 비교 |
| SRAM 빈 예약 주소에 접근 | 실제 물리 depth 기반 bounds 체크 |
| 블록 전송 끝나기 전에 다음 instruction | `done` 최종 목적지 Write 이후만 발생시키기 |
| 3-input GPR read 때문에 잘못된 rs3 | 별도 rs3 selector/operand 래치 구현 및 directed tests |
| Python Weight Packing과 bank 주소 불일치 | Bank별 Word/Byte 위치 Golden 검증 |
| ARGMAX padding 10→12 bytes 오인 | ARG_LEN=10만 비교, tie handling |
| SETADDR가 r4을 덮어 예측 포인터 파괴 | Assembler clobber 확인, r4 임시 용도 고정 |
| Testbench `$readmemh`를 합성 코어로 옮김 | 모델 초기화는 TB에만 |
| 과거 구 Top 테스트가 깨짐 | 기존 Top/테스터 보존, 신규 Top은 별도 생성 |
| 고정 1clk Memory Read 응답을 같은 edge에서 사용 | Read R, capture R+1 체크 |
| 10k 이미지 데이터가 FPGA BRAM에 안 들어감 | TB 메모리와 실제 물리 FPGA Wrapper 분리 |

## 11. 작업별 Codex 보고 형식

각 단계가 끝나면 다음을 포함해 보고한다: (a) 변경한 파일과 기존 파일 영향, (b) 새/수정 포트와 인터페이스, (c) 실행한 테스트 명령과 Pass/Fail, (d) waveform이나 로그 위치, (e) 검증하지 못한 항목, (f) 다음 단계 전 의사결정 필요 여부. 예상 수치와 실측 수치를 구분한다.


## 승인된 별도 후속 작업 — 메모리/PC 복합 Fault 우선순위

Phase 5를 5be9059에 먼저 보존한 뒤 fix/memory-fault-priority-20261124에서 작업한다.
대상은 LW/SW/Block LOAD/STORE의 데이터/next-PC 검사 병합, 사전 접근/시작 차단, Python Golden과 Testbench 일치다.
명령 4개 × Alignment/Region/Bounds/정상 주소의 마지막 IMEM Word 사례를 필수 검증하고, 선행 인코딩/GPR/CSR 및 Timer 보존도 확인한다.
Phase 1~5, Python 및 Legacy RTL 5종 회귀가 완료되어야 한다. 보고서·수정은 Phase 5와 별도 커밋으로 관리한다. Phase 6은 승인 범위가 아니다.

최종 후속 Gate는 **PASS**다. 필수 복합 오류 32사례(armed/unarmed), 기본 16MiB 16사례, 추가 Fault 및 Phase 1~5·Python 27개·Legacy 5종 회귀를 통과했다. 변경·타이밍·재현 로그는 [16번 후속 보고서](16_memory_fault_priority_report.md)를 참조한다. 이 메모리 후속 작업 당시 Phase 6은 승인 대기였으며, 이후 별도 승인으로 완료한 Phase 6 결과는 [18번 보고서](18_phase6_report.md)를 따른다.
