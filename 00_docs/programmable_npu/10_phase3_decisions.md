# Phase 3 범위 및 메모리 오류 분류 확정

날짜: 2026-11-24. 사용자 응답으로 확정한 구현 기준이다. 테스트 PASS 기록은 별도 Phase 3 보고서를 따른다.

## 범위

기존 계획의 Phase 4였던 블록 LOAD/STORE를 이번 Phase 3으로 앞당긴다.
기존 Phase 3의 Scalar LW/SW는 후속 Phase 4 승인 범위로 남긴다.
Phase 5 GEMM과 Phase 6 ARGMAX 구현을 이번 단계에 포함하지 않는다.
이 변경은 Phase 3/4의 수행 순서 재정의이며 ISA 인코딩·메모리 타이밍 변경이 아니다.

## DMEM 영역과 Bounds

외부 DMEM 논리 영역은 상위 4bit=0x1인 [0x10000000,0x20000000)이다.
실제 유효 용량은 Top/TB의 DMEM_BYTES로 정한다 (기본 16MiB).
논리 영역 안의 실제 용량 초과는 MEMORY_BOUNDS(0x06), 외부 주소가 이 논리 영역 밖이면 INVALID_REGION(0x04)이다.
정렬 위반은 기존 ISA 우선순위에 따라 먼저 MISALIGNED(0x05)로 처리한다.
내부 SRAM은 기존 7개 window와 실제 깊이를 그대로 사용하며, window의 빈 공간은 MEMORY_BOUNDS다.

## 부분 전송 오류 — 기존 ISA 9절 적용

주소·길이·은행 경계·32bit wrap을 전송 시작 전에 전체 검사한다.
따라서 정상 입력의 잘못된 주소/길이는 메모리 요청 전에 Fault하며 부분 변경하지 않는다.
고정 지연 외부 메모리 인터페이스에는 오류 응답선이 없다. bus-error 핀이나 handshake를 추가하지 않는다.
전송 중 오류 경로 검증은 TB가 내부 cursor를 잘못된 주소로 바꾸는 fault injection으로 수행한다.
오류 감지 후 추가 요청·쓰기를 중단하고 Error Halt한다.
이미 완료된 목적지 write는 기존 ISA 9절대로 rollback을 보장하지 않는다.
GPR 및 RW 설정 CSR은 전송 중 쓰지 않으며, STATUS/ERROR_CODE 및 실제 active 에지에 따른 Timer 갱신은 정상적인 관찰 상태 변화다.
이 항목은 기존 런타임 Fault 계약의 적용이며 새로운 rollback 규칙을 추가한 것이 아니다.

## 검증 범위

이번 직렬 구현의 정상 LOAD는 요청 R → 응답 캡처 R+1 → SRAM write R+2를 반복한다.
유효 LOAD의 첫 read 요청 에지부터 마지막 write 에지까지 3×word_count개의 active 에지를 센다.
operand 수집·사전 검사·done 확인·Fetch는 제외하며, STORE는 세지 않는다.
런타임 Fault가 발생하면 해당 abort 처리까지 engine active였던 에지도 측정될 수 있다 (ISA의 active 정리 사이클 포함 규칙).
새 NPU Wrapper의 GEMM/ARGMAX 포트는 소유자 선택·메모리 타이밍만 검증하며 실제 연산 엔진의 구현 완료를 뜻하지 않는다.
