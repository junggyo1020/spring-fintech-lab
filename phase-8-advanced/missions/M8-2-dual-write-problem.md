# M8-2 이중 쓰기 문제 재현

> 가이드 수준: L3 · 예상 시간: 5~7h · 선행: M8-1

## 목표
이 미션을 끝내면 다음을 할 수 있다.
- DB 커밋 후 Kafka 발행이 실패해 이벤트가 유실되는 경우를 Testcontainers 테스트로 재현하고, 유실 건수를 단언한다
- Kafka 발행 후 DB가 롤백되어 유령 이벤트가 남는 경우를 테스트로 재현하고, 유령 건수를 단언한다
- `@TransactionalEventListener(phase = AFTER_COMMIT)`가 유실을 막지 못하는 것을 같은 실험으로 보여준다
- 발행 전략 3개의 실험 결과(DB 커밋 건수, 토픽 메시지 건수, 유실, 유령)를 한 표로 기록하고 이론값과 다른 칸의 원인을 설명한다

## 배경
corebank가 이체를 끝내면 고객에게 "입금 3,000원" 알림을 보내야 한다. 알림 발송은 별도 컨슈머가 Kafka 토픽을 읽어 처리한다. 이체 기록은 MySQL에, 알림 이벤트는 Kafka에 써야 하는데, 두 시스템을 한 번에 커밋할 방법이 없다(README 1절). 이벤트가 유실되면 고객은 돈이 빠져나간 것을 모르고, 유령 이벤트가 생기면 고객은 받지도 않은 돈의 입금 알림을 받는다. 후자는 고객이 그 알림을 믿고 결제를 하다가 잔액 부족을 겪는 민원으로 이어진다. M8-1에서 Compose로 띄운 Kafka를 처음 쓰는 미션이고, M8-3에서 Outbox로 고칠 문제를 먼저 숫자로 확인한다.

## 요구사항
1. **이벤트**: corebank는 당행이체가 성공하면 `TransferCompleted` 이벤트를 토픽 `corebank.transfer.completed`(파티션 3개)에 발행한다. 필드는 `transferId`(이체 ID), `fromAccount`, `toAccount`, `amount`(문자열, 예: `"3000"`), `occurredAt`(ISO-8601)이다. 메시지 키는 `fromAccount`, 값은 JSON 문자열이다(`StringSerializer`). JSON 변환은 Jackson 3(`tools.jackson.databind`)으로 한다.
2. **발행 전략 3개**를 구현하고 설정 `corebank.event.publish-strategy`로 고른다. 이 값은 M8-3에서 `outbox`가 추가된다.
   - `before-commit`: 이체 트랜잭션 안에서 `KafkaTemplate.send(...)`를 호출하고 결과를 동기로 기다린 다음 커밋한다
   - `after-commit`: 이체 트랜잭션 메서드가 반환된(커밋된) 다음, 트랜잭션 밖의 호출자가 동기로 발행한다
   - `after-commit-listener`: 이체 트랜잭션 안에서 Spring 애플리케이션 이벤트를 발행하고, `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` 리스너가 Kafka로 동기 발행한다
3. **실패 주입 지점**: 테스트 전용 빈으로 "이체 트랜잭션 안, 커밋 직전"에 `RuntimeException`을 던질 수 있게 한다. 운영 코드에 테스트 여부를 묻는 `if`를 두지 않는다. 주입한 예외로 롤백된 이체는 DB에 아무 행도 남기지 않는다(M6-3의 `idempotency_key` 행 포함).
4. **브로커 장애 주입**: Testcontainers `KafkaContainer`를 Docker pause/unpause로 멈추고 재개한다. 멈춘 동안의 발행은 아래 프로듀서 설정에 따라 3초 안에 예외로 끝나야 한다.
   ```yaml
   # src/test/resources/application-dualwrite.yml
   spring:
     kafka:
       producer:
         acks: all
         properties:
           max.block.ms: 2000
           request.timeout.ms: 1000
           delivery.timeout.ms: 3000   # linger.ms + request.timeout.ms 이상이어야 한다
   ```
5. **실험 절차** (전략마다 1회, 같은 절차):
   - 계좌 A, B를 각각 잔액 1,000,000원으로 만든다. A→B 1,000원 이체를 1번부터 100번까지 순서대로 1건씩 실행한다
   - 41번 직전에 브로커를 pause, 70번 직후에 unpause한다
   - 번호가 10의 배수인 이체(10, 20, …, 100)에는 커밋 직전 실패를 주입한다
   - unpause 후 10초 기다린 다음, 별도 `KafkaConsumer`(새 그룹 ID, `auto.offset.reset=earliest`)로 토픽 전체를 5초 동안 새 메시지가 없을 때까지 읽는다
   - 집계: DB에 커밋된 이체 ID 집합 D, 토픽의 `transferId` 집합 K. 유실 = D − K, 유령 = K − D
