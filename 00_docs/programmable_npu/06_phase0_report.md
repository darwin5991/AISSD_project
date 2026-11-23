# Phase 0 — 기존 RTL 기준선·명세 차이·검증 결과

작성일: 2026-11-24 (Asia/Seoul). 기준 커밋: `2e89b8e994982094a36172a3fd2f65d4a9edaff7`.
작업 브랜치: `phase0/programmable-npu-baseline-20261124`.
로그 실행 ID는 기존 실행기의 UTC 형식을 유지하므로 `20261123_...`로 표시된다.

## 1. 수행 범위와 판정

Phase 0만 수행했다. AGENTS.md, programmable_npu의 README·01~05 문서, 기존 architecture.md·mac_input_pipeline.md 및 지정 RTL/TB/실행기를 읽었다.
기존 RTL·TB·생성 헤더·Python 소스·과거 실행 기록을 수정하거나 삭제하지 않았다. Phase 1 RTL은 작성하지 않았다.
이번 변경은 이 진단 문서와 새 실행 로그·검증 메타데이터·기존 recovery TB 재현 스크립트뿐이다. 새 포트·제어 신호는 없다.

**Phase 0 Gate: PASS**. 기존 테스트 재실행, 재현 명령·로그, 소스 무변경 확인, R→R+6 추적 표를 확보했다.
이는 새 ISA 구현의 PASS가 아니다. 아래 의사결정 항목은 미확정 상태이며, 사용자 승인 전 Phase 1로 진행하지 않는다.

작업 시작 시 main 브랜치에는 tracked 파일 변경이 없었고, `AGENTS.md`, `00_docs/programmable_npu/`, `programmable_npu_codex_v1.0.zip`가 untracked였다.
문서나 패키지를 임의로 stage/commit하지 않았다.

## 2. 현재 RTL 구조와 재사용 범위

현재 합성 RTL은 총 45개 SV 파일: controller 20, memory 6, mac_array 4, accumulator_postprocess 12, common 3이다.
현재 경로는 `start → FC1 → FC2 → FC3 → ARGMAX → done → IDLE`인 고정 MLP다.

