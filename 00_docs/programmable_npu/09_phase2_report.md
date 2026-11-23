# Phase 2 — CSR·SETI·Timer 구현 및 검증

작성일: 2026-11-24 (Asia/Seoul). 작업 브랜치: `phase2/csr-timer-20261124`.
기준 커밋: `d707e52` — `feat(npu): implement and verify Phase 1 scalar fetch core`.
사용자 요청에 따라 Phase 1의 검증 소스·문서 15개를 먼저 이 커밋에 보존한 후 Phase 2를 시작했다.

**Phase 2 Gate: PASS. Phase 3은 시작하지 않았다.**

## 1. 구현 범위와 명세 차이

구현 명령은 기존 Scalar 7개에 SETI/CSRW/CSRR/TSTART/TSTOP을 추가한 범위다.
Opcode·CSR 번호·Error Code·GPR 수·IMEM timing을 변경하지 않았다.

- D-01: RW 설정 CSR 12개의 32bit 원본을 그대로 저장한다. M/N/K/Shift/Mode/주소의 범위·조합·정렬 검사는 쓰기 시 수행하지 않는다.
- 없는 CSR, RO CSR 쓰기는 INVALID_CSR(0x03), 불법 CSR 명령 형식은 ILLEGAL_ENCODING(0x08), 유효 형식의 잘못된 GPR는 INVALID_GPR(0x02) Fault다.
- CSRW는 rd=0인 CSRRW 형식, CSRR은 rs1=0인 CSRRS 형식만 허용한다. CSRW csr,r0도 쓰기이므로 RO 대상이면 Fault다.
- SETI는 [31:19]의 signed imm13을 32bit로 부호 확장하고 [18:7]의 12bit CSR 주소를 사용한다. 이 비트들을 GPR 번호로 해석하지 않는다.
- PERF_COUNT/PERF_OVERFLOW/STATUS/ERROR_CODE는 RO live view다. CSR 설정 배열에 복사해 중복 저장하지 않는다.
- 향후 EXEC 수락 시 CSR snapshot의 구성 유효성을 검사해야 한다. **EXEC 및 그 검사는 이번 단계에 구현하지 않았다.**

Performance Timer는 32bit count, 1bit armed, 1bit sticky overflow다.
TSTART는 count/overflow를 0으로 만들고 arm, TSTOP은 disarm하고 값은 유지한다.
armed && (load_active || gemm_active)일 때만 에지당 1회 증가하며, 두 active가 동시에 1이어도 1회만 센다.
TSTART/TSTOP 에지는 자체 카운트하지 않는다. wrap은 modulo 2^32이며 overflow는 다음 TSTART/Reset까지 유지된다.

기능 명세를 바꿀 만한 충돌이나 새 결정은 발견되지 않았다.
검증 범위의 제한은 다음과 같다.

- 실제 LOAD/GEMM/STORE/ARGMAX 엔진·명령은 아직 없다. 현재 npu_top은 LOAD/GEMM active를 0에 연결한다.
- 테스트용 activity는 perf_timer 및 instruction_controller의 내부 엔진 입력 경계에 TB가 공급한다. public Top test 포트, CSR counter write, 합성용 test hook은 추가하지 않았다.
- 실제 엔진의 시작/마지막 SRAM write에 대한 active 경계와 실제 STORE/ARGMAX 비계수 검증은 Phase 4~6에 남는다.
- STATUS=1/2와 ERROR_CODE의 live CSR 매핑은 CSR unit에서 입력값으로 검증하고, 실제 END/Fault 상태는 통합 TB에서 확인했다. Halt 이후 새 CSRR 명령을 실행하거나 새 외부 CSR 접근 포트를 만들지 않았다.

## 2. 변경 파일·새 내부 신호

