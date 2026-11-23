# Programmable NPU ISA v1.0 — 최종 기능 명세

> 2026-11-24 결정 우선순위: [07_design_decisions_phase0.md](07_design_decisions_phase0.md)의 D-01~D-04와 후속 사용자 확정을 우선 적용한다.

**상태:** 구현 기준 명세 (RTL/Assembler 구현 및 시뮬레이션은 별도). **대상:** 기존 INT8 MLP 가속기의 명령어 구동 확장. **명령어 길이:** 항상 32bit. **Endian:** 메모리의 32bit 워드는 little-endian 바이트 순서 (`byte0` = `[7:0]`). **PC:** 32bit byte address, Reset 후 `0x0000_0000`.

## 1. 프로그래밍 모델

- **GPR:** 8개(`r0..r7`) × 32bit. `r0` 읽기=0, 쓰기 무시. 명령어에는 5bit 레지스터 번호를 인코딩하되 `r8..r31`은 현재 **지원하지 않으며 참조 시 fault**. 나중에 GPR 수를 늘려도 인코딩 변경 없음.
- **CSR:** 12bit 번호, 모든 데이터 32bit, 프로그램 종료/Reset까지 값 유지. 프로그램이 변경할 때만 갱신됨. 초기화 시 모든 R/W 설정 CSR은 0.
- **실행:** 명령어별 blocking, in-order, 파이프라인/동시 명령어 실행 없음. `LOAD`, `STORE`, `EXEC`는 완료를 확인한 뒤에만 다음 명령어 Fetch.
- **PC:** 정상 명령어는 `PC+4`; `BEQ/BNE/JAL`은 RISC-V 방식 PC-relative offset. 실제로 선택된 next PC만 4byte 정렬 및 IMEM 할당 용량 범위를 검사한다. BEQ/BNE가 non-taken이면 후보 target은 검사하지 않고 PC+4만 검사한다. JAL은 target 검증 성공 후에만 link/PC를 갱신한다 (D-04).
- **Reset/시작:** `rst_n=0`에서 GPR/CSR/PC/컨트롤 상태 초기화(내부 SRAM 내용은 초기화하지 않음). 외부 `start` 한 펄스를 IDLE에서 수락하면 `PC=0`으로 FETCH 시작. `END` 또는 Fault 이후에는 Halt 유지; 재실행은 Reset 후 `start`로 진행.
- **주소:** 모든 주소와 길이는 byte 단위. `LW/SW/LOAD/STORE`는 4byte 정렬. 블록 길이는 양수이고 4의 배수. 외부 주소 산술에서 32bit wrap을 금지함.

## 2. 32bit 논리 메모리 맵

| 영역 | 시작 주소 | 의미 / 유효 접근 |
|---|---:|---|
| IMEM | `0x0000_0000` | PC Fetch 전용, 코드 저장, 읽기 전용 |
| 외부 DMEM | `0x1000_0000` | Python이 Weight/Input/Prediction/Performance를 동적 배치, 읽기/쓰기 |
| 내부 SRAM | `0x8000_0000` | 7개 물리 BRAM 접근용 논리 주소 |
| MMIO 예약 | `0xF000_0000` | v1.0에서 접근 불가, 향후 확장 |

**검증 환경 권장 프로파일:** IMEM 64 KiB, DMEM 16 MiB(각각 Testbench 파라미터). DMEM의 예시 유효 범위는 `[0x1000_0000,0x1100_0000)`. 이는 **시뮬레이션 메모리 크기**이지 FPGA의 실제 온칩 BRAM 용량을 뜻하지 않는다. Top과 TB는 동일한 elaboration 파라미터 IMEM_BYTES/DMEM_BYTES를 공유한다. Fetch 경계는 적재 코드 길이가 아닌 IMEM 할당 용량이다. 기본 마지막 유효 word 시작 주소는 0x0000FFFC이며 0x00010000은 요청 전에 MEMORY_BOUNDS Fault다. TB는 미사용 IMEM 전체를 0으로 채운다. 미적재 영역의 0x00000000을 실제로 fetch하면 INVALID_OPCODE(0x01) Fault다. 실제 FPGA의 미사용 메모리 초기값은 이 TB zero fill로 보장되지 않는다 (D-03). 모든 프로그램/데이터는 범위 검사를 수행한다.

### DMEM 오류 분류 (2026-11-24 추가 확정)

