# mlp_top OOC 합성 준비

기존 **2단 MAC 구조**의 프로젝트 생성·OOC 합성·배치배선은 실행했다.
합성은 PASS, 배치·배선 후 100 MHz setup은 WNS -0.058 ns·위반 endpoint 4개로 FAIL이다.
[실행 기록](../07_runs/mlp_top_ooc_impl_20261109_185811_178681Z/README.md)을 보존한다.
새 [3단 MAC 명세](../00_docs/mac_input_pipeline.md), MAC·Control RTL 및 golden·TB/tester·실행기 코드를 수정했다.
새 검증 데이터·헤더는 별도 생성 단계에서 준비했고 생성기 내부 검사는 PASS했다.
새 RTL의 테스트·시뮬레이션·합성·배치배선과 타이밍 개선 여부는 아직 확인하지 않았다.

## 확정 조건

- FPGA part: `xc7a100tcsg324-1`.
- 합성 Top: `mlp_top`. 실제 RTL 전체와 기존 `tb_*` 포트를 유지한다.
- OOC 합성으로 물리 입출력 버퍼 자동 삽입과 보드 핀 지정을 하지 않는다.
- 목표 클럭: `core_clk`, 100 MHz, 주기 10 ns. 이전 2단 구조는 post-route setup FAIL이며 새 3단 구조는 미평가다.
- 첫 타이밍 평가는 내부 레지스터 사이 경로를 대상으로 한다.
- 입력/출력 지연, 보드 핀, I/O 표준, reset 해제 조건은 아직 정하지 않는다.
- 미정 경로를 숨기는 false-path나 임의의 0 ns 입출력 지연은 추가하지 않는다.
- BRAM/DSP 매핑을 강제하는 새 옵션은 추가하지 않는다. 실제 매핑은 합성 후 확인한다.

## 파일

- `constraints/mlp_top_ooc.xdc`: 클럭 제약만 정의한다.
- `tcl/create_mlp_top_ooc_project.tcl`: 실제 RTL과 XDC를 등록하고 OOC 합성 옵션을 설정한다.
  기존 `90_scripts/sim_targets.json`의 Top RTL 목록을 기준으로 작성했으며,
  이후 RTL 구성이 변경되면 두 목록을 함께 관리한다.
- TB, tester, behavioral model, `mlp_top_tb_data.vh`, golden NPZ/HEX는 합성 입력이 아니다.
  따라서 현재 TB 헤더의 이미지 번호는 이 합성 설정에 영향을 주지 않는다.
  실제 보드에서 데이터를 공급하는 회로/방법은 이번 설정의 범위 밖이다.

## 이후 프로젝트를 생성할 때

이 절차는 안내이며 이번 작성 단계에서는 실행하지 않는다.

1. Vivado에서 현재 프로젝트를 닫는다.
2. Tcl Console에서 아래 명령을 실행한다. 다른 위치에 checkout했다면 경로를 바꾼다.

```tcl
source {D:/Data/Local/Desktop/programing/AISSD/project/06_fpga/tcl/create_mlp_top_ooc_project.tcl}
```

프로젝트는 `project/99_build/vivado_mlp_top_ooc/mlp_top_ooc.xpr`에 생성된다.
Tcl은 원본 소스를 참조하며 복사하지 않는다. 기존 출력 폴더가 있으면 덮어쓰지 않고
중단하므로, 재사용할 때는 기존 `.xpr`를 연다. 이 Tcl은 프로젝트 설정까지만 수행하며
`Run Synthesis`, Implementation 또는 시뮬레이션을 자동 실행하지 않는다.

## 새 구조 합성 이후 해석할 범위

별도 승인으로 합성을 실행한 뒤에는 LUT/FF/BRAM/DSP 사용량, 메모리 추론,
경고와 내부 경로의 추정 타이밍을 확인한다. 합성 타이밍은 배선 지연의 추정치를
포함하므로 목표 주파수의 최종 달성 판정은 배치·배선 이후에 한다.

입출력 지연과 reset 해제 조건을 정하지 않았으므로 관련 미제약 경로·경고는
숨기지 않고 별도로 기록한다. 내부 경로가 목표를 만족해도 전체 인터페이스 또는
보드 동작의 타이밍이 통과했다고 보고하지 않는다. 전력·배치배선·보드 검증은 후속 단계다.

## 참고

- [AMD OOC 합성/구현 안내](https://adaptivesupport.amd.com/s/article/59168?language=en_US)
- [설계 명세](../00_docs/architecture.md), 3절 및 6.3절.

기존 합성·배치배선 checkpoint는 이전 2단 구조의 산출물이다. `.xpr`는 수정한 원본 RTL을 참조하므로 새 구조의 결과를 얻으려면 기능 검증 후 재합성이 필요하다. 이번에는 RTL 코드만 수정했고 새 데이터는 앞선 생성 단계에서 준비했다. 기능 검증·재합성·배치배선은 각각 별도 요청을 받아 진행한다. 이번 개정에서 OOC 클럭 위치, 입출력 지연, reset 안전성 또는 DSP 강제 사용을 새로 확정하지 않았다.
