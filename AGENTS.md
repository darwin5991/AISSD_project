# Codex work rules — AISSD Programmable NPU

## 시작 전에 읽을 명세

1. `00_docs/programmable_npu/01_isa_spec.md` — ISA의 규범적 동작
2. `00_docs/programmable_npu/02_architecture.md` — 인터페이스/Timing/RTL 구조
3. `00_docs/programmable_npu/03_implementation_plan.md` — Phase별 작업/변경 범위
4. `00_docs/programmable_npu/04_verification_plan.md` — 테스트/완료 기준
5. `00_docs/architecture.md`와 `00_docs/mac_input_pipeline.md` — 기존 MAC/MLP 동작 베이스라인

## 반드시 지킬 사항

- 명세에 없는 ISA 기능·Opcode·CSR·GPR·메모리 프로토콜을 임의로 추가하거나 교체하지 않는다.
- 기존 `mac_array/*`, `accumulator_postprocess/*`의 산술·MAC 3-stage 파이프라인을 불필요하게 수정하지 않는다. 읽기 R에서 결과 Write R+6 계약 유지.
- SRAM A/B, Weight Bank 0~3, Bias 총 7개의 실제 깊이/주소 범위 및 Single-Port 1clk 동기 읽기를 유지한다.
- 외부 IMEM/DMEM은 Top 외부, PC/Fetch/Decoder 및 SRAM은 내부. Block LOAD/STORE는 GPR 3개 기반; GEMM/ARGMAX는 CSR 설정 기반.
- `r0`은 항상 0, r8~r31 접근 Fault, RD field의 LOAD/STORE rs3 재해석, `SETADDR`는 r4 clobber, 모든 명령어 32bit.
- Timer는 LOAD/GEMM 엔진 active 중에만 증가; STORE/ARGMAX/Scalar/Fetch는 제외. `TSTART` 초기화·`TSTOP` 중지.
- Illegal/Bounds/Alignment 접근은 Fault Halt. Error/Status가 스펙과 다르게 조용히 진행하면 안 됨.
- 기존 Legacy Top/TB 회귀 테스트 보존. 새 Top과 Testbench/Assembler는 별도 파일로 시작하는 전략을 우선한다.
- 합성 RTL 안에 메모리 내용 초기화용 `initial`, `$readmemh`, `$writememh`를 넣지 않는다. TB 외부 메모리 모델만 사용 가능.
- MNIST 10,000장 정확도 테스트는 기본적으로 **Timer OFF, 중간 레이어 STORE OFF, Waveform OFF**.
- 저장소 문서/테스트 결과와 함께 변경 내역을 남기고, 검증되지 않은 결과는 PASS라고 표시하지 않는다.

## 단계별 작업 원칙

- `03_implementation_plan.md`의 **현재 Phase만 작업**하고 해당 Phase의 Test Gate PASS 전에는 다음 Phase로 진행하지 않는다.
- 매 단계: 소스 점검 → 차이/수정 계획 → 작은 변경 → 테스트 실행 → diff / 로그 / 영향 범위 요약.
- 명세와 충돌하거나 설계 결정을 추가해야 할 때는 구현을 멈추고 **선택지 + 권장안 + 파급 범위**를 제시한다.
- CPU 전체 RV32I, AXI, DMA 고급 기능, 멀티 GPR, Conv, Attention은 범위 밖.

## 단계 종료 보고 템플릿

- 구현 단계 / 변경 파일 / 새 포트·제어 신호
- 실행한 테스트 커맨드와 PASS/FAIL
- 결함/회귀 테스트 결과 / 재현 가능한 로그 파일
- 남은 불확실성 / 사용자 결정이 필요한 안건
