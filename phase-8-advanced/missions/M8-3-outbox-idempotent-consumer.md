# M8-3 Transactional Outbox와 멱등 컨슈머

> 가이드 수준: L3 · 예상 시간: 8~10h · 선행: M8-2

## 목표
이 미션을 끝내면 다음을 할 수 있다.
- M8-2의 실험을 `outbox` 전략으로 다시 실행해 "DB 커밋 90건 = 토픽 고유 메시지 90건, 유실 0, 유령 0"을 테스트로 단언한다
- `SELECT ... FOR UPDATE SKIP LOCKED` 폴링 릴레이 2개를 동시에 돌려도 outbox 행 1,000개가 각각 정확히 1번씩 발행되는 것을 테스트로 보여준다
- 같은 메시지가 3번 전달되어도 부수효과(알림 행)가 1번만 생기는 멱등 컨슈머를 만들고, 처리 후 커밋 전 장애에서도 같은 결과가 나오는 것을 테스트로 보여준다
- 같은 계좌의 이벤트가 발행 순서대로 소비되는 조건(키, 파티션, 릴레이 순서)을 테스트와 문서로 설명한다

## 배경
M8-2에서 어떤 순서로 발행해도 유실 또는 유령이 남는다는 것을 숫자로 봤다. Transactional Outbox는 "Kafka에 보낼 메시지"를 이체 기록과 같은 MySQL 트랜잭션에 넣어 두 쓰기를 하나로 만든다(README 2절). 대가로 릴레이 재시도에 의한 중복이 생기므로, 컨슈머가 같은 메시지를 두 번 받아도 결과가 같게 만들어야 한다(README 3절). 실제 은행 앱에서 "입금 알림이 두 번 왔다"는 중복 처리 실패, "알림이 안 왔다"는 유실이다. 이 미션에서 만드는 outbox·릴레이·멱등 컨슈머는 M8-4 Saga의 명령·응답 메시지 전달에 그대로 쓴다.

## 요구사항
1. **outbox 테이블** (corebank, trading 각 스키마에 Flyway 마이그레이션으로 생성). 필수 열:
   - `id`: 메시지 ID. UUID 문자열(36자). Kafka 헤더 `message-id`로 나간다
   - `aggregate_type`, `aggregate_id`: 예 `ACCOUNT`, `110-001`. `aggregate_id`가 Kafka 메시지 키다
   - `event_type`, `topic`, `payload`(JSON 문자열)
   - `trace_parent`: 발행 시점의 W3C `traceparent` 값, 없으면 NULL (M8-5에서 사용)
   - `created_at`, `published_at`(NULL이면 미발행), `attempt_count`
   - 발행 순서를 정할 수 있는 단조 증가 열 1개 (UUID는 순서를 보장하지 않으므로 별도 열이 필요하다. 무엇으로 할지 직접 정한다)
2. **같은 트랜잭션 기록**: `corebank.event.publish-strategy=outbox`일 때 이체 서비스는 이체·분개·`outbox` INSERT를 하나의 DB 트랜잭션에서 커밋한다. 이체 서비스 코드에 `KafkaTemplate` 의존이 없어야 한다.
3. **릴레이 `OutboxRelay`**:
   - 500ms마다 미발행 행을 순서 열 오름차순으로 최대 100개 `SELECT ... FOR UPDATE SKIP LOCKED`로 가져와 Kafka로 보낸다
   - 배치 안의 메시지를 모두 보낸 뒤 결과를 기다리고(`acks=all`), 성공한 행만 `published_at`을 채운 다음 커밋한다. 실패한 행은 `attempt_count`를 1 올리고 미발행으로 남긴다
   - `attempt_count`가 10에 이르면 그 행은 더 보내지 않고 `outbox_stuck` 로그(ERROR)를 남긴다. 이 행은 M8-5에서 메트릭으로 노출한다
   - 처리량 기준: 미발행 행 10,000개를 넣고 릴레이를 시작하면 10초 안에 모두 `published_at`이 채워진다(Testcontainers 환경, 측정값을 문서에 기록). M8-6의 목표 부하 500 req/s를 릴레이가 따라가야 하기 때문이다