[Phase 3 결정](10_phase3_decisions.md)에 따라 외부 DMEM 논리 영역은 상위 4bit=0x1인 [0x10000000,0x20000000)이다. 영역 안에서 DMEM_BYTES 용량을 넘으면 MEMORY_BOUNDS(0x06), 그 밖의 외부 주소는 INVALID_REGION(0x04)이다. 정렬 오류는 기존 우선순위를 따른다.

### 내부 SRAM 창 (각 128 KiB 간격, 실제 깊이는 별도)

| SRAM | 논리 Base | 물리 깊이 | 실제 바이트 크기 |
|---|---:|---:|---:|
| Buffer A | `0x8000_0000` | 196 × 32b | 784 B |
| Buffer B | `0x8002_0000` | 128 × 32b | 512 B |
| Weight Bank 0 | `0x8004_0000` | 29280 × 32b | 117120 B |
| Weight Bank 1 | `0x8006_0000` | 29280 × 32b | 117120 B |
| Weight Bank 2 | `0x8008_0000` | 29280 × 32b | 117120 B |
| Weight Bank 3 | `0x800A_0000` | 29280 × 32b | 117120 B |
| Bias | `0x800C_0000` | 163 × 32b | 652 B |

접근 시 상위 주소로 은행을 선택하고 `(addr - bank_base)/4`로 워드 주소 생성. **예약된 창의 나머지 빈 공간은 접근 가능 메모리가 아님**: 해당 실제 깊이를 넘으면 Memory Fault. DMA/블록 전송이 은행 경계를 넘어가는 것은 허용하지 않음(여러 명령어로 분리).

## 3. 명령어 형식과 인코딩

RISC-V 형식은 표준 필드 배치만 **선택적으로 차용**한다. 이것은 RV32I 전부를 지원하거나 RISC-V CPU 바이너리 호환을 선언하는 명세가 아님.

### 3.1 Scalar / Control (기존 RISC-V 인코딩 준용)

| Assembly | Opcode[6:0] | funct3 | funct7/제약 | Semantics |
|---|---:|---:|---|---|
| `LUI rd, imm20` | `0x37` | — | U | `rd ← imm20 << 12` |
| `ADDI rd, rs1, imm12` | `0x13` | `000` | I | `rd ← rs1 + sext(imm12)` (mod 2³²) |
| `ADD rd, rs1, rs2` | `0x33` | `000` | `0000000` | `rd ← rs1 + rs2` (mod 2³²) |
| `BEQ rs1, rs2, label` | `0x63` | `000` | B | 같으면 `PC ← PC+sext(offset)` |
| `BNE rs1, rs2, label` | `0x63` | `001` | B | 다르면 `PC ← PC+sext(offset)` |
| `LW rd, imm12(rs1)` | `0x03` | `010` | I | 외부 DMEM에서 정렬된 32bit read |
| `SW rs2, imm12(rs1)` | `0x23` | `010` | S | 외부 DMEM에 정렬된 32bit write |
| `JAL rd, label` | `0x6F` | — | J | `rd ← old PC+4`; `PC ← old PC + offset` |
| `CSRW csr, rs1` | `0x73` | `001` | `CSRRW r0,csr,rs1` | 지정한 R/W CSR 전체 갱신 |
| `CSRR rd, csr` | `0x73` | `010` | `CSRRS rd,csr,r0` | CSR 읽기(쓰기 없음) |

R/I/S/B/U/J의 실제 Immediate 비트 스플릿은 RISC-V 공식 인코딩과 동일. `ADDI`, `LW`, `SW`의 signed imm12 범위 `[-2048,2047]`. Branch offset은 signed 13bit **2의 배수**, JAL offset은 signed 21bit **2의 배수**로 인코딩한다. 실제로 선택된 target이 4byte 정렬이 아니면 MISALIGNED Fault이며 non-taken branch의 후보 target은 검사하지 않는다. 지원하지 않는 funct/CSR 변종/잘못된 예약 비트는 Illegal Encoding Fault.

**Scalar LW/SW는 외부 DMEM에만 접근**한다. Base GPR의 unsigned 32bit 값에 signed imm12를 확장 폭으로 더한다. [Phase 4 사용자 확정](12_phase4_decisions.md): 정렬 → 산술 wrap(MEMORY_BOUNDS) → Region → DMEM 용량 Bounds 순서로 검사하며, 음수/32bit 초과 주소를 잘라서 접근하지 않는다. 내부 SRAM의 덩어리 전송은 다음 `LOAD/STORE` 사용. `CSRW/CSRR`은 표준 Zicsr 형식의 위 두 형태만 지원하고 기타 CSR 명령의 지원을 보장하지 않는다.

