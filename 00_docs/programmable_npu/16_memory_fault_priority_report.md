# 메모리/next-PC Fault 우선순위 후속 보고서

기준일: 2026-11-24 (KST). **Gate PASS**. Phase 5 보존 뒤 승인된 별도 수정만 수행했다. Phase 6 ARGMAX는 시작하지 않았다.

## 1. Phase 5 확정 및 커밋 경계

- Phase 5 브랜치: `phase5/gemm-integration-20261124`.
- 커밋: `5be9059844bcf536ef160bee3a4c4ce9e4bf9b6f`.
- 메시지: `feat(npu): implement and verify Phase 5 GEMM engine`.
- ISA/Architecture/Implementation/Verification/07·14 결정/15 보고서/색인에 **최소 K=8**을 반영했다. K=4는 INVALID_CONFIG(0x07), 동시 오류는 Alignment → Region → Bounds → Configuration 순서를 유지한다.
- 해당 커밋은 승인된 Phase 5 파일 22개만 포함한다. 로그·HEX·빌드·Waveform은 제외했다. K 확정 후 재검증은 [Phase 5 보존 실행](../../07_runs/npu_phase5_20261123_201308_938468Z/metrics.json) PASS다.
- 후속 브랜치: `fix/memory-fault-priority-20261124`. 위 커밋을 기준으로 생성했으며 이 보고서와 후속 변경을 별도 커밋으로 관리한다. [15번 보고서](15_phase5_report.md)는 Phase 5 당시의 기록으로 보존하며, 그 보고서의 후속 우선순위 과제는 이번 결과로 해결했다.

## 2. 변경 파일 및 제어 흐름

| 파일 | 변경 |
|---|---|
| [instruction_controller.sv](../../04_rtl/isa/instruction_controller.sv) | GEMM/Scalar/Block 공통 오류 병합, Block 시작 전 전체 검사, XFER_REJECT |
| [phase3_vectors.py](../../90_scripts/npu/phase3_vectors.py) | 독립 Python 오류 병합과 Block 데이터/PC 검사 |
| [phase4_vectors.py](../../90_scripts/npu/phase4_vectors.py) | LW/SW 및 Block Golden 우선순위 |
| [phase5_vectors.py](../../90_scripts/npu/phase5_vectors.py) | 혼합 프로그램 Golden의 LW/SW·Block 검사 일치 |
| [fault_priority_vectors.py](../../90_scripts/npu/fault_priority_vectors.py) (신규) | 수동 기대 오류를 포함한 복합 Fault 시나리오 |
| [tb_npu_fault_priority.sv](../../05_tb/npu/tb_npu_fault_priority.sv) (신규) | 실제 포트·상태·Timer·Halt assertion 및 dump |
| [run_fault_priority.py](../../90_scripts/npu/run_fault_priority.py) (신규) | 독립 TB 실행, Python dump 비교, 소스/로그 기록 |
| 01/02/03/04 명세·README·본 보고서 | 승인 규칙, 구현 영향, 재현 명령 및 Gate 결과 |

총 13개 파일이다. 외부 포트·Opcode·Encoding·CSR 번호 변경은 없다. Controller 내부에 Block next-PC 오류 및 최종 사전 오류 래치, 공통 병합 함수와 XFER_REJECT 상태를 추가했다.

기존 Opcode/Encoding/GPR/CSR 검사를 먼저 수행한 뒤 메모리 오류를 Alignment(05) → Region(04) → 데이터/next-PC Bounds(06) → Configuration(07)로 병합한다. Scalar 주소 산술 wrap은 [12번 결정](12_phase4_decisions.md)의 정렬 → wrap Bounds → Region → 용량 Bounds를 유지한다.

LW/SW는 EXECUTE에서 데이터와 next-PC 오류를 함께 판단한다. Block은 EXECUTE에서 src/dst/next-PC를 래치하고 XFER_ARGS에서 RD 필드의 세 번째 GPR 길이까지 검사한다. 오류가 없어야 기존 Block Engine start를 허용한다. 실패하면 XFER_REJECT를 거쳐 Fault Halt한다.

Fetch 수락 에지 기준 Fault age는 LW/SW=2, Block=4다. Block 데이터 오류의 기존 age=4와 정상 시작 일정은 유지한다. Block next-PC 오류는 기존 age=2에서 age=4로 바뀐다. 이 두 클럭 동안 Engine start/active 및 메모리 접근은 없다. GEMM 검사/실행 일정은 그대로다.

