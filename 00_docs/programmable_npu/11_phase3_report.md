# Phase 3 — Block LOAD/STORE·외부 DMEM·내부 SRAM 구현 및 검증

작성일: 2026-11-24 (Asia/Seoul). 브랜치: `phase3/memory-transfer-20261124`.
기준 커밋: `69410b4` — `feat(npu): implement and verify Phase 2 CSR and performance timer`.

**Phase 3 Gate: PASS. Phase 4는 시작하지 않았다.**

## 1. 시작 전 확인·승인·커밋

AGENTS.md 및 programmable_npu의 01/02/03/04/07/08/09 문서를 읽고 실제 Top/Controller/CSR/Timer,
memory_wrapper/memory_port_mux/single_port_bram/buffer_router/decoder/read mux,
기존 read_issue_control/pipeline_control/address_generator를 확인했다.

Phase 2의 실제 소스·문서 hash와 PASS 기록, Git 변경 목록을 대조했다.
보고서에 해당하는 17개 파일만 변경되어 있었고 관련 없는 Git 변경은 없었다.
해당 변경만 69410b4에 별도 커밋한 후 새 Phase 3 브랜치를 만들었다.
로그·빌드·대량 HEX를 커밋에 넣지 않았다.

확인 중 두 항목을 사용자에게 질의하고 확정받았다.
[10_phase3_decisions.md](10_phase3_decisions.md)에 기록했다.

- 이번 Phase 3은 원래 Phase 4의 블록 LOAD/STORE로 재정의한다. Scalar LW/SW는 후속 Phase 4 승인 범위다.
- 외부 DMEM 논리 영역은 상위 4bit=0x1, [0x10000000,0x20000000)이다. 영역 내 실제 용량 초과는 MEMORY_BOUNDS(0x06), 영역 밖 외부 주소는 INVALID_REGION(0x04).

부분 전송 오류는 ISA 9절에 이미 “이미 쓰인 메모리 rollback을 보장하지 않음”이 명시되어 있었다.
사전 검사를 우선하고, 런타임 Fault의 완료된 prefix는 되돌리지 않는 기존 계약을 적용했다.
ISA Opcode·CSR ID·GPR 수·32bit instruction·고정 메모리 지연은 변경하지 않았다.

## 2. 구현 범위와 파일

| 파일 | 내용 |
|---|---|
| 04_rtl/memory/npu_memory_pkg.sv (신규) | 7개 SRAM bank/depth/base, owner 상수, SRAM/DMEM 전체 범위·정렬·wrap 검사 |
| 04_rtl/memory/sram_address_decoder.sv (신규) | 32bit SRAM byte address → bank/word offset; 축소 전 실제 깊이 검사 |
| 04_rtl/memory/sram_port_mux.sv (신규) | NONE/XFER/GEMM/ARGMAX 소유자별 조합 MUX |
| 04_rtl/memory/npu_memory_wrapper.sv (신규) | 동일 single_port_bram 7개 재사용, 전송·GEMM·ARGMAX 포트 분리, selector만 래치 |
| 04_rtl/memory/block_transfer.sv (신규) | 비파이프라인 직렬 LOAD/STORE, 전체 사전 검사, 워드별 안전 검사, done/Fault/LOAD active |
| 04_rtl/controller/npu_top.sv | 실제 DMEM 요청 연결, SRAM Wrapper 추가, 실제 LOAD active 연결. 외부 포트 추가 없음 |
| 04_rtl/isa/instruction_controller.sv | src/dst 래치, rs3 수집, XFER_ARGS/WAIT, PC/Fetch blocking, 전송 완료·Fault 처리 |
| 04_rtl/isa/instruction_decoder.sv, npu_isa_pkg.sv | 기존 Custom-1 LOAD/STORE decode 및 내부 operation 추가. rd 위치는 rs3 읽기 |
| 90_scripts/npu/run_phase1.py | 현재 Top의 메모리 module 의존 파일 목록만 보완 |
| 05_tb/npu/tb_npu_phase2_active.sv | 새 Controller 포트 연결용 dummy 선언만 추가. 기존 program/기대값은 유지 |
| 90_scripts/npu/phase3_vectors.py (신규) | Python 기계어/DMEM 입력/버스 이벤트/최종 메모리 및 PC/GPR/CSR/Timer Golden |
| 90_scripts/npu/run_phase3.py (신규) | 두 DMEM 용량과 owner TB 실행, 실제 비교 완료 판정·source/data/명령 hash |
| 05_tb/npu/tb_npu_phase3.sv (신규) | 외부 IMEM/DMEM 동기 모델, 이벤트·데이터·에지·상태 scoreboard, runtime cursor fault injection |
| 05_tb/npu/tb_npu_memory_owner.sv (신규) | bank 독립 접근·GEMM 병렬 read·ARGMAX A/B·owner 격리·hold/reset/1clk 검증 |
| 01/02/03/04/README, 10_phase3_decisions.md, 11_phase3_report.md | 승인 내용·진행 계획·검증 범위·보고서 |

