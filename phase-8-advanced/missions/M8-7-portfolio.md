# M8-7 포트폴리오 정리

> 가이드 수준: L3 · 예상 시간: 4~6h · 선행: M8-6

## 목표
이 미션을 끝내면 다음을 할 수 있다.
- 서비스 2개, 저장소 3종(MySQL·Redis·Kafka), 관측 스택 3개, Kafka 토픽 4개를 모두 담은 아키텍처 다이어그램과 매수 Saga 시퀀스 다이어그램을 Mermaid로 그린다
- Michael Nygard 형식(Title, Status, Context, Decision, Consequences) ADR 5개 이상을 측정값 근거와 함께 쓴다
- 트러블슈팅 사례 3개를 "증상 → 가설 → 근거 → 수정 → 검증 수치" 순서로 쓴다
- 처음 보는 사람이 레포 README만 보고 10분 안에 전체 스택을 띄울 수 있는지 새 디렉터리에 clone해서 검증한다

## 배경
면접관과 동료는 코드 전체를 읽지 않는다. README 첫 화면의 다이어그램, 설계 결정의 근거, 장애를 어떻게 찾고 고쳤는지의 기록을 보고 판단한다. "Kafka를 썼다"는 문장보다 "DB 커밋 후 발행 방식에서 100건 중 27건이 유실되는 것을 재현하고, Outbox로 0건을 만들었다"는 문장이 설계 능력을 보여준다. 이 미션은 M8-6까지 쌓인 측정표, 설계 문서, TIL을 하나의 레포 문서로 묶는다. Phase 0부터 쓴 `til/` 기록이 트러블슈팅 사례의 원재료다.

## 요구사항
1. **레포 README** (`phase-8-advanced/workspace/README.md` 또는 포트폴리오용 별도 레포 루트). 아래 절을 이 순서로 둔다.
   - 한 줄 요약 (무엇을 만들었는지, 서비스 수, 핵심 숫자 1개. 예: "500 req/s에서 이체 p99 N ms")
   - 아키텍처 다이어그램 (요구사항 2)
   - 실행 방법: 명령 3줄 이하 (`git clone` → `cd` → `docker compose up -d --build`)와 접속 주소 표(corebank 8081, trading 8082, Grafana 3000, Prometheus 9090, Jaeger 16686)
   - 기술 스택과 버전 표 (Java 21, Spring Boot 4.1.x, MySQL 8.4, Redis 8, Kafka 4.3.x, k6 등 실제로 쓴 버전)
   - 핵심 설계 결정: ADR 목록 링크와 각 1줄 요약
   - 측정 결과: M8-2 이중 쓰기 표 요약, M8-6 기준선과 최종 행 비교
   - 트러블슈팅: 사례 3개 링크와 각 1줄 요약
   - 테스트: `./gradlew test` 테스트 수, JaCoCo 라인 커버리지(모듈별)
2. **다이어그램** (Mermaid, GitHub에서 렌더링되는지 확인):
   - 구성도(`flowchart`): 클라이언트, corebank, trading, MySQL(스키마 2개 표시), Redis, Kafka 토픽 4개(`corebank.transfer.completed`, `trading.cash.commands`, `corebank.cash.replies`, DLT), Prometheus, Grafana, Jaeger. 화살표에 프로토콜(HTTP, JDBC, Kafka, OTLP, scrape)을 적는다
   - 시퀀스(`sequenceDiagram`): M8-4 정상 매수 흐름(주문 접수 → `HoldCash` → `CashHeld` → 체결 2회 → `CaptureHold` 2회 → `ReleaseHold` → `COMPLETED`)과 홀드 타임아웃 보상 흐름 1개
