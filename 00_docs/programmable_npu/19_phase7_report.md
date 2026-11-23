# Phase 7 — MNIST Application Verification 보고서

작성일: 2026-11-24 (Asia/Seoul). **승인된 G0~G4 및 전체 회귀 Gate PASS.**
브랜치: feat/phase7-mnist-20261124. 기준/현재 HEAD: 4d4cd434496f7c4568bfdc4bc8df7c3ca6293cee (Phase 6).
시작 작업 트리는 Clean이었고 최종 작업 트리는 승인된 신규 Python/TB와 문서 변경만 포함한다. 커밋·Push는 하지 않았다.

## 1. 승인 범위와 보존

원본 MNIST 첫 1/5/100/200장만 실제 Programmable NPU RTL에서 추론했다. G4는 0~199번으로 G3의 0~99번을 포함한다. 10,000장, 별도 모델 전환, FPGA/BMEM/합성은 미실행이다. 기존 ISA·CSR·8 GPR·외부 IMEM/DMEM 프로토콜과 04_rtl 전체를 변경하지 않았다. 기존 Phase 1~6·Fault·Legacy TB/실행기·모델/양자화·Golden도 보존했다. 보호 대상 기존 소스 134개의 실행 전후 SHA-256이 동일하다.

AGENTS, ISA/Architecture/Implementation/Verification, Phase 0/5/6 결정과 기존 보고서·실제 RTL을 읽고 구현했다. 17/18번의 과거 HEAD 414fd57·미구현 계획·미커밋 표현은 당시 이력이며 Phase 6 보존 HEAD는 4d4cd43이다.

## 2. 신규/수정 파일과 인터페이스

| 파일 | 역할 |
|---|---|
| 90_scripts/npu/run_scenario.py 신규 | 단일 실행 명령, G0~G4/기존 회귀, Manifest/소스 snapshot/hash, 시간·메모리 기록, 실패 시 중단 |
| assembler.py 신규 | Phase 1~6 인코더 재사용, Label/LI/SETADDR 확장, Immediate·GPR·Branch·PC 검사, Application 프로그램 |
| memory_allocator.py 신규 | 4byte 정렬 byte address, 중복·16MiB Bounds, 영역 Manifest |
| weight_packer.py 신규 | 기존 LayerViewer/model/양자화/pack8 재사용, 모델 1회 로드, INT8 4bank/Bias, Padding·역변환 검사 |
| golden_compare.py 신규 | CPU INT64 정수 GEMM 후 signed INT32 wrap, ReLU/shift/saturation, lowest-index 및 비교·정확도 |
| 05_tb/npu/tb_npu_application.sv 신규 | 외부 메모리, LOAD/Engine/CSR/Prediction/Timer/END/Fault/timeout 관측 |
| 90_scripts/npu/tests/test_application.py 신규 | 전용 unit 9개; 독립 decode/stub 실행으로 8 GPR liveness·루프 검증 |
| README/03/04 수정, 본 19번 보고서 신규 | 승인 범위·명령·Gate·실측·후속 범위 |

기존 RTL 파일 수정 및 신규 Top 포트·제어 신호는 없다. Application TB는 기존 npu_top 외부 포트와 검증용 내부 관측만 사용한다. IMEM/DMEM은 Top 밖, SRAM 7개는 기존 Wrapper 내부다. Read R→R+1 소비, 상승 에지 Write, SRAM 깊이·폭·추가 Output Register 없음, MAC R→R+6/Bias 일정이 모두 그대로다.

## 3. 실행 환경과 명령

Python 3.11.16, PyTorch 2.11.0+cu128, torchvision 0.26.0+cu128, NumPy 2.4.6, Vivado XSim 2025.2.
conda aissd의 실제 import와 CUDA 인식은 성공했다. Golden은 CPU NumPy INT64이며 GPU 추론을 사용하지 않는다.