| 영역 / 실제 파일 | 확인한 현재 동작 | 새 명세와의 차이 / 향후 조치 |
|---|---|---|
| controller/mlp_top.sv | start/busy/done, prediction[3:0], tb_en/we/addr[19:0]/wdata/rdata. Memory·MAC·누산기·Control 및 조합 unpack 연결 | IMEM/DMEM/fault 포트 없음. Legacy Top 보존, 신규 npu_top 추가 |
| control_unit.sv, control_fsm.sv, control_state_pkg.sv | 5-state FSM, 레이어 0~2 자동 진행 후 ARGMAX. 종료 후 재시작 가능. 미사용 상태는 IDLE 복구 | 명령어별 실행·END/Fault sticky Halt와 다름. 새 Instruction FSM·GEMM FSM 필요. 기존 recovery 정책을 ISA Fault에 복사하면 안 됨 |
| layer_config_lut.sv | FC1/2/3의 길이·base·shift·ReLU 고정 | 신규 경로에서는 CSR snapshot 사용. Legacy LUT 유지 |
| mlp_counters.sv, address_generator.sv | layer[1:0], input_word[7:0], output_group[6:0], weight[14:0], bias[7:0]. 입력/출력 buffer base offset 없음 | 새 GEMM에서 K_words, output_groups와 base offset 계산. 넓은 산술로 범위 검사 후 물리 주소 폭으로 축소 |
| read_issue_control.sv, pipeline_control.sv, pipeline_event_control.sv | 그룹 간 읽기 공백 1클럭, input valid +1, 결과/다음 bias +5, write/주소/완료 +6 | 정상 FC 지연 재사용. 짧은 K의 bias 처리와 동적 종료 조건은 별도 검토 필요 |
| argmax_control/schedule.sv, control_read_mux.sv | 레이어 상태 및 길이 10, B buffer에 결합 | 독립 start/done, A/B와 ARG_SRC offset, ARG_LEN=1~10 필요 |
| argmax_unit/tracker/update.sv, signed_compare8.sv, byte_select4.sv | signed strict >, 동점이면 기존의 작은 인덱스 유지 | 비교 datapath 재사용. 결과를 GPR 32bit로 zero-extend |
| memory_wrapper.sv, memory_port_mux.sv | busy=0 TB / busy=1 core. Weight/Bias core_we=0, weight 4개 bank의 주소/enable 공통 | 실행 중 개별 bank LOAD/STORE 불가. 새 SRAM ownership MUX·wrapper·decoder 필요 |
| buffer_router.sv | 반대 A/B로 read/write. in_addr 8bit, out_addr 7bit, B RAM은 low 7bit 주소 | 반대 buffer 규칙 재사용. offset 포함 주소와 bounds 검사 추가. 출력 A의 word 128~195 등은 기존 7bit out_addr를 그대로 쓰면 표현 불가 |
| tb_address_decoder.sv, tb_read_mux.sv | 20bit TB 주소에서 bank/word 선택. 합법 주소만 지원; alignment/depth 오류 정책 없음 | ISA용 32bit 영역/정렬/실제 깊이 검사기로 사용 불가. Legacy 전용 보존 |
| single_port_bram.sv | 동기 write, registered read 1clk, en=0/write 때 rdata hold. 저장 배열 reset/초기화 없음 | 동작 모델 재사용. 최종 BMEM IP는 Phase 8에 별도 적용·검증 |
| mac_array/* | INT8 operand → product32 → sum32의 3단. valid=3단, invalid 데이터도 매 클럭 진행 | 산술·파이프라인 변경 필요 없음 |
| accumulator_postprocess/* | bias sign extension/shift → int32 누산 → 독립 결과 register → ReLU → arithmetic shift → signed INT8 saturation/packing | 산술·latency 변경 필요 없음. bias_load와 psum_valid 중첩 금지 |
| common/*, unpack_int8x4.sv | 비동기 active-low reset, 기존 조합 연산/packing | 재사용 |

SRAM 물리 깊이와 폭은 새 명세와 일치한다.

| SRAM | ISA byte base | 실제 words | 실제 bytes | 물리 word 주소 폭 |
|---|---:|---:|---:|---:|
| A | 0x80000000 | 196 | 784 | 8 |
| B | 0x80020000 | 128 | 512 | 7 |
| W0 | 0x80040000 | 29280 | 117120 | 15 |
| W1 | 0x80060000 | 29280 | 117120 | 15 |
| W2 | 0x80080000 | 29280 | 117120 | 15 |
| W3 | 0x800A0000 | 29280 | 117120 | 15 |
| Bias | 0x800C0000 | 163 | 652 | 8 |

7개 모두 Single-Port, 32bit, 1clk 동기 읽기다. 예약된 128KiB 창 전체를 실제 SRAM으로 간주하면 안 된다.
주소 폭을 줄이기 전에 bounds를 검사해야 B 주소 alias, weight 주소 wrap 등을 막을 수 있다.
합성 RTL의 실행 코드에서 메모리 초기화용 initial/$readmemh/$writememh는 발견되지 않았다.
현재는 ram_style=block, Weight RAM_DECOMP=area인 추론 RAM이며, BMEM IP 인스턴스/생성 설정은 아직 없다.

## 3. MAC read(R) → output write(R+6) 추적

아래는 해당 입력의 읽기 에지 기준이다. result/write 행은 **그룹의 마지막 입력 읽기 R**에 적용한다.
첫 bias 초기화는 그룹 0의 첫 bias 읽기 다음 에지이며, 결과/다음 bias 일정과 구분한다.

| 상승 에지 | 데이터 동작 | 코드상의 제어/근거 |
|---|---|---|
| R | input 및 weight RAM이 주소 수락, 에지 뒤 rdata 갱신 | single_port_bram의 registered read |
| R+1 | MAC input/weight register capture | pipeline_control u_mac_valid DEPTH=1; MAC input registers. 첫 bias도 first_read+1 |
| R+2 | signed8 곱을 sign-extend한 product32 register capture | dot_product4 u_product |
| R+3 | 2-level tree 결과 partial_sum32 및 psum_valid 갱신 | dot_product4 u_partial_sum; mac_array u_valid DEPTH=3 |
| R+4 | 직전 에지의 유효 partial_sum 누산 | psum_valid를 accumulator32에 직접 연결 |
| R+5 | 완료 accumulator를 result32에 저장, 다음 그룹 bias 초기화 가능 | u_result_load DEPTH=5, u_next_bias DEPTH=5 |
| R+6 | 조합 후처리 결과 word를 반대 buffer에 기록 | u_output_write/u_output_address/u_layer_stored DEPTH=6 |

delay_line 출력은 목적 레지스터가 샘플링할 에지 전에 안정된다. RAM 응답을 요청 에지에서 소비하는 구조가 아니다.
bias_load와 result_load는 같은 에지에 올 수 있지만 bias_load와 psum_valid는 겹치면 안 된다.
현재 FC의 K_words는 196/128/32로 충분히 길다. 새 ISA의 짧은 K에서는 아래 D-02를 해결해야 한다.
이번 회귀는 기존 scoreboard의 데이터·제어 시점을 확인했으며 별도 waveform을 생성하지 않았다.

## 4. 이번에 실제 실행한 검증

실행 환경: Vivado/XSim 2025.2, 실제 테스트 Python은 manifest/명령에 기록된 3.14.5 (tags/v3.14.5:5607950, May 10 2026, 10:43:50) [MSC v.1944 64 bit (AMD64)]이다.
정확한 Python 버전은 [phase0_metrics.json](../../07_runs/programmable_npu_phase0_20261123_164539_851093Z/phase0_metrics.json)을 따른다.
읽기 전용 점검 셸의 python은 Anaconda 3.13.9였으나, 권한 승인 후 실행 환경에서는 다른 Python이 선택되었다.
실행은 기존 runner를 사용했고 golden 재생성·헤더 교체·waveform 기록은 하지 않았다.

저장소 루트에서 재현:

~~~powershell
python -B -m unittest discover -s 90_scripts/tests -v
python -B -m unittest discover -s 03_model/golden/tests -v
python -B 90_scripts/run.py control_unit --vivado-bin D:/AMDDesignTools/2025.2/Vivado/bin
python -B 90_scripts/run.py memory_wrapper --vivado-bin D:/AMDDesignTools/2025.2/Vivado/bin
python -B 90_scripts/run.py mac_array --vivado-bin D:/AMDDesignTools/2025.2/Vivado/bin
python -B 90_scripts/run.py accumulator_postprocess --vivado-bin D:/AMDDesignTools/2025.2/Vivado/bin
python -B 90_scripts/run.py mlp_top --vivado-bin D:/AMDDesignTools/2025.2/Vivado/bin
python -B 07_runs/programmable_npu_phase0_20261123_164539_851093Z/reproduce_recovery.py
~~~

reproduce_recovery.py는 이미 존재하던 tb_control_unit_recovery.sv를 복사해 컴파일하는 실행용 스크립트다.
재실행 때 이 스크립트를 새 audit 폴더로 복사해야 한다. 기존 recovery 결과 폴더 덮어쓰기를 거부한다.
기존 run.py도 실행마다 새 디렉터리를 만들며, 헤더 hash·generation manifest·format·타이밍을 검사한다.
Recovery TB는 sim_targets.json에 등록되어 있지 않아 별도로 실행했다.

| 검증 | 결과 | 비교 범위 / 로그 |
|---|---|---|
| Runner unit | PASS: 15 tests | [runner_unit.log](../../07_runs/programmable_npu_phase0_20261123_164539_851093Z/runner_unit.log) |
| Golden unit | PASS: 12 tests | [golden_unit.log](../../07_runs/programmable_npu_phase0_20261123_164539_851093Z/golden_unit.log) |
| control_unit | PASS | 29478 vectors; 442054 checks; errors=0; [simulate.log](../../07_runs/control_unit_xsim_20261123_164545_905483Z/logs/simulate.log) |
| memory_wrapper | PASS | 265018 vectors; 1708039 checks; errors=0; [simulate.log](../../07_runs/memory_wrapper_xsim_20261123_164608_791186Z/logs/simulate.log) |
| mac_array | PASS | 265021 vectors; 1325105 checks; errors=0; [simulate.log](../../07_runs/mac_array_xsim_20261123_164816_963735Z/logs/simulate.log) |
| accumulator_postprocess | PASS | 265019 vectors; 265019 checks; errors=0; [simulate.log](../../07_runs/accumulator_postprocess_xsim_20261123_165033_967604Z/logs/simulate.log) |
| mlp_top | PASS | 265018 vectors; 913476 checks; errors=0; [simulate.log](../../07_runs/mlp_top_xsim_20261123_165105_428104Z/logs/simulate.log) |
| Legacy recovery TB | PASS | unused states 5/6/7, 3 cases; [simulate.log](../../07_runs/programmable_npu_phase0_20261123_164539_851093Z/recovery/logs/simulate.log) |

모든 기능 시뮬레이션은 실제 RTL을 선택했고 behavioral 대체 모듈이 없다.
단위 테스트 27개는 Python 실행기/생성기 검증이며 RTL PASS로 대체하지 않았다.
Control/Memory/MAC/누산기 standalone는 sample 0, 현재 Top 헤더는 sample 7이다. sample 7의 기대 prediction은 9다.
Top은 초기 117607word write/read, FC1 128word·FC2 32word·FC3 3word의 write probe, 마지막 buffer 324word와 busy/done/prediction을 비교한다.
현재 테스트가 새 ISA, 모든 K/N/shift 경계, 잘못된 메모리 주소, 전체 MNIST 정확도까지 검증한다는 뜻은 아니다.

소스 무변경 확인: 74개 기존 RTL/TB/헤더/Python/설정 파일을 SHA-256 비교, 변경/삭제 0개.
[실행 명령·종료 코드](../../07_runs/programmable_npu_phase0_20261123_164539_851093Z/test_results.json),
[소스 무결성](../../07_runs/programmable_npu_phase0_20261123_164539_851093Z/source_integrity.json),
[recovery 로그](../../07_runs/programmable_npu_phase0_20261123_164539_851093Z/recovery/logs/simulate.log)를 보존했다.

Recovery 실행 보조 명령은 최초 Windows 인용 오류로 Python 시작 단계에서 SyntaxError가 났다.
호출을 고친 뒤 실제 compile/elaborate/simulate 및 3개 상태 검사가 PASS했다. RTL 결함으로 분류하지 않았다.

## 5. 과거 기록과 문서 상태의 차이

architecture.md, mac_input_pipeline.md, verification.md, 04_rtl/README.md 및 다수 RTL 주석에는 아직 “3-stage 미검증”이 남아 있다.
하지만 실제 07_runs에는 2026-11-10의 3-stage standalone·Top 검증 및 합성/구현과 2026-11-17의 BRAM 최적화 검증 기록이 있다.
따라서 “기존 결과 전부 2-stage”로 해석하면 틀리다. 본 단계에서는 기존 문서를 덮어쓰지 않고 이 보고서에 차이를 기록한다.

가장 최근 완료된 [BRAM area 실행](../../07_runs/mlp_top_bram_area_20261117_034211_860987Z/metrics.json)은:

- RTL samples 0/4/7 PASS, routed functional samples 0/4/7 PASS.
- 100MHz OOC post-route 내부 setup slack +0.130ns, hold +0.164ns.
- BRAM 109.5 tiles/135 (81.11%), RAMB36=104, RAMB18=11; routed LUT=3025, register=907.
- 해당 실행의 snapshot에 있는 RTL 45개와 TB 2개가 현재 파일과 hash 일치한다.
- 해당 값은 **과거 Legacy 결과**다. 이번 단계에서 합성·배치배선을 재실행하지 않았고 새 NPU의 timing/자원으로 인용할 수 없다.
- manifest에서 boundary timing/reset release safety는 검증되지 않았다고 구분한다. routed functional은 지연을 넣은 gate-level timing simulation과 구분해야 한다.

과거 첫 BRAM area 시도(032639)는 ERROR, 다음 완료 시도(034211)는 PASS다. 실패 기록은 보존한다.
현재 .gitignore는 07_runs 전체와 로컬 Python tests 디렉터리를 제외한다. 따라서 로그는 로컬 보존이며, 이 요약 문서와 달리 일반 git add만으로 추적되지 않는다.
별도 보관/공유 시 로그·생성 데이터·실행 snapshot이 함께 있어야 재현 가능하다.

## 6. 누락 기능과 설계 의사결정

### 6.1 명세상 예정된 기능 차이 — Legacy 결함과 구분

PC/Fetch/Decoder/GPR/ALU/CSR/Timer/ISA Fault Halt/외부 IMEM·DMEM/block transfer/독립 GEMM·ARGMAX는 현재 미구현이다.
04_rtl/isa와 05_tb/npu 디렉터리도 없다. 이는 현재 fixed MLP의 검증 실패가 아니라 새 설계의 구현 범위다.
Legacy의 IDLE 복귀, 무검사 TB decoder, 고정 LUT를 새 ISA의 정상 동작으로 그대로 사용해서는 안 된다.

ISA §3.4의 8개 기계어 검산 벡터를 필드 산술로 재계산해 표와 일치함을 확인했다.
FC2/FC3 weight byte base도 각각 0x80040000 + 25088×4 = 0x80058800,
0x80040000 + 29184×4 = 0x8005C800으로 현재 LUT와 일치한다.
이 검산은 decoder/assembler 구현 테스트가 아니다.

### D-01 — CSR 설정값의 조기 Fault 허용 문구 (Phase 2 전 확정)

ISA §3.2는 설정 범위를 실행 시 검사하면서 “쓰기 단계 조기 검증 가능(최종 동작 동일)”이라고 한다.
그러나 “SETI K,3 → SETI K,4 → EXEC GEMM”에서는 조기 Fault와 실행 시 검사 결과가 다르다.

- 선택 A (권장): 존재하는 RW CSR의 값은 32bit 그대로 저장하고, 범위는 해당 EXEC 수락 때 snapshot 전체로 검증. 없는 CSR/RO 쓰기는 해당 쓰기 명령에서 즉시 Fault.
- 선택 B: 설정 범위를 각 write에서 검사하도록 명세 변경.
- 영향: csr_file, Instruction Controller, Error PC/코드, assembler 프로그램 허용 범위, CSR directed tests.
- 이번 단계에서는 선택하지 않았다.

### D-02 — K=4에서 기존 bias 스케줄의 재사용 한계 (Phase 5 전 확정)

ISA는 K>0, K%4=0을 허용한다. 기존 fixed FC는 K_words>=32지만, K_words=1·output_groups>=3으로 기존 스케줄을 확장하면:

| 에지 | Bias SRAM / 누산기 동작 |
|---|---|
| R | 그룹 0 input 및 bias 0 read |
| R+1 | 그룹 0 bias load |
| R+2 | 공백 1클럭 후 그룹 1 input 및 bias 1 read |
| R+4 | 그룹 2 input 및 bias 2 read; RAM 출력이 bias 2로 변경 |
| R+5 | 그룹 0 result capture와 그룹 1 bias_load. 직접 배선이면 bias 1 대신 bias 2를 소비 |

이는 코드·계약에서 유도한 **정적 타이밍 위험**이며 새 GEMM RTL로 재현한 FAIL은 아니다.
현재 고정 FC 회귀에는 해당 구성이 없다.

- 선택 A (권장): 신규 GEMM 경로에서 bias 응답을 그룹에 맞춰 보관/정렬하여 기존 MAC·누산기·R+6·그룹 공백 1클럭을 유지.
- 선택 B: K 최소값 제한 또는 짧은 K의 추가 공백을 명세에 명시. 현재 지원 범위/사이클 계약 변경이 필요.
- 영향: 새 gemm_controller/pipeline 제어, bias staging, K=4/8 및 그룹 1/2/3+ directed tests와 Timer 기대치.
- 이번 단계에서는 staging이나 ISA 제한을 구현하지 않았다.

### D-03 — IMEM/DMEM bounds의 전달 및 “프로그램 크기” 의미 (Phase 1 전 확인)

ISA §2는 메모리 상한을 TB 프로파일 파라미터로 두고 §7은 “프로그램 크기 초과 Fault”를 요구한다.
Top 포트에는 limit 입력이 없으며, 실제 적재 코드 길이와 할당 IMEM 용량 중 무엇을 fetch 경계로 삼는지 구분이 부족하다.

- 선택 A (권장): Top과 TB가 동일 elaboration 파라미터로 IMEM/DMEM 용량을 공유하고 fetch bounds는 할당 IMEM 용량으로 정의. 권장 기본 64KiB/16MiB.
- 선택 B: 실제 적재 코드 길이를 별도 설정하여 그 바깥 fetch도 Fault. 값의 전달 계약 추가 필요.
- 영향: npu_top/PC 검사, TB memory model, Python manifest와 경계 테스트.
- 실제 용량과 적재 코드 길이가 다른 경우의 기대 동작은 구현 전에 확인해야 한다.

### D-04 — non-taken branch의 잘못된 후보 target (Phase 1 전 확인)

ISA는 “모든 목표 4byte 정렬/IMEM 범위”와 taken 시 PC 변경을 명시하지만 non-taken 후보 target 검사 여부는 명시하지 않는다.
예: 비교가 false인 BEQ의 offset=2 또는 후보가 IMEM 밖인 경우.

- 선택 A (권장): 실제 선택된 next PC만 alignment/bounds 검사. non-taken이면 PC+4 검사.
- 선택 B: branch 조건과 무관하게 후보 target도 검사.
- 영향: branch Fault 시점/코드, directed tests. offset 비트의 2byte 표현 가능성과 4byte PC 정렬 Fault를 구분해야 한다.
- 이번 단계에서는 어느 정책도 구현하지 않았다.

D-01~04는 보고 및 논의 대상이다. 명세 원문을 임의로 고치지 않았다.
BMEM에서는 primitive output register만 끄는 것으로 전체 read latency=1이 자동 보장되지는 않는다.
IP 설정·rdata hold·reset·NO_CHANGE를 행동 모델과 비교해야 하며 현재 inferred RAM의 과거 PASS가 IP 검증을 대신하지 않는다.

## 7. 향후 파일별 변경·검증 계획 (실행하지 않음)

| Phase | 신규/변경 후보 | 보존할 기존 파일 / 해당 Gate |
|---|---|---|
| 1 | 04_rtl/isa/npu_isa_pkg.sv, instruction_decoder.sv, register_file.sv, scalar_alu.sv, instruction_controller.sv; controller/npu_top.sv; 별도 scalar TB와 최소 machine-word fixture | mlp_top 및 기존 tests 보존. 1clk IMEM fixture는 Fetch 검증에 필요한 최소 범위로 준비; PC/GPR trace, branch/jal, invalid GPR/opcode/encoding/PC, r0, END/Halt |
| 2 | csr_file.sv, perf_timer.sv, instruction_controller 확장; CSR/Timer unit TB | CSR 번호·32bit 보존, RO/invalid Fault, signed imm13, Timer overflow/active edge, r4 clobber 검증. D-01 확정 필요 |
| 3 | npu_memory_model.sv, tb_npu_scalar.sv, DMEM selector 필요 시 추가 | 고정 1clk LW/SW, write commit, hold, 정렬/영역/bounds/wrap 및 fault 후 부작용 검사 |
| 4 | npu_memory_wrapper.sv, sram_address_decoder.sv, sram_port_mux.sv, block_transfer.sv | legacy memory_wrapper/mux/decoder 유지. 7개 실제 깊이 및 모든 bank LOAD→STORE, rs3/GPR 불변, 마지막 write 뒤 done |
| 5 | gemm_controller.sv 및 별도 GEMM FSM/counters/address/read/pipeline 제어. 기존 제어 파일은 원형 참고 후 새 경로에 추출 | mac_array/*, accumulator_postprocess/* 보존. FC1/2/3 bit-exact, 동적 A/B offset, K/N 경계, 짧은 K, R~R+6, done/Timer. D-02 해결 필요 |
| 6 | argmax_engine.sv, 독립 argmax schedule/control | signed compare/tracker 재사용. 길이 1/3/4/9/10, tie/음수/padding, A/B offset, rd=r0, 잘못된 길이/주소 Fault |
| 7 | 90_scripts/npu/run_scenario.py 및 assembler/allocator/packer/compare 기능, NPU용 runner target/TB | 기존 run.py target 및 generated headers 유지. 작은 검산기/fixture는 앞 Phase Gate에 필요한 범위만 먼저 도입하고 이 단계에서 통합. 정확도 10k는 Timer·중간 STORE·waveform OFF |
| 8 | 별도 BMEM IP 생성 Tcl/wrapper, NPU용 합성 top/constraints 및 IP 동등성 검증 | Legacy OOC Tcl/XDC 유지. 1clk·NO_CHANGE·SRAM 깊이, 기능 회귀 후 자원/timing/power 실측 |

기존 90_scripts/sim_targets.json의 5개 target은 유지하고 새 NPU target을 별도로 추가하는 방향이다.
패키지는 사용 모듈보다 먼저 컴파일하고, 기존 header의 NVEC/PIPELINE_DEPTH/해시 검사를 우회하지 않는다.
각 실제 구현 Phase에서 해당 Gate를 먼저 통과한 후 다음 단계로 진행한다.

## 8. 완료 상태와 남은 범위

PASS: Phase 0 진단·기존 회귀·로그·무변경 검증·timing 추적 표를 완료했다.
이번 단계에서 기존 RTL 기능 결함으로 재현된 실패는 없다.
문서의 검증 상태 누락과 새 설계의 기능 차이, 의사결정 항목은 위에 구분했다.

새 ISA/외부 메모리/LOAD·STORE/GEMM 일반화/Timer/ARGMAX 독립 실행/10,000장 정확도/BMEM IP 전환은 검증하지 않았다.
합성·배치배선·power·waveform도 이번 단계에서 실행하지 않았다.
**Phase 1은 사용자 승인 대기이며 시작하지 않았다.**