3. **ADR** `docs/adr/NNNN-slug.md` (번호 4자리, 0001부터):
   - 형식: `# NNNN. 제목` / `## Status` (Proposed, Accepted, Superseded by NNNN 중 하나) / `## Context` / `## Decision` / `## Consequences`
   - Context에 그 결정을 내린 미션의 측정값이나 재현 결과를 1개 이상 숫자로 적는다 (예: M5-8 비교표의 처리량, M8-2 유실 건수)
   - Decision에 고르지 않은 선택지를 1개 이상 적고 고르지 않은 이유를 쓴다
   - Consequences에 감수한 단점을 2개 이상 적는다
   - 5개 이상, 그중 2개 이상은 Phase 8 주제다. 주제 후보:

   | 후보 | 비교할 선택지 | 근거 미션 |
   |---|---|---|
   | 이체 동시성 제어 방식 | 비관적 락 / 낙관적 락 / 조건부 UPDATE | M5-8, M6-4 |
   | 멱등성 키 저장소 | DB 유니크 제약 / Redis `SET NX` | M4-4, M6-3 |
   | 다중 인스턴스 동시성 | Redisson 분산락 / DB 락 | M6-8 |
   | 매칭 엔진 동시성 모델 | 종목별 단일 스레드 이벤트 루프 / 락 기반 호가창 | M7-4 |
   | 호가창 복구 | 명령 로그 전체 재생 / 스냅샷 + 이후 로그 재생 | M7-8 |
   | 이벤트 발행 | 폴링 Outbox / CDC(Debezium) / AFTER_COMMIT 리스너 | M8-2, M8-3 |
   | Saga 조정 방식 | 오케스트레이션 / 코레오그래피 | M8-4 |
   | 매수 대금 홀드 위치 | trading 내부 예수금 / corebank 계좌 | M8-4 |
   | 금액 표현과 직렬화 | `BigDecimal` + 문자열 / `long` 원 단위 / JSON 숫자 | M1-1, M4-6 |
   | 타행이체 결과 미확정 처리 | 조회 후 확정 / 자동 재시도 / 즉시 실패 처리 | M6-7 |

4. **트러블슈팅** `docs/troubleshooting/NN-slug.md` 3개:
   - 절 순서: `## 증상`(관찰한 현상과 수치, 예: "동시 이체 1,000건 후 총액이 3,000원 줄었다") / `## 가설`(2개 이상, 각각 확인 방법) / `## 근거`(로그, 스레드 덤프, `SHOW ENGINE INNODB STATUS`, Grafana 패널, Jaeger 트레이스 중 실제 자료 발췌) / `## 수정`(무엇을 왜 바꿨는지, 커밋 링크) / `## 검증`(재현 테스트 이름과 수정 전후 수치)
   - 3개 중 1개 이상은 Phase 8에서 겪은 문제(M8-1 ~ M8-6), 1개 이상은 동시성·DB 락 문제(Phase 2, 5, 6)
   - 각 사례에 재현 테스트가 있어야 한다. 테스트가 없는 사례는 지금 테스트를 작성한 뒤 기록한다
5. **처음 보는 사람 검증**: 레포를 새 디렉터리(예: `/tmp/portfolio-check`)에 clone하고, README의 명령만 그대로 따라 실행해 `scripts/wait-healthy.sh` 성공까지 걸린 시간을 README "실행 방법" 절 아래에 적는다. README에 없는 명령을 하나라도 실행해야 했다면 README를 고치고 다시 잰다.
6. **정리 체크리스트**: `docs/portfolio-checklist.md`에 아래 항목을 체크박스로 두고 모두 체크한다.
   - 레포에 비밀번호·토큰이 커밋되지 않았다 (`git log -p | grep -i -E "password|secret|token"` 결과 검토, 학습용 기본값만 있음을 확인)
   - `.env`, `build/`, IDE 설정 파일이 `.gitignore`에 있다
   - 모든 ADR·트러블슈팅 문서가 README에서 링크된다
   - Mermaid 다이어그램이 GitHub 웹에서 렌더링된다 (스크린샷)
   - GitHub Actions 최신 실행이 초록색이다
   - 각 Phase의 TIL에서 이 레포 문서로 옮긴 항목에 링크가 있다

## 직접 작성할 테스트 시나리오

이 미션의 테스트는 문서 검증 절차다. `docs/portfolio-checklist.md` 아래에 표로 적는다.

