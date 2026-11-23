# Programmable NPU v1.0 — RTL 아키텍처 및 인터페이스 명세

> 2026-11-24 결정 우선순위: [07_design_decisions_phase0.md](07_design_decisions_phase0.md)의 D-01~D-04와 후속 사용자 확정을 우선 적용한다.

**근거 RTL:** `04_rtl/controller/mlp_top.sv`, `control_unit.sv`, `pipeline_control.sv`, `read_issue_control.sv`, `address_generator.sv`, `layer_config_lut.sv`, `argmax_*`, `04_rtl/memory/memory_wrapper.sv`, `memory_port_mux.sv`, `buffer_router.sv`, `single_port_bram.sv`, `04_rtl/mac_array/*`, `04_rtl/accumulator_postprocess/*` (2026-11-24 GitHub 기본 브랜치 확인). **기존 문서:** `00_docs/architecture.md`, `00_docs/mac_input_pipeline.md`.

현재 구현은 [Phase 5 보고서](15_phase5_report.md)의 Scalar/CSR/Timer, LW/SW, Block LOAD/STORE, 내부 SRAM 7개 및 CSR Snapshot 기반 단일 GEMM까지다. ARGMAX는 후속 승인 범위다. [10](10_phase3_decisions.md)·[12](12_phase4_decisions.md)·[14번 결정](14_phase5_decisions.md)을 적용한다. 최소 K=8은 실제 검증 후 사용자 승인으로 확정한 정식 지원 하한이다.

## 1. 최상위 구조

```text
                  [외부 Instruction Memory: 32b read, fixed 1clk]
                                      ↑ ↓
+------------------------- programmable npu_top -----------------------+
| Instruction Controller (PC / fetch FSM / decoder / branch / halt)    |
|      ↕                  ↕                       ↕                    |
| GPR 8x32 + scalar ALU   CSR Bank             Perf Timer              |
|      ↕                  ↕                       ↕                    |
|                   Execution Dispatch                               |
|      +-------------------+---------------------+                    |
|      |                   |                     |                    |
|  Block Transfer    GEMM Controller        ARGMAX Controller          |
|  (LOAD/STORE)      (FC one-shot)          (signed INT8)             |
|      |                   |                     |                    |
|      +-------- SRAM Port MUX / Addr Decode ----+                    |
|                    |            |                                    |
|             Buffer A/B     W0..W3 + Bias                           |
|                    ↑            ↑                                    |
|             [existing unpack → MAC(3-stage) → Acc/Postprocess]     |
|                                                                      |
|  Scalar LW/SW + Block Transfer → External Data Memory Port          |
+-------------------------------↕--------------------------------------+
                   [외부 Data Memory: 32b R/W, fixed 1clk]
```

- IMEM와 DMEM은 **Top 바깥**. PC/Fetch/Decoder, SRAM, GEMM/ARGMAX/Timer/GPR/CSR은 **Top 내부**.
- 명령어 파이프라인 없음. 한 번에 한 명령어만 발행하며, 실행 엔진은 `start/active/done` 핸드셰이크를 사용. 동일 명령어 내에서 읽기·계산·쓰기 단계는 기존 파이프라인을 유지.
- Weight/Bias는 최초 LOAD 이후 내부 SRAM에 유지되며, 다음 명령에서 덮어쓰지 않으면 재사용 가능.
- `LOAD/STORE`는 GPR 3개를 디코딩하고, GEMM/ARGMAX는 CSR 스냅샷과 `EXEC` operation ID로 실행.

## 2. Top 포트 계약 (설계 목표)

| 방향 | 포트 | 의미 |
|---|---|---|
| In | `clk`, `rst_n`, `start` | 상승 에지, active-low Reset, IDLE 시작 펄스 |
| Out | `busy`, `done`, `fault` | 실행 중, 정상 종료 1-cycle pulse, Error-Halt sticky |
| Out | `imem_en`, `imem_addr[31:0]` | 외부 명령 메모리 Read 요청 (PC byte address) |
| In | `imem_rdata[31:0]` | Read 요청 에지 직후 동기 갱신되는 32bit 명령어 |
| Out | `dmem_en`, `dmem_we`, `dmem_addr[31:0]`, `dmem_wdata[31:0]` | 단일 외부 데이터 메모리 R/W 요청 |
| In | `dmem_rdata[31:0]` | 동기 읽기 결과 |

