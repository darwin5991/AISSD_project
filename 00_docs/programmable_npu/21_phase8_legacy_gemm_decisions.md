# Phase 8 후속 — Legacy GEMM 재사용 설계 결정

2026-11-24 KST. 사용자 구현 승인. 시작 Branch: phase8/direct-bram-inference-20261124. 시작 HEAD: 1192f3f4f7b6c7e2b34e8b09ab4f0f885d5b65d5. 시작 Working Tree clean. 현재 브랜치 유지, Commit/Push 없음.

## 1. 최신 GEMM 계약

이 결정은 GEMM에 한해 01/02/03/04 및 14번의 기존 하드웨어 설정/Runtime Fault 보장을 대체한다. 15~20번 결과 보고서는 과거 실행 기록으로 보존한다.

- 명령 수락 시 CSR 10개 원본 32bit를 한 에지에 Snapshot한다. ISA 인코딩/CSR 번호와 CSR readback을 변경하지 않는다.
- 정상 설정을 프로그램/fixture 생성 시 소프트웨어로 검사한다: M=1, N=1~512, K>=8이고 4의 배수, Input/Output은 반대 A/B, 정렬된 정상 역할 및 실제 깊이 안의 전체 배치, signed Bias Shift -32~31, Output Shift 0~31, ACT 0/1. K=4는 소프트웨어 ValueError다.
- GEMM 하드웨어 설정/Region/Bounds/Runtime 검사와 오류 병합을 제거한다. 잘못된 GEMM 설정의 실행/오류/종료/메모리 보존은 보장하지 않으며 새로운 동작을 정의하지 않는다.
- Fetch/Decode/GPR/CSR 접근 권한/next-PC, Scalar LW/SW, LOAD/STORE, ARGMAX, END/Fault Halt는 변경하지 않는다. 유효 GEMM이라도 next-PC 오류이면 기존 Instruction Controller가 Start 전에 차단한다.
- 기존 오류 출력은 포트 호환용 ERR_OK/fault=0이다. 다른 명령어의 오류 회로를 제거하지 않는다.

## 2. 실행 구조

- gemm_controller 내부의 최소 Adapter와 IDLE/PREP/RUN/DRAIN FSM만 사용한다. control_state_pkg의 control_state_t와 실제 상태 의미를 사용한다.
- pipeline_control/read_issue_control/counter_en/pipeline_event_control/delay_line은 원본 그대로 사용한다. layer_index=0, Layer Counter/자동 Layer 전이/자동 ARGMAX 없음.
- Input 8bit와 Group 7bit counter_en을 두 개 인스턴스화한다.
- S에서 설정 저장/PREP, S+1 RUN 진입, S+2 첫 Read다. 기존 한 사이클 그룹 공백, 첫 Bias R+1, 후속 Bias/Result R+5, Write R+6 유지.
- 마지막 layer_stored에 해당하는 실제 Write 에지에서 Done 레지스터를 올리고 IDLE로 복귀한다. 다음 에지에 Instruction Controller가 완료를 소비한다. 매 GEMM Reset 없음.
- Timer는 이전과 같이 PREP/RUN/DRAIN 상승 에지만 센다. Snapshot/Fetch/검사 대기, STORE/ARGMAX 제외.

## 3. 주소와 보존 범위

Input=Input Base+Input Counter, Weight=Weight Cursor, Bias=Bias Base+Group, Output=Output Base+6단 지연 Group이다.

Base는 유효한 SRAM 창 내부의 byte-to-word 변환이다. A/B/Bias Base는 8bit, Weight Cursor는 15bit다. 계산한 주소는 기존 15bit GEMM 포트에 전달하며 Output A 128~195를 자르지 않는다. Weight Cursor는 실제 Read마다 한 번 증가하고 그룹 공백/Drain에서 유지한다.

7개 SRAM 깊이/포트/Reset/BRAM inference, MAC/Accumulator/Postprocess, 외부 IMEM/DMEM 및 Reset Wrapper는 변경하지 않는다. 새로운 Pipeline Stage/메모리/ISA 기능 없음.

## 4. 소프트웨어 및 검증 경계

gemm_config.validate_gemm_config는 원본 전체 값과 넓은 Python 정수로 전체 배치를 검사한다. Application build_program은 모든 Layer를 프로그램 생성 전에 검사하고, 정상 GEMM fixture 생성도 EXEC 설정을 검사한다. 임의 수기 바이너리의 CSR 흐름을 분석하는 범용 검증기는 아니다.

G0 문서/소스 확인, G1 Legacy 연결, G2 Cursor/주소, G3 정상 GEMM/파형, G4 첫 200장, G5 선택 회귀 이후에만 G6 동일 10ns FPGA Flow로 진행한다. 각 단계의 실제 근거와 최종 판정은 22번 보고서를 따른다. 기존 GEMM Fault suite의 제외 항목을 새 PASS로 표시하지 않는다.

Timing FAIL이면 임의 주파수/예외/대규모 구조 변경 없이 결과 보고 후 중단한다. 10,000장은 실행하지 않는다.