4. **보관 정책**: `published_at`이 7일 이상 지난 행은 1시간마다 삭제한다. 시각은 `Clock` 빈으로 주입받아 테스트에서 고정한다.
5. **멱등 컨슈머 (corebank 알림)**:
   - 컨슈머 그룹 `corebank-notification`이 `corebank.transfer.completed`를 구독한다
   - 메시지 하나당 `notification` 테이블에 2행(출금 계좌 A에 "출금 1,000원", 입금 계좌 B에 "입금 1,000원")을 INSERT한다. `notification`에는 이체 ID 유니크 제약을 두지 않는다. 중복 방지는 아래 `processed_message`만으로 해야 이 미션의 장치를 검증할 수 있다
   - `processed_message` 테이블: PK (`consumer`, `message_id`), `processed_at`. `consumer`는 컨슈머 이름(예: `corebank-notification`)이다. 같은 DB를 쓰는 다른 컨슈머가 같은 메시지를 처리해도 충돌하지 않게 하기 위해서다
   - `processed_message` INSERT와 `notification` INSERT는 같은 DB 트랜잭션이다. PK 중복이면 트랜잭션을 롤백하고 메시지는 "이미 처리됨"으로 정상 완료(ack) 처리한다
   - `message-id` 헤더가 없는 메시지는 처리하지 않고 DLT로 보낸다
6. **오프셋 커밋**: 오프셋은 DB 트랜잭션 커밋 후에 커밋된다. `spring.kafka.consumer.enable-auto-commit=false`를 명시하고, `spring.kafka.listener.ack-mode`를 무엇으로 했는지와 이유를 `docs/outbox-design.md`에 적는다.
7. **재시도와 DLT**: 처리 중 예외는 1초 간격 3회 재시도 후 `corebank.transfer.completed.DLT` 토픽으로 보낸다(Spring for Apache Kafka의 `DefaultErrorHandler` + `DeadLetterPublishingRecoverer`). JSON 파싱 실패는 재시도하지 않고 바로 DLT로 보낸다.
8. **순서 보장 범위**: 같은 `aggregate_id`의 메시지는 같은 파티션으로 가고(키), 릴레이 1개가 순서 열 오름차순으로 보내므로 컨슈머는 커밋 순서대로 받는다. 릴레이 인스턴스가 2개일 때 이 보장이 깨질 수 있는 시나리오를 `docs/outbox-design.md`에 시간 순서 표로 적는다.
9. **trading에도 같은 장치**: trading 스키마에 `outbox`, `processed_message`를 만들고 릴레이를 띄운다. 발행할 이벤트는 M8-4에서 정하므로, 이 미션에서는 trading 릴레이가 테스트용 행 1개를 발행하는 통합 테스트까지만 만든다.
10. **CDC 비교(구현하지 않음)**: Debezium MySQL 커넥터로 outbox를 옮기는 방식과 폴링 릴레이를 지연, DB 부하, 운영할 구성 요소 수, 순서 보장 4개 기준으로 비교한 표를 `docs/outbox-design.md`에 적는다. 이 표는 M8-7 ADR의 근거가 된다.

## 직접 작성할 테스트 시나리오

Testcontainers(MySQL 8.4, `apache/kafka:4.3.2`) 통합 테스트로 작성한다. 릴레이 스케줄러는 테스트에서 끄고 `OutboxRelay`의 1회 실행 메서드를 직접 호출해도 된다.

