# Phase 1 — Scalar/Fetch 구현 및 검증 결과

작성일: 2026-11-24 (Asia/Seoul). 브랜치: `phase1/scalar-fetch-20261124`.
기준 커밋: `ebbaa86`. Phase 0 전용 브랜치에서 분기했다.
**Phase 1 Gate: PASS. Phase 2는 시작하지 않았다.**

## 1. 적용한 설계 결정과 범위

[07 설계 결정](07_design_decisions_phase0.md)을 우선 적용하고 01~04 명세·계획 및 README에 반영했다.
07번 D-03의 모호한 오류 이름은 후속 사용자 확정에 따라 **0x00000000 → INVALID_OPCODE(0x01)**로 명확히 했다.
새 Opcode/CSR/GPR/Error Code나 메모리 프로토콜은 추가하지 않았다.

| 결정 | 반영 | 이번 단계의 검증 범위 |
|---|---|---|
| D-01 | RW CSR 원본 32bit 저장, EXEC snapshot에서 범위 검사, 중간 설정값 조기 Fault 금지로 문서 수정 | CSR RTL·검증은 Phase 2이므로 미구현·미검증 |
| D-02 | K=4 실행 전 INVALID_CONFIG, start/SRAM write 금지; 짧은 K staging 제외; 지원 하한은 Phase 5에서 결정 | GEMM RTL·K 경계 검증은 Phase 5이므로 미구현·미검증 |
| D-03 | IMEM 할당 용량을 Top/TB 공통 elaboration 파라미터로 공유. TB 전체 IMEM zero fill. 미적재 0 명령어 오류 코드=0x01 | 64KiB와 256B 용량에서 내부/마지막 word/용량 밖 및 미적재 영역 검증 |
| D-04 | BEQ/BNE의 선택된 next PC만 검사. JAL 오류 시 link/PC write 차단 | taken/non-taken, misalign/bounds, link 불변 검증 |

구현 명령은 LUI/ADDI/ADD/BEQ/BNE/JAL/END 7개다.
CSR bank·Timer·LW/SW·LOAD/STORE·GEMM/ARGMAX·내부 SRAM은 이번 scalar skeleton에 포함하지 않았다.
후속 Phase의 정상 명령을 실행할 수 있는 완성된 v1.0 코어가 아니며, 현재 decoder는 미지원 명령을 Fault로 차단한다.
기존 Legacy MLP 경로, MAC 3-stage 산술·R→R+6 계약, SRAM 7개 구현 및 회귀 데이터는 그대로 보존했다.

## 2. 변경 파일

| 파일 | 변경 내용 |
|---|---|
| 01_isa_spec.md | 결정 우선순위, CSR 검증 시점, 짧은 K 제한, IMEM 용량 및 0 opcode 오류, 선택된 next PC/JAL 검증 |
| 02_architecture.md | Top/TB 용량 파라미터 및 결정 적용. 현재 Phase 1 skeleton 범위를 명시 |
| 03_implementation_plan.md | Phase 1 gate/fixture, Phase 2 D-01 및 Phase 5 D-02 검증 항목 반영 |
| 04_verification_plan.md | I-10 보완, I-11/12 추가, I-07 D-01 및 G-08 D-02 추가 |
| README.md | 결정 문서 우선순위와 현재 구현 범위/보고서 링크 |
| 07_design_decisions_phase0.md | 사용자가 추가한 결정 기록을 유지하고, 후속 확정된 0 opcode 오류 이름만 명확히 함 |
| 04_rtl/isa/npu_isa_pkg.sv (신규) | 명세에 있는 Opcode, Error/Status, memory base/default capacity 및 Phase 1 operation type |
| 04_rtl/isa/instruction_decoder.sv (신규) | 7개 명령 형식·immediate·사용하는 GPR 필드만 검사, encoding → GPR 오류 우선순위 |
| 04_rtl/isa/register_file.sv (신규) | 8×32bit, 비동기 low reset, 2 read/1 write, r0=0 |
| 04_rtl/isa/scalar_alu.sv (신규) | ADD/ADDI modulo-2^32, U immediate, equality, PC-relative branch/JAL 및 link |
| 04_rtl/isa/instruction_controller.sv (신규) | PC/IR, fixed-1clk Fetch FSM, blocking 실행, 최소 내부 Status/Error, END/Fault Halt |
| 04_rtl/controller/npu_top.sv (신규) | Scalar skeleton, 명세 Top 포트, 미사용 DMEM 출력 0 |
| 05_tb/npu/tb_npu_phase1.sv (신규) | 동기 IMEM 모델·zero fill, PC/명령어/GPR scoreboard, Halt/Reset/start/무부작용 검사 |
| 90_scripts/npu/run_phase1.py (신규) | directed fixture encoder·독립 Python ISA interpreter, 두 용량 프로파일, XSim/기존 회귀 호출·provenance |
| 08_phase1_report.md (신규) | 이 보고서 |