6. **이론값**: 아래 표는 "브로커가 멈춘 동안 보낸 요청은 하나도 기록되지 않는다"고 가정한 값이다. 실제 결과가 다르면 다른 칸과 원인을 `docs/dual-write-report.md`에 적는다.

   | 전략 | DB 커밋 | 토픽 메시지 | 유실 | 유령 |
   |---|---|---|---|---|
   | `before-commit` | 63 | 70 | 0 | 7 |
   | `after-commit` | 90 | 63 | 27 | 0 |
   | `after-commit-listener` | 90 | 63 | 27 | 0 |

   계산: `before-commit`은 41~70번 30건이 발행 실패로 롤백되고, 남은 70건 중 10의 배수 7건(10, 20, 30, 40, 80, 90, 100)은 발행 후 롤백된다 → DB 100 − 30 − 7 = 63, 토픽 70, 유령 7. `after-commit` 계열은 10의 배수 10건이 발행 전에 롤백되어 DB 90, 41~70번 중 10의 배수가 아닌 27건은 커밋 후 발행 실패 → 토픽 90 − 27 = 63, 유실 27.
7. **관찰 기록**: `after-commit-listener`에서 리스너가 예외를 던졌을 때 HTTP 응답 코드(또는 서비스 메서드 호출자가 받은 결과)와 그 시점의 A 잔액을 기록한다.

## 직접 작성할 테스트 시나리오

`@SpringBootTest` + Testcontainers(MySQL 8.4, `apache/kafka:4.3.2`) 통합 테스트로 작성한다. 테스트 이름에 전략 이름을 넣는다.

반드시 포함할 경우 (최소 6개):
- `before-commit` 전략으로 요구사항 5 실험 → 유령 ≥ 1건, 유실 0건 단언
- `after-commit` 전략으로 요구사항 5 실험 → 유실 ≥ 1건, 유령 0건 단언
- `after-commit-listener` 전략으로 요구사항 5 실험 → 유실 ≥ 1건 단언
- 브로커 정상, 실패 주입 없음, 이체 20건 → 세 전략 모두 D = K (기준선 테스트, `@ParameterizedTest`)
- `before-commit` 전략에서 브로커 pause 중 이체 1건 → 이체가 실패하고 A·B 잔액이 변하지 않음 (Kafka 장애가 이체 가용성을 떨어뜨리는 것을 보여준다)
- 같은 `fromAccount`로 연속 발행한 메시지 10건이 토픽에서 같은 파티션에 순서대로 있음

## 제약
- 브로커 장애는 실제 컨테이너로 만든다. `KafkaTemplate`을 목(mock)으로 바꿔 예외를 던지는 방식은 "보냈는데 실패로 보이는" 경우를 재현하지 못한다.
- `KafkaTemplate.send(...)`가 돌려주는 `CompletableFuture`를 기다리지 않고 넘어가지 않는다. 기다리지 않으면 실패가 로그에만 남고 테스트는 성공으로 보인다. 기다리는 시간 제한은 `delivery.timeout.ms`보다 길게 둔다.
- 이 미션에서는 실패한 발행을 재시도하는 코드를 넣지 않는다. 재시도는 문제를 줄일 뿐 없애지 못한다는 것을 M8-3과 비교하기 위해서다.
- 테스트 하나가 60초를 넘지 않게 한다. 넘으면 프로듀서 타임아웃 설정이 적용됐는지 확인한다.

## 힌트
<details>
<summary>힌트 1: 컨테이너 일시정지 API</summary>

Testcontainers의 `DockerClientFactory.instance().client()`가 돌려주는 docker-java 클라이언트에 `pauseContainerCmd(containerId)`, `unpauseContainerCmd(containerId)`가 있다. `stop()`/`start()`는 매핑 포트가 바뀌어 프로듀서가 재연결하지 못하므로 쓰지 않는다. 선택으로 `org.testcontainers:testcontainers-toxiproxy`를 써 볼 수 있지만, Kafka 클라이언트는 advertised listener 주소로 다시 접속하므로 프록시를 우회하지 않게 설정해야 한다.
</details>

## 완료 기준
- [ ] `./gradlew :corebank:test --tests '*DualWrite*'`에서 이 미션의 테스트 6개 이상이 통과한다
- [ ] `docs/dual-write-report.md`에 전략 3개 × 열 5개(DB 커밋, 토픽 메시지, 유실, 유령, 이론값과의 차이 원인) 표가 있다
- [ ] 같은 문서에 요구사항 7의 관찰 결과(HTTP 상태 또는 반환값, A 잔액)가 있다
- [ ] PR 본문에 위 테스트 시나리오 표를 붙이고 리뷰를 먼저 받았다

## 생각해볼 질문
1. pause된 브로커에 보낸 요청이 TCP 수신 버퍼에 남아 있다가 unpause 후 기록되면, 프로듀서는 실패로 알았는데 메시지는 존재한다. 이 "결과 미확정" 상태는 M6-7 타행이체 타임아웃과 어떤 점이 같은가?
2. Kafka 트랜잭션(`KafkaTransactionManager`)과 DB 트랜잭션을 차례로 커밋하면 두 커밋 사이에 프로세스가 죽었을 때 어떤 불일치가 남는가? 어느 쪽을 먼저 커밋해도 남는 이유를 시간 순서 그림으로 설명한다.
3. 이 미션의 세 전략 중 하나를 고르라면 유실과 유령 중 어느 쪽을 감수하겠는가? M8-3의 Outbox는 이 선택을 어떻게 없애는가?