~~~powershell
& "C:/Users/darwi/.conda/envs/aissd/python.exe" -X utf8 -B 90_scripts/npu/run_scenario.py --vivado-bin D:/AMDDesignTools/2025.2/Vivado/bin
~~~

기본 G0~G4와 전체 회귀를 한 명령에서 실행했다. wall timeout 기본 1800초/도구 stage, TB 제한은 1,000,000+40,000×N cycle이다. 개발용 --counts/--no-regressions 실행은 최종 Gate를 대체하지 않는다.

실행 ID(UTC): npu_phase7_20261123_220156_054531Z. [Manifest](../../07_runs/npu_phase7_20261123_220156_054531Z/manifest.json), [Metrics](../../07_runs/npu_phase7_20261123_220156_054531Z/metrics.json), [Python unit](../../07_runs/npu_phase7_20261123_220156_054531Z/application_unit.log). 문서 날짜는 KST다.

## 4. 데이터·Packing·Golden


| 원본 | Bytes | SHA-256 |
|---|---:|---|
| MLP_MNIST_GPU_FINAL_BEST.pth | 1879001 | aaa85326d75d57f3ebe964e3cb75cff8e07a213e12fc967bf6f8b2988e3133bd |
| t10k-images-idx3-ubyte | 7840016 | 0fa7898d509279e482958e8ce81c8e77db3f2f8254e26661ceb7762c4d494ce7 |
| t10k-labels-idx1-ubyte | 10008 | ff7bcfd416de33731a308c3f266cc351222c34898ecbeaf847f06e48f7ec33f2 |

데이터는 원본 IDX 순서이며 모델 로드는 1회다. 전처리는 float32(pixel)/255에서 mean=0.1307, std=0.3081 정규화를 수행한다. 입력 signed F5, Weight F7/F7/F7, Bias F9/F8/F7, 출력 signed F2/F2/F2다. 오프라인 입력/Weight/Bias는 nearest-even, 실행은 INT32 wrap 후 FC1/2 ReLU, 산술 우측 shift 10/7/7, signed INT8 saturation이다.

각 Word의 첫 요소는 bits[7:0]. Bank=출력 lane, byte=입력 lane이며 layer→output group→input word 순이다. FC3 Weight/Bias의 출력 10/11 lane은 zero padding이고 ARGMAX는 실제 10개만 비교한다. 동점은 가장 작은 index다. 최종 modulo 2^32는 매 부분합의 wrap과 동치이며 INT64 중간 합은 이 모델 크기에서 overflow하지 않는다.

G0는 기존 IntegerMLP에 RTL 설정을 명시하여 200장 각 Layer/Prediction과 대조했다. 기존 기본 설정/overflow 예외 정책을 변경하지 않았다. Phase 5 packed-address kernel은 0/7/199번을 별도로 비교했고 기존 Legacy 모델 W0~3/Bias 117,283words 및 checkpoint hash도 일치했다. unit 9개는 모두 PASS다.

## 5. Assembly와 주소 배치

최초 W0~3/Bias 5회 LOAD 뒤 r1=Input Pointer, r2=LOAD Dst, r3=784, r4=CSR scratch, r5=ARGMAX 결과, r6=Prediction Pointer, r7=Input End를 사용한다. 루프는 Input LOAD→FC1 GEMM→FC2 GEMM→FC3 GEMM→ARGMAX→SW→r1+784/r6+4→BNE→END다. CFG의 원본 10개 Snapshot도 TB가 각 GEMM 시작 때 검사한다.

각 FC는 기존 Phase 5의 A→B/B→A/A→B, N=512/128/10, K=784/512/128, Bias shift=3/1/2, Output shift=10/7/7, ACT=1/1/0이다. SETADDR는 r4만 clobber한다. 기존 Builder의 r1~r3 임시 사용 경로는 루프 생성에 호출하지 않는다. G1 STORE도 r2/r4/r5를 사용하여 loop-live r1/r3/r6/r7을 보존한다.

