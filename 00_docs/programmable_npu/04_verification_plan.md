# Programmable NPU v1.0 — 검증 계획 및 Acceptance Criteria

> **Phase 8 후속 최신 계약(2026-11-24):** GEMM은 소프트웨어에서 검증한 정상 설정을 전제로 한다. GEMM 하드웨어의 설정/Region/Bounds/Runtime 오류 검사는 제거했다. 원본 Snapshot, next-PC, 다른 명령어의 오류 처리와 SRAM/MAC/Timer 계약은 유지한다. [21번 결정](21_phase8_legacy_gemm_decisions.md)과 [22번 구현 보고서](22_phase8_legacy_gemm_report.md)가 이전 GEMM Fault 서술보다 우선한다.

> 2026-11-24 결정 우선순위: [07_design_decisions_phase0.md](07_design_decisions_phase0.md)의 D-01~D-04와 후속 사용자 확정을 우선 적용한다.

**방침:** Python이 테스트셋/주소/기계어/Golden을 생성하고, TB가 `imem`, `dmem`을 초기화해 DUT를 구동한 뒤 결과 영역만 추출한다. Testbench에서 실제 SRAM을 직접 수정하지 않고 정상 명령어 LOAD/STORE 경로를 검증. 시간 측정은 선택적인 짧은 Microbenchmark에서만 수행.

## 1. 테스트 환경 구조

```text
Python scenario runner
  ├── Model/Weight Packer (INT8 x4, 4 Weight Banks)
  ├── Dynamic DMEM Allocator + Manifest
  ├── Assembly Generator + Assembler -> IMEM.hex, DMEM.hex
  ├── Golden (layer output/prediction/performance expectation)
  └── Simulation runner -> compare/dump/summary
                            ↓
                      Testbench (SystemVerilog)
                      [IMEM 1clk] [DMEM 1clk]
                            ↓        ↓
                        [programmable npu_top]
                            ↓
                 done / fault / timeout / data dump
```

- 초기 데이터: `$readmemh`는 Testbench 외부 메모리 모델에서만 허용. 실행 중 입력/가중치는 NPU `LOAD`를 통해 내부 SRAM으로 이동.
- 완료 후 TB가 예측 결과나 Layer 결과처럼 Python이 manifest로 알려준 영역만 `$writememh` 또는 Testbench 파일 기록으로 추출. `SW`는 GPR의 32bit 값이 DMEM으로 기록되는지 검증.
- Memory Model은 32bit 배열, DMEM Base와 Index 변환을 명확히 구현. Read는 단일 posedge synchronous, Write도 single posedge.
- Timestamp/Waveform은 Directed Test만 저장. 10,000장 Long Run은 waveform OFF, Timeout 충분히 크게 설정.

## 2. ISA/Scalar Directed Tests

| ID | 테스트 | 합격 기준 |
|---|---|---|
| I-01 | Reset/Start/PC+4/END | Fetch PC 순서 정확, done 1클럭, Halt 후 접근 없음 |
| I-02 | `LUI`, `ADDI`, `ADD` | 32bit signed imm 및 modulo 2³² 계산 일치 |
| I-03 | `BEQ/BNE` taken/non-taken | branch target=old PC+offset, 루프 횟수 정확 |
| I-04 | `JAL` | old PC+4 Writeback/대상 PC 정확 |
| I-05 | `LW/SW` | 정렬된 32bit 외부 DMEM R/W bit-exact |
| I-06 | `SETI` | signed 13bit 양 끝(-4096,4095)와 sign extension |
| I-07 | `CSRR/CSRW` | RW 원본 32bit 저장, 중간 invalid 값 조기 Fault 금지, EXEC snapshot 검사, 없는 CSR/RO 쓰기 즉시 Fault (D-01) |
| I-08 | `LOAD/STORE` rs3 | rd 자리 읽기 소스, 쓰기back 없음, 원본 GPR 유지 |
| I-09 | Invalid GPR/CSR/Opcode/Encoding | ERROR_CODE/STATUS/fault sticky, 메모리 부작용 금지 |
| I-10 | branch/PC misalign/out-of-bounds | 선택된 next PC만 검사, non-taken 후보 오류 무시, JAL 오류 시 link/PC 불변 |
| I-11 | IMEM 할당 용량/미적재 영역 (D-03) | Top/TB 용량 공유, 전체 미사용 word zero fill, 0 명령어 INVALID_OPCODE(0x01), 마지막 유효 word 허용/용량 밖 요청 금지 |
| I-12 | Phase 1 Reset/Halt/부작용 | r0~r7 reset, busy 중 start 무시, 정상/오류 Halt에서 start 무시 및 fetch/write 없음, reset 후 재실행 |