반드시 포함할 경우 (최소 10개):
- M8-2 요구사항 5 실험을 `outbox` 전략으로 실행 → unpause 후 30초 안에 D와 K가 같고 크기 90, 유실 0, 유령 0
- 이체 커밋 직전 실패 주입 → `outbox` 행 0개
- 브로커 pause 중 릴레이 1회 실행 → 모든 행 `published_at` NULL, `attempt_count` 1 증가
- 릴레이가 Kafka 전송 성공 후 `published_at` 갱신 전에 예외 → 다음 실행에서 같은 `message-id`가 다시 발행됨(토픽에 같은 ID 2건)
- 릴레이 2개를 스레드 2개에서 동시에 반복 실행, 미발행 행 1,000개 → 토픽 메시지 1,000건, `message-id` 고유값 1,000개
- 미발행 10,000행 → 10초 안에 전부 발행 (경과 시간을 테스트 출력에 기록)
- 같은 `message-id` 메시지를 3번 발행 → `notification` 2행, `processed_message` 1행
- 컨슈머가 DB 커밋 후 ack 전에 예외(테스트 전용 빈으로 주입) → 재전달 후에도 `notification` 2행
- 잘못된 JSON 메시지 → 재시도 없이 DLT에 1건, `notification` 0행
- 같은 계좌 키로 이체 20건 → 컨슈머가 받은 `transferId` 순서가 커밋 순서와 같음
- `published_at`이 7일 1분 전인 행과 6일 23시간 전인 행 → 정리 작업 후 앞의 행만 삭제

## 제약
- 릴레이는 outbox 행을 `DELETE`로 처리 완료 표시하지 않는다. `published_at`을 채운다. 발행 지연(`published_at − created_at`)을 M8-5에서 측정하기 위해서다.
- Kafka 오프셋, 파티션 번호를 메시지 ID로 쓰지 않는다. 릴레이가 재발행하면 오프셋이 바뀐다.
- `processed_message` 확인을 "SELECT로 존재 확인 후 INSERT"로 하지 않는다. 같은 메시지를 컨슈머 2개가 동시에 받으면 둘 다 SELECT에서 없음을 보고 처리한다. PK 제약 위반으로 판단한다.
- 컨슈머 안에서 Kafka 발행이 필요하면(M8-4) `KafkaTemplate`을 직접 쓰지 않고 같은 트랜잭션의 outbox INSERT로 한다.

## 힌트
<details>
<summary>힌트 1: 릴레이 2개가 같은 행을 가져가지 않는지 확인하는 방법</summary>

MySQL 세션 2개를 열고 첫 세션에서 `START TRANSACTION; SELECT ... LIMIT 5 FOR UPDATE SKIP LOCKED;`를 실행한 채로 둔 다음, 두 번째 세션에서 같은 쿼리를 실행해 어떤 행이 나오는지 본다. 순서 열에 인덱스가 없으면 결과가 어떻게 달라지는지 `performance_schema.data_locks`로 함께 확인한다(M5-9).
</details>

## 완료 기준
- [ ] `./gradlew test`에서 이 미션의 테스트 10개 이상이 통과한다
- [ ] M8-2의 `outbox` 전략 행이 `docs/dual-write-report.md` 표에 추가되어 있고 유실 0, 유령 0이다
- [ ] `docs/outbox-design.md`에 테이블 정의, ack-mode 선택 이유, 릴레이 2개 순서 역전 시간 순서 표, CDC 비교표(기준 4개)가 있다
- [ ] 요구사항 3의 10,000행 발행 시간(초)이 문서에 기록되어 있고 10초 이하다
- [ ] PR 본문에 테스트 시나리오 표를 붙이고 리뷰를 먼저 받았다

## 생각해볼 질문
1. 폴링 간격을 500ms에서 50ms로 줄이면 발행 지연과 MySQL 부하는 각각 어떻게 바뀌는가? 미발행 행이 0개일 때도 실행되는 쿼리가 1초에 몇 번인지 계산해 본다.
2. `processed_message` 행은 영원히 쌓인다. 며칠이 지난 행을 지워도 안전한지는 무엇으로 정해지는가? (힌트: 릴레이 재발행이 일어날 수 있는 최대 시간, Kafka 토픽 보존 기간)
3. M8-4에서 trading이 보낸 "홀드 요청" 명령과 그 뒤의 "홀드 해제" 명령이 corebank에 역순으로 도착하면 어떤 일이 생기는가? 요구사항 8의 시나리오와 연결한다.