정상 `END`: `done` 1-cycle pulse, `busy=0`, `fault=0`, `STATUS=1`에 진입. Fault: `done=0`, `busy=0`, `fault=1` 유지, `STATUS=2`.

상위 `start`는 기존 `mlp_top`의 시작/완료 패턴을 유지하려는 **인터페이스 구현 기준**이다. Reset 이후 외부 IMEM/DMEM을 먼저 로드하고 `start`를 펄스시키는 TB를 작성한다. `start`가 실행 중 들어오면 무시, Halt 해제는 Reset만 가능.

### 외부 메모리 1-cycle timing

```
Read:
 cycle R(before rising edge): en=1, we=0, addr=A
 edge R: memory captures A; rdata updated after edge R
 edge R+1: DUT may capture/consume rdata(A)

Write:
 cycle W(before rising edge): en=1, we=1, addr=A, wdata=D
 edge W: memory[A]=D committed; no write response needed
```

- Request/Response 별도 ready/valid 없음, 대기 시간 가변 아님. **Read 결과를 요청 edge와 동일 edge에서 DUT가 샘플링하지 않도록 함.**
- IMEM와 DMEM은 각각 물리적으로 단일 포트. `LW/SW`와 블록 전송 간 충돌은 Instruction Controller가 순차 실행을 보장하므로 DMEM port selector만 필요.
- 외부 DMEM의 기준 주소는 `0x1000_0000`; Testbench 메모리 인덱스는 `(dmem_addr - base) >> 2`로 변환. IMEM 주소는 `(PC>>2)`.
- D-03/D-04: IMEM_BASE=0, DMEM_BASE=0x10000000. Top/TB가 IMEM_BYTES/DMEM_BYTES 파라미터를 공유한다. Fetch는 적재 길이가 아닌 할당 용량 기준이며, TB는 모든 미사용 IMEM word를 0으로 채운다 (실제 fetch 시 INVALID_OPCODE=0x01). BEQ/BNE는 선택된 next PC만 검사하고, JAL target 오류 때 link/PC를 갱신하지 않는다.
- Testbench 프로파일: 64 KiB IMEM, 16 MiB DMEM 권장. 대형 DMEM 모델은 **시뮬레이터 호스트 메모리**이며 FPGA 내부 BRAM과 분리해 해석.

## 3. 내부 SRAM과 Port Selector

현재 `memory_wrapper`에는 이미 **Single-Port RAM 7개**, `buffer_router`, `memory_port_mux x7`, `tb_address_decoder`, `tb_read_mux`가 있다. 기존 `memory_port_mux`는 `busy=1`에서 core, `busy=0`에서 TB를 선택한다. 따라서 **프로그램 실행 도중 LOAD/STORE로 Weight/Bias/Buffer에 쓰기**를 할 수 없다.

### v1 변경

1. SRAM 물리 인스턴스 7개와 포트 형식 `(en,we,word_addr,wdata,rdata)` 유지.
2. `GEMM`, `ARGMAX`, `BLOCK_XFER` 중 활성 소유자를 선택하는 SRAM 접근 MUX 추가. 이 단계에서 `busy`는 Top 전체 실행 상태이지 SRAM 소유자를 의미하지 않는다.
3. Transfer Engine에서 **A/B, W0..W3, Bias 모두** 읽기/쓰기를 허용. 특히 Weight/Bias에 `core_we=0`으로 고정한 기존 연결을 새 Transfer Write 경로로 우회/대체해야 함.
4. 내부 주소는 `0x8000_0000` 기반 32bit byte address. Bank Base와 실제 물리 깊이 검증 후 word address를 RAM 폭(8/7/15/8bit)에 맞게 전달. 해당 Bank의 reserved 128 KiB 창 나머지는 invalid.
5. GEMM은 Input Buffer 한 개 읽기 + 반대쪽 Output Buffer 쓰기 + Weight 4개 병렬 읽기 + Bias 읽기를 허용. 모두 **서로 다른 SRAM 단일 포트**이므로 충돌 없음. 기존 `buffer_router`의 핑퐁 선택 로직 재사용 가능하지만 내부 base/offset 디코딩 기능은 추가 필요.
6. ARGMAX는 A 또는 B 입력 Buffer 읽기만 허용. 같은 SRAM 포트로 동시에 GEMM 실행하지 않음.
7. 기존 TB 직접 쓰기 경로는 기존 RTL 회귀 테스트용으로 보존하거나 Legacy Wrapper에 격리. **최종 프로그래머블 NPU 정상 실행은 반드시 LOAD/STORE 명령을 통해 데이터를 이동**해야 함.

