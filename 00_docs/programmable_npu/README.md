# Programmable NPU v1.0 — 문서 색인

> 문서 확정일: 2026-11-24 · 대상 저장소: `darwin5991/AISSD_project` · 구현 상태: **명세 확정 / 새 ISA RTL 미구현**
>
> 기존 `00_docs/architecture.md`는 **고정 3-Layer MLP 베이스라인**을 설명한다. 이 디렉터리는 그 RTL을 **명령어 구동 NPU**로 확장하기 위한 새로운 구현 계약이다. 기존 성능/정확도 수치를 새 설계의 검증 결과로 인용하지 않는다.

## 문서 순서

1. [`01_isa_spec.md`](01_isa_spec.md): 명령어·인코딩·CSR/GPR·주소 공간·Timer·오류의 **기능 계약**
2. [`02_architecture.md`](02_architecture.md): 모듈/인터페이스, 메모리 사이클, 기존 RTL 재사용·변경 범위
3. [`03_implementation_plan.md`](03_implementation_plan.md): Codex 작업 단계, 기존 파일별 변경 계획, 완료 기준
4. [`04_verification_plan.md`](04_verification_plan.md): 유닛→통합→MNIST 정확도→합성/Timing 검증 계획
5. [`../../AGENTS.md`](../../AGENTS.md): Codex용 저장소 작업 규칙(배포 시 저장소 루트에 배치)

## 이번에 최종 확정한 선택

- IMEM/외부 DMEM: **독립적인 32-bit Single-Port 동기식 인터페이스**, 고정 1클럭 읽기 응답; Write는 요청 수락 상승 에지에 완료.
- Timer: `TSTART/TSTOP`으로 활성화/정지, **LOAD/GEMM 엔진이 실제 active인 사이클만** 32-bit 카운트; STORE·ARGMAX·Fetch·CSR·Scalar는 제외.
- Fault: `ERROR_CODE`와 `STATUS`를 기록하고 **Error Halt**, 프로그램 내 trap 없음, Reset으로 복구.
- 내부 SRAM: **1클럭 동기식 읽기**, 각 RAM Single-Port, 추가 BRAM primitive output register 없음. 최종 FPGA 구현은 과제 조건에 맞는 Block Memory Generator(BMEM) Native Single-Port IP로 매핑.

## 결정과 가정의 구분

- **확정된 구조**: 32-bit 고정 명령어, 8×32-bit GPR(`r0=0`), CSR 기반 GEMM, GPR 3개 기반 블록 LOAD/STORE, 별도 EXEC GEMM/ARGMAX, 단일 순차 실행, 외부 IMEM/DMEM, 내부 SRAM 7개, 10,000장 정확도 테스트에서는 Timer·중간 출력 STORE 생략.
- **v1.0 구현 프로파일로 고정한 세부 규칙**: 아래 명세에 명시된 인코딩·오류 코드·메모리 상태·상위 start/done 핸드셰이크·지원 범위. 대화에서 다루지 않은 극단적인 경우를 임의 구현으로 결정하지 않도록 문서에 명시함.
- **이번 범위 밖**: RV32I 완전 호환, 명령어 파이프라인, AXI/DDR, 멀티코어, Conv/Attention, 물리 GPR 증설, 연산/전송 중첩, 다중 Timer.

명세 간 충돌 시 01의 ISA 기능 계약 → 02의 사이클/인터페이스 계약 → 03의 구현 절차 → 04의 테스트 순서로 판단한다. 기존 베이스라인은 레거시 RTL 해석의 근거이며 새 ISA 명세보다 우선하지 않는다.
