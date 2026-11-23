# Phase 4 — Scalar LW/SW 구현 및 검증

작성일: 2026-11-24 (Asia/Seoul). 작업 브랜치: `phase4/scalar-memory-20261124`.
기준 커밋: `6ccd00d` — `feat(npu): implement and verify Phase 3 block memory transfer`.

**Phase 4 Gate: PASS. Phase 5 GEMM은 시작하지 않았다.**

## 1. Phase 3 보존 및 시작 전 점검

현재 브랜치의 git status/diff와 Phase 3 보고서, 최종 검증 소스 snapshot 및 문서 hash를 대조했다.
관련 없는 변경이 없었으며, 승인된 Phase 3 파일 22개만 사용자가 지정한 메시지로 6ccd00d에 커밋했다.
07_runs의 로그/HEX와 99_build의 빌드는 커밋에서 제외했다.
커밋 후 clean 상태를 확인하고 Phase 4 브랜치를 만들었다.

AGENTS.md, ISA/Architecture/Implementation/Verification Plan, Phase 3 보고서와
기존 MAC 파이프라인 기준 문서를 다시 확인했다. 실제 Controller/Decoder/GPR/ALU/CSR/Timer,
Top/Block Transfer/7개 SRAM Wrapper 및 기존 검증 스크립트를 점검했다.

Base+signed imm12 산술 wrap과 Region 오류의 우선순위가 겹치는 경우를 질의했다.
사용자 확정은 [12_phase4_decisions.md](12_phase4_decisions.md)에 기록했다.
이번 단계에서 새 Opcode/CSR 번호/프로토콜을 추가하거나 변경하지 않았다.

## 2. 변경 및 신규 파일

| 파일 | 변경 내용 |
|---|---|
| 04_rtl/isa/instruction_decoder.sv | 기존 Opcode 0x03/0x23의 LW/SW, funct3=010만 허용, I/S imm12 부호 확장, 유효한 GPR 참조만 검사 |
| 04_rtl/isa/npu_isa_pkg.sv | OP_LW/OP_SW를 끝에 추가. 내부 enum을 5bit로 확장하고 기존 operation 값 유지. 외부 명령어는 계속 32bit |
| 04_rtl/isa/instruction_controller.sv | 확장 폭 EA/사전 Fault 검사, 주소·write data 래치, MEM_REQ/MEM_WAIT, 지연된 LW writeback, Scalar/Block DMEM 선택 |
| 05_tb/npu/tb_npu_phase4.sv (신규) | 동기 외부 메모리, 요청/데이터/에지 scoreboard, 매 에지 GPR/CSR 조기 변경 차단, 실제 trace/final dump |
| 90_scripts/npu/phase4_vectors.py (신규) | I/S encoder, Python ISA/메모리 Golden, exhaustive signed immediate·정상·Fault·Scalar/Block 혼합 fixture |
| 90_scripts/npu/run_phase4.py (신규) | 소규모 debug 및 3개 DMEM 용량 실행, 실제 RTL dump의 Python 비교, source/data/spec hash·timeout·종료 검증 |
| 00_docs/programmable_npu/01_isa_spec.md | 승인된 wrap 검사 순서 및 LW/SW 기계어 검산 벡터 명시 |
| 00_docs/programmable_npu/02_architecture.md | Scalar/Block DMEM 선택과 LW/SW 실제 완료 타이밍/구현 상태 기록 |
| 00_docs/programmable_npu/03_implementation_plan.md | Phase 4 승인·PASS·실행 결과, Phase 5 승인 경계 |
| 00_docs/programmable_npu/04_verification_plan.md | I-05 및 Scalar 메모리 Fault/Timer 제외의 실제 검증 범위 |
| 00_docs/programmable_npu/README.md | 현재 진행 상태와 12/13 문서 인덱스 |
| 00_docs/programmable_npu/12_phase4_decisions.md (신규) | 사용자 확정 wrap 우선순위 |
| 00_docs/programmable_npu/13_phase4_report.md (신규) | 본 실행 결과 |

