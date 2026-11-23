# Phase 6 — ARGMAX 설계 결정 D-01/D-02

날짜: 2026-11-24 (Asia/Seoul). 기준 HEAD: `414fd57` (부모 Phase 5 `5be9059`).

**상태: P6-D-01/P6-D-02 사용자 최종 확정 유지.** 최초 문서화 이후 사용자 후속 요청으로 Phase 6 RTL 구현·검증을 승인받았고 **Gate PASS**했다. [18번 구현 보고서](18_phase6_report.md)를 따른다. 아래 결정 본문은 그대로 보존하며 최초 문서 작업의 승인 경계와 현재 실행 결과를 구분한다.

이 문서의 **P6-D-01/P6-D-02**는 Phase 6에 한정한 식별자다. [07번 결정](07_design_decisions_phase0.md)의 기존 D-01(CSR 원본 저장/EXEC 검증)·D-02(GEMM K 제한)를 대체하지 않는다.

## P6-D-01 — ARGMAX 데이터/next-PC 오류 통합

ARGMAX 데이터 오류와 선택된 next-PC Bounds가 동시에 발생하면 GEMM 및 LW/SW·Block과 같은 우선순위를 적용한다.

1. 기존 Opcode/Encoding 검사.
2. 기존 GPR/CSR 선행 검사.
3. Alignment → MISALIGNED(0x05).
4. Region 및 A/B source 역할 → INVALID_REGION(0x04).
5. 실제 Buffer 범위 및 next-PC Bounds → MEMORY_BOUNDS(0x06).
6. Configuration → INVALID_CONFIG(0x07).

ARGMAX도 EXEC 수락 시의 Snapshot을 검사하고 데이터 오류와 next-PC 오류를 병합한 뒤, 성공한 경우에만 실제 Engine start/SRAM Read를 허용한다. 잘못된 next-PC의 정상 주소도 요청을 발행하지 않는다. 잘못된 Encoding/GPR는 메모리·설정 오류보다 먼저 Fault한다. EXEC ARGMAX 자체에는 CSR 번호 operand가 없으며, 잘못된 CSR 접근은 해당 SETI/CSRW/CSRR에서 기존 규칙으로 처리한다.

| 데이터 조건 + next-PC Bounds | 최종 ERROR_CODE |
|---|---|
| Alignment 위반 | 0x05 |
| 잘못된 Region/Weight/Bias source | 0x04 |
| Buffer Bounds 위반 | 0x06 |
| 정상 데이터 | 0x06 |
| 주소·범위는 정상이고 ARG_LEN만 0 또는 11 | 0x06 |

기존 Scalar 주소 산술 wrap의 [12번 결정](12_phase4_decisions.md)은 유지한다. 새 오류 코드나 END 예외를 추가하지 않는다.

## P6-D-02 — 원본 ARG_LEN으로 Word 수·전체 범위를 먼저 검사

`L`은 Snapshot의 **원본 unsigned 32bit ARG_LEN**이다. 아래 값은 축소 없이 충분히 넓은 폭으로 계산한다. 계획에서는 모두 64bit로 확장한 산술을 사용한다.

| 값 | 계산 |
|---|---|
| 필요한 SRAM Word 수 W | ceil(L/4) = (zext64(L)+3) >> 2 |
| 실제 읽기 범위 크기 B | W × 4 bytes |
| 끝 주소 E, exclusive | zext64(ARG_SRC) + B |
| 선택 Buffer 끝 T, exclusive | Buffer base + 4 × 실제 word 깊이 |

ARG_SRC의 4byte 정렬, A/B 논리 Region/역할을 확인한 뒤 시작 주소와 E를 실제 Buffer 범위에 대해 검사한다. ARG_SRC는 T보다 작아야 하고 E는 T 이하여야 한다. **L이 0 또는 10 초과여도 Bounds 검사를 생략하지 않는다.** 그 뒤에 원본 L이 1~10인지 Configuration을 검사한다. next-PC Bounds도 P6-D-01에 따라 Configuration보다 우선한다.

- LEN=0이면 W=0, E=ARG_SRC다. W−1 방식의 underflow를 피한다. 정상 시작 주소이면 0x07, 시작 주소가 Buffer 끝이면 0x06이다.
- LEN=11이면 W=3, B=12다. base에서는 0x07, 끝에서 8byte만 남은 위치에서는 0x06이다.
- LEN=0xFFFFFFFF이면 W=0x40000000, B=0x100000000이다. 32bit의 L+3 또는 B 절단으로 0이 되어서는 안 된다. A/B source에서는 실제 범위를 초과하므로 0x06이다.
- LEN=0x10000001이면 하위 4bit=1이어도 W=0x04000001이다. 정상 1개 요청으로 오인해서는 안 되며 A/B source에서는 0x06이다.
- ARG_LEN은 INT8 요소 수다. 길이 자체의 4byte 정렬 조건은 없다. LEN=1/3/9/10은 정상이다.
- 모든 검증을 통과한 후에만 좁은 길이/주소 필드를 실행에 소비하고 실제 Read를 허용한다.

A/B 이외 Region은 먼저 0x04로 판정하며, 다른 Bank의 깊이로 ARGMAX Bounds를 검사하지 않는다.

## 기존 계약 유지

- EXEC ARGMAX,r5 = `0x020022AB`, ARG_SRC=`0x7E0`, ARG_LEN=`0x7E1`. Opcode/Encoding/CSR 번호 변경 없음.
- [07번 D-01](07_design_decisions_phase0.md): RW CSR 쓰기는 원본 32bit 저장, 검증은 EXEC Snapshot 기준이다. ARG_SRC/LEN도 같은 수락 에지에 원자적으로 Snapshot한다.
- Buffer A/B, signed INT8, 오름차순 비교, lowest-index tie, 유효 요소 외 padding 비교 제외.
- 결과 32bit zero-extend, rd=r0은 검사·실행 후 결과 쓰기만 생략.
- GEMM 완료 후 자동 실행 없음. 내부 argmax_done과 END의 Top done을 구분한다. Top done은 END에서만 1클럭이다.
- ARGMAX는 Timer 대상이 아니다. Count/armed/overflow를 보존한다.
- Fault Halt의 PC/GPR/RW CSR 보존, STATUS/ERROR_CODE 기록·유지, Reset 후 재실행 규칙 유지.
- 기존 SRAM 7개, 32bit 폭/깊이, Single-Port 1clk Read, MAC R→R+6 및 Legacy RTL 보존.

## 반영 위치와 최초 문서 작업의 승인 경계 (이력)

- [ISA 6절·9절](01_isa_spec.md): 기능·검증·오류 계약.
- [Architecture 5절](02_architecture.md): Snapshot 책임, 사전 검사와 SRAM 타이밍.
- [Implementation Plan Phase 6](03_implementation_plan.md): 권장 순서·신규/수정 예정 파일.
- [Verification Plan 5.1절](04_verification_plan.md): 입력·기대 코드·부작용·타이밍 테스트 명세. 최초 문서화 시 미실행이었으며 후속 결과는 18번 보고서 PASS를 따른다.
- [README](README.md): 현재 승인 범위와 문서 색인.

두 결정의 미정 선택지는 해소됐다. 독립 Engine 및 FSM/포트 이름은 아직 RTL로 구현하지 않은 권장 구현 계획이다. 이번 작업은 테스트 항목을 문서에 추가하며 실행 가능한 테스트 코드/RTL을 작성하거나 기존 회귀를 실행하지 않는다. 별도 승인 전 Phase 6 구현 및 Phase 7 작업을 진행하지 않는다.
