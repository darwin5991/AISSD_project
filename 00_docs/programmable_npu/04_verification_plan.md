# Programmable NPU v1.0 — 검증 계획 및 Acceptance Criteria

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

Phase 2 실측 범위: I-06/07, I-09 CSR/RO/형식 Fault 및 T-01/06/07, 테스트용 LOAD/GEMM active 에지·OR·동적 PERF read를 검증했다. 실제 LOAD/GEMM/STORE/ARGMAX 명령과 마지막 SRAM write 경계는 Phase 4~6 통합 후 T-02~05 전체 항목을 검증해야 한다. [Phase 2 결과](09_phase2_report.md)는 이를 구분한다.

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
| G-06 | `M>1`, `K%4 !=0`, Buffer depth 초과 | INVALID_CONFIG 또는 MEMORY_BOUNDS Fault |
| G-07 | R~R+6 Pipeline | input_valid, psum_valid, bias_load, result_load, out_we 시점 맞음 |
| G-08 | D-02 짧은 K | K=4는 INVALID_CONFIG, 엔진 start/SRAM write 없음; K=8/12/16/32 분석 후 지원 하한 확정 |
| A-01 | ARGMAX signed negative/positive | signed 기준 최대 인덱스 반환 |
| A-02 | ARGMAX tie / length=1,3,10 | 최솟값 인덱스 우선, 길이만큼만 비교 |
| A-03 | FC3 N=10 padding | 10개만 비교, 나머지 2개 무시 |
| A-04 | `ARG_LEN=0`/11, 잘못된 SRC | Fault 코드 정확 |

Golden 계산은 기존 `03_model/generate_golden.py`, `03_model/golden/*`, 양자화 로직을 우선 활용하되 **최신 3-stage RTL과 현재 데이터 형식**에 대응하는지를 재검증해야 함. 과거의 측정 결과를 새 설계 PASS로 대체하지 말 것.

## 6. 최종 응용 시나리오

### S-01 — 1장 End-to-End + 중간 레이어 검증

- Model Weight Bank×4와 Bias를 **명령어로 내부 SRAM LOAD**.
- Image 1장 LOAD, FC1→FC2→FC3를 각 `EXEC GEMM`, 중간 FC1/2/3 출력은 `STORE`하여 Python bit-exact Golden과 비교.
- `EXEC ARGMAX, rd` 결과 `SW`로 DMEM 저장, 정답 Label과 비교.
- 필요 시 `TSTART/TSTOP`으로 LOAD/GEMM 각각 개별 사이클 측정.
- 외부 W/Bias 재적재 없이 다음 이미지 처리까지 테스트.

### S-02 — 몇 장 End-to-End, 반복 Branch

- Python이 N장을 선택하고 주소/마지막 이미지 다음 주소를 생성.
- `BNE` 루프를 사용하여 해당 N번 정확히 반복, predictions[0..N-1] 일치.
- 레지스터 8개로 수립한 Pointer Live Range 분석을 Assembly 검사에 포함.

### S-03 — MNIST 10,000장 정확도 (권장 기본 프로파일)

- Weight Bank×4 + Bias 처음 1회 LOAD.
- 각 이미지에서 Input LOAD → FC1/FC2/FC3 EXEC → ARGMAX → `SW` prediction word.
- **TSTART/TSTOP 없음**, **FC1/FC2/FC3 intermediate STORE 없음**, **Waveform OFF**.
- 10,000 × 784B = 7,840,000B input; predictions = 10,000×4B=40,000B. Python Dynamic Allocator가 overlap 검증.
- RTL Prediction 10,000개 모두 Golden/Label과 검증. 정확도는 `correct/10000 ×100`으로 보고, 기존 FP32/기존 INT8 모델의 측정과 비교하되 새 설계의 결과는 실측으로만 기록.
- Optional: Error/Timeout 발생 이미지 index, PC, 마지막 CSR/GPR 상태를 TB 디버그 로그에 기재.

### S-04 — 별도 모델/가중치 세트

- Python이 두 가지 Weight Set 각각을 외부 DMEM에 배치하고 LOAD 명령으로 선택한 세트를 내부 SRAM에 적재.
- Model A→B 변환 후 FC1/2/3 결과가 달라지는지 검증, 동일 모델 재선택 시 일치 검증.
- 모델이 다르더라도 현재 Gemm Bank Count/메모리 실제 Depth/`M=1`, INT8 등의 지원 범위를 벗어나면 Fault 또는 Python 배치 오류로 처리.

## 7. FPGA/BMEM 및 합성 검증

- Native Single-Port BMEM IP, 32bit interface, Primitive Output Register Disabled, 1clk synchronous read. 전환 전후 Memory Model 출력/Timing 비교.
- Testbench 외부 Memory HEX 초기화 방식과 실제 합성 가능한 코어를 분리 (`initial`, `$readmemh/$writememh`가 합성 RTL에 포함되지 않아야 함).
- Synthesis에서 내부 SRAM이 Block RAM으로 인스턴스화되었는지 확인. OOC Synthesis + Implementation Timing, WNS≥0 목표. LUT/FF/BRAM/DSP 및 Power 보고.
- 최소 waveform 자료: LOAD 외부→내부 Write, GEMM의 SRAM Input/Weight Read, Output SRAM Write, DONE, ARGMAX Read/Result.

## 8. 공통 PASS 판정 / 실패 기준

- **PASS**는 실제 실행 로그, 예상 데이터 비교, 종료 상태, 타임아웃 여부로 판단. 예상 일정은 추정치로 따로 표시.
- Fail 즉시 오류 주소/PC/instruction, 기대/실제 값, 첫 불일치 시각, 수정된 파일/Commit을 기록.
- 큰 테스트 실행 전에 필수 directed tests가 모두 통과해야 함.
- 명세 변경이 필요한 실패는 Codex가 직접 규칙을 바꾸지 않고 문서 수정안 및 영향 범위를 먼저 제시.