기존 소스/TB/스크립트/설정 100개 기준으로 기존 파일 변경은 ISA Controller/Decoder/package 3개뿐이다.
나머지 97개는 hash가 같고 삭제도 없다. Block Transfer 및 memory package/decoder/MUX/Wrapper,
7개 single_port_bram, NPU Top, Legacy MLP/MAC/Accumulator/Postprocess,
GPR/Scalar ALU/CSR/Timer와 기존 Phase 1~3 테스트/runner는 변경하지 않았다.

## 3. 명령어 인코딩 및 동작

| 명령 | Opcode | funct3 | immediate | 검산 벡터 |
|---|---:|---|---|---|
| LW rd,imm12(rs1) | 0x03 | 010 | instruction[31:20], signed 12bit | LW r5,4(r1) = 0x0040A283 |
| SW rs2,imm12(rs1) | 0x23 | 010 | {instruction[31:25],instruction[11:7]}, signed 12bit | SW r2,-4(r1) = 0xFE20AE23 |

LW는 외부 DMEM의 32bit word 전체를 rd에 기록한다. SW는 rs2의 32bit 원본 전체를 기록한다.
부분 byte enable, LB/LH/SB/SH 및 내부 SRAM Scalar 접근은 구현하지 않았다.
유효 immediate 범위는 -2048~2047이다. rs1의 unsigned 32bit 값과 signed immediate를 33bit로 더하고,
범위/정렬 검사를 통과한 주소만 32bit 요청 주소로 래치한다.

LW는 rd/rs1, SW는 rs1/rs2만 GPR 참조다.
LW의 instruction[24:20]과 SW의 instruction[11:7]은 immediate의 일부이므로 GPR 오류로 취급하지 않는다.
r8~r31은 실제 operand 참조일 때 INVALID_GPR(0x02)다.
r0는 계속 0이며, LW rd=r0도 유효 주소의 실제 read와 Fault 검사를 수행하고 writeback 결과만 버린다.
SW rs2=r0는 0을 기록한다. rd=rs1 및 rs1=rs2 alias, load-use/store-use 의존성을 검증했다.

## 4. 메모리 인터페이스·타이밍

Top 외부 포트의 추가/삭제/폭 변경이 없다. IMEM와 DMEM은 별도 포트다.
기존 32bit Single-Port, byte address, 4byte alignment, 1clk synchronous read,
posedge full-word write, disabled/write read-data hold 계약을 유지했다.

Controller 내부에서 MEM_REQ는 Scalar 요청을, XFER_WAIT는 기존 Block Transfer 요청을 선택한다.
나머지 상태의 DMEM 요청은 비활성이다. 응답은 기존 dmem_rdata를 사용하며 현재 소유자만 캡처한다.
추가 arbiter/queue/ready-valid/pipeline은 없다.
SRAM Wrapper나 BRAM read 경로는 수정하지 않았다.

| 에지 | LW | SW |
|---|---|---|
| EXECUTE | Decode/GPR/선택된 next PC/EA 검증 후 주소 래치 | 주소와 rs2 write data 래치 |
| R (MEM_REQ) | DMEM read 수락, 메모리 rdata는 에지 직후 갱신 | DMEM write commit |
| R+1 (MEM_WAIT) | 유효 rdata를 GPR에 writeback하고 PC 전진 | write 이후 완료 확인, PC 전진 |
| R+2 | 다음 Fetch 요청 | 다음 Fetch 요청 |

LW 요청 에지에는 GPR을 갱신하지 않는다. 완료 전 PC/Fetch/GPR/CSR 변경도 차단한다.
기존 Scalar 연산은 Fetch 기준 age=2, 유효 LW/SW는 age=4, 오류는 요청 전 age=2에 Halt한다.
Block LOAD/STORE의 기존 3N+4 완료 age와 3N LOAD active 규칙은 변하지 않았다.
Top done은 END에서만 1cycle이며 각 LW/SW에서 펄스하지 않는다.