기존 RTL/TB/runner/target 목록/헤더는 수정하지 않았다.
새 assembler 전체, CSR 접근 포트, Timer 제어는 만들지 않았다.
Python encoder는 Phase 1 검산 fixture만 만들며 Phase 7 통합 assembler/scenario toolchain을 구현한 것이 아니다.

## 3. 포트·제어 및 Timing

신규 npu_top은 명세의 clk/rst_n/start, busy/done/fault,
imem_en/imem_addr[31:0]/imem_rdata[31:0],
dmem_en/dmem_we/dmem_addr[31:0]/dmem_wdata[31:0]/dmem_rdata[31:0]를 사용한다.
IMEM_BYTES 기본 65536, DMEM_BYTES 기본 16777216이며 base는 ISA package의 0/0x10000000이다.
DMEM 포트는 Phase 1에서 비활성이며 용량 파라미터만 미래 인터페이스에 맞춰 둔다.

내부에 state, pc, instruction, register_write, decode_error, fetch_error, next_pc_error를 둔다.
status[31:0]/error_code[7:0]는 내부 제어 상태이며 공개 CSR 접근이나 새 Top debug 포트가 아니다.
TB는 이 상태와 GPR을 관찰만 한다. 계층 경로로 값을 쓰거나 내부 SRAM을 직접 초기화하지 않는다.

| 에지/상태 | 동작 |
|---|---|
| start 수락 | IDLE → FETCH_REQ, busy=1, PC=0 |
| R / FETCH_REQ | PC 정렬·용량 검사 통과 때만 imem_en. 외부 TB memory가 주소를 샘플링하고 R 직후 rdata 갱신 |
| R+1 / FETCH_WAIT | imem_rdata를 IR에 capture |
| R+2 / EXECUTE | instruction encoding/GPR 및 실제 선택된 next PC 검사. 통과 시 GPR/PC 갱신 |
| END | PC를 해당 END 주소에 유지, STATUS=1, done 정확히 1cycle, 이후 Halt |
| Fault | PC/GPR 갱신 없이 STATUS=2, 오류 sticky, done=0, fault=1, 이후 Halt |

한 명령마다 Fetch/수신/실행을 직렬화한다. IMEM 요청 에지에서 응답을 소비하지 않는다.
주소 계산은 33bit로 확장하고 범위 비교는 충분한 폭으로 수행하여 음수 target의 wrap을 허용하지 않는다.
정렬 오류는 Bounds보다 우선하며, instruction encoding → GPR → 정렬/Bounds 순서를 지킨다.
JAL을 포함하여 유효성 검사에 실패한 명령은 GPR에 쓰지 않는다.
END는 다음 명령을 실행하지 않으므로 마지막 유효 IMEM word에 위치해도 정상 종료한다.
일반 명령의 선택된 sequential next PC가 범위 밖이면 해당 실행 단계에서 Fault를 내고 PC/GPR commit을 차단한다.