### SRAM 접근 매트릭스

| 현재 실행 명령 | A/B | W0..W3 | Bias | 외부 DMEM |
|---|---|---|---|---|
| `LOAD` | 목적지일 때 Write | 선택된 한 Bank Write | 선택 시 Write | Read |
| `STORE` | 선택 시 Read | 선택된 한 Bank Read | 선택 시 Read | Write |
| `EXEC GEMM` | 입력 Read / 출력 Write (반대 Buffer) | 공통 Word Offset 병렬 Read | Read | 사용 안 함 |
| `EXEC ARGMAX` | 지정 Buffer Read | 사용 안 함 | 사용 안 함 | 사용 안 함 |
| `LW` / `SW` | 사용 안 함 | 사용 안 함 | 사용 안 함 | Read / Write |

### Block Transfer 구현 기준

- 최초 버전은 **워드 단위 직렬 Read → 응답 수령 → Write**로 구현해도 됨. LOAD의 읽기 대상은 외부 DMEM, 쓰기는 내부 SRAM; STORE는 반대. 소스 읽기 응답이 등록된 뒤에만 목적지 Write; 한 요청의 마지막 Write가 완료되어야 `done`.
- 한 명령어는 한 내부 SRAM Bank에서 시작/끝나야 함. 전송 중 주소는 내부 로컬 word cursor로 증가하며, `rs1/rs2/rs3` GPR 원본은 불변.
- 추후 읽기/쓰기를 Word Pipeline으로 겹치는 최적화는 **동작/주소/종료/Timer 규칙을 보존하는 경우만 허용**, 초기 Codex 구현 단계에서는 생략.

## 4. GEMM 실행 경로 재구성

Phase 5 구현 승인은 [14번 결정](14_phase5_decisions.md)을 따른다. CSR file의 10개 설정을 병렬 출력하고 Instruction Controller에서 원자적 Snapshot → CHECK → START → WAIT를 수행한다. 검증 전 Engine start/메모리 접근/Timer active는 금지한다.
독립 GEMM Engine은 기존 unpack/MAC/Accumulator를 연결하고, layer 없는 Controller가 PREP 1edge → RUN → DRAIN → 완료 → IDLE로 실행한다. 최종 Write 이후에만 done을 알린다.
Wrapper의 기존 GEMM bank별 물리 포트를 사용하며, 주소는 축소 전에 전체 설정/끝 주소 및 실행 중 접근을 검사한다. 입력/출력은 반대 Buffer이고 Weight 4 bank는 같은 offset으로 병렬 Read한다.


### 현재 구조

현재 `control_unit.sv`는 `start → FC1 → FC2 → FC3 → ARGMAX → done` 자동 진행. `layer_config_lut.sv`가 고정 3 Layer 설정을 제공하며, `control_fsm.sv`와 `read_issue_control.sv`에 `layer_index`와 ARGMAX 자동 전이가 들어 있다.

### 새 구조

