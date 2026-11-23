# Phase 0 이후 추가 확정 사항 — D-01~D-04

날짜: 2026-11-24. 참고: `06_phase0_report.md` 6절. **이 문서는 설계 결정 기록**이며 코드 변경이나 테스트 PASS를 의미하지 않는다.

## D-01 — CSR 검증 시점: A 확정

- 존재하는 R/W 설정 CSR은 `SETI/CSRW` 시 들어온 **32bit 원본 값 그대로 저장**한다.
- 설정 범위, 조합, SRAM 크기·주소 검사는 해당 `EXEC` 수락 시 CSR snapshot 기준으로 수행한다. 유효하지 않은 중간값에 대한 조기 Fault는 금지한다.
- 없는 CSR 주소, RO CSR 쓰기, 불법 명령 형식은 해당 CSR 명령에서 즉시 Fault.
- 예: `SETI K,3; SETI K,128; EXEC GEMM`에서 첫 설정은 허용하며, GEMM은 최종 K=128로 검사.

## D-02 — 짧은 K 미지원으로 범위 제한 (A/B 대안 대신 사용자 결정)

- **초기 버전에서는 K=4 등 짧은 K를 실행하지 않는다.** 짧은 K 처리를 위한 Bias 별도 staging/정렬 회로는 현재 구현 범위에 포함하지 않는다.
- 특히 **K=4는 항상 미지원으로 처리하고 `EXEC GEMM` 수락 시 `INVALID_CONFIG` Fault를 내며, GEMM 시작이나 SRAM 쓰기를 해서는 안 된다.** Fault 없는 무시/잘못된 출력 생성은 허용하지 않는 것을 권장한다.
- K는 4의 배수여야 하지만 4의 배수라는 이유로 모두 지원되는 것은 아니다. **정확한 최소 지원 K는 Phase 5에서 경계 타이밍 분석 및 directed simulation을 통해 결정**한다. 확인 전에는 기존 FC의 K=128/512/784만 기존 동작의 안전성이 알려진 상태로 취급한다(새 ISA 통합 자체의 검증 완료를 의미하지 않음).
- `K=8,12,16,32` 등의 경계 시험을 통해 지원 하한을 확정한다. 짧은 K를 나중에 지원하고 싶다면 staging 또는 gap 정책을 별도 제안/승인받아야 한다.

## D-03 — IMEM Fetch 범위: A 확정

- **IMEM 할당 용량**을 경계 검사 기준으로 한다. 적재한 코드 길이를 Top으로 전달하거나 검사하지 않는다.
- 기본 프로파일: `IMEM_BASE=0x00000000`, `IMEM_BYTES=64*1024` (16,384개 32bit word). `DMEM_BASE=0x10000000`, `DMEM_BYTES=16*1024*1024`. Top과 TB는 동일한 elaboration 파라미터로 용량을 공유한다.
- 예: 256byte(64 instruction) 프로그램이 적재됐어도 PC=0x00000100은 IMEM **용량 안**에 있으므로 fetch 시도. TB가 사용하지 않는 모든 IMEM word를 0x00000000으로 초기화했으므로 `INVALID_OPCODE(0x01)` (후속 사용자 확정: 0 opcode는 기존 오류 표의 알 수 없는 opcode로 처리; 새 오류 코드 추가 없음)이 된다.
- 반면 PC=0x00010000은 용량 바깥이므로 Fetch 요청 전 `MEMORY_BOUNDS` Fault. PC는 4byte 정렬이어야 하며 마지막 유효 Word 시작 주소는 0x0000FFFC이다.
- TB에서 전체 미사용 IMEM을 0으로 초기화하는 이유는 미적재 영역의 X/랜덤 값으로 인한 비결정성을 없애기 위해서다. **실제 FPGA/BRAM/IP에서는 미사용 Word가 자동 0이라는 보장이 없으므로** 별도 ROM 이미지 초기화, 전체 메모리 로드, 또는 사용하지 않는 영역을 접근하지 않도록 보장하는 방안이 필요하다.
- 정상 프로그램은 `END`로 종료. 미적재 영역에 진입하면 0을 illegal instruction으로 처리하지만, 이 동작은 **TB의 명시적 zero fill에 의존**한다.

## D-04 — Branch 후보 검사: A 확정

- `BEQ/BNE`에서 조건에 따라 **선택된 next PC**(`PC+offset` 또는 `PC+4`)만 정렬/IMEM Bounds 검사한다. 조건이 거짓일 때 후보 target의 misalign/out-of-range는 Fault를 발생시키지 않는다.
- `JAL`은 항상 target 검사. invalid target이면 link register/PC 상태 변경 전에 Fault 처리.
- 예: `PC=0x100`, `BEQ r1,r2,+2`, 조건 거짓이면 PC=0x104 정상. 참이면 목표 0x102가 4byte misalign이므로 Fault.

## Codex 반영

1. Phase 1 구현 전 이 문서를 `01_isa_spec.md`, `02_architecture.md`, `03_implementation_plan.md`, `04_verification_plan.md`와 함께 읽는다.
2. Phase 1은 D-03/D-04와 기존 Scalar/Fetch 범위만 구현하고, Phase 2에서 D-01, Phase 5에서 D-02를 구현한다.
3. 각 Phase에서 아직 검증하지 않은 지원 범위를 PASS로 표시하지 않는다.
4. 기존 `mlp_top` RTL 및 회귀 테스트는 보존한다. 임의로 Phase 2 이상으로 넘어가지 않는다.