| 파일 | 변경 |
|---|---|
| 04_rtl/isa/csr_file.sv (신규) | RW 12개 원본 저장, 16개 CSR 주소 해석·권한, RO live read, commit 차단 |
| 04_rtl/isa/perf_timer.sv (신규) | 32bit Engine-only Timer, arm/start/stop/wrap/sticky overflow |
| 04_rtl/isa/npu_isa_pkg.sv | 기존 명세의 CSR ID 16개, TSTART/TSTOP word 및 Phase 2 operation 상수 |
| 04_rtl/isa/instruction_decoder.sv | SETI/CSRW/CSRR/TSTART/TSTOP decode, signed imm13 및 CSR 필드 |
| 04_rtl/isa/instruction_controller.sv | CSR/Timer 연결, CSRR GPR writeback, CSR Fault 우선순위 및 원자적 commit gate |
| 04_rtl/controller/npu_top.sv | 현재 없는 엔진의 LOAD/GEMM active를 0으로 연결. 외부 포트 변화 없음 |
| 90_scripts/npu/run_phase1.py | 기존 Scalar 테스트 내용은 유지하고 CSR/Timer module 의존 파일 2개만 추가 |
| 90_scripts/npu/phase2_vectors.py (신규) | Phase 2 fixture encoder·독립 Python ISA/CSR 기준 모델 |
| 90_scripts/npu/run_phase2.py (신규) | 명세/Python/SV CSR ID 일치 검사, XSim 실행·snapshot·hash·판정 |
| 05_tb/npu/tb_npu_phase2.sv (신규) | PC/GPR/12개 RW CSR/Timer 상태 scoreboard, Halt/Reset/Fault 무부작용 |
| 05_tb/npu/tb_npu_phase2_units.sv (신규) | 전체 CSR 주소·권한, raw 값, RO view, Timer edge/overflow 검증 |
| 05_tb/npu/tb_npu_phase2_active.sv (신규) | 인위적으로 생성한 테스트용 activity로 TSTART/TSTOP/동적 PERF_COUNT read 연결 검증 |
| 02_architecture.md, 03_implementation_plan.md, 04_verification_plan.md, README.md | 구현 현황·검증 범위·후속 엔진 경계 명시 |
| 09_phase2_report.md (신규) | 이 보고서 |

기존 scalar_alu.sv/register_file.sv, Phase 1 TB/fixture, Legacy RTL/TB/헤더 및 기존 공통 run.py/sim_targets.json은 수정하지 않았다.
MAC·누산기·SRAM Datapath와 R→R+6 계약을 변경하지 않았다.

새 내부 제어 신호:

- decoder → controller: csr_address[11:0], 추가 operation.
- CSR file: access_en/write_request로 접근 권한을 확인하고, commit_en으로 실제 저장을 허용한다. 오류 판정이 commit gate에 의존하는 조합 루프가 없다.
- controller: csr_access/csr_error/execute_error/instruction_commit, CSRR용 register_write_data 선택.
- Timer: timer_start/timer_stop, load_engine_active/gemm_engine_active, perf_count/perf_overflow/timer_armed.

Fetch R → IR capture R+1 → 실행 R+2 일정은 유지한다.
Encoding/GPR/CSR 오류를 next PC 정렬·Bounds보다 먼저 판정한다.
CSR 쓰기·GPR 쓰기·TSTART/TSTOP은 모두 성공한 instruction_commit에서만 발생한다.
따라서 마지막 word의 잘못된 next PC나 Fault 명령이 CSR·link·Timer 상태를 조용히 변경하지 않는다.
동적 PERF_COUNT CSRR은 GPR writeback 에지 직전의 카운터 값을 읽는 것으로 검증했다.

## 3. 실행 명령과 실제 결과

저장소 루트에서 실행했다.

~~~powershell
python -B 90_scripts/npu/run_phase1.py --legacy --vivado-bin D:/AMDDesignTools/2025.2/Vivado/bin
python -B 90_scripts/npu/run_phase2.py --vivado-bin D:/AMDDesignTools/2025.2/Vivado/bin
~~~

첫 명령은 Phase 2가 연결된 현재 RTL에서 기존 Scalar 2개 프로파일, 기존 Python tests 및 Legacy RTL 5종을 실행한다.
두 번째 명령은 Phase 2 통합 2개 프로파일과 CSR/Timer unit, 테스트용 active 통합 검증을 실행한다.
도구: Vivado/XSim 2025.2. Python: 3.14.5 (tags/v3.14.5:5607950, May 10 2026, 10:43:50) [MSC v.1944 64 bit (AMD64)].
실행 ID는 UTC, 보고 날짜는 Asia/Seoul 기준이다.