공유 SRAM Wrapper·MUX·BRAM·Block Engine·GEMM Engine·MAC·Accumulator·Legacy RTL 및 기존 TB는 수정하지 않았다. 기존 7개 SRAM 깊이, Single-Port 1clk Read, 상승 에지 Write, MAC R→R+6 계약과 Bias 스케줄은 유지했다. 기준 소스/모델/TB/설정 110개 중 위 기존 소스 4개만 달라졌고 나머지 106개는 SHA-256이 동일하다.

## 3. 필수 복합 오류 결과

IMEM 4KiB의 마지막 명령 위치 PC=0x00000FFC에서 검사했다. 아래 모든 칸은 RTL/Python 일치 PASS다.

| 명령 | Alignment + next-PC Bounds | Region + next-PC Bounds | 데이터 Bounds + next-PC Bounds | 정상 데이터 + next-PC Bounds |
|---|---|---|---|---|
| LW | 05 | 04 | 06 | 06 |
| SW | 05 | 04 | 06 | 06 |
| Block LOAD | 05 | 04 | 06 | 06 |
| Block STORE | 05 | 04 | 06 | 06 |

필수 16조합을 Timer armed/unarmed 양쪽에서 수행해 32사례를 검증했다. 기본 16MiB DMEM에서도 16조합을 다시 실행했다. 추가 사례는 length=0+PC Bounds→06, length misalignment+PC Bounds→05, SRAM Bounds, Alignment+Region, invalid GPR→02, illegal encoding→08, invalid/read-only CSR→03, unknown opcode→01이다.

각 사례는 r1~r7 및 모든 RW CSR에 0이 아닌 값을 준비한다. 정상 LOAD 2워드와 STORE 2워드로 SRAM/DMEM을 먼저 변경하고 마지막 명령으로 이동한다. Fault 명령에서는 다음을 확인했다.

- PC=0xFFC, 전체 GPR 및 RW CSR 보존. STATUS=ERROR, ERROR_CODE는 표의 값.
- 모든 외부 DMEM 및 실제 7개 SRAM enable=0, Block start=0, GPR writeback=0. 잘못된 요청의 읽기/쓰기를 모두 차단했다.
- 정상 준비 전송의 메모리 이벤트 8개 뒤 Fault 요청 이벤트는 0개. 실제 trace/final-memory dump를 Python 기대값과 비교했다.
- armed 사례는 준비 LOAD의 6클럭만 누적하여 Count=6, unarmed는 0. STORE/Scalar/Fetch/사전 Fault는 증가시키지 않는다.
- Fault Halt 10클럭 동안 Count/armed/overflow 각각 보존 assertion을 수행했다. 기존 Timer overflow/TSTART/TSTOP 규칙은 Phase 2 회귀에서도 PASS다.

주 검증 74사례의 최종 오류 분포는 05=20, 04=8, 06=24, 02=8, 08=8, 03=4, 01=2다. armed 37사례 Count=6, unarmed 37사례 Count=0이다.

## 4. 실행 명령과 검증 결과

저장소 루트 PowerShell, Python 3.14.5 / Vivado XSim 2025.2에서 실행했다. 아래 `--vivado-bin` 경로는 실제 사용한 설치 경로다.

```powershell
python -X utf8 -B 90_scripts/npu/run_fault_priority.py --vivado-bin D:\\AMDDesignTools\\2025.2\\Vivado\\bin
python -X utf8 -B 90_scripts/npu/run_phase1.py --legacy --vivado-bin D:\\AMDDesignTools\\2025.2\\Vivado\\bin
python -X utf8 -B 90_scripts/npu/run_phase2.py --vivado-bin D:\\AMDDesignTools\\2025.2\\Vivado\\bin
python -X utf8 -B 90_scripts/npu/run_phase3.py --vivado-bin D:\\AMDDesignTools\\2025.2\\Vivado\\bin
python -X utf8 -B 90_scripts/npu/run_phase4.py --vivado-bin D:\\AMDDesignTools\\2025.2\\Vivado\\bin
python -X utf8 -B 90_scripts/npu/run_phase5.py --vivado-bin D:\\AMDDesignTools\\2025.2\\Vivado\\bin
```