Phase 1 Gate는 I-01~04, I-09의 opcode/encoding/GPR 부분, I-10~12다. I-05~08 및 CSR/Timer는 후속 Phase이며 본 Gate PASS에 포함하지 않는다.

Phase 4 실측 범위: I-05 LW/SW 전체 signed imm12, 32bit data/alias/r0, I-09 실제 GPR/예약 funct3, 주소 정렬/Region/Bounds/wrap 및 마지막 IMEM word의 부작용 차단을 검증했다. 실제 RTL dump를 Python Golden과 재비교했으며, 7개 bank 각각 Scalar/Block 혼합 경로와 Scalar Timer 제외도 PASS다. read R → R+1 GPR writeback 및 SW write 이후 완료는 소규모 WDB/VCD와 scoreboard로 확인했다. [13_phase4_report.md](13_phase4_report.md), [12번 확정](12_phase4_decisions.md)을 따른다.

## 3. SRAM/DMEM/전송 검증

| ID | 테스트 | 합격 기준 |
|---|---|---|
| M-01 | 모든 SRAM에 1word LOAD→STORE | 32bit 데이터 일치 |
| M-02 | Buffer A 196word / B 128word | 시작·끝 word 정확, no off-by-one |
| M-03 | W0/W1/W2/W3 각각 29280word | 각 Bank의 마지막 word까지 일치, bank 혼동 없음 |
| M-04 | Bias 163word | signed INT8 packed word의 바이트 순서 일치 |
| M-05 | SRAM reserved window hole | 실제 깊이 초과 시 Memory Bounds Fault |
| M-06 | DMEM base/end, 4byte misalign, zero-length | 범위/정렬/설정 Fault 코드 일치 |
| M-07 | Transfer final word | 실제 목적 write commit 후 done, 다음 Fetch 지연 보장 |
| M-08 | Rdata hold | en=0 및 write 시 read data 유지 |
| M-09 | External DMEM 1clk read | 요청 상승 에지 R 후 갱신, R+1 샘플링 정확 |
| M-10 | GEMM/Input/Weight/Bias port ownership | 서로 다른 SRAM은 병렬 read, 같은 SRAM 포트 충돌 없음 |

## 4. Timer 정확도

Phase 2 실측 범위: I-06/07, I-09 CSR/RO/형식 Fault 및 T-01/06/07, 테스트용 LOAD/GEMM active 에지·OR·동적 PERF read를 검증했다. [Phase 2 결과](09_phase2_report.md)를 보존한다.

Phase 3 실측 범위: 블록 I-08 및 메모리 M-01~09, 실제 LOAD의 T-02/마지막 SRAM write 경계, T-04 중 STORE 제외를 검증했다. 7개 SRAM 전체 깊이·왕복·경계/정렬/영역/길이 Fault·runtime cursor Fault·비영 GPR/RW CSR 보존 및 실제 bus 에지/데이터를 Python Golden과 비교했다. [Phase 3 결과](11_phase3_report.md)의 94 cases와 owner 53 checks가 근거다. 실제 GEMM T-03, ARGMAX T-04 및 전체 프로그램 T-05는 Phase 5~7 통합 후 검증한다.

| ID | Sequence | Counter 기대 동작 |
|---|---|---|
| T-01 | `TSTART`→Scalar/CSR→`TSTOP` | 0 |
| T-02 | `TSTART`→`LOAD`→`TSTOP` | LOAD `engine_active`인 상승 에지 수 |
| T-03 | `TSTART`→`EXEC GEMM`→`TSTOP` | GEMM `engine_active`인 상승 에지 수 |
| T-04 | `TSTART`→`STORE`→`ARGMAX`→`TSTOP` | 0 |
| T-05 | `TSTART`→LOAD+GEMM→`TSTOP` | 두 active count 합계 |
| T-06 | `TSTART` 두 번 / `TSTOP` 후 읽기 | 재시작 시 0, 정지 후 값 고정 |
| T-07 | 단위 TB에서 counter overflow 유발 | 2³² wrap 및 sticky overflow=1 |

