# MLP End-to-End Accelerator

> **2026-11-10 명세 개정:** MAC 입력·가중치 레지스터 1단을 추가해 데이터·valid 경로를 3단으로 변경했다. MAC·Control RTL과 검증환경 코드를 3단 명세에 맞게 수정했고 새 검증 데이터·헤더 5종을 생성했다. 생성기 내부 검사는 PASS했지만 새 RTL의 테스트·시뮬레이션·합성·배치배선은 아직 실행하지 않았다. [변경 범위와 일정](00_docs/mac_input_pipeline.md)을 따른다. 기존 실행 기록은 이전 구조의 이력으로 보존한다.

MNIST MLP 모델의 양자화·분석부터 RTL 설계, testbench 검증, FPGA 구현, 실험 결과와 최종 보고서까지 관리하는 프로젝트입니다.

과제 가이드의 대상 연산은 `FC1 (784 → 512) → ReLU → FC2 (512 → 128) → ReLU → FC3 (128 → 10)`이며, Dropout과 Softmax는 제외합니다. 제공 체크포인트의 실제 구조, bias 사용 여부, 입력 전처리는 모델 로딩 단계에서 확인해야 합니다.

## 현재 상태

- 디렉터리 구조와 기존 참고 자료·체크포인트 배치를 정리했습니다.
- 모델 분석·8비트 양자화는 [단일 분석 노트북](03_model/notebooks/mlp_int8_analysis.ipynb)에서 진행합니다. `aissd` Python 커널로 위에서 아래로 실행합니다. 함수·클래스는 `03_model/src/`에 있으며, 노트북 8번 설정 셀에서 소수부 비트 수와 signed·unsigned를 선택합니다.
- 기본 저장 대상은 노트북에서 직접 선택한 형식입니다. 전체 weight와 예시 입출력은 `07_runs/mlp_int8_analysis/arrays.npz`, 실험 비교표는 같은 폴더의 `results.csv`에 저장합니다.
- 입력 전처리는 노트북에서 학습 calibration으로 비교합니다. 표준 정규화가 선택되면 입력에도 음수가 생기므로 기본 입력은 signed 8비트를 사용합니다.
- 기존 2단 MAC 구조의 실제 RTL·TB·공통 실행기를 작성했고, 전체 실제 RTL Top 이미지 0~9 검증을 통과했습니다. 새 MAC 입력 레지스터를 포함한 3단 구조의 명세와 golden·TB/tester·실행기 코드는 수정했습니다. 실제 RTL을 수정하고 새 헤더도 생성했으며, 생성기 내부 검사를 통과했습니다. 새 RTL의 테스트·시뮬레이션·합성·타이밍 검증은 아직입니다.
- 아래 파일명과 실행 흐름은 앞으로 구현할 기준이며, 실행 가능한 명령은 구현 후 이 문서에 추가합니다.

## 디렉터리 구조

```text
project/
├── README.md
├── .gitignore                  # 프로젝트 데이터·생성 결과 관리 규칙
├── 00_docs/
│   ├── reference/              # 제공 가이드, 보고서 템플릿, 참고 그림
│   └── report/                 # 작성 중인 보고서와 보고서용 그림
├── 01_configs/
│   └── experiments/            # 실험별 설정 조합
├── 02_data/
│   ├── README.md               # 데이터 출처·전처리·샘플 선택 규칙
│   └── raw/                    # 프로젝트 데이터셋
├── 03_model/
│   ├── src/                    # 모델 로딩·평가·분석·양자화·HEX export
│   ├── notebooks/              # 탐색 및 시각화
│   └── checkpoints/            # 원본 및 보존할 모델 체크포인트
├── 04_rtl/
│   ├── mac_array/              # MAC array와 전용 곱셈·adder tree
│   ├── accumulator_postprocess/ # 누산기·bias 정렬·출력 후처리
│   ├── memory/                 # 메모리 wrapper·RAM·접근 경로
│   ├── controller/             # Control unit·ARGMAX·Top
│   └── common/                 # 여러 큰 모듈이 공유하는 레지스터·지연·덧셈기
├── 05_tb/
│   ├── unit/                   # 개별 모듈 검증
│   ├── layer/                  # FC 레이어 단위 검증
│   ├── system/                 # 전체 MLP end-to-end 검증
│   └── common/                 # 데이터 로더·비교기·공통 task
├── 06_fpga/
│   ├── constraints/            # 타이밍·핀 제약
│   ├── ip/                     # BMEM 등 IP 설정 및 재생성 파일
│   └── tcl/                    # 프로젝트 생성·합성·구현 스크립트
├── 07_runs/                    # 실행별 설정 스냅샷과 실험 결과
├── 08_submission/              # 최종 제출용 파일과 ZIP
├── 90_scripts/                 # 전체 단계에서 사용하는 자동화 스크립트
└── 99_build/                   # 재생성 가능한 툴 작업 파일·캐시
```

