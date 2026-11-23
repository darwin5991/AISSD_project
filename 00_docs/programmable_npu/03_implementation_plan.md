# Programmable NPU v1.0 — Codex 구현 계획

> 2026-11-24 결정 우선순위: [07_design_decisions_phase0.md](07_design_decisions_phase0.md)의 D-01~D-04와 후속 사용자 확정을 우선 적용한다.

**목표:** 기존 고정 3-Layer INT8 MLP RTL을 보존·재활용하면서 ISA v1.0에 따른 Programmable NPU Top, Python 통합 테스트 환경, FPGA 구현 경로를 단계적으로 완성. **현재 진행:** Phase 2 검증 상태를 69410b4에 보존한 뒤, 사용자 승인에 따라 Phase 3 블록 LOAD/STORE·SRAM·실제 LOAD Timer 구현과 검증을 완료했다. [Phase 3 실행 보고서](11_phase3_report.md)의 Gate PASS를 보고하며, 사용자 승인 전 Phase 4 Scalar LW/SW로 진행하지 않는다.

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

> 2026-11-24 사용자 승인: 블록 LOAD/STORE를 Phase 3으로 앞당기고 Scalar LW/SW는 후속 Phase 4 승인 범위로 남긴다. Phase 3 Gate PASS이며, 상세 결과는 [11_phase3_report.md](11_phase3_report.md)에 기록했다. Phase 4는 미시작이다.

## Phase 4 — 외부 IMEM/DMEM 모델, Scalar LW/SW, 주소 검증

**신규 후보:** `04_rtl/isa/external_memory_port.sv` 또는 `dmem_request_mux.sv`(필요 시), `05_tb/npu/npu_memory_model.sv`, `05_tb/npu/tb_npu_scalar.sv`.

**수행:** 동기식 고정 1-cycle IMEM/DMEM 32bit Single-Port TB. CPU `LW/SW`만 외부 DMEM 범위 지원; `S/B/I/U/J` Immediate decoding/Word Alignment, memory region+bounds faults.

**완료 조건:** Address+WriteData+ReadData를 waveform과 scoreboard로 검증; Read 요청 edge R와 소비 edge R+1 규칙 PASS.

## Phase 5 — GEMM 1회 실행 엔진 통합

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

**테스트:** D-02에 따라 K=4는 INVALID_CONFIG/start·SRAM write 없음 확인. K=8/12/16/32 경계 분석·시뮬레이션 후 정확한 최소 지원 K 확정 (현재 staging 추가 금지). 독립 FC1/2/3 각각 CSR 기반 GEMM, 입력/출력 버퍼 반대 선택, Packed INT8 Weight 4 Bank 동기 읽기, Bias shift, Out shift, ReLU, N=10 padding, `done` 최종 write 이후, 지원하지 않는 `M>1`/Overflow Config Fault. 기존 Python Golden과 layerwise bit-exact.

**완료 조건:** 3개 FC의 모든 출력 워드 Golden 일치; 전체 MLP도 3×`EXEC GEMM` 결과가 이전 베이스라인과 동일. Timer GEMM active count 일치.

## Phase 6 — ARGMAX 독립 실행, END/Halt 통합

**변경 후보:** `argmax_control.sv`, `argmax_schedule.sv`; 기존 `argmax_unit.sv`, `signed_compare8.sv`, `argmax_tracker.sv` 재사용. `argmax_engine.sv` 신규 wrapper 권장.

**테스트:** `ARG_LEN=1,3,4,9,10`, 음수 데이터, 최댓값 동점 시 lowest index, FC3의 마지막 두 padding byte 제외, A/B 선택, `rd=r0` 결과 무시, 다른 레이어 뒤에서도 독립 실행, `ARG_LEN=0,11` Fault.

**완료 조건:** `EXEC ARGMAX,rd` Writeback, 정상 종료 `done`, Fault sticky 상태와 Reset 재시작 PASS.

## Phase 7 — Python 생성·검증 하네스

**파일 후보:** `90_scripts/npu/` 아래 `run_scenario.py`, `assembler.py` 또는 `customasm` 규칙 파일, `memory_allocator.py`, `weight_packer.py`, `golden_compare.py`; 초기에 **단일 Python Entry-point**로 유지하고 내부 함수/모듈로 점진 분리 가능.

**기능:**

1. Test Scenario(한 장/몇 장/10,000장, 다른 모델 가중치 세트, microbench) 수신.
2. Weight/Bias INT8 Packing 및 **4개 은행별** 물리 순서 변환. 자동 외부 Memory Allocation(4byte align), Input/Expected/Output Region 분리, Manifest JSON 출력(필요 시).
3. Assembly 생성(모델 LOAD 1회 → 실행 루프), 32bit machine code로 Assemble, IMEM HEX/DMEM HEX 출력. `SETADDR` clobber 규칙 준수.
4. XSim 등 시뮬레이터 실행, `done`까지 기다리거나 timeout 처리, Prediction/Layer Output/Timer의 결과 영역만 dump.
5. Python bit-exact Golden 비교 및 Accuracy Summary. 실행 프로파일별 파형 기록(짧은 테스트만 ON).

**정확도 10,000장:** 처음에 Weight Bank×4/Bias를 LOAD, 매 이미지 `LOAD input→FC1→FC2→FC3→ARGMAX→SW prediction`만 실행. **Timer 명령과 매 레이어 STORE는 기본 생성에서 제외**. Input Pointer +784, Prediction Pointer +4, BNE로 반복.

**완료 조건:** 1장/몇 장 Layerwise Test, 10,000장 Accuracy Test, 주소 배치 자동화, Output/Golden 비교 모두 PASS. Long-run은 Timer·Waveform OFF로 메모리·시간 절감.

## Phase 8 — FPGA BMEM IP 적용 / 합성 / Timing / 보고

**수행:** 최종 내부 SRAM 7개를 Native Single-Port BMEM IP/호환 Wrapper로 연결(primitive output register disabled), 1clk read를 검증. 외부 DMEM 16MiB TB 모델은 **합성하지 않음**; 실제 FPGA 외부 메모리 연동은 과제 범위에 맞는 별도 Wrapper로 구분. Vivado 합성/배치배선, Timing Slack, LUT/FF/BRAM/DSP, Power 분석. 최소한 과제에서 요구하는 메모리 transfer/compute waveform 확보.

**완료 조건:** BMEM IP 동기 응답이 행동 모델과 동등, 기능 회귀, 지정 클럭에서 WNS≥0 목표, 자원/파워/Timing 보고서 생성. 실제 도구 실행 결과만 정량 결과로 기록.

## 9. 구현 순서와 테스트 게이트 요약

| 단계 | 기능 | 다음 단계로 넘어가는 조건 |
|---|---|---|
| 0 | 기존 RTL 기준선 | 기존 시뮬레이션/현재 제한 확인 |
| 1 | Fetch/ALU/Branch | Branch loop·PC·GPR PASS |
| 2 | CSR/Timer/Error | CSR·Timer·Fault PASS |
| 3 | SRAM/Block XFER (사용자 범위 재정의) | 모든 Bank LOAD/STORE 및 Timer/Fault PASS |
| 4 | 외부 Scalar LW/SW (후속 승인) | DMEM 동기 1clk 동작 PASS |
| 5 | GEMM | FC1/2/3 Golden bit-exact PASS |
| 6 | ARGMAX/Halt | 유효/오류 경로 PASS |
| 7 | Python/Testbench | 소량/10k Accuracy PASS |
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