오버플로 테스트는 실제 2³² 클럭을 기다리지 않고 Timer unit TB에서 내부 초기 카운트 설정용 **테스트 전용 훅/파라미터 또는 TB 전용 force/release**를 이용하여 검증한다. 이 훅은 합성 대상 명세에 포함하지 않음. 활성 범위를 준수했는지 확인하려면 `engine_active`, final write, count를 waveform에서 같이 관찰.

## 5. GEMM/ARGMAX 정확도

| ID | 테스트 | 판정 |
|---|---|---|
| G-01 | FC1 784→512 (A→B) | 128 × packed 32bit 출력 Golden bit-exact |
| G-02 | FC2 512→128 (B→A) | 32 words bit-exact |
| G-03 | FC3 128→10 (A→B) | 유효 10bytes bit-exact, 마지막 2 padding byte 제외 |
| G-04 | GEMM 연속 3회, 각각 CSR 변경 | 이전 `layer_config_lut` 순서와 동일 계산 |
| G-05 | 서로 다른 Weight Set로 반복 실행 | 해당 선택한 내부 SRAM 데이터로 계산, Weight 잔류 재사용 확인 |
| G-06 | M/N/K/Shift/Mode·SRAM 역할·실제 깊이 | 최신 GEMM 계약은 생성기 검사로 확인; 제거한 하드웨어 Fault 조합은 실행 대상에서 제외 |
| G-07 | R~R+6 Pipeline | input_valid, psum_valid, bias_load, result_load, out_we 시점 맞음 |
| G-08 | 짧은 K | K=4는 소프트웨어 거부; K=8/12/16/32 정상 실행·Bias·R→R+6 유지 |
| A-01 | ARGMAX signed negative/positive | signed 기준 최대 인덱스 반환 |
| A-02 | ARGMAX tie / length=1,3,4,9,10 | 동점 중 가장 작은 인덱스 우선, 길이만큼만 비교 |
| A-03 | FC3 N=10 padding | 10개만 비교, 나머지 2개 무시 |
| A-04 | `ARG_LEN=0`/11, 잘못된 SRC | P6-D-01/D-02의 Alignment→Region→Bounds→Config, invalid 길이도 전체 범위 검사 |

Golden 계산은 기존 `03_model/generate_golden.py`, `03_model/golden/*`, 양자화 로직을 우선 활용하되 **최신 3-stage RTL과 현재 데이터 형식**에 대응하는지를 재검증해야 함. 과거의 측정 결과를 새 설계 PASS로 대체하지 말 것.

Phase 5 실측 범위: G-01~08, 원자적 원본 Snapshot/live CSR 변경 무시, INT32 양방향 wrap와 기존 Saturation, raw 32bit field 검사, 동적 A/B/Weight/Bias offset·마지막 Word, GEMM next-PC/설정 복합 오류 및 runtime prefix 차단을 검증했다. T-03 및 LOAD+GEMM 합산 microbenchmark도 PASS다. 주 173 cases, K 경계 72 cases, Legacy FC 출력 326words, 매 누산/result 갱신의 실제 dump를 Python과 비교했다. [15_phase5_report.md](15_phase5_report.md). 기존 메모리 명령의 PC/data 복합 오류 일반화는 이후 [16번 후속 보고서](16_memory_fault_priority_report.md)에서 완료했다. 독립 ARGMAX는 후속 Phase 6에서 구현·검증했고 아래 결과를 따른다. Application은 후속 Phase 7에서 첫 1/5/100/200장 승인 범위를 검증했다. 10,000장은 별도 승인 범위다.

### 5.1 Phase 6 ARGMAX 테스트 명세 및 실행 결과 — Gate PASS

[17번 P6-D-01/P6-D-02](17_phase6_decisions.md)를 기준으로 테스트 항목과 기대값을 확정한다. 후속 구현 승인 후 RTL/TB/Python Golden을 구현하고 A-01~A-16/A-B01~18/A-P01~07을 실제 실행해 PASS했다. 최종 411회 실행·2,983,083 RTL checks·517,258 Python 비교·599개 ARGMAX 비교 상태, 두 IMEM의 PC Fault 216회 및 전체 회귀 PASS다. [18번 보고서](18_phase6_report.md)의 로그/파형/source hash를 따른다. 아래 0x00은 사전 검증 성공이며 실제 PASS 근거는 해당 실행 기록이다.