### 3.2 `SETI` — CSR 즉시값 쓰기 (Custom-0)

```
[31:19] signed imm13 | [18:7] csr[11:0] | [6:0] 0x0B
```

- 형식: `SETI csr, signed_immediate`, immediate 범위 `[-4096,4095]`; `CSR[csr] ← sign_extend_32(imm13)`.
- 없는 CSR/Read-Only CSR 쓰기/불법 형식은 해당 명령에서 즉시 Fault. 존재하는 RW 설정 CSR은 SETI/CSRW의 32bit 원본 값을 그대로 저장하고, 값 범위·조합·SRAM 주소/크기는 해당 EXEC 수락 시 snapshot 전체로 검증한다. 중간 설정값에 대한 조기 Fault는 금지한다 (D-01).

### 3.3 NPU 전용 공통 포맷 (Custom-1)

```
[31:25] funct7 | [24:20] rs2 | [19:15] rs1 |
[14:12] funct3 | [11:7] rd_or_rs3 | [6:0] 0x2B
```

| funct3 | 명령어 | funct7 | rs1 | rs2 | rd_or_rs3 | 동작 |
|---|---|---:|---|---|---|---|
| `000` | `LOAD rs1,rs2,rs3` | 0 | 외부 Src GPR | 내부 Dst GPR | Length GPR | DMEM → 내부 SRAM |
| `001` | `STORE rs1,rs2,rs3` | 0 | 내부 Src GPR | 외부 Dst GPR | Length GPR | 내부 SRAM → DMEM |
| `010` | `EXEC GEMM` | 0 | 0 | 0 | 0 | CSR 설정 GEMM 1회 |
| `010` | `EXEC ARGMAX, rd` | 1 | 0 | 0 | 결과 GPR | CSR 설정 ARGMAX 1회 |
| `011` | `TSTART` | 0 | 0 | 0 | 0 | Counter 초기화 후 arm |
| `011` | `TSTOP` | 1 | 0 | 0 | 0 | Counter disarm/hold |
| `011` | `END` | 2 | 0 | 0 | 0 | 정상 종료/Halt |

- `LOAD/STORE`의 세 번째 레지스터 번호는 R-type의 **rd 위치를 읽기 소스 rs3로 재사용**함. GPR writeback 없음. 3개의 읽기 값을 1~여러 클럭에 걸쳐 래치해도 ISA상 동일.
- `LOAD/STORE`는 **DMA와 같은 블록 복사**지만 복사 중 다른 명령어는 실행하지 않음. `length_bytes > 0`, `length % 4 == 0`, 시작/끝 주소 정렬·범위 확인. 명령어가 완료될 때 원본 GPR 값은 불변.
- `EXEC`는 설정 CSR의 **스냅샷을 명령 수락 시** 취하며, `gemm_done/argmax_done` 후 다음 Fetch.
- 미사용 필드는 0이어야 함. 지원하지 않는 funct7/funct3는 Illegal Encoding Fault.

### 3.4 기계어 인코딩 검산 벡터

아래는 위 필드 정의로 계산한 **32bit instruction word**이며 Decoder와 Python Assembler의 첫 번째 일치 검사에 사용한다.

| Assembly | 기대 기계어 |
|---|---:|
| `LW r5,4(r1)` | `0x0040_A283` |
| `SW r2,-4(r1)` | `0xFE20_AE23` |
| `LOAD r1,r2,r3` | `0x0020_81AB` |
| `STORE r1,r2,r3` | `0x0020_91AB` |
| `EXEC GEMM` | `0x0000_202B` |
| `EXEC ARGMAX,r5` | `0x0200_22AB` |
| `TSTART` | `0x0000_302B` |
| `TSTOP` | `0x0200_302B` |
| `END` | `0x0400_302B` |
| `SETI M,1` | `0x000B_E20B` |

### 3.5 어셈블러 의사 명령어

- `.equ NAME, VALUE`: 어셈블러 상수 심볼, NPU 실행 명령이 아님.
- `LI rd, 32bit_value`: 일반적인 `LUI` + 필요한 경우 `ADDI`로 확장; signed lower-12 보정이 필요함. 12bit 범위 값은 `ADDI rd,r0,imm`로 최적화 가능.
- `SETADDR csr, constant`: `LI r4,constant` + `CSRW csr,r4`로 확장하는 **v1 어셈블러 관례**. `r4`는 clobber 됨. 실행 중 `r4`에 보존할 값이 있을 때 사용 금지/코드 생성기 검사. 필요 시 명시적 `LI`/`CSRW` 사용.
- `EXEC GEMM`, `EXEC ARGMAX,r5` 등은 위 Custom-1 비트 패턴의 어셈블러 표기; 시스템 명령도 동일.