| 검증 | 결과 | 실제 비교 / 로그 |
|---|---|---|
| Phase 2 IMEM 65536 B | PASS | 98 scenarios / 763 steps / 75116 checks; [log](../../07_runs/npu_phase2_20261123_180028_393257Z/logs/65536/simulate.log) |
| Phase 2 IMEM 256 B | PASS | 98 scenarios / 763 steps / 75116 checks; [log](../../07_runs/npu_phase2_20261123_180028_393257Z/logs/256/simulate.log) |
| CSR/Timer unit | PASS | 4096 addresses / 156 Timer edges / 8752 checks; [log](../../07_runs/npu_phase2_20261123_180028_393257Z/logs/units/simulate.log) |
| Synthetic active controller | PASS | 9 instructions / 27 cycles / 114 checks; [log](../../07_runs/npu_phase2_20261123_180028_393257Z/logs/active/simulate.log) |
| 기존 Scalar 두 용량 | PASS | 각 61 cases / 432 steps / 25100 checks; [metrics](../../07_runs/npu_phase1_20261123_175245_845340Z/metrics.json) |
| 기존 Python unit | PASS: 27 tests | [runner 15](../../07_runs/npu_phase1_20261123_175245_845340Z/runner_unit.log), [golden 12](../../07_runs/npu_phase1_20261123_175245_845340Z/golden_unit.log) |
| Legacy control_unit | PASS | 29478 vectors / 442054 checks; [log](../../07_runs/control_unit_xsim_20261123_175259_873746Z/logs/simulate.log) |
| Legacy memory_wrapper | PASS | 265018 vectors / 1708039 checks; [log](../../07_runs/memory_wrapper_xsim_20261123_175317_914428Z/logs/simulate.log) |
| Legacy mac_array | PASS | 265021 vectors / 1325105 checks; [log](../../07_runs/mac_array_xsim_20261123_175524_385125Z/logs/simulate.log) |
| Legacy accumulator_postprocess | PASS | 265019 vectors / 265019 checks; [log](../../07_runs/accumulator_postprocess_xsim_20261123_175740_810150Z/logs/simulate.log) |
| Legacy mlp_top | PASS | 265018 vectors / 913476 checks; [log](../../07_runs/mlp_top_xsim_20261123_175813_132978Z/logs/simulate.log) |

Phase 2 통합 합계: **98 scenarios × 2개 용량, 1,526개 명령어 실행 기록, 150,232회 비교, errors=0**.
CSR/Timer unit의 8,752회와 테스트용 active 통합의 114회 비교는 별도다.
기존 Python runner 15 + golden 12 = 27 tests도 PASS했으며, Python PASS를 RTL PASS로 대신 사용하지 않았다.

확인한 directed 항목:

- RW 모든 CSR reset/readback/isolation, SETI -4096/4095/-1/0 부호 확장.
- 0xFFFFFFFF/0x80000000/0x7FFFFFFF/0x12345FED 등 전체 32bit CSRW 보존. 좁은 Shift/Mode 포트에 맞춘 조기 truncation 없음.
- K=3 저장→readback→K=128 덮어쓰기, 잘못된 중간 M/N/Shift/Mode/주소/ARG_LEN도 Fault 없이 보존. EXEC 유효성 검사 PASS를 의미하지 않음.
- SETADDR의 LI r4 + CSRW 확장, signed low12 보정, r4 clobber 및 CSR readback.
- CSR 주소 4,096개 전체 read/write 권한, 예약 CSR과 RO 쓰기, CSRW r0, CSRR rd=r0.
- 잘못된 funct3/예약 필드/GPR, 오류 우선순위, Fault 뒤 CSR/GPR 변경 금지, 마지막 IMEM word의 commit 차단.
- TSTART→Scalar/CSR/Fetch→TSTOP의 count=0, 재시작/반복 정지, Halt/Reset.
- 156개 Timer edge: unarmed/inactive hold, LOAD/GEMM 단독 및 OR, 최종 active 에지 포함, TSTART/TSTOP 자체 제외, random 패턴.
- TB 전용 force/release로 count를 0xFFFFFFFE에 seed하고 FFFFFFFF→00000000 wrap 및 sticky overflow 확인. 합성 RTL에는 해당 초기화 포트·파라미터·initial을 넣지 않음.
- 테스트용 active가 변하는 controller에서 9개 명령·27cycle을 실행하고, CSRR의 실제 동적 PERF_COUNT/정지값/재시작값을 비교.
- seed 2000~2007의 제한된 random CSR/scalar/system 프로그램.