짧은 mixed program의 VCD에서 SW 805ns→815ns, 855ns→865ns 완료,
LW 1305ns→1315ns, 1355ns→1365ns writeback을 확인했다 (주기 10ns).
LW 반환 데이터는 각각 0x80000000, 0x00000000이다.
debug만 WDB/VCD를 저장하고 대량 테스트에서는 waveform을 저장하지 않았다.

## 5. Fault·Timer 검증

Opcode/Encoding과 실제 GPR 참조를 먼저 검사한다.
기존 next-PC 검증 성공 후 Scalar EA는 사용자 확정대로 다음 순서로 검사한다.

1. 최종 EA 4byte 정렬: MISALIGNED(0x05).
2. 음수 또는 0xFFFFFFFF 초과의 산술 wrap: MEMORY_BOUNDS(0x06).
3. 상위 4bit가 0x1이 아닌 주소: INVALID_REGION(0x04).
4. [0x10000000,0x10000000+DMEM_BYTES) 내 word 범위 초과: MEMORY_BOUNDS(0x06).

예: 0xFFFFFFFC+4와 0-4는 0x06, 0-1은 정렬 우선으로 0x05,
0x10000000-4는 wrap이 없는 미지원 Region이므로 0x04다.
SRAM/IMEM/MMIO 주소와 다른 Region은 외부 Scalar 경로로 접근하지 못한다.
잘못된 funct3는 ILLEGAL_ENCODING(0x08)이며 invalid GPR보다 우선한다.

주 테스트 315개 중 정상 END 155개, Fault 160개다:
MISALIGNED 16, MEMORY_BOUNDS 15, INVALID_REGION 19, INVALID_GPR 96, ILLEGAL_ENCODING 14.
주소/인코딩/GPR 오류는 해당 명령의 DMEM 요청과 GPR/RW CSR 부작용이 없다.
모든 시나리오는 12개 RW CSR과 r1~r7을 비영 sentinel로 준비한다.
매 에지 조기 갱신 금지, 완료 시 전체 GPR/CSR/Timer/PC/상태, Halt 10클럭의 접근/재시작 차단을 확인했다.

마지막 IMEM word의 LW/SW도 next-PC Bounds Fault로 요청 전에 차단한다.
정상 SW→LW 후 잘못된 SW를 실행한 경우, 앞선 정상 write는 유지하고 잘못된 write 및 이후 instruction Fetch는 차단했다.
이것은 이전 명령을 rollback한다는 뜻이 아니다.

Timer RTL은 변경하지 않았다. TSTART로 armed인 Scalar-only 프로그램에서도 count는 0이다.
7개 SRAM 각각 Scalar SW→Block LOAD→Block STORE→Scalar LW의 혼합 시나리오에서
2word Block LOAD만 6을 세고 Scalar LW/SW 및 Block STORE 동안은 증가하지 않는다.
기존 Phase 2 Overflow/sticky/start-stop 검증도 회귀 PASS다.

## 6. 실행 명령 및 실제 결과

저장소 루트에서 실행했다.

~~~powershell
python -X utf8 -B 90_scripts/npu/run_phase4.py --debug-only --vivado-bin D:/AMDDesignTools/2025.2/Vivado/bin
python -X utf8 -B 90_scripts/npu/run_phase4.py --vivado-bin D:/AMDDesignTools/2025.2/Vivado/bin
python -B 90_scripts/npu/run_phase1.py --legacy --vivado-bin D:/AMDDesignTools/2025.2/Vivado/bin
python -B 90_scripts/npu/run_phase2.py --vivado-bin D:/AMDDesignTools/2025.2/Vivado/bin
python -B 90_scripts/npu/run_phase3.py --vivado-bin D:/AMDDesignTools/2025.2/Vivado/bin
~~~

Vivado/XSim 2025.2, Python 3.14.5 (tags/v3.14.5:5607950, May 10 2026, 10:43:50) [MSC v.1944 64 bit (AMD64)].
실행 ID는 UTC이고 작성일은 Asia/Seoul이다.
최초 debug-only 실행도 PASS였으며, 최종 판정은 아래 전체 실행의 debug+3 profiles와 회귀를 사용한다.