G2/G3/G4는 111word/444B, LOOP=0xC0, END=0x1B8다. 100/200장 기계어 차이는 LI r6/r7 확장 위치 39~42의 4word이며 명령 구조는 동일하다. 실제 확장 Assembly listing, program.bin, imem.hex와 주소/파일 hash는 각 data/Gx manifest에 있다. G1은 중간 STORE를 추가한 132word다.

기본 IMEM 64KiB/DMEM 16MiB. W0~3는 각 117,120B, Bias는 652B이며 외부 W0 시작은 0x10000000, Bias 끝/Input 시작은 0x1007288C다. 내부 Bank 주소와 외부 배치 주소는 구분한다.

| 프로파일 | Input [start,end) | Prediction [start,end) | 사용 용량 |
|---|---|---|---:|
| 100장 | 0x1007288C~0x10085ACC | 0x10085ACC~0x10085C5C | 547,932B |
| 200장 | 0x1007288C~0x10098D0C | 0x10098D0C~0x1009902C | 626,732B |

모든 영역은 4byte 정렬·비중복·Bounds 검사를 통과했다. Prediction은 0xFFFFFFFF sentinel로 초기화한다. HEX는 연속 Word로 저장하고 전체 미사용 IMEM/DMEM zero fill은 TB에서 수행한다. 상세 주소와 파일 hash는 각 프로파일 Manifest에 있다.

## 6. Gate별 실측

| Gate | 이미지 | Golden 일치 | Label 정답/정확도 | TB cycle | XSim wall s | Layer STORE words |
|---|---:|---:|---|---:|---:|---:|
| G1 | 1 | 1/1 | 1/1 (100.00%) | 382,828 | 4.438 | 163 |
| G2 | 5 | 5/5 | 5/5 (100.00%) | 503,326 | 6.953 | 0 |
| G3 | 100 | 100/100 | 100/100 (100.00%) | 3,378,406 | 65.984 | 0 |
| G4 | 200 | 200/200 | 200/200 (100.00%) | 6,404,806 | 127.500 | 0 |

모든 Gate 정상 END, Fault/timeout 없음, Golden 불일치 0이다. G4의 실제 RTL Prediction 첫 100개는 G3와 동일하다. 두 정확도 수치는 첫 100/200장 부분집합 결과이며 10,000장 정확도로 일반화하지 않는다. Label 정확도 하한은 추가하지 않았다.

G1은 FC1/2/3의 128/32/3word 총 163word 및 Prediction을 TB와 Python 양쪽에서 실제 관측 dump와 비교했다. G3/G4의 모델 LOAD는 각 5회뿐이며 총 LOAD 105/205, GEMM 300/600, ARGMAX 100/200, BNE 100/200, Prediction Write 100/200회다. 동적 명령 수는 6,249/12,449로 이전 1,024-step fixture 제한을 사용하지 않는다.

모든 Application에서 Timer armed/count/overflow=0을 매 cycle 확인했다. TSTART/TSTOP·Waveform은 없고 G2/G3/G4의 Layer STORE는 0회다. 표의 cycle은 TB clock 통계로 PERF Timer 측정이 아니다.

## 7. 호스트 메모리와 실행 방식

| Gate | xsim.exe peak working set MiB | xsimk.exe peak working set MiB | 프로세스 트리 sampled RSS 합 peak MiB |
|---|---:|---:|---:|
| G3 | 214.50 | 46.12 | 865.36 |
| G4 | 214.09 | 46.10 | 865.84 |

psutil로 0.1초 간격 관측했고 각 프로세스에서는 Windows peak working set도 읽었다. 트리 RSS 합은 Python·launcher·simulator를 포함하며 공유 메모리 중복이 있을 수 있다. FPGA 자원/BRAM 수치가 아니다. 전체 상세 memory sample summary와 도구별 elapsed time은 Manifest에 있다.