Overflow 실측 로그는 다음과 같다.

~~~text
load=1 gemm=0 count=ffffffff overflow=0 armed=1
load=0 gemm=1 count=00000000 overflow=1 armed=1
load=0 gemm=0 count=00000000 overflow=1 armed=1
stop=1        count=00000000 overflow=1 armed=0
~~~

전체 실행에서 RTL/scoreboard FAIL 또는 timeout은 없었다.
파일 작성 보조 호출의 인용 문제는 실행 전 정리했으며, 이를 기능 검증 PASS/FAIL과 혼동하지 않았다.

## 4. 로그·소스 보존·검증 한계

- [Phase 2 metrics](../../07_runs/npu_phase2_20261123_180028_393257Z/metrics.json)
- [도구 명령·CSR 계약·source/data hashes](../../07_runs/npu_phase2_20261123_180028_393257Z/manifest.json)
- [64KiB 통합 trace](../../07_runs/npu_phase2_20261123_180028_393257Z/logs/65536/simulate.log), [256B trace](../../07_runs/npu_phase2_20261123_180028_393257Z/logs/256/simulate.log)
- [전체 CSR·Timer edge 및 Overflow 로그](../../07_runs/npu_phase2_20261123_180028_393257Z/logs/units/simulate.log)
- [테스트용 active 통합 로그](../../07_runs/npu_phase2_20261123_180028_393257Z/logs/active/simulate.log)
- [Scalar·Legacy 회귀 metrics](../../07_runs/npu_phase1_20261123_175245_845340Z/metrics.json)
- [Phase 2 종합·소스 무결성](../../07_runs/npu_phase2_20261123_180028_393257Z/completion.json)

구현 전 기존 소스·테스트·헤더·설정 **82개**의 hash를 보관했다.
계획한 기존 파일 변경은 위 표의 RTL 4개 및 Scalar runner 의존 목록 1개뿐이며, 나머지 **77개**는 변경/삭제되지 않았다.
현재 파일은 검증에 사용한 source snapshot과 일치한다.
07_runs/99_build는 기존 .gitignore에 따라 로컬 보존하며, 일반 git add로 로그가 함께 저장되지는 않는다.
현재 Phase 2 변경은 자동 커밋하지 않았다. 사용자가 요청한 Phase 1 보존 커밋은 이미 완료했다.

기능/설정 명세와 다른 새 기능은 없다.
실제 엔진 active와 마지막 SRAM write의 관계, EXEC snapshot 검사, DMEM/SRAM 전송, 10,000장 정확도는 미검증이다.
waveform·합성·배치배선·power는 이번 단계에 실행하지 않았다. Timer timing 근거는 각 에지의 실제 로그·기준 비교다.

## 5. 남은 문제와 다음 승인 경계

현재 Phase 2 Gate에서 재현된 기능 결함 또는 추가 설계 결정 요청은 없다.
D-01의 실제 EXEC snapshot/범위 검사는 GEMM/ARGMAX 통합 때 수행해야 하며 아직 PASS로 표시하지 않는다.
D-02의 K 지원 하한은 Phase 5에서 결정한다.
실제 엔진을 연결할 때 반드시 qualified LOAD/GEMM active만 Timer에 전달하고 STORE/ARGMAX/Fetch/Scalar를 제외해야 한다.

**Phase 2만 완료했으며, 사용자 승인 전 Phase 3으로 진행하지 않는다.**