기존 Legacy Top/control/memory_wrapper/memory_port_mux, MAC/Accumulator/Postprocess,
single_port_bram, register_file/scalar_alu, 기존 생성 헤더 및 공통 run.py/sim_targets.json은 변경하지 않았다.
단일 엔진 순차 실행만 구현했고 전송 pipeline·LOAD/GEMM 동시 실행·외부 Ready/Valid·bus-error 핀은 추가하지 않았다.

## 3. Top·Memory Wrapper 인터페이스

NPU Top의 기존 IMEM/DMEM 포트는 유지한다. DMEM은 32bit full-word, byte address, 4byte alignment다.
실제 외부 memory storage는 TB의 모델에 있고, NPU는 en/we/addr/wdata/rdata 접근 제어만 가진다.
IMEM와 DMEM은 별도 포트이며 전송 중 다음 instruction fetch를 하지 않는다.
Top/TB가 DMEM_BYTES를 공유한다 (기본 16MiB). 검증에는 256KiB 전체 테스트와 기본 16MiB smoke를 사용했다.

Wrapper의 새 내부 포트는 다음과 같다.

- XFER: 32bit 논리 byte address/en/we/wdata, rdata/error.
- GEMM: 각 bank별 physical word address/en/we/wdata/rdata. 여러 서로 다른 SRAM의 병렬 read/write 경로를 제공한다.
- ARGMAX: 논리 byte address/en과 read data/error.
- owner: 명령어별 명시적 선택. 복잡한 arbitration이나 request queue는 없다.

현재 Top은 실제 전송 중 XFER만 선택하고, 나머지 엔진 입력은 비활성으로 둔다.
GEMM physical 포트는 향후 Controller가 사전 검증한 주소를 공급하는 내부 포트다.
ARGMAX의 CSR 범위/길이/A·B 한정 등 실행 구성 검사는 Phase 6에 남는다.
이 포트를 unit에서 검증한 것이 새 GEMM/ARGMAX 엔진을 구현했다는 뜻은 아니다.

| SRAM | 논리 base | 32bit word 깊이 | RAM word 주소 폭 |
|---|---:|---:|---:|
| A | 0x80000000 | 196 | 8 |
| B | 0x80020000 | 128 | 7 |
| W0 | 0x80040000 | 29280 | 15 |
| W1 | 0x80060000 | 29280 | 15 |
| W2 | 0x80080000 | 29280 | 15 |
| W3 | 0x800A0000 | 29280 | 15 |
| Bias | 0x800C0000 | 163 | 8 |

모두 원래 single_port_bram의 Single-Port/posedge write/registered read 1clk/NO_CHANGE 동작이다.
추가 output data register를 넣지 않았다. read bank selector만 RAM과 같은 에지에 래치한다.
기존 메모리 내용은 Reset으로 지우지 않으며 owner TB에서 Reset 이후 실제 readback으로 보존을 확인했다.

## 4. LOAD/STORE Operand 및 타이밍

ISA 그대로 LOAD rs1,rs2,rs3 = 외부 source / 내부 destination / length_bytes다.
STORE는 내부 source / 외부 destination / length_bytes다.
세 번째 GPR는 RD field이며 GPR writeback이 없다. r0=0, r8~r31 참조 Fault도 유지한다.

기존 2-read GPR file을 보존했다. EXECUTE에서 src/dst를 래치하고,
다음 XFER_ARGS에서 두 번째 read port를 rs3로 선택해 length를 수집한다.
전송 중 원본 GPR와 RW 설정 CSR은 갱신하지 않는다. CSR 주소/길이를 전송 operand로 사용하지 않는다.

엔진 시작 전 전체 src/dst/length를 검사한다. 유효한 경우에만 첫 요청 상태로 진입한다.