번호는 주 작업이 시작되는 순서를 나타냅니다. `00_docs`와 `01_configs`에서 요구사항·설정을 준비하고, `02_data`와 `03_model`에서 데이터 준비·모델 분석·양자화를 진행합니다. 하드웨어 작업은 `04_rtl → 05_tb → 06_fpga` 순서로 나란히 배치했습니다. 설계와 검증은 반복해서 진행하며, 각 단계의 결과는 `07_runs`에 기록하고 최종 제출물은 `08_submission`에 모읍니다. 문서와 보고서는 프로젝트 전 기간에 걸쳐 갱신합니다.

`90_scripts`와 `99_build`는 모든 단계에서 사용하는 공통 도구·작업 공간이므로 뒤쪽에 배치했습니다.
빈 작업 디렉터리는 `.gitkeep`으로 유지합니다. 코드와 설정 파일은 실제 구현 시 추가합니다.

## 참고 자료

- [프로젝트 가이드 PDF](00_docs/reference/AISSD_project-1.pdf)
- [프로젝트 가이드 Markdown](00_docs/reference/AISSD_project-1.md)
- [보고서 원본 템플릿 DOCX](00_docs/reference/AISSD_project_report_template-1.docx)
- [보고서 템플릿 Markdown](00_docs/reference/AISSD_project_report_template-1.md)
- [체크포인트 관리 안내](03_model/checkpoints/README.md)

`00_docs/reference/`의 제공 자료는 원본으로 보존합니다. 보고서는 템플릿 DOCX를 `00_docs/report/`에 복사해서 작성하고 제공 양식을 유지합니다. 추출된 Markdown의 깨진 문자나 누락된 내용은 원본 PDF·DOCX에서 확인합니다.

## 개발 흐름

1. **모델 기준 확보**: 체크포인트의 구조·bias·전처리를 확인하고 FP32 정확도를 측정합니다.
2. **분석 및 양자화**: weight·activation 분포를 분석하고 비트폭별 정확도와 수치 오차를 비교합니다.
3. **정수 기준 모델 구현**: RTL과 동일한 비트폭, 반올림, 포화, 연산 순서를 적용합니다.
4. **데이터 규약 및 export**: 메모리 배치를 정하고 weight·입력·레이어별 기대 출력 HEX를 생성합니다.
5. **RTL 검증**: 연산 모듈 → FC 레이어 → 전체 MLP 순서로 검증합니다.
6. **FPGA 구현 및 실험**: 합성·구현 후 자원 사용량, 타이밍, cycles, latency 등을 기록합니다.
7. **보고서 및 제출**: 근거가 되는 실행 ID를 연결하고 RTL·TB·HEX·보고서를 패키징합니다.

FP32와 양자화 모델은 정확도와 수치 오차로 비교합니다. 정수 기준 모델과 RTL은 같은 입력에 대해 비트 단위 일치를 확인합니다. 최종 분류 결과뿐 아니라 FC1·FC2·FC3의 중간 출력도 비교합니다.

## 구현하면서 추가할 파일

| 위치 | 역할 |
| --- | --- |
| `00_docs/requirements.md` | 과제 요구사항과 검증 항목 |
| `00_docs/architecture.md` | 블록 구성, 데이터 흐름, 제어 방식, 담당 범위 |
| `00_docs/numeric-format.md` | 양자화 및 정수 연산 규칙 |
| `00_docs/memory-map.md` | 주소 배치, 행렬 저장 순서, HEX 포맷 |
| `01_configs/model.yaml` | 모델 구조, 전처리, 데이터·체크포인트 경로 |
| `01_configs/quantization.yaml` | 비트폭, scale, 반올림·포화 규칙 |
| `01_configs/hardware.yaml` | 병렬도, 메모리 구성, 목표 클록 |
| `03_model/src/models.py` | assignment1에서 복사한 모델 정의 |
| `03_model/src/quantization.py` | 8비트 형식·설정 생성·정수 추론 |
| `03_model/src/analysis.py` | 노트북용 로딩·평가·시각화·탐색·NPZ 저장 API |

설정의 기준은 `01_configs/`에 두고, Python과 RTL에 필요한 상수는 해당 설정에서 생성하는 방식으로 구현합니다. 생성된 RTL 상수·헤더는 실행 결과 또는 빌드 디렉터리에 저장하고 원본 설정과 연결합니다.

`numeric-format.md`에는 입력·weight·bias·누산기·출력의 비트폭, signed 여부, scale, 반올림·잘림, overflow·saturation, ReLU·재양자화 순서를 명시합니다. `memory-map.md`에는 행렬 저장 순서, 주소, HEX 한 줄의 비트폭, packing 순서를 명시합니다.

## 실험 결과 관리