- **Instruction Controller**는 `EXEC GEMM` 1개를 발행하고 `gemm_done`을 기다린다.
- D-01: CSR write 시 RW 원본 32bit 보존, 실행 설정값 검증은 EXEC snapshot 시에만 수행한다. D-02: 짧은 K bias staging은 현재 제외, K=4는 선행 오류가 없으면 실행 전 INVALID_CONFIG 및 start/write 금지. 정식 지원 하한 K=8은 Phase 5 경계 검증 후 사용자 승인으로 확정했다.
- **GEMM Controller**는 CSR Snapshot(`SRC0/1/DST/BIAS`, `M,N,K`, Shift/Mode)으로 입력 워드 수(`K/4`), 출력 그룹 수(`ceil(N/4)`), Weight/Bias 시작 Word Offset, 핑퐁 Buffer 선택을 정한다.
- **GEMM FSM**은 `IDLE→PREP→RUN→DRAIN→DONE`으로 한 레이어만 실행; `DRAIN`은 최종 출력 SRAM Write 에지가 완료되었음을 보장.
- 기존 `input_word`(8bit), `output_group`(7bit) counter는 재사용하고 **layer counter는 제거**. `address_generator`는 `SRC1_BASE`, `BIAS_BASE`와 CSR 파생값에 따라 계산하도록 수정.
- 기존 `pipeline_control`의 R+1~R+6 제어 지연, `mac_input_valid`, `bias_load`, `result_load`, `out_we`는 최대한 그대로 유지. `read_issue_control`의 layer 조건/출력 종료 조건만 설정 기반으로 수정.
- `mac_array.sv`, Dot-product, `accumulator_postprocess.sv`, Bias alignment, ReLU, Shift, Saturation은 **계산 규칙/지연 변경 금지** (실제 문제가 재현되었을 때만 별도 승인 후 수정).
- `SRC1_BASE`는 W0 주소이지만 weight 데이터는 W0..W3 **동일 offset**에서 병렬로 읽음. 이 제약과 Weight Bank 파일별 packing은 Python 및 ISA 문서에 명시.

### 기존 3-stage MAC 확정 지연 (읽기 상승 에지 R 기준)

| 시점 | 작업 |
|---|---|
| R | Input + Weight BRAM Read |
| R+1 | MAC 입력/가중치 레지스터 + input_valid 1단 |
| R+2 | 32bit 곱 결과 + valid 2단 |
| R+3 | Adder Tree 부분합 + valid 3단 |
| R+4 | Accumulate |
| R+5 | 완료된 accumulator 결과 레지스터 Capture / 다음 Bias 초기화 |
| R+6 | 출력 32bit Word를 Output Buffer에 Write |

**한 그룹 사이 읽기 공백 1클럭** 및 마지막 그룹의 Drain을 유지한다. 다음 `EXEC GEMM`은 이전 출력 쓰기 완료 후에만 시작. 과거 전체 3-layer의 고정 cycle count는 새 ISA 제어 오버헤드를 포함하지 않으므로 새 전체 프로그램의 예상 클럭으로 직접 사용하지 않는다.

## 5. ARGMAX 독립 엔진

- 기존 `argmax_unit.sv`(byte_select4, signed_compare8, argmax_tracker)를 가능한 한 재사용.
- 기존 `argmax_control/argmax_schedule`은 `state=ARGMAX`와 `class_index<=9`로 고정돼 있음. 이를 `argmax_start`, `ARG_SRC`, `ARG_LEN(1..10)`, `argmax_done` 기반으로 바꿔 독립 Engine으로 구성.
- Read 1clk latency 반영, `ARG_SRC` base word offset을 포함한 인덱싱. 동점은 lowest index. 마지막 임의 padding byte 무시. 결과는 32bit GPR rd에 zero-extend Writeback.
- 기존 `control_read_mux`는 GEMM/ARGMAX 전용 입력 포트 선택을 담당했지만 이제 SRAM ownership MUX와 역할이 중복될 수 있음. 통합/삭제는 회귀 테스트 통과 조건으로만 수행.

## 6. Instruction / Scalar / CSR / Timer

