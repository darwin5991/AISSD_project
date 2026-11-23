# Phase 5 — GEMM Engine Integration 구현 및 검증

작성일: 2026-11-24 (Asia/Seoul). 브랜치: `phase5/gemm-integration-20261124`.
기준 커밋: `6efeec4` — Phase 4 Scalar LW/SW 보존 커밋.

**Phase 5 Gate: PASS. 최소 K=8은 후속 사용자 승인으로 정식 지원 하한을 확정했다. Phase 6은 시작하지 않았다.**

## 1. 승인과 적용 기준

AGENTS.md, ISA/Architecture/Implementation/Verification Plan, D-01~D-04, 기존 MAC/MLP 타이밍과 실제 RTL,
Phase 4 보고서를 확인했다. clean 상태에서 Phase 5 브랜치와 기준 소스 hash를 만들었다.

사용자가 확정한 사항은 [14_phase5_decisions.md](14_phase5_decisions.md)에 먼저 기록했다.

- INT32 누산은 modulo 2^32 후 signed 해석. 기존 Bias 정렬의 32bit 절단과 INT8 Saturation 유지.
- 주소/설정 오류는 Alignment → Region → Memory Bounds → Configuration. K=4에도 선행 오류 우선.
- 잘못된 SRAM 역할은 INVALID_REGION(0x04), 같은 SRC0/DST Buffer는 INVALID_CONFIG(0x07).
- 10개 CSR 원본을 원자적으로 Snapshot하고 원본 32bit를 검사한 뒤 실행.
- K=8/12/16/32·출력 그룹·연속 실행을 검증하고, 통과한 8을 후속 사용자 승인으로 정식 지원 하한으로 확정.
- MAC/Accumulator/SRAM/Legacy 보존, 자동 ARGMAX 없음, Timer는 실행 PREP부터 최종 Write까지.
- 합성/FPGA는 이번 Gate 필수 조건이 아니며 Phase 6은 별도 승인 범위.

## 2. 변경·신규 파일

| 파일 | 변경 내용 |
|---|---|
| 04_rtl/controller/gemm_controller.sv (신규) | Layer 없는 IDLE/PREP/RUN/DRAIN/COMPLETE/FAILED, 원본 설정 검증, bank별 주소/접근, 기존 지연·Bias 일정 |
| 04_rtl/controller/gemm_engine.sv (신규) | 기존 unpack/MAC/Accumulator 인스턴스와 7개 물리 SRAM 포트 연결 |
| 04_rtl/controller/npu_top.sv | Engine 추가, OWNER_GEMM 선택, 실제 GEMM active/완료/오류 연결 |
| 04_rtl/isa/csr_file.sv | 기존 설정 10개의 병렬 read-only 내부 출력 추가. RW 저장 동작 유지 |
| 04_rtl/isa/instruction_controller.sv | 원자적 Snapshot, GEMM_CHECK/START/WAIT, next-PC/설정 오류 우선순위 병합, 완료/Fault 처리 |
| 04_rtl/isa/instruction_decoder.sv, npu_isa_pkg.sv | 기존 0x0000202B의 정확한 decode와 내부 OP_GEMM/상수 추가 |
| 03_model/golden/accumulator_postprocess_golden.py | Bias 정렬/누산의 signed INT32 wrap 적용. 기존 정상 Legacy 수치 유지 |
| 90_scripts/npu/run_phase1.py | 현재 Top에 필요한 기존 산술/신규 Engine compile 의존 목록 추가 |
| 05_tb/npu/tb_npu_phase2_units.sv, tb_npu_phase2_active.sv | 추가된 내부 포트의 wildcard 연결 선언만 보완. 기존 program/기대값 유지 |
| 05_tb/npu/tb_npu_phase5.sv (신규) | 실제 SRAM/DMEM 요청·등록 응답·제어·INT32 상태·PC/GPR/CSR/Timer scoreboard, TB 전용 Snapshot/runtime hook |
| 90_scripts/npu/phase5_vectors.py (신규) | 독립 기계어/수치/메모리/제어 Golden, 동적 설정·경계·Fault·Legacy FC fixtures |
| 90_scripts/npu/run_phase5.py (신규) | 실행/timeout/실제 비교 완료 판정, 결과 dump 재비교, hashes, debug waveform 및 named-case 실행 |
| 01/02/03/04/07/README, 14_phase5_decisions.md, 15_phase5_report.md | 확정 사항·현행 구조·검증 범위·진행 상태·보고서 |