## 4. CSR 맵

| CSR | 이름 | R/W | 의미 |
|---|---|---|---|
| `0x7C0` | `SRC0_BASE` | RW | GEMM Input 내부 SRAM byte address |
| `0x7C1` | `SRC1_BASE` | RW | GEMM W0 논리 창 내 Weight-group base |
| `0x7C2` | `DST_BASE` | RW | GEMM Output 내부 SRAM byte address |
| `0x7C3` | `BIAS_BASE` | RW | GEMM Bias 내부 SRAM byte address |
| `0x7C4` | `M` | RW | v1 프로파일은 `M=1`만 지원 |
| `0x7C5` | `N` | RW | 유효 출력 요소 수, 1~512 |
| `0x7C6` | `K` | RW | 입력 요소 수, 양수, 4의 배수; 초기 버전 K=4 미지원, 정확한 지원 하한은 Phase 5에서 확정 |
| `0x7C7` | `BIAS_SHIFT` | RW | signed -32~31, 실제 엔진 포트 6bit |
| `0x7C8` | `OUT_SHIFT` | RW | unsigned 0~31, 실제 엔진 포트 5bit |
| `0x7C9` | `ACT_MODE` | RW | 0=none, 1=ReLU |
| `0x7E0` | `ARG_SRC` | RW | ARGMAX 입력 내부 Buffer byte address |
| `0x7E1` | `ARG_LEN` | RW | v1 범위 1~10, INT8 값 개수 |
| `0x7F0` | `PERF_COUNT` | RO | 32bit 누적 Engine Active 클럭 |
| `0x7F1` | `PERF_OVERFLOW` | RO | 0 또는 1, sticky overflow |
| `0x7F2` | `STATUS` | RO | 0=READY/RUNNING, 1=END HALT, 2=ERROR HALT |
| `0x7F3` | `ERROR_CODE` | RO | 아래 오류 번호, 정상/Reset=0 |

`XFER_SRC`, `XFER_DST`, `XFER_LEN` CSR은 **존재하지 않음**. CSR 외부 하드웨어 MMIO 공간은 v1 미지원.

## 5. GEMM의 유효 구성/레이아웃

- `EXEC GEMM` 한 번은 **하나의 FC 레이어(M=1)** 실행. 기존 MAC 4x4, INT8×INT8→signed32, 4-lane 누산·Bias·ReLU/Shift/Saturate 경로를 그대로 사용.
- D-02: 초기 버전은 짧은 K용 bias staging을 추가하지 않는다. K=4는 EXEC 수락 시 INVALID_CONFIG Fault이며 GEMM start/SRAM write를 금지한다. 정확한 최소 지원 K는 Phase 5의 K=8/12/16/32 경계 분석·directed simulation 후 확정한다. 현재 기존 동작의 안전성이 알려진 K=128/512/784도 새 ISA 통합 PASS를 뜻하지 않는다.
- `K_words = K/4`, `output_groups = ceil(N/4)`; 출력 저장 워드 개수는 `output_groups`. 마지막 그룹의 N을 초과하는 lane은 0으로 패딩된 데이터로 취급하며 모델 packer가 해당 Weight/Bias를 0으로 채움. N 개 유효 출력 외의 lane은 정확도/ARGMAX 평가 대상이 아님.
- `SRC0_BASE`: Buffer A 또는 B, `DST_BASE`: **반대쪽 Buffer**. 입력·출력은 동일 단일 포트 Buffer에 동시에 배치할 수 없음.
- `SRC1_BASE`: **Weight Bank 0의 논리 창 주소**. 물리 Weight Bank 0..3은 그 **동일 word offset**을 병렬 Read. Weight는 `출력 그룹 → K_words` 순서, 각 은행에 4개의 output lane별 INT8 × input 4개를 한 워드에 배치.
- `BIAS_BASE`: Bias SRAM에서 각 출력 그룹당 32bit packed signed INT8 ×4를 읽음.
- 모든 주소는 4byte 정렬, 계산한 마지막 접근까지 해당 물리 메모리 깊이를 넘지 않아야 함. `K_words`와 `output_groups`는 기존 주소/카운터 폭과 Buffer 용량을 만족해야 함. K 입력을 읽는 SRAM의 실제 깊이, 출력 SRAM 깊이, 29280 Weight 워드와 163 Bias 워드를 모두 사전 검사.
- `BIAS_SHIFT`, `OUT_SHIFT`, `ACT_MODE`는 명령 수락 시 고정. 기존 pipeline의 BRAM read(R) → MAC 입력 R+1 → product R+2 → sum R+3 → accumulate R+4 → result R+5 → write R+6를 보존.