| 에지 | LOAD | STORE |
|---|---|---|
| R | DMEM read 요청 수락 | 지정 SRAM read 요청 수락 |
| R 직후 | 외부 모델 registered rdata 갱신 | RAM registered rdata 갱신 |
| R+1 | 응답을 data_buffer에 capture | 응답을 data_buffer에 capture |
| R+2 | SRAM write commit | DMEM write commit |
| 다음 R+3 | 다음 word read 또는 완료 확인 | 다음 word read 또는 완료 확인 |

각 word 뒤 주소는 +4, remaining_bytes는 -4다. 한 명령은 한 SRAM bank 안에서 시작·종료한다.
마지막 write 에지 이후 engine done이 올라오고 Controller가 다음 에지에 완료를 확인해 PC를 전진한다.
Top done은 블록 완료가 아니라 END에서만 1cycle이며, Fault는 sticky Error Halt다.

기존 GEMM은 read R → MAC operands R+1 → product R+2 → psum R+3 → accumulate R+4 → result R+5 → write R+6다.
해당 Legacy 파일과 schedule은 그대로다. 새 Wrapper도 조합 MUX와 같은 1clk RAM만 사용한다.
신규 NPU GEMM 연결·CSR snapshot·새 GEMM 전체 schedule 검증은 Phase 5에 남는다.

## 5. Timer와 Fault

LOAD active는 첫 READ_REQ부터 마지막 WRITE_REQ의 샘플링 에지까지 유지된다.
operand 수집·사전 검사·engine done 확인·Fetch는 제외한다.
정상 N-word LOAD는 정확히 3N active edges다. STORE는 active LOAD 입력을 올리지 않는다.
TSTART/TSTOP/32bit wrap/sticky overflow RTL은 변경하지 않았고 기존 Phase 2 회귀도 통과했다.

| 실제 전체 깊이 LOAD | Timer count | 뒤따른 STORE |
|---|---:|---|
| Buffer A 196word | 588 | 증가 없음 |
| Buffer B 128word | 384 | 증가 없음 |
| W0/W1/W2/W3 각 29280word | 각 87840 | 증가 없음 |
| Bias 163word | 489 | 증가 없음 |
| 7개 bank 각 2word 연속 LOAD | 42 | 7개 STORE 동안 증가 없음 |

모든 메모리 시나리오에서 RW CSR 12개를 서로 다른 비영 sentinel로 먼저 설정했다.
GEMM에 부적합한 중간 설정값도 포함하며, 블록 전송은 이를 검증하거나 소비하지 않는다.
각 instruction과 Halt에서 모든 GPR 및 12개 RW CSR을 Golden과 비교했다.

- 정렬: src/dst/length 모두 4byte 정렬; MISALIGNED=0x05.
- 영역: LOAD/STORE 방향·DMEM 논리 영역·SRAM bank window; INVALID_REGION=0x04.
- 범위: 실제 DMEM 용량, SRAM 깊이/빈 window/은행 넘김, 33bit end 산술의 wrap; MEMORY_BOUNDS=0x06.
- 길이 0: 앞선 검사를 통과한 경우 INVALID_CONFIG=0x07.
- illegal encoding/invalid GPR는 기존 우선순위에 따라 전송 시작 전에 Fault한다.
- 정상 입력의 잘못된 주소/길이는 메모리 요청 0회, Timer active 0회이며 부분 write가 없다.
- GPR/CSR 설정값은 Fault 때도 보존한다. STATUS/ERROR_CODE 및 실행된 active 에지에 따른 PERF 갱신은 정상 관찰 상태 변화다.

런타임 Fault는 정상 전송으로 A 4word를 준비한 뒤, 다음 LOAD의 첫 write 이후 TB에서
dst_cursor를 A의 실제 깊이 바깥으로 강제하여 검증했다.
다음 요청은 차단되고 MEMORY_BOUNDS Error Halt, done=0, 추가 fetch/read/write 없음, GPR/RW CSR 보존을 확인했다.
완료된 새 prefix write는 1word이고 rollback 회로는 없다.
해당 LOAD의 Timer는 첫 word의 3edges + abort 처리 1edge = 4다.
이는 기존 ISA의 engine active 정리 에지 포함 및 런타임 rollback 미보장 계약을 적용한 것이다.
외부 메모리는 오류 응답선이 없으므로 이 테스트를 외부 bus/ECC 오류 감지 기능의 검증으로 해석하면 안 된다.

## 6. 실제 실행 명령·결과

저장소 루트에서 실행:

~~~powershell
python -B 90_scripts/npu/run_phase1.py --legacy --vivado-bin D:/AMDDesignTools/2025.2/Vivado/bin
python -B 90_scripts/npu/run_phase2.py --vivado-bin D:/AMDDesignTools/2025.2/Vivado/bin
python -B 90_scripts/npu/run_phase3.py --vivado-bin D:/AMDDesignTools/2025.2/Vivado/bin
~~~

도구: Vivado/XSim 2025.2. Python: 3.14.5 (tags/v3.14.5:5607950, May 10 2026, 10:43:50) [MSC v.1944 64 bit (AMD64)]. 실행 ID는 UTC, 보고 날짜는 Asia/Seoul이다.

| 검증 | 실제 결과 | 재현 로그 |
|---|---|---|
| Phase 3 256KiB | PASS: 87 cases / 2124 steps / 470814 events / 6711895 checks | [전체](../../07_runs/npu_phase3_20261123_183607_542116Z/logs/262144/simulate.log) |
| Phase 3 기본 16MiB | PASS: 7 cases / 156 steps / 8 events / 9097 checks | [smoke](../../07_runs/npu_phase3_20261123_183607_542116Z/logs/16777216/simulate.log) |
| SRAM owner/timing | PASS: 7 banks / 53 checks | [owner](../../07_runs/npu_phase3_20261123_183607_542116Z/logs/owner/simulate.log) |
| Phase 1 Scalar | PASS: 64KiB/256B 각각 61 cases / 432 steps / 25100 checks | [metrics](../../07_runs/npu_phase1_20261123_182553_326192Z/metrics.json) |
| Phase 2 CSR/Timer | PASS: 두 IMEM 각각 98 cases / 763 steps / 75116 checks | [metrics](../../07_runs/npu_phase2_20261123_182613_014477Z/metrics.json) |
| CSR/Timer unit | PASS: 4096 CSR 주소 / 156 Timer edges / 8752 checks | [metrics](../../07_runs/npu_phase2_20261123_182613_014477Z/metrics.json) |
| Synthetic active | PASS: 9 instructions / 27 cycles / 114 checks | [metrics](../../07_runs/npu_phase2_20261123_182613_014477Z/metrics.json) |
| 기존 Python unit | PASS: runner 15 + golden 12 = 27 tests | [runner](../../07_runs/npu_phase1_20261123_182553_326192Z/runner_unit.log), [golden](../../07_runs/npu_phase1_20261123_182553_326192Z/golden_unit.log) |
| Legacy control_unit | PASS: 442054 checks, errors=0 | [metrics](../../07_runs/control_unit_xsim_20261123_182608_728302Z/metrics.json) |
| Legacy memory_wrapper | PASS: 1708039 checks, errors=0 | [metrics](../../07_runs/memory_wrapper_xsim_20261123_182628_628643Z/metrics.json) |
| Legacy mac_array | PASS: 1325105 checks, errors=0 | [metrics](../../07_runs/mac_array_xsim_20261123_182835_229281Z/metrics.json) |
| Legacy accumulator_postprocess | PASS: 265019 checks, errors=0 | [metrics](../../07_runs/accumulator_postprocess_xsim_20261123_183054_841577Z/metrics.json) |
| Legacy mlp_top | PASS: 913476 checks, errors=0 | [metrics](../../07_runs/mlp_top_xsim_20261123_183129_059354Z/metrics.json) |

최종 Phase 3: **94 scenarios, 2280 instruction records, 470822 memory events**, owner 53 checks를 포함해 **6721045회 비교**.
모든 종료/비교 수/실제 tool return code와 timeout 부재를 확인한 결과다.
Scalar·CSR regression과 Python unit·Legacy 회귀를 별도 scope로 구분했다.

필수 항목별 검증:

- 7개 SRAM 각각 LOAD→STORE, 각 bank 전체 물리 깊이, 1/2/7word와 마지막 word/offset.
- bank별 서로 다른 내용 적재 후 연속 STORE로 독립성·잔류 데이터 재사용 확인.
- 외부/내부 시작·끝·바로 바깥, window hole·은행 경계·주소 wrap·영역/방향 오류·잘못된 길이.
- rs3 재해석, r0 length 및 r8/r31, operand alias와 reserved funct fault.
- 각 DMEM/SRAM 요청의 주소·종류·데이터·에지를 Python bus Golden과 비교. 누락/추가 요청도 실패로 처리.
- 동기 read 응답과 disabled/write read-data hold, 추가 output data register 없음.
- 최종 외부 메모리 및 guard words 비교. SRAM을 계층 경로로 초기화하거나 읽지 않고 실제 LOAD/STORE를 사용.
- 모든 RW CSR의 비영 sentinel, GPR/CSR 보존, 정상/오류 Halt 후 start 무시 및 추가 접근 차단.
- 실제 LOAD active와 마지막 SRAM write를 에지 단위로 확인. STORE 비계수·unarmed LOAD·여러 LOAD 합산.
- 전체 명령의 PC·GPR·CSR·Timer scoreboard, 전송 중 busy/start 무시 및 Fetch blocking.
- owner 단위 검증: 7개 parallel GEMM physical reads, ARGMAX A/B reads, 비소유자 격리, SRAM read hold 및 Reset 내용 보존.
- 내부 cursor fault injection으로 중간 오류 경로·prefix·Error Halt 검증.

첫 통합 실행도 PASS였으나 CSR 0 초기값만으로 무부작용을 판단하지 않도록
fixture에 12개 비영 sentinel을 추가한 뒤 최종 suite를 재실행했다. 그 사이 RTL은 바뀌지 않았다.
첫 실행은 npu_phase3_20261123_183323_456551Z에 보존하고 최종 판정은 아래 실행을 사용한다.
기능 FAIL/timeout은 없었다. 대량 waveform·합성·배치배선·power·MNIST 정확도는 실행하지 않았다.

## 7. 로그·무결성·변경 영향

- [최종 Phase 3 metrics](../../07_runs/npu_phase3_20261123_183607_542116Z/metrics.json)
- [실제 명령·source/data/spec hashes](../../07_runs/npu_phase3_20261123_183607_542116Z/manifest.json)
- [전체 256KiB test log](../../07_runs/npu_phase3_20261123_183607_542116Z/logs/262144/simulate.log)
- [기본 16MiB smoke log](../../07_runs/npu_phase3_20261123_183607_542116Z/logs/16777216/simulate.log)
- [SRAM owner/timing log](../../07_runs/npu_phase3_20261123_183607_542116Z/logs/owner/simulate.log)
- [기존 Phase 2 회귀](../../07_runs/npu_phase2_20261123_182613_014477Z/metrics.json)
- [기존 Scalar/Python/Legacy 회귀](../../07_runs/npu_phase1_20261123_182553_326192Z/metrics.json)
- [최종 종합·소스 보호 확인](../../07_runs/npu_phase3_20261123_183607_542116Z/completion.json)

기준 소스·TB·헤더·설정 89개를 hash로 비교했다.
승인된 기존 파일 변경은 NPU Top/Controller/Decoder/ISA package와 runner 의존 목록,
Phase 2 active TB의 새 포트 선언 등 6개뿐이고 나머지 83개는 변경/삭제되지 않았다.
Legacy MAC·Accumulator·Postprocess·RAM·Wrapper·MLP Top 및 기존 헤더는 보존했다.
현재 기능 소스는 세 회귀 실행의 snapshot hash와 일치한다.
합성 RTL에 메모리 초기화용 initial/readmemh/writememh를 추가하지 않았다.

07_runs/99_build는 기존 .gitignore에 따라 로컬 보존이다.
현재 Phase 3 변경은 자동 커밋하지 않았으며, 사용자가 요청한 Phase 2 보존 커밋만 완료했다.

## 8. 남은 범위·다음 승인 경계

Phase 3 Gate에서 재현된 기능 결함과 미해결 사용자 설계 결정은 없다.

- 승인된 Phase 4: Scalar LW/SW의 I/S immediate·외부 DMEM 접근·GPR writeback·정렬/영역/Bounds 검사 및 block/scalar DMEM port 선택. 이번 단계에서는 구현하지 않았다.
- Phase 5: CSR snapshot 기반 GEMM과 실제 owner 연결, K 하한/D-02, 새 GEMM의 R→R+6·Timer 검증.
- Phase 6: CSR ARGMAX 구성 검증·실제 엔진 연결. 현재 Wrapper unit PASS가 전체 ARGMAX ISA PASS를 뜻하지 않는다.
- 실제 FPGA 외부 memory/IP·BMEM 전환·합성/timing/전력·10,000장 NPU 정확도는 후속 범위다.

**Phase 3만 완료했으며, 사용자 승인 전 Phase 4로 진행하지 않는다.**