| ID | 추가 테스트 | 합격 기준 (실행 PASS) |
|---|---|---|
| A-05 | ARG_SRC/LEN 원자적 Snapshot | 수락 에지의 두 원본 32bit를 함께 보관; TB 전용 live CSR 변경을 실제 관찰하고 Snapshot 실행 불변 확인 |
| A-06 | 실제 A/B 경계 | 아래 A-B 매트릭스의 시작/끝/범위/길이 오류 코드 및 요청 차단 |
| A-07 | ARG_LEN 원본·산술 폭 | 0x10000001, 0xFFFFFFFC/FD/FFFFFFFF의 W/B/E와 Bounds; 하위 비트 alias·32bit L+3/4W wrap 금지 |
| A-08 | 마지막 IMEM 복합 Fault | 아래 A-P 매트릭스; Alignment/Region이 next-PC Bounds보다 우선, Config보다 Bounds 우선 |
| A-09 | Fault 무부작용·Halt | Engine start/DMEM/7개 SRAM 접근/Writeback=0, PC/GPR/RW CSR 보존, STATUS=2·최초 코드 sticky, Halt 중 start 무시 |
| A-10 | A/B source 역할·offset | A/B 및 비영 word offset 정상; 각 Weight bank/Bias/DMEM/IMEM/MMIO/예약 SRAM 창은 0x04 |
| A-11 | Encoding/GPR/CSR 선행 오류 | 예약 funct/rs1/rs2=0 위반은 0x08, 유효 형식 rd=r8~r31은 0x02; 데이터·PC 오류가 겹쳐도 선행. CSR 오류는 해당 SETI/CSRW/CSRR에서 0x03 |
| A-12 | GPR 결과·r0 버림 | 초기 rd 비영 값, 정상 index의 상위 28bit=0; r0도 검사·Read·비교 후 결과만 버림 |
| A-13 | 독립·연속 실행 | GEMM 뒤 별도 EXEC, A/B·길이·최대 위치 변경 연속 실행; 새 index/첫 값 초기화, 이전 결과 잔류 없음 |
| A-14 | T-04 Timer 제외 | 준비 LOAD 후 TSTART→STORE→ARGMAX→TSTOP=0; 앞선 LOAD/GEMM의 비영 count와 armed/overflow도 실행/Fault 동안 보존 |
| A-15 | Read/최종 비교/Writeback | R 요청·R+1 소비, 마지막 비교 뒤 안정된 결과만 GPR에 기록; 내부 argmax_done 1회, Top done은 END에서만 1클럭 |
| A-16 | Reset·상태 보존 | 실행 중 PC/GPR/RW CSR 유지, busy 중 start 무시, 도중 Reset 취소, 정상/오류 Halt 뒤 Reset 재실행 |

A-01~03은 -128/-1/0/127 및 모두 음수, 최대가 첫/중간/마지막 위치, 워드 경계를 넘는 동점, 최대가 갱신되지 않는 경우를 포함한다. LEN=1/3/4/9/10을 A/B 양쪽에서 검증한다. 유효 10개는 음수이고 padding 2개는 +127인 데이터로 padding 비교 금지를 확인한다. 독립 Golden의 예: [-128,-1,0,127]→3, [-128,-5,-8]→1, [-5,7,7,-1]→1. LEN=1은 값과 관계없이 index=0이다.

#### A-B: ARG_LEN 및 실제 Buffer 경계 기대값

아래 각 행은 정상 next-PC, 유효 인코딩/GPR를 전제로 **A/B 각각** 수행한다. base는 선택 Buffer 시작, T는 실제 끝(exclusive)이며 A의 T=0x80000310, B의 T=0x80020200이다. W는 원본 unsigned L에서 넓게 계산한 ceil(L/4)다.