| 검증 | 실제 결과 | 재현 로그 |
|---|---|---|
| Phase 4 debug | PASS: 1 cases / 39 steps / 12 events / RTL 4275 checks / Python 1145 words | [simulate](../../07_runs/npu_phase4_20261123_190342_359465Z/logs/debug/simulate.log) |
| Phase 4 65536 | PASS: 315 cases / 32691 steps / 8590 events / RTL 3362317 checks / Python 950457 words | [simulate](../../07_runs/npu_phase4_20261123_190342_359465Z/logs/65536/simulate.log) |
| Phase 4 4096 | PASS: 11 cases / 355 steps / 61 events / RTL 36657 checks / Python 10415 words | [simulate](../../07_runs/npu_phase4_20261123_190342_359465Z/logs/4096/simulate.log) |
| Phase 4 16777216 | PASS: 11 cases / 355 steps / 61 events / RTL 36657 checks / Python 10415 words | [simulate](../../07_runs/npu_phase4_20261123_190342_359465Z/logs/16777216/simulate.log) |
| Golden unit | PASS: 8206 checks | [metrics](../../07_runs/npu_phase4_20261123_190342_359465Z/metrics.json) |
| Phase 1 Scalar | PASS: 64KiB/256B 각각 61 cases / 432 steps / 25100 checks | [metrics](../../07_runs/npu_phase1_20261123_190341_096469Z/metrics.json) |
| Phase 2 CSR/Timer | PASS: 두 IMEM 각각 98 cases / 763 steps / 75116 checks | [metrics](../../07_runs/npu_phase2_20261123_190339_943980Z/metrics.json) |
| Phase 2 units/active | PASS: CSR 4096주소 / Timer 156edges / 8752 checks; active 9 instructions / 27 cycles / 114 checks | [metrics](../../07_runs/npu_phase2_20261123_190339_943980Z/metrics.json) |
| Phase 3 block | PASS: 256KiB 87 cases / 6711895 checks; 기본 16MiB 7 cases / 9097 checks; owner 53 checks | [metrics](../../07_runs/npu_phase3_20261123_190338_075169Z/metrics.json) |
| 기존 Python unit | PASS: runner 15 + golden 12 = 27 tests | [runner](../../07_runs/npu_phase1_20261123_190341_096469Z/runner_unit.log), [golden](../../07_runs/npu_phase1_20261123_190341_096469Z/golden_unit.log) |
| Legacy control_unit | PASS: 442054 checks / errors=0 | [metrics](../../07_runs/control_unit_xsim_20261123_190359_931350Z/metrics.json) |
| Legacy memory_wrapper | PASS: 1708039 checks / errors=0 | [metrics](../../07_runs/memory_wrapper_xsim_20261123_190422_149018Z/metrics.json) |
| Legacy mac_array | PASS: 1325105 checks / errors=0 | [metrics](../../07_runs/mac_array_xsim_20261123_190631_141399Z/metrics.json) |
| Legacy accumulator_postprocess | PASS: 265019 checks / errors=0 | [metrics](../../07_runs/accumulator_postprocess_xsim_20261123_190848_372543Z/metrics.json) |
| Legacy mlp_top | PASS: 913476 checks / errors=0 | [metrics](../../07_runs/mlp_top_xsim_20261123_190920_117776Z/metrics.json) |

Phase 4 최종 실행 합계는 debug 포함 338 scenario executions / 33440 instruction records / 8724 memory events,
RTL 3439906 checks 및 Python 실제 dump 972432개 word 비교다.
Golden unit 8206 checks는 별도로 구분한다.
실행 결과의 모든 tool return code=0, 예상 종료/비교 수 충족, timeout 없음, 실행 중 소스 변경 없음이다.
실제 observed trace에서 LW와 SW 각각 signed immediate -2048~2047 전체가 정상 실행되었음을 집계했다.
[coverage.json](../../07_runs/npu_phase4_20261123_190342_359465Z/coverage.json)을 참조한다.