합성 RTL에는 메모리 초기화용 initial/readmemh/writememh를 넣지 않았다.
기존 MAC이나 BRAM read latency에는 영향을 주지 않는다.

## 4. 실행 명령·결과

저장소 루트에서 재현:

~~~powershell
# 최종 Scalar/Fetch 검증: PATH에서 Vivado 검색
python -B 90_scripts/npu/run_phase1.py

# Vivado bin을 지정하고 기존 단위·RTL 회귀까지 실행
python -B 90_scripts/npu/run_phase1.py --legacy --vivado-bin D:/AMDDesignTools/2025.2/Vivado/bin
~~~

실제 실행은 먼저 `python -B 90_scripts/npu/run_phase1.py --legacy`로 전체 suite를 시작했다.
이후 실패 로그에 실제값·기대값을 보강하고 도구 경로의 고정 기본값을 제거한 최종 TB/runner로
`python -B 90_scripts/npu/run_phase1.py --vivado-bin D:/AMDDesignTools/2025.2/Vivado/bin`를 재실행했다.
그 사이 RTL은 바뀌지 않았고 Legacy 회귀는 별도 디렉터리에서 계속 진행했다.
최종 directed source snapshot과 현재 신규 코드의 hash 일치를 확인했다.

도구: Vivado/XSim 2025.2. Python: 3.14.5 (tags/v3.14.5:5607950, May 10 2026, 10:43:50) [MSC v.1944 64 bit (AMD64)].
실행 ID의 날짜는 기존 도구의 UTC 형식이며, 사용자 날짜는 2026-11-24다.

| 검증 | 결과 | 상세/로그 |
|---|---|---|
| Phase 1 IMEM 65536 B | PASS | 61 cases / 432 steps / 25100 checks; [simulate.log](../../07_runs/npu_phase1_20261123_173326_603893Z/logs/65536/simulate.log) |
| Phase 1 IMEM 256 B | PASS | 61 cases / 432 steps / 25100 checks; [simulate.log](../../07_runs/npu_phase1_20261123_173326_603893Z/logs/256/simulate.log) |
| 기존 Python unit | PASS: 27 tests | [runner 15](../../07_runs/npu_phase1_20261123_172902_627661Z/runner_unit.log), [golden 12](../../07_runs/npu_phase1_20261123_172902_627661Z/golden_unit.log) |
| Legacy control_unit | PASS | 29478 vectors / 442054 checks; [simulate.log](../../07_runs/control_unit_xsim_20261123_172917_599569Z/logs/simulate.log) |
| Legacy memory_wrapper | PASS | 265018 vectors / 1708039 checks; [simulate.log](../../07_runs/memory_wrapper_xsim_20261123_172937_282724Z/logs/simulate.log) |
| Legacy mac_array | PASS | 265021 vectors / 1325105 checks; [simulate.log](../../07_runs/mac_array_xsim_20261123_173147_840559Z/logs/simulate.log) |
| Legacy accumulator_postprocess | PASS | 265019 vectors / 265019 checks; [simulate.log](../../07_runs/accumulator_postprocess_xsim_20261123_173406_936907Z/logs/simulate.log) |
| Legacy mlp_top | PASS | 265018 vectors / 913476 checks; [simulate.log](../../07_runs/mlp_top_xsim_20261123_173438_240481Z/logs/simulate.log) |

**최종 Phase 1 directed 합계:** 61개 시나리오 × 2개 용량, 864개 명령어 실행 기록, 50,200회 비교, 오류 0.
기록에는 END/Fault 검출 step도 포함하며, 모든 step이 GPR write를 commit한다는 뜻은 아니다.
Python 기준 모델은 정수 PC 산술·word decoding·GPR 상태로 기대값을 계산하고 RTL 출력으로 기대값을 만들지 않는다.

확인한 항목:

- signed imm12 경계, 음수/양수 ADDI, ADD wrap/alias, LUI 상위 비트, r0 쓰기 무시.
- BEQ/BNE의 taken/non-taken 및 뒤로 분기하는 루프, JAL 전방/후방·link·rd=r0.
- U/J/immediate 비트 위치를 미사용 GPR 필드로 오인하지 않음.
- r8/r31의 rd/rs1/rs2 불법 접근, opcode/encoding/GPR/정렬/Bounds 오류 우선순위.
- non-taken의 잘못된 후보 target 무시, taken misalign/out-of-bounds, JAL 오류 시 기존 link 값 보존.
- 마지막 유효 word END, 용량 밖 target의 요청 차단, 미적재 word fetch 후 0 opcode Fault.
- request R → IR capture R+1, 명령어별 PC와 r0~r7의 bit-exact 비교.
- busy 중 start 무시, END/Fault Halt에서 start 무시·추가 Fetch/DMEM write/GPR 변화 없음.
- 매 시나리오 Reset 및 Halt 뒤 재시작, Fetch가 진행 중일 때 비동기 Reset 취소.
- seed 1000~1007의 제한된 random scalar 프로그램. 모든 프로그램이 종료해야 PASS.

기존 회귀는 기존 run.py와 sim_targets.json을 그대로 사용했다.
단위 테스트는 runner 15개 + golden 12개이며 새 RTL 기능 검증과 구분한다.
Legacy Top은 현재 헤더 sample 7/prediction 9를 사용하며 중간 layer write와 최종 memory readback을 비교한다.
이번에 10,000장 정확도·합성·배치배선·power·waveform은 실행하지 않았다.

## 5. 로그·무변경 검증·diff

- [최종 directed metrics](../../07_runs/npu_phase1_20261123_173326_603893Z/metrics.json)
- [최종 source/data hash 및 실제 도구 명령](../../07_runs/npu_phase1_20261123_173326_603893Z/manifest.json)
- [64KiB PC/명령어 trace 및 scoreboard 로그](../../07_runs/npu_phase1_20261123_173326_603893Z/logs/65536/simulate.log)
- [256B 로그](../../07_runs/npu_phase1_20261123_173326_603893Z/logs/256/simulate.log)
- [전체 suite/Legacy 결과](../../07_runs/npu_phase1_20261123_172902_627661Z/metrics.json)
- [최종 종합/Legacy 보존 확인](../../07_runs/npu_phase1_20261123_173326_603893Z/completion.json)

구현 전 기존 소스·테스트·헤더·설정 74개와 최종 파일의 SHA-256을 비교했다: 변경/삭제 0개.
기존 tracked RTL/TB/90_scripts의 diff는 없다. 추가 파일만 별도로 둔다.
기존 .gitignore에 따라 07_runs/99_build 산출물은 로컬 보존이며 일반 git add로 추적되지 않는다.
기존 보고서·과거 실행 결과는 수정하지 않았다. 커밋은 이번 요청 범위에서 자동 생성하지 않았다.

## 6. 남은 문제와 다음 승인 경계

Phase 1 Gate에서 재현된 RTL 기능 실패: 없음.
D-03의 오류 이름에 대한 추가 결정은 사용자 응답으로 해결했고 명세/07 문서에 반영했다.
현재 Phase 1 범위에서 추가 사용자 설계 결정이 필요한 안건은 없다.

- Phase 2: D-01 CSR 저장/검증 시점, SETI/CSRR/CSRW, Timer 및 RO CSR readback 구현·검증.
- Phase 3 이후: 실제 DMEM 전송 및 Fault, SRAM ownership/LOAD·STORE, CSR 기반 GEMM/ARGMAX.
- Phase 5: D-02에 따라 K=4 거부 및 K=8/12/16/32 경계 분석으로 정확한 지원 하한 확정. 현재 지원 하한을 임의로 정하지 않았다.
- 새 npu_top의 합성/FPGA timing 및 전체 NPU 응용 정확도는 미검증.

**Phase 1만 완료했으며, 사용자 승인 전 Phase 2로 진행하지 않는다.**