기존 MNIST 사용 예시:

| FC | `SRC0→DST` | `SRC1_BASE` | `BIAS_BASE` | (M,N,K) | (Bias,Out,Act) |
|---|---|---|---|---|---|
| FC1 | A→B | `0x8004_0000` | `0x800C_0000` | (1,512,784) | (3,10,1) |
| FC2 | B→A | `0x8005_8800` | `0x800C_0200` | (1,128,512) | (1,7,1) |
| FC3 | A→B | `0x8005_C800` | `0x800C_0280` | (1,10,128) | (2,7,0) |

## 6. ARGMAX

- `EXEC ARGMAX, rd`는 `ARG_SRC`가 가리키는 내부 A/B Buffer의 packed signed INT8 값 `ARG_LEN`개를 순서대로 비교.
- 최댓값 인덱스를 32bit zero-extend하여 GPR `rd`에 기록. 동점이면 **가장 작은 인덱스** 유지. `rd=r0`이면 결과 버림.
- v1 프로파일에서 `ARG_LEN`은 1~10. 기존 4bit 인덱스 비교 Datapath를 재사용하며 가변 길이에 맞춰 스케줄러를 수정. 범위·정렬·Buffer 끝 검사. N을 초과한 마지막 워드의 padding은 비교하지 않음.
- GEMM 자동 종료 뒤 ARGMAX를 자동으로 실행하지 않음; 반드시 별도 `EXEC ARGMAX, rd` 필요.

## 7. 메모리 인터페이스 계약 (선택 A)

- IMEM, 외부 DMEM은 **서로 독립적인** 32bit Single-Port. 두 메모리의 요청선: `en`, `we`(IMEM 없음/0), `addr[31:0]`, `wdata[31:0]`; 응답선: `rdata[31:0]`.
- **동기 Read:** 상승 에지 R에 `en=1,we=0,addr` 수락 → R 직후 `rdata` 갱신 → NPU는 **R+1 상승 에지** 이후 단계에서 소비. 별도 Ready/Valid 없음. `en=0` 또는 write 시 read data hold.
- **Write:** 상승 에지에 `en=1,we=1`이면 해당 32bit 워드 즉시 기록. 부분 Byte Enable 없음. Read Data 출력은 Write 동안 Hold(`NO_CHANGE` 동작). 명령어 제어는 write가 실제 반영된 뒤 완료 선언.
- IMEM Read Only, PC/word 정렬 위반·IMEM 할당 용량 초과 Fault (적재 코드 길이는 검사하지 않음). DMEM `LW/SW`와 Block Transfer가 공유하는 한 포트를 상위 MUX로 선택.
- v1에서는 요청 Stall/Backpressure/가변 지연 없음. AXI/DDR 연결 시 별도 Adapter가 이 고정 지연 인터페이스를 충족하도록 버퍼링하거나, 후속 ISA 마이크로아키텍처 버전에서 handshake를 추가해야 함.

## 8. Performance Timer (선택 B)

- 32bit Unsigned 단일 카운터 + 1bit sticky overflow + 1bit armed. `TSTART`: 카운터/overflow=0, armed=1. `TSTOP`: armed=0, Count 유지.
- `armed=1`이고 **Block LOAD 엔진 또는 GEMM 엔진의 `engine_active`가 1인 클럭에만** +1. STORE, ARGMAX, Fetch, Decode, CSR, Scalar, `TSTART/TSTOP` 자체, 외부 결과 기록은 카운트하지 않음.
- `engine_active`: 명령 수락으로 시작해 **첫 유효 전송·연산 준비 사이클부터 최종 목적 SRAM 쓰기가 완료되는 에지까지** 유지. 카운터는 각 상승 에지 직전에 보이는 `engine_active`를 샘플링해 증가; 최종 쓰기 에지도 포함. 엔진이 완료 전용 파이프라인 정리 사이클을 필요로 한다면 그 active 사이클도 측정 범위에 포함. FETCH와 다음 명령어로 넘어가기 위한 빈 사이클은 제외.
- 한 구간에 LOAD와 GEMM 여러 개를 실행하면 해당 active 클럭의 **합계** 측정. 연속 측정은 다음 `TSTART`로 초기화. `PERF_COUNT`는 정지 후에도 읽을 수 있음.
- `0xFFFF_FFFF + 1`에서는 modulo-2³² wrap, `PERF_OVERFLOW=1` sticky; 다음 TSTART에서 초기화. 별도 Fault로 처리하지 않음.
- 대규모 MNIST 정확도 프로그램에는 TSTART/TSTOP/중간결과 STORE를 넣지 않는 것이 기본 테스트 프로파일.