필수/추가 시나리오는 다음과 같다.

- 0, signed 경계, all-ones, packed byte 패턴의 32bit LW/SW bit-exact.
- 모든 I/S형 imm12, 양·음수 offset, unaligned base + offset의 정렬된 EA, base가 Region 밖이어도 최종 EA가 유효한 경우.
- 유효 GPR 조합, rd=rs1, rs1=rs2, r0 읽기/쓰기/주소 Fault 및 back-to-back data dependency.
- DMEM 시작/마지막 word/용량 끝, positive·negative offset의 경계 교차, 정렬/Region/Bounds/wrap.
- r8~r31의 4개 operand 역할 전체 96개 Fault와 unsupported funct3 우선순위 14개.
- 7개 bank 각각 Scalar SW→LOAD→STORE→LW로 공유 DMEM 소유자 전환과 데이터 보존.
- armed Timer의 Scalar 제외, 실제 Block LOAD만 증가.
- 매 요청의 주소/종류/데이터/에지, read response/hold, 누락·추가 요청 차단, 최종 DMEM/guard 확인.
- RTL 실제 PC/GPR/CSR/Timer trace 및 최종 DMEM dump를 Python이 다시 비교.
- 기존 Phase 1~3 및 Python 27개·Legacy 5종 회귀 유지.

## 7. 로그·해시·남은 범위

- [최종 metrics](../../07_runs/npu_phase4_20261123_190342_359465Z/metrics.json)
- [실제 명령/source/data/spec hashes](../../07_runs/npu_phase4_20261123_190342_359465Z/manifest.json)
- [64KiB 전체 테스트](../../07_runs/npu_phase4_20261123_190342_359465Z/logs/65536/simulate.log)
- [4KiB 테스트](../../07_runs/npu_phase4_20261123_190342_359465Z/logs/4096/simulate.log)
- [기본 16MiB 테스트](../../07_runs/npu_phase4_20261123_190342_359465Z/logs/16777216/simulate.log)
- [debug log](../../07_runs/npu_phase4_20261123_190342_359465Z/logs/debug/simulate.log)
- [소규모 타이밍 VCD](../../07_runs/npu_phase4_20261123_190342_359465Z/timing.vcd), [WDB](../../07_runs/npu_phase4_20261123_190342_359465Z/timing.wdb)
- [VCD 에지 대조 결과](../../07_runs/npu_phase4_20261123_190342_359465Z/wave_audit.json)
- [최종 회귀/보호 소스/문서 해시](../../07_runs/npu_phase4_20261123_190342_359465Z/completion.json)

현재 소스는 최종 Phase 1/2/3/4 검증 snapshot hash와 일치한다.
기능 FAIL/timeout은 없었다. 합성 RTL의 메모리 initial/readmemh/writememh를 추가하지 않았다.
합성/배치배선/FPGA/전력/MNIST 10,000장 정확도는 실행하지 않았다.
로그/HEX/파형/빌드는 기존 gitignore에 따라 로컬에 보존한다.
Phase 4 변경은 아직 커밋하지 않았다.

Phase 4 Gate에서 미해결 기능 결함이나 사용자 결정 대기 항목은 없다.
명세와의 차이는 승인된 Scalar wrap 우선순위 명시뿐이며, 기존 Encoding/CSR/Block/SRAM 타이밍은 유지했다.

다음 Phase 5는 CSR snapshot 기반 GEMM, 실제 SRAM owner 연결, D-02의 최소 K 분석·검증,
기존 R→R+6 계약 및 실제 GEMM Timer 검증에 의존한다. 이번 단계에서는 구현하지 않았다.
ARGMAX 및 실제 FPGA 메모리/IP 전환도 후속 범위다.

**Phase 4에서 작업을 중단한다. 사용자 승인 없이 Phase 5 GEMM으로 진행하지 않는다.**