| ID | ARG_SRC | 원본 ARG_LEN | W | 기대 ERROR_CODE/동작 |
|---|---|---:|---:|---|
| A-B01 | base | 0 | 0 | 0x07, Read 없음 |
| A-B02 | base | 11 | 3 | 0x07, Read 없음 |
| A-B03 | T−4 | 4 | 1 | 0x00, 마지막 word 1회 Read |
| A-B04 | T−4 | 5 | 2 | 0x06, 전체 범위 초과 |
| A-B05 | T−12 | 10 | 3 | 0x00, 3회 Read·유효 10개만 비교 |
| A-B06 | T−8 | 10 | 3 | 0x06 |
| A-B07 | T−12 | 11 | 3 | 0x07, 범위는 맞지만 Configuration 오류 |
| A-B08 | T−8 | 11 | 3 | 0x06, invalid 길이여도 Bounds 우선 |
| A-B09 | T | 0 | 0 | 0x06, 시작 Bounds; W−1 underflow 금지 |
| A-B10 | T | 1 | 1 | 0x06, 실제 깊이 바로 밖 |
| A-B11 | base+1 | 0 | 0 | 0x05, Alignment 우선 |
| A-B12 | base | 0x00000010 | 4 | 0x07, 유효 범위지만 길이 16 |
| A-B13 | base | 0x10000001 | 0x04000001 | 0x06, 하위 4bit=1로 자르지 않음 |
| A-B14 | base | 0xFFFFFFFC | 0x3FFFFFFF | 0x06, 넓은 전체 범위 |
| A-B15 | base | 0xFFFFFFFD | 0x40000000 | 0x06, L+3 올림 산술 wrap 금지 |
| A-B16 | base | 0xFFFFFFFF | 0x40000000 | 0x06, B=0x100000000; 32bit 절단 금지 |
| A-B17 | T−4 | 1 / 3 | 1 | 0x00, 길이 정렬 조건 없음 |
| A-B18 | T−12 | 9 | 3 | 0x00, 마지막 3byte padding 무시 |

추가 Region/우선순위 사례: 정렬된 Weight 0~3/Bias/DMEM/IMEM/MMIO/예약 창을 source로 두고 LEN=0/11/0xFFFFFFFF를 적용하면 0x04가 Bounds/Config보다 우선한다. 같은 source를 비정렬로 만들면 0x05다. A/B 창의 실제 깊이 밖 주소는 0x04가 아니라 0x06이다. 시작 주소/길이 조합별 모든 Fault에서 요청은 0회여야 한다.

#### A-P: ARGMAX 데이터 오류 + next-PC Bounds

ARGMAX를 IMEM_BYTES−4에 둔다. 4KiB IMEM에서는 PC=0xFFC, 기본 64KiB에서는 PC=0xFFFC다. 두 용량에서 아래 기대 우선순위를 확인한다.

| ID | 데이터/설정 조건 | 동시에 발생하는 오류 | 기대 ERROR_CODE |
|---|---|---|---|
| A-P01 | ARG_SRC=base+1, LEN=0 | Alignment + Config + next-PC Bounds | 0x05 |
| A-P02 | 정렬된 Weight/Bias/DMEM source, LEN=0/11 | Region + Config + next-PC Bounds | 0x04 |
| A-P03 | ARG_SRC=T−8, LEN=11 | 데이터 Bounds + Config + next-PC Bounds | 0x06 |
| A-P04 | 정상 ARG_SRC/LEN=1/3/4/9/10 | next-PC Bounds만 발생 | 0x06 |
| A-P05 | ARG_SRC=base, LEN=0/11 | Config + next-PC Bounds | 0x06 |
| A-P06 | 잘못된 Encoding 및 rd와 데이터 오류 | Encoding + GPR + 데이터/PC 오류 | 0x08 |
| A-P07 | 유효 형식, rd=r8/r31 및 데이터 오류 | GPR + 데이터/PC 오류 | 0x02 |

A-P01~05는 A/B 각각 및 Timer armed/unarmed, rd=r0/비영 유효 GPR에서도 확인한다. r1~r7과 RW CSR을 비영 값으로 준비하고, 정상 LOAD/STORE로 SRAM/DMEM guard를 구성한 뒤 Fault를 발생시킨다. 목표 명령의 Engine start·논리 Read 요청·실제 RAM enable·모든 write가 0이고 PC/GPR/RW CSR 및 Timer Count/armed/overflow가 그대로인지 검사한다. STATUS/ERROR_CODE의 Fault 기록은 정상 상태 변화로 구분한다. Halt에서도 위 조건을 계속 확인하고 Reset 후 정상 프로그램 재실행을 검증한다.

#### Python·RTL 비교, 파형 및 회귀 계획

Python은 packed bytes를 signed INT8로 풀고 처음 L개에서 최초 최대 인덱스를 계산한다. W/B/E와 오류 코드는 Python의 넓은 정수 및 위 수동 기대값으로 독립 계산하며 RTL 출력으로 기대값을 만들지 않는다.

정상 프로그램은 LOAD로 SRAM 준비 → EXEC ARGMAX → SW 결과 → END를 실행하고 실제 DMEM dump를 Python과 비교한다. 선택 Buffer의 Read 횟수 W/주소/데이터, PC/GPR/CSR/Timer trace 및 SRAM/DMEM guard도 비교한다. 내부 SRAM 내용을 TB에서 직접 초기화하지 않는다. Snapshot용 live CSR 변경은 TB 전용 주입/관찰로 제한하며 프로그램에 동시 CSR 쓰기 기능을 추가하지 않는다.