## 9. Fault / Halt (선택 B)

| ERROR_CODE | 상수 이름 | 예시 |
|---:|---|---|
| `0x00` | `OK` | 오류 없음 |
| `0x01` | `INVALID_OPCODE` | 알 수 없는 Opcode |
| `0x02` | `INVALID_GPR` | r8~r31 참조 |
| `0x03` | `INVALID_CSR` | 없는 CSR / RO에 Write |
| `0x04` | `INVALID_REGION` | 미지원 메모리 영역, LOAD/STORE 방향 오류 |
| `0x05` | `MISALIGNED` | PC/주소/길이 정렬 위반 |
| `0x06` | `MEMORY_BOUNDS` | 실물 SRAM 깊이, IMEM/DMEM 배정 크기 초과, 범위 wrap |
| `0x07` | `INVALID_CONFIG` | GEMM/ARGMAX 지원 범위 위반, Length 0 |
| `0x08` | `ILLEGAL_ENCODING` | 예약 funct3/funct7/필드 조합 |

- **오류 감지 후** `ERROR_CODE` 설정, `STATUS=2`, `fault=1`(Halt 동안 유지), `busy=0`, 이후 메모리 write/엔진 start 불허. `END`면 `STATUS=1`, `done` **1클럭 펄스**, Halt 유지. Reset만 Halt 해제.
- 주소/길이/구성 오류는 **명령 실행 시작 전 가능한 한 검증**하여 부분 부작용을 줄임. 검증되지 않은 런타임 Fault에서 이미 쓰인 메모리의 rollback은 보장하지 않음.
- 동일 사이클 여러 오류 가능 시 우선순위: Opcode/Encoding → GPR/CSR → Alignment → Region → Bounds → Config. 첫 오류 코드만 sticky 기록.
- Reset 시 `STATUS=0`, `ERROR_CODE=0`, `fault=0`, `done=0`.

## 10. 예시 어셈블리 (정확도 테스트 내부)

```asm
; Python allocator가 IMG_BASE/IMG_END/PRED_BASE를 제공
; r1=image pointer, r2=performance pointer (정확도 테스트에선 불필요),
; r3=784, r5=BUF_A/ARGMAX result, r6=prediction pointer, r7=image end.
LI r1, IMG_BASE
LI r3, 784
LI r6, PRED_BASE
LI r7, IMG_END
SETI M, 1
SETADDR ARG_SRC, BUF_B
SETI ARG_LEN, 10
LOOP:
    LI r5, BUF_A
    LOAD r1, r5, r3
    ; FC1/FC2/FC3 설정 (SETADDR, SETI) + 각 EXEC GEMM
    EXEC ARGMAX, r5
    SW r5, 0(r6)
    ADDI r1, r1, 784
    ADDI r6, r6, 4
    BNE r1, r7, LOOP
END
```

위 코드는 반복/분기 원리를 보여주는 **부분 예시**다. 실제 생성기는 Weight Bank 4개와 Bias LOAD, 각 FC 설정·EXEC, 가중치 pack 및 외부 주소 정의까지 포함해야 한다.

## 11. 명시적인 비목표 / 변경 관리

- v1: `M=1` only, INT8 GEMM/ARGMAX, GPR 8개, Read Port 3개 또는 다중 사이클 GPR Operand fetch 허용, 단일 Timer, 외부 메모리 고정 1clk, BRAM 1clk.
- 추가 예정 기능(현재 미구현): 10/16/32 GPR, LOAD immediate 변형, 모델 Descriptor, 다중 M, Weight Bank 수 추상화, Conv/Attention, AXI, 시스템 Trap, Timer 별도 Event Type.
- 지원 범위를 늘리는 경우 **명세 버전 변경 후 구현**. Codex가 임의로 확장해서는 안 됨.