| 블록 | 내부 상태 | 핵심 역할 |
|---|---|---|
| `instruction_controller` | PC, instruction register, FSM, halt | 외부 IMEM Fetch→Decode→Execute→WB; Branch/Jump 처리, 순차 완료 대기 |
| `register_file` | r0..r7 | 32bit 읽기/쓰기, r0=0, invalid GPR Fault |
| `scalar_alu` | 조합 | ADD, ADDI, equality comparison, 주소 계산, JAL link |
| `csr_file` | 설정·Status/Code | `SETI/CSRW/CSRR`, Snapshot, Read-only CSR 보호 |
| `perf_timer` | count, armed, overflow | TSTART/TSTOP, LOAD/GEMM `engine_active`만 Count |
| `block_transfer` | src, dst, remaining, phase | 32bit word 복사, 양쪽 메모리 R/W, bounds/complete |
| `gemm_controller` | counters, FSM, pipeline tags | 1 GEMM 실행, MAC Read/Write 스케줄, done |
| `argmax_engine` | index, read/compare phase | 가변 1~10 signed INT8 비교, 결과 |

Phase 2 구현: CSR file은 access_en/write_request로 주소·권한을 확인하고 별도 commit_en에서만 원본 32bit를 저장한다. Phase 5에서 GEMM 원자적 Snapshot과 실행 전 설정 검증을 추가했다. ARGMAX Snapshot/검증은 후속 범위다. PERF/STATUS/ERROR CSR은 live read다. Timer는 load_engine_active/gemm_engine_active 두 qualified 입력의 OR만 센다. Phase 3의 npu_top은 실제 Block Transfer LOAD active를 연결하며 GEMM active는 Phase 5의 실제 Engine 실행 PREP~최종 Write에 연결한다. 별도 TB의 기존 테스트용 activity 입력은 유지한다. 신규 npu_memory_wrapper는 기존 single_port_bram 7개를 같은 깊이와 1clk read로 재사용하고 XFER/GEMM/ARGMAX 포트를 분리한다. 새 output data register는 없으며 GEMM은 Phase 5에서 연결했으며 ARGMAX 엔진은 현재 비활성이다. 외부 DMEM은 byte address의 32bit Single-Port 고정 동기 read이고, read R 수락 → R+1 capture → R+2 write로 직렬 전송한다.

Phase 4 구현: Controller에서 unsigned Base + signed imm12를 33bit로 계산하여 정렬 → 산술 wrap → Region → 용량 Bounds를 검사한다. MEM_REQ에서 Scalar 요청, XFER_WAIT에서 기존 Block Transfer 요청을 조합 선택한다. 응답 저장소나 외부 포트/프로토콜을 추가하지 않는다. LW는 read 수락 R 다음 R+1에 GPR writeback/PC 전진하며, SW는 write R 후 R+1에 완료한다. 대기 중 다음 Fetch/GPR/CSR 갱신은 차단한다. 기존 7개 SRAM/Wrapper 및 Block Transfer RTL은 보존했다.

### Instruction Controller FSM 권장

`IDLE → FETCH_REQ → FETCH_WAIT/DECODE → (SCALAR_EXEC / CSR_EXEC / XFER_WAIT / GEMM_WAIT / ARGMAX_WAIT / SYSTEM_EXEC) → COMMIT_PC → FETCH_REQ`, 별도 `HALTED`/`FAULT_HALT`.

- Read Request를 수락한 에지와 명령어 register에 안전하게 capture하는 에지를 분리.
- NPU 장기 명령에는 `start` 1회만 내보내고, 해당 엔진의 `done`이 최종 메모리 Write 완료 후 1회만 올라와야 함.
- scalar `LW`는 외부 DMEM read 응답 뒤 `rd` Writeback; `SW`는 write 수락 에지 이후 완료 처리.
- 대기 상태에 있는 동안 중복 start, PC 전진, GPR/CSR writeback 금지.

## 7. 파일별 기존 RTL 활용 계획