작은 Debug에서 clk/reset, owner, argmax_en/address/rdata/error, 물리 RAM enable/address/rdata, index/lane/candidate/initialize/compare/greater/prediction, 내부 done, GPR writeback, PC, Top done, Timer를 파형으로 확인한다. Read R 직후 rdata 갱신 → R+1 소비, 워드 내 hold, 마지막 비교 결과 갱신 후 Writeback 순서를 대조한다. 대량 waveform은 OFF다.

최종 Gate는 A-01~A-16·위 매트릭스 및 Phase 1~5/메모리 Fault 후속/Python unit/Legacy RTL 5종 회귀의 실제 PASS와 소스·로그·파형 근거로 **PASS** 판정했다. 첫 요소 뒤 TB 전용 index=15 주입으로 실행 중 오류→추가 처리 차단·Error Halt·Writeback 금지도 검증했다. Phase 7/8은 수행하지 않았다.

## 6. 응용 시나리오 — Phase 7 첫 200장 Gate PASS

2026-11-24 사용자 승인 범위는 G0/G1/G2/G3/G4이며 10,000장과 별도 모델 전환은 포함하지 않는다. [19번 보고서](19_phase7_report.md), [실행 Manifest](../../07_runs/npu_phase7_20261123_220156_054531Z/manifest.json), [실측 metrics](../../07_runs/npu_phase7_20261123_220156_054531Z/metrics.json)를 따른다. 기존 Phase 1~6와 Fault/Legacy 검증은 보존하고 새 Application TB를 사용한다.

### G0 — 데이터·생성기·독립 Golden

- 원본 MNIST test IDX 헤더·payload·label을 검사하고 원본 순서 0~199를 선택한다. 체크포인트·IDX·소스 SHA-256과 aissd Python/PyTorch/torchvision/NumPy 버전을 기록한다.
- 입력 F5, Weight F7/F7/F7, Bias F9/F8/F7, 출력 signed F2/F2/F2. 오프라인 nearest-even, INT32 wrap, FC1/2 ReLU, 산술 우측 shift 10/7/7 후 signed INT8 saturation, ARGMAX lowest-index를 적용한다.
- 기존 IntegerMLP와 200장 Layer/Prediction, Phase 5 packed-address kernel의 0/7/199번 Layer, 기존 Legacy W0~3/Bias 총 117,283words를 비교한다.
- 전용 Python unit 9개로 범위·중복·Branch/Immediate/GPR·LI carry·루프 live register·debug STORE·wrap/음수 shift/tie·정확도 분리를 검사한다.

### S-01 / G1 — 1장 End-to-End

Weight/Bias 5회 LOAD → Input LOAD → FC1/2/3 각각 EXEC GEMM 및 STORE → ARGMAX → SW → END. FC1/2/3의 128/32/3word 총 163word와 Prediction을 Python에 bit-exact 비교한다. G1의 debug STORE는 r2/r4/r5만 사용한다. Golden/Label 1/1, 모든 중간 출력 PASS다.

### S-02 / G2 — 첫 5장 연속

기존 8 GPR로 BNE 루프를 실행하고 모델 LOAD는 최초 5회만 허용한다. Input 주소 +784, Prediction +4, 최종 Pointer와 반복 횟수, Engine 완료 및 Prediction 5/5를 확인했다. 중간 STORE/Timer/Waveform은 OFF다.

### S-03 / G3·G4 — 첫 100장·200장

