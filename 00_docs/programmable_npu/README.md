# Programmable NPU v1.0 — 문서 색인

> 문서 확정일: 2026-11-24 · 대상 저장소: `darwin5991/AISSD_project` · 구현 상태: **Phase 1~5 Scalar/CSR/Timer/Block/SRAM/GEMM 구현·검증 PASS / 최소 K=8 확정 / 메모리·PC 복합 Fault 후속 Gate PASS / Phase 6 승인 대기**
>
> 기존 `00_docs/architecture.md`는 **고정 3-Layer MLP 베이스라인**을 설명한다. 이 디렉터리는 그 RTL을 **명령어 구동 NPU**로 확장하기 위한 새로운 구현 계약이다. 기존 성능/정확도 수치를 새 설계의 검증 결과로 인용하지 않는다.

## 문서 순서

1. [`01_isa_spec.md`](01_isa_spec.md): 명령어·인코딩·CSR/GPR·주소 공간·Timer·오류의 **기능 계약**
2. [`02_architecture.md`](02_architecture.md): 모듈/인터페이스, 메모리 사이클, 기존 RTL 재사용·변경 범위
3. [`03_implementation_plan.md`](03_implementation_plan.md): Codex 작업 단계, 기존 파일별 변경 계획, 완료 기준
4. [`04_verification_plan.md`](04_verification_plan.md): 유닛→통합→MNIST 정확도→합성/Timing 검증 계획
5. [`../../AGENTS.md`](../../AGENTS.md): Codex용 저장소 작업 규칙(배포 시 저장소 루트에 배치)
6. [06_phase0_report.md](06_phase0_report.md): 기존 RTL 기준선 진단
7. [07_design_decisions_phase0.md](07_design_decisions_phase0.md): D-01~D-04 확정 사항 (우선 적용)
8. [08_phase1_report.md](08_phase1_report.md): Phase 1 구현·실행 검증 및 후속 범위
9. [09_phase2_report.md](09_phase2_report.md): Phase 1 보존 커밋 및 Phase 2 CSR/Timer 검증
10. [10_phase3_decisions.md](10_phase3_decisions.md): Phase 재정의·DMEM 논리 영역 사용자 확정
11. [11_phase3_report.md](11_phase3_report.md): Phase 2 보존 커밋 및 Phase 3 Block LOAD/STORE·SRAM·Timer 검증
12. [12_phase4_decisions.md](12_phase4_decisions.md): Scalar 주소 산술 wrap 오류 우선순위 사용자 확정
13. [13_phase4_report.md](13_phase4_report.md): Phase 3 보존 커밋 및 Phase 4 Scalar LW/SW 검증
14. [14_phase5_decisions.md](14_phase5_decisions.md): INT32 wrap·GEMM 오류 우선순위·역할·하한 검증 방침
15. [15_phase5_report.md](15_phase5_report.md): 독립 GEMM/Snapshot/수치·타이밍·회귀 결과와 최소 K 확정
16. [16_memory_fault_priority_report.md](16_memory_fault_priority_report.md): Phase 5 보존 커밋·별도 브랜치의 메모리/next-PC 오류 통합 및 전체 회귀 PASS

## 이번에 최종 확정한 선택

- IMEM/외부 DMEM: **독립적인 32-bit Single-Port 동기식 인터페이스**, 고정 1클럭 읽기 응답; Write는 요청 수락 상승 에지에 완료.
- Timer: `TSTART/TSTOP`으로 활성화/정지, **LOAD/GEMM 엔진이 실제 active인 사이클만** 32-bit 카운트; STORE·ARGMAX·Fetch·CSR·Scalar는 제외.
- Fault: `ERROR_CODE`와 `STATUS`를 기록하고 **Error Halt**, 프로그램 내 trap 없음, Reset으로 복구.
- 내부 SRAM: **1클럭 동기식 읽기**, 각 RAM Single-Port, 추가 BRAM primitive output register 없음. 최종 FPGA 구현은 과제 조건에 맞는 Block Memory Generator(BMEM) Native Single-Port IP로 매핑.

## 결정과 가정의 구분

- **확정된 구조**: 32-bit 고정 명령어, 8×32-bit GPR(`r0=0`), CSR 기반 GEMM, GPR 3개 기반 블록 LOAD/STORE, 별도 EXEC GEMM/ARGMAX, 단일 순차 실행, 외부 IMEM/DMEM, 내부 SRAM 7개, 10,000장 정확도 테스트에서는 Timer·중간 출력 STORE 생략.
- **v1.0 구현 프로파일로 고정한 세부 규칙**: 아래 명세에 명시된 인코딩·오류 코드·메모리 상태·상위 start/done 핸드셰이크·지원 범위. 대화에서 다루지 않은 극단적인 경우를 임의 구현으로 결정하지 않도록 문서에 명시함.
- **이번 범위 밖**: RV32I 완전 호환, 명령어 파이프라인, AXI/DDR, 멀티코어, Conv/Attention, 물리 GPR 증설, 연산/전송 중첩, 다중 Timer.

명세 간 충돌 시 [07 설계 결정](07_design_decisions_phase0.md)의 D-01~D-04 및 [10](10_phase3_decisions.md)·[12](12_phase4_decisions.md)·[14 후속 사용자 확정](14_phase5_decisions.md) → 01의 ISA 기능 계약 → 02의 사이클/인터페이스 계약 → 03의 구현 절차 → 04의 테스트 순서로 판단한다. 기존 베이스라인은 레거시 RTL 해석의 근거이며 새 ISA 명세보다 우선하지 않는다.