| 현재 파일/그룹 | 초기 구현 판단 | 이유 |
|---|---|---|
| `controller/mlp_top.sv` | 레거시 테스트 기준선으로 보존, 신규 `npu_top.sv` 도입 권장 | 기존 TB와 비교 가능한 상태 유지; 최종 synthesis top은 신규 Top 선택 |
| `controller/control_unit.sv` | 현 동작 보존 후 내용 일부를 `gemm_controller`로 추출/개편 | 3-layer 자동 실행과 ARGMAX 결합 제거 |
| `controller/control_fsm.sv`, `control_state_pkg.sv` | GEMM 전용 새 FSM 또는 수정 | layer/ARGMAX 자동 전이 제거 |
| `controller/layer_config_lut.sv` | 신규 경로에서 미사용 | 설정은 CSR; 레거시 Top 전용 파일로 남겨도 됨 |
| `controller/mlp_counters.sv` | 입력/출력 group 카운터 재사용/간소화 | layer counter 제거 |
| `controller/address_generator.sv` | 수정 | CSR base/length/offset 사용 |
| `controller/read_issue_control.sv` | 수정 | layer fixed 조건 제거, 동적 K/N bounds |
| `controller/pipeline_control.sv`, `pipeline_event_control.sv` | 최소 수정 | 3-stage MAC timing 유지 |
| `controller/argmax_control.sv`, `argmax_schedule.sv` | 수정 | ARG_SRC/LEN에 따른 독립 엔진 |
| `controller/argmax_unit.sv`, `argmax_tracker.sv` 등 비교 Datapath | 유지 | signed compare와 lowest-index tie 재사용 |
| `memory/memory_wrapper.sv` | 리팩터링/전용 wrapper 추가 | exec 중 block transfer write/read 및 주소 디코딩 필요 |
| `memory/memory_port_mux.sv` | 교체 또는 신규 `sram_port_mux.sv` | 기존 `busy` 2-way MUX는 부적합 |
| `memory/buffer_router.sv` | 재사용 가능; 주소 offset 지원 검토 | 입력/출력 반대 Buffer 선택 기능 유지 |
| `memory/tb_address_decoder.sv`, `tb_read_mux.sv` | 레거시 TB 전용으로 격리 가능 | 정상 ISA Data path는 사용하지 않음 |
| `memory/single_port_bram.sv` | 시뮬레이션 모델/기존 검증 유지 | 1clk read 동작 확정; FPGA 최종 BMEM IP wrapper 별도 |
| `mac_array/*`, `accumulator_postprocess/*`, `common/*` | 기본적으로 그대로 | 기존 연산 정확도와 파이프라인 보존 |
| `05_tb/controller/*` | 신규 NPU TB를 별도 작성 | IMEM/외부 DMEM HEX 모델, 결과 dump/compare 필요 |

**중요:** 이 표는 새 Top을 분리해 **레거시 파일을 보존하는 권장 구현 전략**이다. 파일 명칭/물리적 계층을 완전히 동일하게 유지하는 것은 ISA 기능 요구사항이 아니다.

## 8. 외부/내부 메모리 물리 현실과 FPGA

- DMEM 16 MiB에 MNIST 10,000개를 배치하는 것은 **시뮬레이션 모델**. 이를 Artix-7 내부 BRAM으로 모두 합성하는 설계가 아님. 실제 FPGA 구동 시에는 온보드 DDR/Host Streaming/외부 Storage Adapter 등 새로운 주변 시스템이 필요.
- 과제 조건상 최종 **NPU 내부 SRAM 7개**에 Block Memory Generator IP의 Native Single-Port 구성을 적용하고 Primitive Output Register 비활성화. 포트는 `clka/ena/wea/addra/dina/douta`를 대응시키고 Full-Word Write(별도 Byte Write 비활성화) 사용. Read-while-Write 데이터 Hold 계약에 맞도록 `NO_CHANGE`에 해당하는 메모리 Write Mode를 선택·검증. 동작은 `single_port_bram` 모델과 동일한 1clk Read로 맞추고 Simulation과 Post-Synthesis에서 확인.
- BRAM 내용은 Reset으로 초기화하지 않는다. `initial/$readmemh/$writememh`는 Testbench/외부 모델에만 사용, 합성 대상 코어에서는 사용 금지. 외부 데이터는 LOAD로 내부 SRAM에 적재.
- 성능·자원·Power/Timing 수치는 실제 Vivado 합성/배치배선 리포트를 통해서만 주장. MAC 변경 없이도 Address MUX/Decoder/CSR/ALU가 추가되므로 타이밍을 다시 측정해야 함.
