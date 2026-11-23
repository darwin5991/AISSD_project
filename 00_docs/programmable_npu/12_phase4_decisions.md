# Phase 4 설계 확인 — Scalar LW/SW 주소 산술

작성일: 2026-11-24 (Asia/Seoul).

Phase 3 보존 커밋 6ccd00d에서 Phase 4 Scalar LW/SW 구현을 시작한다.
Phase 5 GEMM은 별도 승인 전 진행하지 않는다.

## 사용자 확정: Base + signed imm12의 wrap 오류 우선순위

ISA의 wrap=MEMORY_BOUNDS 규칙과 Region 우선순위가 겹치는 경우를 질의했고 사용자가 다음 순서를 승인했다.

1. 최종 주소의 4byte 정렬 검사: MISALIGNED(0x05).
2. 확장 폭으로 계산한 주소가 음수이거나 0xFFFFFFFF 초과: MEMORY_BOUNDS(0x06).
3. wrap이 없는 주소의 상위 4bit가 0x1이 아니면 INVALID_REGION(0x04).
4. DMEM_BYTES 내 마지막 4byte word를 벗어나면 MEMORY_BOUNDS(0x06).

32bit로 잘라 Region 검사에 넣기 전에 산술 wrap을 검사한다.
Opcode/Encoding 및 GPR 검사는 기존처럼 주소 검사보다 우선한다.
기존 next-PC 유효성 검사를 통과한 명령만 메모리 요청 상태로 진입하며,
LW/SW의 마지막 IMEM word에서 next-PC Bounds Fault 시에도 DMEM/GPR 부작용을 금지한다.
기존 Block LOAD/STORE 검사 순서와 RTL은 바꾸지 않는다.

예: 0xFFFFFFFC + 4 및 0 + (-4)는 0x06,
0 + (-1)은 정렬 우선으로 0x05, 0x10000000 + (-4)는 wrap이 없으므로 0x04다.