| 실행 | 결과 및 실제 비교량 | metrics |
|---|---|---|
| 복합 Fault 최종 | debug 1 + 주 검증 74 + 기본 DMEM 16 = 91회, 492,453 RTL checks, 99,497 Python 관측값 비교, 오류 병합 unit 25 PASS | [203056 실행](../../07_runs/npu_fault_priority_20261123_203056_374654Z/metrics.json) |
| Phase 1 | IMEM 64KiB/256B 각각 61사례·25,100 checks PASS | [202157 실행](../../07_runs/npu_phase1_20261123_202157_595555Z/metrics.json) |
| Phase 2 | 각 98사례·75,116 checks, CSR/Timer unit 8,752 checks, synthetic active 114 checks PASS | [202150 실행](../../07_runs/npu_phase2_20261123_202150_895123Z/metrics.json) |
| Phase 3 | 주 검증 87사례·6,711,905 checks, 기본 DMEM 7사례·9,107 checks, 7-bank owner 53 checks PASS | [202154 실행](../../07_runs/npu_phase3_20261123_202154_064413Z/metrics.json) |
| Phase 4 | 주 검증 315사례·3,362,317 RTL checks·950,457 Python 비교, debug/4KiB/16MiB 모두 PASS, unit 8,206 PASS | [202158 실행](../../07_runs/npu_phase4_20261123_202158_818578Z/metrics.json) |
| Phase 5 | 주 검증 173사례·37,451,392 RTL checks·1,576,573 Python 비교, Legacy FC 326워드, debug/16MiB 및 unit 460 PASS | [202156 실행](../../07_runs/npu_phase5_20261123_202156_278103Z/metrics.json) |

Phase 5 회귀는 K=8/12/16/32, 출력 그룹·연속 실행·Snapshot·INT32 wrap·R→R+6/Bias/Timer를 포함한다. K=4 INVALID_CONFIG와 동시 오류 우선순위도 유지한다.

Phase 1의 `--legacy`에서 Python 단위 테스트를 실제 실행했다.

- `python -B -m unittest discover -s 90_scripts/tests -v`: **15 PASS**, [로그](../../07_runs/npu_phase1_20261123_202157_595555Z/runner_unit.log).
- `python -B -m unittest discover -s 03_model/golden/tests -v`: **12 PASS**, [로그](../../07_runs/npu_phase1_20261123_202157_595555Z/golden_unit.log).

같은 실행에서 기존 Legacy RTL 5종을 `python -B 90_scripts/run.py <target> --vivado-bin D:\\AMDDesignTools\\2025.2\\Vivado\\bin`으로 검사했다. 모두 실제 RTL, errors=0, PASS다.

| Target | Checks | 실행 metrics |
|---|---|---|
| control_unit | 442,054 | [결과](../../07_runs/control_unit_xsim_20261123_202223_116783Z/metrics.json) |
| memory_wrapper | 1,708,039 | [결과](../../07_runs/memory_wrapper_xsim_20261123_202243_138532Z/metrics.json) |
| mac_array | 1,325,105 | [결과](../../07_runs/mac_array_xsim_20261123_202444_907273Z/metrics.json) |
| accumulator_postprocess | 265,019 | [결과](../../07_runs/accumulator_postprocess_xsim_20261123_202654_321359Z/metrics.json) |
| mlp_top | 913,476 | [결과](../../07_runs/mlp_top_xsim_20261123_202724_651682Z/metrics.json) |

## 5. 결함 재현과 근거

수정 전 Phase 5 Controller로 새 TB를 실행하여 LW Alignment+PC Bounds에서 **actual=06, expected=05, PC=0xFFC** 실패를 재현했다. [수정 전 로그](../../07_runs/npu_fault_priority_20261123_201933_617823Z/logs/debug/simulate.log)의 Controller 스냅샷은 5be9059의 원본과 동일하다.

첫 수정 컴파일에서 선언 전 rs2_data 참조 오류가 발생했다([로그](../../07_runs/npu_fault_priority_20261123_202033_078127Z/logs/debug/compile.log)). 선언 뒤로 assign을 이동해 해결했고 이후 최종 소스로 모든 위 검증을 통과했다. 실패 실행도 보존했다.

최종 실행에는 [coverage.json](../../07_runs/npu_fault_priority_20261123_203056_374654Z/coverage.json), [독립 관측 감사 스크립트](../../07_runs/npu_fault_priority_20261123_203056_374654Z/audit_evidence.py), [완료 감사](../../07_runs/npu_fault_priority_20261123_203056_374654Z/completion.json), manifest의 소스 SHA-256, 실제 trace/final dump 및 compile/elaborate/simulate 로그가 있다. 회귀 실행 스냅샷과 현재 소스의 해시도 비교했다. 대량 검증 Waveform은 OFF, 작은 debug만 기록했다. 생성 로그/HEX/빌드/Waveform/감사 산출물은 Git 커밋에서 제외했다.

## 6. 남은 문제와 중단 경계

승인된 복합 Fault 범위의 미해결 결함은 없다. 메모리 프로토콜 변경이나 런타임 rollback 보장을 추가하지 않았다. Phase 5의 합성/FPGA/MNIST 10,000장 검증을 이번 Gate의 PASS로 주장하지 않는다.

최소 K=8은 사용자 확정 사항이다. Phase 6 ARGMAX는 별도 승인이 필요하며 이번 작업에서 구현하거나 시작하지 않았다.