대량 이벤트·누산 Trace 정답표는 만들지 않는다. LOAD의 외부 Read와 내부 Write src/dst/data/개수·순서, Instruction Fetch/Branch, GEMM/ARGMAX start/done, Prediction만 가볍게 관측한다. Python Golden NPZ와 입력/모델 HEX는 재현·선택 이미지 debug에 사용한다. 이후 불일치 시 해당 이미지 또는 이전 순서를 포함한 prefix 재실행으로 G1형 중간 Layer STORE를 수집할 수 있다.

## 8. 기존 회귀 실제 재실행

- phase1: **PASS** — [metrics](../../07_runs/npu_phase1_20261123_220544_138217Z/metrics.json), [상위 실행 로그](../../07_runs/npu_phase7_20261123_220156_054531Z/phase1.log).
- phase2: **PASS** — [metrics](../../07_runs/npu_phase2_20261123_221126_057403Z/metrics.json), [상위 실행 로그](../../07_runs/npu_phase7_20261123_220156_054531Z/phase2.log).
- phase3: **PASS** — [metrics](../../07_runs/npu_phase3_20261123_221151_174576Z/metrics.json), [상위 실행 로그](../../07_runs/npu_phase7_20261123_220156_054531Z/phase3.log).
- phase4: **PASS** — [metrics](../../07_runs/npu_phase4_20261123_221222_648114Z/metrics.json), [상위 실행 로그](../../07_runs/npu_phase7_20261123_220156_054531Z/phase4.log).
- phase5: **PASS** — [metrics](../../07_runs/npu_phase5_20261123_221255_029479Z/metrics.json), [상위 실행 로그](../../07_runs/npu_phase7_20261123_220156_054531Z/phase5.log).
- phase6: **PASS** — [metrics](../../07_runs/npu_phase6_20261123_221353_423997Z/metrics.json), [상위 실행 로그](../../07_runs/npu_phase7_20261123_220156_054531Z/phase6.log).
- fault_priority: **PASS** — [metrics](../../07_runs/npu_fault_priority_20261123_221424_869350Z/metrics.json), [상위 실행 로그](../../07_runs/npu_phase7_20261123_220156_054531Z/fault_priority.log).

phase1 --legacy 안에서 기존 Python runner/Golden unit 27개와 Legacy control_unit, memory_wrapper, mac_array, accumulator_postprocess, mlp_top 5종을 모두 재실행했다. 각 child 실행 명령·종료 코드·metrics hash는 최상위 Manifest/Metrics에 있다. 기존 테스트를 생략하거나 실패를 PASS로 치환하지 않았다.

## 9. 실패 이력·보존·남은 범위

최초 aissd 의존성 확인은 읽기 전용 샌드박스가 임시 디렉터리 probe를 막아 torchvision import가 실패했다. 동일 명령을 승인된 권한으로 실행해 Python/PyTorch/torchvision/NumPy import와 CUDA 인식을 확인했다. 패키지 설치·업그레이드나 환경 설정 변경은 하지 않았다. Application unit/G0/G1/G2/G3/G4 및 기존 회귀에는 기능 실패·Golden 불일치·timeout이 없었고 RTL 수정도 없었다.

기존 RTL/테스트 SHA 보존, G3/G4 코드 구조 및 Prediction prefix, 파형 없음, 문서·Artifact hash의 최종 확인은 실행 디렉터리의 completion.json에 기록한다. 현재 변경은 신규 기능/검증 7개와 문서 4개(보고서 포함)다. 로그·HEX·Binary·NPZ·build·snapshot은 기존 gitignore에 따라 로컬 실행 디렉터리에만 남긴다.

승인 범위의 미해결 기능 문제나 설계 결정 대기 항목은 없다. 이번 모델과 첫 200장에 한한 Application Gate이며 모든 데이터/프로그램에 대한 보장을 의미하지 않는다. 10,000장 전체 정확도, 별도 모델 전환, FPGA/BMEM/합성/Timing은 별도 승인 후 수행한다. 커밋·Push 없이 Phase 7에서 중단한다.