- 원본 순서 첫 100장(0~99), 첫 200장(0~199). 실제 RTL G4 결과의 첫 100개와 G3 Prediction도 일치해야 한다.
- 동일 Assembly 구조에서 Pointer/End 주소만 변경한다. IMEM/DMEM은 64KiB/16MiB이며 Allocator가 정렬·중복·전체 범위를 검사한다.
- 모델 LOAD 5회 + Input LOAD N회, GEMM 3N회, ARGMAX N회, BNE N회, Prediction SW N회를 확인한다.
- 외부 메모리는 32bit Single-Port, byte address, 4byte 정렬, Read R 응답을 R+1에서 소비하고 Write는 상승 에지에 완료한다. 기존 내부 SRAM/Datapath는 변경하지 않는다.
- 가벼운 TB가 LOAD의 src/dst/length 및 실제 데이터 순서, 원본 CSR Snapshot, Prediction 주소/값/개수, END 1cycle/Halt, Fault/timeout을 검사한다. 상세 cycle/event 정답표 배열은 사용하지 않는다.
- TSTART/TSTOP 없음, Count/armed/overflow=0 유지, Waveform OFF, 중간 Layer STORE 0회. 명령·TB cycle 통계는 Timer 측정과 구분한다.
- 완료 조건: 정상 END, Fault 없음, Prediction 정확히 N개, RTL/Golden 불일치 0. Label 정답률은 별도 실측하며 임의 하한을 추가하지 않는다.
- 실측: G3 Golden 100/100·Label 100/100, G4 Golden 200/200·Label 200/200 PASS. 실행 시간·호스트 메모리는 19번과 metrics를 따른다.

### 후속 승인 범위

기존 S-03의 10,000장 정확도 목표와 S-04 모델 전환은 유지하되 이번 Gate 완료 조건에서 제외한다. Phase 7 범위에서는 10,000장 결과·전체 정확도·FPGA 합성을 수행하거나 PASS로 표시하지 않았다. 후속 승인된 Direct BRAM 합성 결과는 다음 Phase 8 절과 20번 보고서를 따른다. 기존 Phase 1~6/Memory Fault/Python/Legacy 5종 회귀도 모두 실제 재실행 PASS했다.

## 7. Phase 8 — Direct RTL BRAM / FPGA OOC 검증

최신 사용자 승인으로 기존 BMEM IP 전환 검증을 직접 RTL BRAM Inference 검증으로 대체한다. FPGA는 xc7a100tcsg324-1, Vivado 2025.2, npu_clk=100MHz(10ns)다. 첫 Synthesis는 npu_top·single_port_bram 무수정으로 실행한다. BMG IP/.xci와 TB 외부 메모리 모델은 합성 입력에서 제외한다.

| Gate | 필수 검증 |
|---|---|
| P8-1 | 7개 SRAM의 논리 Width/Depth/Array Bits, RAMB36/RAMB18 수, LUTRAM/FF 대체 여부, 자원≤135타일, 출력 레지스터 추가 없음 |
| P8-2 | 실제 합성 Netlist의 G1 Prediction 및 FC1/2/3 163word Golden 일치 |
| P8-3 | Reset Async Assert/2edge Sync Release, EN=0/Write 시 출력 Hold, Reset 중 쓰기 차단·내용 유지·해제 후 첫 Read |
| P8-4 | FPGA Wrapper G1/G4(200장), 원래 Phase 1~6·Memory Fault Priority·Python·Legacy RTL 5종 및 기존 Application G0/G1/G4 재실행 |
| P8-5 | opt_design / place_design / phys_opt_design / route_design / DRC 및 자원 보고 |
| P8-6 | 내부 OOC Setup/Hold: WNS≥0, WHS≥0, TNS=0, THS=0. Logic/Route/Skew와 Worst Path를 기록 |

물리 RAM_SP/RAM_SDP 포트 구성과 논리 Single-Port 의미를 구분한다. 작은 RAM의 물리 512word 패딩은 ISA Bounds를 늘리지 않는다. Write 중 출력 Hold는 primitive WRITE_MODE 문자열 하나로 판정하지 않고 기존 Read/Write Enable 배타성과 기능 비교를 함께 확인한다.

외부 I/O Delay·보드 핀·전압·False/Multicycle Path를 임의로 추가하지 않는다. check_timing의 no_input_delay/no_output_delay와 BRAM 비동기 제어/Reset 관련 DRC를 숨기지 않는다. 내부 OOC 통과가 보드 전체 Timing이나 비동기 전이의 아날로그 안전성 검증을 뜻하지 않는다. BRAM/용량/도구 실행 실패 또는 Timing 실패 시 원인과 대안을 보고하고 승인 없이 RTL·Read Latency·MAC Pipeline·주파수·예외를 변경하지 않는다.

G4는 Timer/Waveform/중간 Layer STORE OFF, Prediction 200개와 Golden 200/200·정상 END·Fault 없음으로 판정한다. G1에서만 Layer STORE를 사용한다. 이번 Phase 8에서 신규 파형은 저장하지 않았고 기존 Phase 5/6의 R→R+6/R→R+1 파형 근거와 신규 기능 로그를 구분한다. 실제 측정값과 실패 이력은 [20번 보고서](20_phase8_report.md)에 기록한다.