각 실행은 새 실행 ID를 사용하고 기존 결과를 덮어쓰지 않습니다. 예: `exp_001_w8a8_pe16`.

```text
07_runs/exp_001_w8a8_pe16/
├── manifest.json               # Git commit, 변경 상태, seed, 도구 버전, 파일 해시
├── config.yaml                 # 기본값까지 반영된 실제 실행 설정
├── README.md                   # 실험 목적, 실행 명령, 결과 해석
├── analysis/                   # 분포·범위·양자화 오차
├── vectors/                    # weight·입력·레이어별 기대 출력 HEX
├── sim/                        # 로그, 비교 결과, 필요한 파형
├── implementation/             # 자원 사용량·타이밍 보고서
├── figures/                    # 결과 그래프
└── metrics.json                # 정확도, cycles, latency, 자원 등
```

- `manifest.json`에는 체크포인트·입력·HEX의 해시와 평가 샘플 ID를 기록합니다. 작업 트리가 수정된 상태면 패치나 소스 스냅샷도 외부 백업에 보존합니다.
- 다른 실행의 HEX나 체크포인트를 재사용하면 원본 실행 ID와 파일 해시를 기록합니다.
- cycles·latency는 데이터 로딩 포함 여부, 측정 시작·종료 조건, 클록 주파수를 함께 기록합니다.
- `99_build/`에는 재생성 가능한 작업 파일을 두고, 보존할 로그·보고서는 해당 `07_runs/<실행 ID>/`로 옮깁니다.
- 보고서에서 사용한 수치와 그림은 실행 ID와 원본 결과 경로를 명시합니다. 보고서에 실제 삽입한 그림은 `00_docs/report/`에 보존합니다.

## Git 및 백업 정책

| 항목 | 관리 방식 |
| --- | --- |
| 소스, 설정, 제약, IP 재생성 파일, 문서 | Git에 기록 |
| 실행별 `manifest.json`, `config.yaml`, `metrics.json`, `README.md` | Git에 기록 |
| 데이터셋, 모델 체크포인트 | Git에서 제외, 원본 출처·해시·백업 위치 기록 |
| 실행별 HEX, 파형, 상세 로그, 구현 결과 | Git에서 제외, 보존할 실행은 외부 백업 |
| 빌드 캐시, 제출물 복사본·ZIP | Git에서 제외 |
| 보고서 원고 및 최종 DOCX·PDF | `00_docs/report/`에서 Git에 기록 |

상위 `.gitignore`의 `*.pt`, `*.pth`, `*.ckpt` 제외 규칙도 적용됩니다. 데이터와 대형 결과는 저장 위치만으로 백업되지 않으므로, 외부 백업과 복구 절차를 함께 관리합니다. `07_runs/`에 남길 새로운 요약 파일 형식은 `.gitignore`의 허용 목록에 추가합니다.

## 환경과 경로

- Python 패키지의 초기 기준은 저장소 루트의 [requirements.txt](../requirements.txt)입니다. 실제 검증한 Python·PyTorch·CUDA 버전은 실행 manifest에 기록합니다.
- FPGA part, Vivado·시뮬레이터 버전은 선택 후 설정과 실행 manifest에 기록합니다.
- 경로는 `project/`를 기준으로 설정하고 개인 PC의 절대경로를 코드에 고정하지 않습니다.
- 프로젝트 데이터셋의 기본 위치는 `02_data/raw/`입니다. 기존 저장소 루트 `../data/`를 재사용할 경우 설정에 명시하고 중복 다운로드를 피합니다.
- 노트북은 분석과 시각화에 사용하고, 반복 실행에 필요한 처리는 `03_model/src/`와 `90_scripts/`에 구현합니다.

## 과제 구현 및 제출 확인

다음은 제공 가이드에서 확인한 주요 항목입니다. 상세 조건은 원본 가이드를 기준으로 확인합니다.

- 대상 MLP의 FC1 → ReLU → FC2 → ReLU → FC3를 end-to-end로 실행합니다.
- `readmemh`·`readmemb`는 tester에서만 사용합니다.
- `initial`·delay 사용은 testbench 및 제공 SRAM 파일에 대한 가이드의 허용 범위로 제한합니다.
- SRAM은 BMEM으로 구현하고, `reg` 배열로 대체하지 않습니다.
- timing slack은 양수여야 합니다.
- 제출물에는 설계한 `.v`·`.sv`, testbench, 데이터 import용 HEX, 최종 보고서 DOCX·PDF를 포함합니다.
- 최종 제출 파일명은 가이드의 `{Student_ID}_{Korean_name}` 규칙에 맞춥니다.

`08_submission/`은 검증된 소스·HEX·보고서를 모으는 용도로 사용합니다. 작업 원본은 각 소스 디렉터리와 `00_docs/report/`에서 관리하고, 패키징 스크립트는 구현 시 `90_scripts/`에 추가합니다.
