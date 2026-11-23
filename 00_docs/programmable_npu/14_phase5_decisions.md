# Phase 5 확정 설계 결정과 검증 경계

날짜: 2026-11-24 (Asia/Seoul). 사용자 승인에 따른 Phase 5 구현 기준이다.

- INT32 누산은 상위 비트 절단 후 2의 보수 Signed INT32로 해석하는 wrap-around다. Bias 정렬의 기존 32bit 절단과 INT8 Output Saturation을 유지한다. Python Golden도 동일한 수치 규칙을 따른다. 산술 Overflow를 새 Fault로 만들지 않는다.
- 메모리/설정 오류 우선순위: Alignment → Region → Memory Bounds → Configuration. Opcode/Encoding/GPR/CSR의 기존 선행 검사는 유지한다.
- K=4는 미지원 INVALID_CONFIG다. 다른 오류가 겹치면 위 우선순위를 적용하므로 D-02의 이전 '항상' 표현을 이 결정으로 한정한다.
- GEMM 역할에 맞지 않는 Bank는 INVALID_REGION(0x04), SRC0/DST가 같은 Buffer인 조합은 INVALID_CONFIG(0x07)다.
- K=8/12/16/32와 출력 그룹 수·연속 GEMM의 실제 검증이 PASS했고 2026-11-24 후속 사용자 승인으로 최소 K=8을 정식 지원 하한으로 확정했다. K=4는 INVALID_CONFIG(0x07)이며 다른 오류가 겹치면 기존 우선순위를 적용한다. K=4용 Bias staging/추가 gap은 구현하지 않는다.
- MAC/Accumulator/Postprocess, SRAM 7개, 1clk read와 R→R+6 및 기존 Bias 일정을 보존한다. Legacy LUT/Controller는 보존하고 독립 GEMM Controller를 추가한다.
- CSR 설정 원본 10개를 한 에지에 Snapshot하고 원본 32bit로 검사한 뒤에만 GEMM을 시작한다. 내부 GEMM 완료는 IDLE 복귀이며 NPU END와 구분한다. 자동 ARGMAX는 없다.
- Timer는 Snapshot/검증을 제외하고 첫 실행 PREP부터 최종 Output Write까지 센다. 정상 제안 구조는 PREP 1edge + RUN(그룹 사이 1edge gap) + DRAIN이다.
- 합성/FPGA 검증은 이번 Gate 필수 조건이 아니다. Phase 6은 별도 승인 전 진행하지 않는다.