## 8. 공통 PASS 판정 / 실패 기준

- **PASS**는 실제 실행 로그, 예상 데이터 비교, 종료 상태, 타임아웃 여부로 판단. 예상 일정은 추정치로 따로 표시.
- Fail 즉시 오류 주소/PC/instruction, 기대/실제 값, 첫 불일치 시각, 수정된 파일/Commit을 기록.
- 큰 테스트 실행 전에 필수 directed tests가 모두 통과해야 함.
- 명세 변경이 필요한 실패는 Codex가 직접 규칙을 바꾸지 않고 문서 수정안 및 영향 범위를 먼저 제시.


## 별도 후속 Gate — 마지막 IMEM의 데이터/next-PC 복합 Fault

LW/SW/Block LOAD/STORE 각각 Alignment+PC Bounds=0x05, Region+PC Bounds=0x04,
데이터 Bounds+PC Bounds=0x06, 정상 주소+PC Bounds=0x06을 검증한다.
Block length=0+PC Bounds는 0x06이고, length misalignment+PC Bounds는 0x05다.
인코딩/GPR/CSR/Opcode 선행 규칙, PC/GPR/RW CSR 보존, 모든 물리 DMEM/SRAM 접근 및 Block start 차단을 확인한다.
각 사례 전에 정상 LOAD/STORE로 SRAM/DMEM을 준비한다. armed에서 누적 Count=6, unarmed에서 0을 만든 후 Fault가 이를 바꾸지 않는지 비교한다.
Python 예상 오류를 명시하고 RTL 실제 trace/final-memory dump와 재비교한다. Phase 1~5·Python unit·Legacy 5종 회귀도 필수다.

최종 후속 Gate는 **PASS**다. 필수 복합 오류 32사례(armed/unarmed), 기본 16MiB 16사례, 추가 Fault 및 Phase 1~5·Python 27개·Legacy 5종 회귀를 통과했다. 변경·타이밍·재현 로그는 [16번 후속 보고서](16_memory_fault_priority_report.md)를 참조한다. 이 메모리 후속 작업 당시 Phase 6은 승인 대기였으며, 이후 별도 승인으로 완료한 Phase 6 결과는 [18번 보고서](18_phase6_report.md)를 따른다.

## 9. Phase 8 Legacy GEMM 재사용 Gate

21번 결정을 따른다. G0 계약/소스 확인 → G1 연결 → G2 주소/Cursor → G3 정상 GEMM/파형 → G4 첫 200장 → G5 선택 회귀 → G6 FPGA 순서다. 실제 결과는 22번 보고서와 각 새 Run에서 확인한다.

정상 Phase 5는 run_phase5.py --reuse-gate g3로 실행한다. 72개 K/N/방향/유효 경계, Shift/INT32 수치, Snapshot, 연속 GEMM, FC 326word, Timer와 정상 설정의 next-PC 차단을 포함한다. 기존 GEMM 잘못된 설정/Runtime 주입/복합 Fault는 제거한 계약으로 분류하며 새 PASS로 주장하지 않는다. 과거 테스트와 로그는 보존한다.

G2는 --reuse-gate g2로 비영 Base/끝 Word/A↔B/Output A>=128를 검사한다. audit_gemm_reuse_wave.py는 실제 작은 VCD에서 S+2, R+1/R+4/R+5/R+6, Bias, 한 사이클 공백과 Cursor Read-only 증가를 독립 확인한다.

Application은 run_scenario.py --counts 200 --no-regressions로 기존 생성기/TB를 재사용한다. 원본 첫 200장, 모델 LOAD 5회+Input LOAD 200회, GEMM 600회, ARGMAX/Prediction 200회, 정상 END/Golden 불일치 0을 요구한다. Timer/Waveform/중간 Layer STORE OFF, 10,000장 미실행이다. 이 실행의 기존 Phase 7 전체 Gate 표시는 PARTIAL이며 이번 G4의 200장 완료와 구분한다.

G5는 run_gemm_reuse_regressions.py의 Scalar/Python/Legacy 5종, Scalar/Block 정상 혼합, GEMM→ARGMAX 양방향 및 연속 ARGMAX를 사용한다. G6은 기존 동일 FPGA/10ns 제약과 Flow, 새 BRAM 검토/Netlist 기능/Reset/DRC/Setup/Hold로 판정한다. Timing FAIL이면 변경 확대 없이 중단한다.