반드시 포함할 경우 (최소 5개):
- 새 디렉터리 clone → README 명령만 실행 → 모든 서비스 healthy까지 걸린 시간(분:초)
- README의 모든 상대 경로 링크가 열린다 (GitHub 웹에서 클릭하거나 링크 검사 도구 실행 결과)
- ADR 5개 각각에 숫자 근거 1개 이상, 고르지 않은 선택지 1개 이상, 단점 2개 이상이 있다 (ADR별 체크 표)
- 트러블슈팅 3개 각각의 재현 테스트가 `./gradlew test --tests '<테스트 이름>'`으로 통과한다
- 이 레포를 처음 보는 사람 1명(동료, 스터디원)에게 README만 보여주고 3분 안에 "무엇을 만들었고 어떤 문제를 풀었는가"를 말하게 한 결과 기록. 사람을 구하지 못했다면 녹음한 3분 자기 설명으로 대신하고 그 사실을 적는다

## 제약
- 다이어그램을 이미지 파일로만 넣지 않는다. Mermaid 텍스트로 두어야 코드가 바뀔 때 diff로 함께 고칠 수 있다. draw.io를 쓴다면 `.drawio` 원본도 커밋한다.
- ADR은 결정 당시의 맥락을 남기는 문서다. 나중에 결정을 바꿨다면 기존 ADR을 고쳐 쓰지 않고 새 ADR을 추가한 뒤 기존 ADR의 Status를 `Superseded by NNNN`으로 바꾼다.
- 측정하지 않은 수치를 쓰지 않는다. 모든 숫자는 레포 안의 측정표·테스트·스크린샷 중 하나로 연결된다.
- 트러블슈팅에 "원인을 찾아 해결했다"처럼 근거 없는 문장을 쓰지 않는다. 근거 절에 실제 자료 발췌가 있어야 한다.

## 힌트
없음.

## 완료 기준
- [ ] 레포 README에 요구사항 1의 8개 절이 순서대로 있고, 구성도·시퀀스 다이어그램이 GitHub 웹에서 렌더링된다
- [ ] `docs/adr/`에 Nygard 형식 ADR 5개 이상이 있고, 그중 2개 이상이 Phase 8 주제다
- [ ] `docs/troubleshooting/`에 사례 3개가 있고, 각 사례의 재현 테스트가 통과한다
- [ ] 새 디렉터리 clone 검증 시간이 README에 적혀 있고 10분 이하다
- [ ] `docs/portfolio-checklist.md`의 체크박스가 모두 체크되어 있다

## 생각해볼 질문
1. 이 커리큘럼에서 고른 결정 중 서비스 규모가 100배(계좌 1억 개, 초당 주문 50,000건)가 되면 가장 먼저 뒤집힐 ADR은 무엇인가? 무엇이 먼저 한계에 닿는지 M8-6 측정값으로 추정한다.
2. 커리큘럼 이후 공부할 주제를 아래에서 2개 고르고, 이 레포의 어느 부분을 바꾸는 실습으로 시작할지 적는다.
   - Kubernetes: Compose를 Deployment·Service·readiness probe·HPA로 옮기고 롤링 배포 중 이체 실패율 측정
   - CDC 실제 구현: Debezium MySQL 커넥터 + Kafka Connect로 폴링 릴레이를 대체하고 발행 지연 비교
   - Kafka Streams와 exactly-once: 체결 이벤트로 종목별 1분 봉(OHLC) 집계
   - 장애 주입: Toxiproxy·Chaos Mesh로 네트워크 지연 500ms를 넣고 Saga 타임아웃·서킷 브레이커 동작 검증
   - OpenTelemetry Collector tail 샘플링: 느린 요청과 오류 트레이스만 100% 보관
   - 합의 알고리즘과 복제: DDIA 1판 9장 "Consistency and Consensus", Kafka KRaft의 Raft 기반 메타데이터 복제
   - 금융 보안: OAuth 2.1 Authorization Server, mTLS 서비스 간 인증, 감사 로그 위변조 방지(해시 체인)
3. 27.5주 동안 가장 오래 막힌 미션은 무엇이었고, 그때 문서가 무엇을 더 알려줬다면 덜 막혔겠는가? 이 레포에 이슈로 남긴다.
