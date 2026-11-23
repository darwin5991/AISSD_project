# Codex 첫 작업 요청 예시

다음 메시지를 저장소를 연 Codex에 전달하면 된다.

---

`00_docs/programmable_npu/README.md`, `01_isa_spec.md`, `02_architecture.md`, `03_implementation_plan.md`, `04_verification_plan.md` 및 저장소 루트 `AGENTS.md`를 읽어라. 기존 `00_docs/architecture.md`와 `00_docs/mac_input_pipeline.md`, 실제 `04_rtl`/`05_tb` 소스도 확인하라.

이 프로젝트는 기존 고정 3-Layer MLP RTL을 32bit ISA 기반 Programmable NPU로 확장하는 작업이다. 합의된 ISA/타이밍 계약을 임의 수정하지 말고, `03_implementation_plan.md`에 적힌 **Phase 0만 먼저 수행**해라.

1. 현재 RTL 모듈 구조·파일·포트를 점검하고 명세와 충돌하거나 추가 결정이 필요한 부분을 찾아라.
2. 기존 테스트 재실행 방법과 최신 코드 기준의 Pass/Fail 상태를 확인하라. 테스트를 실행하지 않았다면 실행한 것처럼 보고하지 마라.
3. 이번 단계에서는 RTL 기능을 수정하거나 대량 리팩터링하지 말고, Phase 0 진단과 단계별 구체적인 변경/검증 계획만 작성하라.
4. 보고할 때는 파일별 변경 필요성, 기존 Datapath 재사용 가능 범위, BMEM IP 및 Memory Read Latency 위험, 기존 Testbench 회귀 계획, 명세에서 추가 의사결정이 필요한 사항을 명확히 구분하라.
5. Phase 0 결과를 보고하고 사용자 확인을 받은 후 Phase 1 구현을 시작하라.

특히 `mac_array`의 3-stage 파이프라인 및 `accumulator_postprocess`의 연산, BRAM read(R)→최종 output write(R+6) 타이밍은 필요성이 입증되기 전까지 수정하지 마라. 기존 `mlp_top`은 Legacy 회귀에 사용할 수 있도록 보호하고, 신규 `npu_top`으로 점진적 마이그레이션을 우선 검토해라.

---

## 문서 배포

아래 구조를 저장소 루트에 복사한다.

```text
AGENTS.md
00_docs/
  programmable_npu/
    README.md
    01_isa_spec.md
    02_architecture.md
    03_implementation_plan.md
    04_verification_plan.md
    05_codex_kickoff.md
```

`AGENTS.md`는 Codex가 읽을 수 있도록 **저장소 루트**에 놓는다. 이 압축 패키지는 기존 파일을 덮어쓰지 않는 새 경로를 사용한다.