총 22개 파일이다. 기존 소스/모델/TB/스크립트/설정 105개 중 변경은 위 9개 기존 소스 파일이며 나머지 96개는 hash가 같다.
새 RTL 2개와 별도 TB/fixture/runner를 추가했다. Legacy RTL 변경·삭제는 없다.

mac_array/*, accumulator_postprocess/*의 RTL, common 산술/레지스터, Legacy control/LUT/MLP Top,
기존 Block Transfer, memory package/Wrapper/MUX/decoder 및 single_port_bram 7개는 수정하지 않았다.
기존 테스트 프로그램과 생성 헤더/대량 데이터도 보존했다.

## 3. 구조·인터페이스·CSR

외부 NPU Top 포트와 IMEM/DMEM 프로토콜은 변경하지 않았다.
SRAM Wrapper의 기존 GEMM bank별 en/we/15bit word-address/32bit data 포트를 사용한다.
입력 A/B 한 개, Weight 4개, Bias는 Read하며 반대 Buffer에만 Write한다.
Weight/Bias는 쓰지 않는다. 여러 서로 다른 Single-Port SRAM의 병렬 접근을 유지한다.

새 Engine은 기존 unpack_int8x4, mac_array, accumulator_postprocess를 직접 연결한다.
Layer LUT/Layer counter/고정 3-Layer 전이/자동 ARGMAX는 새 경로에 없다.
GEMM 완료 후 Engine은 IDLE로 복귀한다. NPU done은 END에서만 1cycle이다.
일반 완료 사이에 전체 Datapath Reset을 요구하지 않으며 첫 Bias Load로 누산기를 초기화한다.

설정은 기존 0x7C0~0x7C9의 SRC0/SRC1/DST/BIAS/M/N/K/BIAS_SHIFT/OUT_SHIFT/ACT_MODE다.
CSR bank는 설정 10개를 병렬 출력하고 Controller가 EXEC 수락 에지에 모두 래치한다.
GEMM_CHECK에서 검사하고 유효한 경우에만 GEMM_START를 1회 발생시킨다.
Snapshot과 설정 검사 중 active/start/SRAM 접근은 없다.
ARG_SRC/ARG_LEN은 GEMM에서 검사하거나 소비하지 않는다.

실행 인코딩은 기존 `EXEC GEMM = 0x0000202B` 그대로다.
rs1/rs2/rd 및 예약 필드는 0이며 GPR Operand/Writeback이 없다.
잘못된 미사용 필드·아직 미구현인 EXEC ARGMAX는 ILLEGAL_ENCODING이다.
새 Opcode/CSR/GPR/외부 메모리 handshake는 추가하지 않았다.

## 4. 원본 검증·주소·Fault

Shift 등의 하위 비트가 아닌 Snapshot의 전체 32bit 값으로 먼저 유효성을 검사한다.
축소된 엔진 필드는 검증 성공 이후에만 실행에 소비한다.

- M=1, N=1~512, K 양수·4의 배수·정식 지원 하한 8.
- BIAS_SHIFT는 signed -32~31, OUT_SHIFT=0~31, ACT_MODE=0/1.
- SRC0/DST는 A/B, SRC1은 W0 창, BIAS는 Bias 창. SRC0/DST는 반대 Buffer.
- W=K/4, G=ceil(N/4). 입력 K bytes, 각 Weight Bank K×G bytes, 출력/Bias 각 4G bytes.
- 그룹·곱·끝 주소를 64bit로 계산하고 실제 깊이/끝 주소를 검증한 뒤 물리 주소 폭으로 전달.
- 주소 4개 정렬 위반은 0x05, 역할/Region은 0x04, 실제 깊이/범위 wrap은 0x06, 형상/Shift/Mode/동일 Buffer는 0x07.
- K%4는 요소 수의 Configuration 검사이며 Byte Address 정렬 오류로 오분류하지 않는다.
- 실행 중 word/group/물리 주소도 검사하고 잘못된 접근은 그 요청부터 차단한다.

설정 오류와 next-PC 오류가 겹치는 GEMM도 같은 우선순위로 병합한다.
마지막 IMEM Word에서 Alignment+K=4+next-PC Bounds는 0x05,
역할 오류+K=4+next-PC Bounds는 0x04, K=4+next-PC Bounds는 0x06이다.
Opcode/Encoding/GPR/CSR 선행 규칙은 유지한다. 오류 시 PC/GPR/RW CSR은 명령 전 상태로 보존한다.
STATUS/ERROR_CODE 및 실제 실행 에지에 따른 PERF 갱신은 정상 관찰 상태 변화다.

주 테스트는 정상 END 117개와 Fault 56개다: MISALIGNED 6, INVALID_REGION 8,
MEMORY_BOUNDS 17, INVALID_CONFIG 21, ILLEGAL_ENCODING 4.
런타임 사례를 제외한 Fault 프로그램의 메모리 요청은 0회다.

Runtime Bounds는 첫 Output Write 이후 TB가 input_word를 255로 바꾸어 검증했다.
완료된 출력 prefix는 1word, 이후 접근/Write는 차단, 0x06 Error Halt와 GPR/RW CSR 보존을 확인했다.
Rollback은 기존 ISA대로 보장하지 않는다. 이 사례의 Timer는 abort 처리 에지를 포함해 10이다.
외부 bus/ECC 오류 감지 핀을 새로 추가한 검증은 아니다.

Snapshot 검증은 TB에서 live CSR K를 8→4→8로 변경했다.
실제 `live_K=4 snapshot_K=8`을 assertion/log로 확인했고 Engine은 Snapshot K=8로 완료했다.
이 hook은 TB 전용 상태 주입이며 일반 프로그램의 동시 CSR 쓰기 인터페이스가 아니다.
내부 SRAM 내용은 TB가 직접 초기화하지 않고 LOAD로 적재하고 STORE로 확인했다.

## 5. INT32 수치·R→R+6·Bias

MAC 및 누산기 RTL은 변경하지 않았다.
Python은 Bias 정렬과 각 누산 후 low 32bit를 signed INT32로 해석한다.
그 다음 기존 ReLU → arithmetic right shift → [-128,127] Saturation → packed INT8 순서를 따른다.
산술 Overflow는 Fault가 아니다.

양방향 wrap 사례의 실제 누산값은 다음과 같다.

`0x80000000 → 0x7FFF03FC → 0x80000000`

첫 단계는 음수 방향 범위 초과, 다음 단계는 양수 방향 범위 초과다.
최종 result register도 0x80000000이며 INT8 Saturation 결과를 STORE로 비교했다.
전체 시험에서 Bias·누산·결과 레지스터의 모든 예정 갱신을 4개 lane 모두 비교했다.

| Input/Weight Read 기준 | 실제 검증한 동작 |
|---|---|
| R | Input + W0~W3 SRAM read |
| R+1 | MAC operand capture와 input_valid |
| R+2 | 기존 MAC product register |
| R+3 | 기존 partial-sum register |
| R+4 | 유효 부분합 누산 |
| R+5 | 마지막 입력의 결과 Capture, 필요 시 다음 Bias Load |
| R+6 | Output SRAM Write |

제어 scoreboard는 R+1/R+4/R+5/R+6, 실제 SRAM 요청·등록 응답/hold,
수치 scoreboard는 누산·결과 register 갱신을 검사했다. MAC 내부 3단은 원형과 기존 MAC 회귀로 보존을 확인했다.
첫 Bias는 첫 read+1, 후속 Bias는 이전 그룹 마지막 read+5다.
result_load와 bias_load 동시는 허용하고 bias_load/psum_valid 중첩은 금지했다.
그룹 사이 read 공백은 1edge이고 추가 SRAM output register/Bias staging을 넣지 않았다.

Debug VCD에서 첫 Read=3855ns, 최종 Output Write=3985ns, active=15edges다.
3915ns에는 다음 Bias Read와 이전 Bias Load가 같은 에지에 발생했다.
에지 전 Bias word 0x2E248F37을 소비하고 에지 후 RAM 출력은 0x0C388823으로 바뀌는 것을 확인했다.
따라서 K=8의 동일 에지 소비를 실제 동기 RAM/누산기 연결에서 검증했다.

## 6. 최소 K 확정·Timer·Legacy 결과

**최소 K=8은 2026-11-24 사용자 후속 승인으로 정식 지원 하한을 확정했다.** 검증 당시 제안 상태였던 실행 기록은 이력으로 보존한다.
K=8/12/16/32 각각 N=1/4/5/8/9/10/12/20/512, A→B/B→A의 72개 경계 사례를 검증했다.
각 물리 SRAM의 마지막 주소를 포함하며, Buffer A의 128번 이상 출력 Word도 검증했다.
K=4는 higher-priority 오류가 없으면 INVALID_CONFIG이며 Engine start/접근이 없다.

정상 active는 PREP 1edge + RUN + DRAIN이며 Snapshot/CHECK/START/Fetch는 제외한다.
마지막 Output Write 에지를 포함하고 이후 완료 확인/다음 Fetch는 제외한다.
W=K/4, G=ceil(N/4)일 때 실제 Count는 `G×(W+1)+6`과 일치했다.

| K | G=1 | G=2 | G=3 | G=5 | G=128 |
|---:|---:|---:|---:|---:|---:|
| 8 | 9 | 12 | 15 | 21 | 390 |
| 12 | 10 | 14 | 18 | 26 | 518 |
| 16 | 11 | 16 | 21 | 31 | 646 |
| 32 | 15 | 24 | 33 | 51 | 1158 |

K=8/N=12를 Reset 없이 4회 실행한 Count=60, unarmed GEMM=0,
LOAD+GEMM 합산 및 STORE/Scalar/Fetch 제외를 확인했다.
기존 Timer start/stop/wrap/sticky-overflow 회귀도 PASS다.

| Legacy 샘플 7 비교 | 출력 Word | GEMM active Count |
|---|---:|---:|
| 독립 FC1 784→512 | 128 | 25222 |
| 독립 FC2 512→128 | 32 | 4134 |
| 독립 FC3 128→10 | 3 | 105 |
| 3×EXEC GEMM 연속 실행 | 163 | 29461 |

신규 NPU의 STORE 결과를 보존된 Legacy 샘플 7의 fc1/fc2/fc3_output.hex와 직접 비교했다.
독립+연속 합계 326words다. 입력/Weight/Bias/출력 파일은 원본 manifest hash를 검사했다.
별도 Legacy MLP full-RTL 회귀도 PASS하여 같은 기준 데이터와 기존 Datapath를 재검증했다.
N 비정렬 꼬리 lane은 기존 packer의 Weight/Bias zero padding을 따른다. 자동 ARGMAX는 실행하지 않았다.

## 7. 실행 명령·최종 결과

~~~powershell
python -X utf8 -B 90_scripts/npu/run_phase5.py --debug-only --vivado-bin D:/AMDDesignTools/2025.2/Vivado/bin
python -X utf8 -B 90_scripts/npu/run_phase5.py --case atomic_snapshot_live_csr_change --vivado-bin D:/AMDDesignTools/2025.2/Vivado/bin
python -X utf8 -B 90_scripts/npu/run_phase5.py --vivado-bin D:/AMDDesignTools/2025.2/Vivado/bin
python -B 90_scripts/npu/run_phase1.py --legacy --vivado-bin D:/AMDDesignTools/2025.2/Vivado/bin
python -B 90_scripts/npu/run_phase2.py --vivado-bin D:/AMDDesignTools/2025.2/Vivado/bin
python -B 90_scripts/npu/run_phase3.py --vivado-bin D:/AMDDesignTools/2025.2/Vivado/bin
python -X utf8 -B 90_scripts/npu/run_phase4.py --vivado-bin D:/AMDDesignTools/2025.2/Vivado/bin
~~~

next-PC/GEMM 복합 오류 보완 후에는 Phase 1을 --legacy 없이, Phase 2~5를 다시 실행했다.
Legacy 5종은 이번 작업에서 실제 실행해 PASS했고 최종 변경이 해당 RTL/TB에 영향을 주지 않았음을
각 Legacy 실행 manifest의 모든 source hash와 header hash로 대조했다. Python 27개 unit 대상도 변경되지 않았다.
재실행하지 않은 Legacy 결과와 최신 NPU 결과를 구분하여 아래에 기록했다.

도구: Vivado/XSim 2025.2, Python 3.14.5 (tags/v3.14.5:5607950, May 10 2026, 10:43:50) [MSC v.1944 64 bit (AMD64)]. 실행 ID는 UTC이고 보고 날짜는 Asia/Seoul이다.

| 검증 | 실제 결과 | 재현 로그 |
|---|---|---|
| Phase 5 debug | PASS: 1 cases / 98 steps / 110 events / 10 numeric updates / RTL 18041 checks / Python 3024 words | [simulate](../../07_runs/npu_phase5_20261123_201308_938468Z/logs/debug/simulate.log) |
| Phase 5 1048576 | PASS: 173 cases / 13691 steps / 844738 events / 65619 numeric updates / RTL 37451392 checks / Python 1576573 words | [simulate](../../07_runs/npu_phase5_20261123_201308_938468Z/logs/1048576/simulate.log) |
| Phase 5 16777216 | PASS: 1 cases / 98 steps / 110 events / 10 numeric updates / RTL 18041 checks / Python 3024 words | [simulate](../../07_runs/npu_phase5_20261123_201308_938468Z/logs/16777216/simulate.log) |
| 공유/독립 Golden unit | PASS: 460 checks | [metrics](../../07_runs/npu_phase5_20261123_201308_938468Z/metrics.json) |
| Phase 1 최신 Scalar | PASS: 64KiB/256B 각각 61 cases / 432 steps / 25100 checks | [metrics](../../07_runs/npu_phase1_20261123_195648_283656Z/metrics.json) |
| Phase 2 최신 | PASS: 두 IMEM 각각 98 cases / 763 steps / 75116 checks; unit 8752, active 114 checks | [metrics](../../07_runs/npu_phase2_20261123_195647_350832Z/metrics.json) |
| Phase 3 최신 | PASS: 87+7 cases / 6711895+9097 checks, owner 53 checks | [metrics](../../07_runs/npu_phase3_20261123_195646_131194Z/metrics.json) |
| Phase 4 최신 | PASS: 315+11+11+debug 1 cases, 양쪽 imm12 각 4096개 | [metrics](../../07_runs/npu_phase4_20261123_195644_565000Z/metrics.json) |
| 기존 Python unit | PASS: runner 15 + golden 12 = 27 tests | [runner](../../07_runs/npu_phase1_20261123_194536_550546Z/runner_unit.log), [golden](../../07_runs/npu_phase1_20261123_194536_550546Z/golden_unit.log) |
| Legacy control_unit | PASS: 442054 checks / errors=0; 현재와 같은 compile 소스 | [metrics](../../07_runs/control_unit_xsim_20261123_194559_534173Z/metrics.json) |
| Legacy memory_wrapper | PASS: 1708039 checks / errors=0; 현재와 같은 compile 소스 | [metrics](../../07_runs/memory_wrapper_xsim_20261123_194619_235003Z/metrics.json) |
| Legacy mac_array | PASS: 1325105 checks / errors=0; 현재와 같은 compile 소스 | [metrics](../../07_runs/mac_array_xsim_20261123_194822_887261Z/metrics.json) |
| Legacy accumulator_postprocess | PASS: 265019 checks / errors=0; 현재와 같은 compile 소스 | [metrics](../../07_runs/accumulator_postprocess_xsim_20261123_195032_017221Z/metrics.json) |
| Legacy mlp_top | PASS: 913476 checks / errors=0; 현재와 같은 compile 소스 | [metrics](../../07_runs/mlp_top_xsim_20261123_195103_003921Z/metrics.json) |

Phase 5 최종 실행 합계: debug 포함 175 executions / 13887 instructions / 844958 memory events,
65948 control events / 65639 numeric updates, RTL 37487474 checks와 Python 실제 dump 1582621words 비교.
공유/독립 Golden unit 460 checks는 별도다.
모든 최종 tool return code=0, 예상 종료/비교 수 완료, timeout 없음, 실행 중 소스 변경 없음이다.

## 8. 검증 과정의 실패와 수정

- npu_phase5_20261123_194407_852341Z: XSim이 CSR 배열 원소 force/release를 지원하지 않아 elaboration ERROR. Scalar CSR 입력 hook으로 변경했다.
- npu_phase5_20261123_194537_774446Z: 초기 전체 suite PASS였으나 live CSR 변경 자체를 아직 관찰하지 못했다. 최종 판정으로 사용하지 않는다.
- npu_phase5_20261123_194808_219026Z: 추가 관찰 assertion이 실제 CSR K가 바뀌지 않는 hook 문제를 검출했다. TB register deposit과 복구로 수정했다.
- npu_phase5_20261123_195040_138934Z: 단독 Snapshot 사례에서 live K=4 / Snapshot K=8을 관찰하고 PASS.
- 최종 제어 검토에서 GEMM 설정과 next-PC 오류의 우선순위 병합을 보완하고 4개 복합 Fault 사례를 추가했다.
- 최종 판정은 npu_phase5_20261123_201308_938468Z와 아래 최신 NPU 회귀를 사용한다.

실패 기록은 삭제하지 않았다. MAC/Accumulator 산술·파이프라인을 바꾸어 문제를 우회하지 않았다.
Waveform은 작은 debug에만 저장했고 대량 suite에서는 저장하지 않았다.

## 9. 로그·무결성·후속 범위

- [최종 Phase 5 metrics](../../07_runs/npu_phase5_20261123_201308_938468Z/metrics.json)
- [명령/source/data/spec/Legacy 데이터 hashes](../../07_runs/npu_phase5_20261123_201308_938468Z/manifest.json)
- [1MiB 전체 시뮬레이션](../../07_runs/npu_phase5_20261123_201308_938468Z/logs/1048576/simulate.log)
- [기본 16MiB smoke](../../07_runs/npu_phase5_20261123_201308_938468Z/logs/16777216/simulate.log)
- [K/Timer/Fault/INT32 coverage](../../07_runs/npu_phase5_20261123_201308_938468Z/coverage.json)
- [Debug VCD](../../07_runs/npu_phase5_20261123_201308_938468Z/timing.vcd), [WDB](../../07_runs/npu_phase5_20261123_201308_938468Z/timing.wdb)
- [VCD 에지 대조](../../07_runs/npu_phase5_20261123_201308_938468Z/wave_audit.json)
- [최종 회귀·소스/문서 무결성](../../07_runs/npu_phase5_20261123_201308_938468Z/completion.json)

K=8 승인 정리 후 Phase 5 전체 suite를 npu_phase5_20261123_201308_938468Z에서 재실행해 PASS했다. 최신 Phase 1~4 및 이 Phase 5 실행의 source snapshot은 현재 소스와 일치한다.
Legacy 5종의 실제 compile source/header도 현재와 같다.
합성 RTL에 메모리 initial/readmemh/writememh를 추가하지 않았다.
로그·HEX·파형·빌드는 기존 gitignore에 따라 로컬 보존한다. Phase 5 변경은 이 보고서와 함께 사용자 지정 메시지의 보존 커밋에 포함한다. 후속 Fault 수정은 별도 브랜치·커밋으로 관리한다.

Phase 5에서 미해결된 GEMM 기능 결함은 없다. 다음 항목은 구분해서 남긴다.

- 최소 K=8 정식 지원 하한 승인 완료. K=4와 다른 오류가 겹치면 기존 우선순위 적용.
- 별도 후속 작업 승인: LW/SW·Block의 마지막 IMEM Word에서 데이터 Alignment/Region과 next-PC Bounds가 겹치는 기존 공통 경로를 승인된 Alignment → Region → Bounds → Config 순서로 통합한다. Phase 5 커밋 이후 별도 브랜치·보고서·커밋에서 구현·검증하며, 이 Phase 5 보존 커밋에는 후속 RTL 수정을 포함하지 않는다.
- Phase 6: 독립 ARGMAX 실행/CSR 검증/GPR 결과 연결. 이번 단계에서는 구현하지 않았다.
- 합성/FPGA/BMEM 전환/Timing/Power 및 NPU MNIST 10,000장 정확도는 미실행 후속 범위다.
- K=8/12/16/32와 기존 FC K=128/512/784를 검증했으며 모든 가능한 설정을 exhaustive하게 실행한 것은 아니다.

**Phase 5에서 중단한다. 사용자 승인 없이 Phase 6으로 진행하지 않는다.**
