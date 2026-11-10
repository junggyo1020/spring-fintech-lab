# M8-4 Saga

> 가이드 수준: L3 · 예상 시간: 9~11h · 선행: M8-3

## 목표
이 미션을 끝내면 다음을 할 수 있다.
- 지정가 매수 주문이 trading(주문·매칭)과 corebank(대금 홀드)를 거쳐 끝나는 흐름을 오케스트레이션 Saga 상태 머신(상태 8개, 전이표 12줄)으로 구현한다
- 단계별 실패(홀드 거절, 홀드 응답 타임아웃, 매칭 엔진 제출 실패, 사용자 취소, 확정 실패, 메시지 중복, 메시지 역순)를 주입하는 테스트 12개 이상을 통과시킨다
- 모든 테스트가 끝날 때 "홀드 누수 0원, 생성된 돈 0원" 불변식 5개를 검사하는 공통 검증 메서드를 만든다
- 오케스트레이션과 코레오그래피를 기준 6개로 비교한 표를 쓰고, 이 미션의 선택 근거를 적는다

## 배경
Phase 7에서는 trading 안에서 예수금 홀드와 주문이 한 DB 트랜잭션이었다. 서비스가 나뉘면 "주문 생성"과 "대금 홀드"가 서로 다른 DB에 있어 한 트랜잭션으로 묶을 수 없다. 홀드는 걸렸는데 주문이 실패하고 홀드를 풀지 않으면 고객의 주문가능금액이 영원히 묶인다(홀드 누수). 반대로 홀드 없이 체결되면 없는 돈으로 주식을 산 것이 된다. Saga는 각 단계를 로컬 트랜잭션으로 나누고 실패 시 보상으로 되돌린다(README 5절). M8-3의 outbox와 멱등 컨슈머가 이 미션의 모든 명령·응답을 나른다.

### 이 Phase의 규칙: 매수 대금은 corebank 계좌에서 홀드한다
은행 연계 증권계좌를 단순화한 모델로, Phase 7에서 trading 안에 있던 매수 예수금 홀드를 corebank 계좌 홀드로 옮긴다. 매도 수량 홀드는 trading에 그대로 둔다. corebank 계좌는 아래 세 금액을 가진다.

| 필드 | 뜻 |
|---|---|
| `balance` | 계좌 잔액. Saga 중에는 바뀌지 않는다 |
| `held_amount` | 미체결 매수 주문 때문에 묶인 금액 |
| `pending_settlement_amount` | 체결됐지만 T+2 결제일 전이라 출금 예정인 금액 |

주문·출금 가능 금액 = `balance` − `held_amount` − `pending_settlement_amount`. 결제일에 `pending_settlement_amount`를 실제 출금(분개)하는 처리는 M7-6의 결제 예정 내역을 쓰며 이 미션 범위 밖이다.

홀드 금액(이 미션의 규칙) = 주문가격 × 수량 + 수수료. 수수료 = 금액 × 0.015%, 원 미만 절사. 매수에는 증권거래세가 없다(fintech-domain-facts 2절, 확인일 2026-11-10).

| 사건 | 계산 | corebank 변화 |
|---|---|---|
| 지정가 71,000원 × 10주 매수 주문 | 710,000 + floor(106.5) = 710,106 | `held_amount` +710,106 |
| 70,900원 × 4주 체결 | 283,600 + floor(42.54) = 283,642 | `held_amount` −283,642, `pending_settlement_amount` +283,642 |
| 71,000원 × 6주 체결 (전량 체결) | 426,000 + floor(63.9) = 426,063 | `held_amount` −426,063, `pending_settlement_amount` +426,063 |
| 남은 홀드 해제 | 710,106 − 283,642 − 426,063 = 401 | `held_amount` −401 → 이 주문의 홀드 0 |
| (다른 경우) 4주 체결 후 잔량 취소 | 710,106 − 283,642 = 426,464 | `held_amount` −426,464 |

체결가 70,900원은 50,000원 이상 200,000원 미만 구간의 호가단위 100원을 지킨다(fintech-domain-facts 3절). 지정가 매수는 지정가 이하에서만 체결되므로 확정 금액 합계는 홀드 금액을 넘지 않는다.

## 요구사항
1. **범위**: 지정가 매수 주문만 Saga로 처리한다. 시장가 주문과 매도 주문은 이 미션에서 다루지 않는다.
2. **메시지와 토픽** (모두 M8-3 outbox로 발행, 멱등 컨슈머로 소비):

   | 토픽 | 방향 | 메시지 | 키 |
   |---|---|---|---|
   | `trading.cash.commands` | trading → corebank | `HoldCash(sagaId, accountNumber, amount)`, `CaptureHold(sagaId, executionId, amount)`, `ReleaseHold(sagaId)` | 계좌번호 |
   | `corebank.cash.replies` | corebank → trading | `CashHeld`, `CashHoldRejected(reason)`, `HoldCaptured(executionId)`, `HoldCaptureFailed(executionId, reason)`, `HoldReleased(releasedAmount)` | sagaId |

3. **corebank 홀드 처리**:
   - `HoldCash`: 가능 금액 ≥ amount면 홀드를 만들고 `CashHeld`, 아니면 `CashHoldRejected(INSUFFICIENT_FUNDS)`. 같은 계좌에 동시에 온 홀드 2개가 가능 금액을 넘게 승인되지 않는다(Phase 5·6의 락 전략 중 하나 사용)
   - `CaptureHold`: 해당 Saga 홀드의 남은 금액에서 amount를 빼 `pending_settlement_amount`로 옮긴다. 같은 `executionId`는 한 번만 반영된다. 남은 금액보다 크면 반영하지 않고 `HoldCaptureFailed(EXCEEDS_HOLD)`
   - `ReleaseHold`: 남은 금액 전부를 해제하고 `HoldReleased(해제 금액)`. 남은 금액이 0이면 `HoldReleased(0)`
   - `ReleaseHold`가 `HoldCash`보다 먼저 도착하면 그 sagaId를 "종료됨"으로 기록하고 `HoldReleased(0)`을 보낸다. 이후 같은 sagaId의 `HoldCash`는 `CashHoldRejected(SAGA_CLOSED)`로 거절한다
4. **trading 오케스트레이터 `BuyOrderSaga`**: `saga_instance` 테이블에 상태를 저장한다. 필수 열은 `saga_id`, `order_id`, `state`, `hold_amount`, `captured_amount`, `pending_capture_count`, `deadline_at`, `retry_count`, `version`(낙관적 락)이다. 상태 전이는 아래 표만 허용하고, 표에 없는 (상태, 이벤트) 조합은 상태를 바꾸지 않고 WARN 로그를 남긴다.

   | 현재 상태 | 이벤트 | 다음 상태 | 동작 |
   |---|---|---|---|
   | (없음) | 매수 주문 접수 | `HOLD_REQUESTED` | 주문 `PENDING` 저장(Phase 7 `OrderStatus`에 홀드 확정 전 상태 `PENDING`을 이 미션에서 추가한다) + `HoldCash` outbox, `deadline_at` = 지금 + 10초 (한 트랜잭션) |
   | `HOLD_REQUESTED` | `CashHeld` | `OPEN` | 주문을 매칭 엔진에 제출 |
   | `HOLD_REQUESTED` | `CashHoldRejected` | `REJECTED` | 주문 `REJECTED`(사유 저장) |
   | `HOLD_REQUESTED` | `deadline_at` 경과 | `COMPENSATING` | `ReleaseHold` |
   | `OPEN` | 매칭 엔진 제출 실패 | `COMPENSATING` | `ReleaseHold`, 주문 `REJECTED` |
   | `OPEN` | 체결 | `OPEN` | `CaptureHold`, `pending_capture_count` +1 |
   | `OPEN` | 전량 체결 또는 잔량 취소 확정 | `CLOSING` | (체결분 `CaptureHold` 후) `ReleaseHold` |
   | `OPEN`, `CLOSING` | `HoldCaptured` | 그대로 | `pending_capture_count` −1, `captured_amount` 누적 |
   | `OPEN`, `CLOSING` | `HoldCaptureFailed` | 그대로 | 1, 2, 4, 8, 16초 간격으로 `CaptureHold` 재발행, 5회 실패 시 `STUCK` |
   | `CLOSING` | `HoldReleased` 수신 + `pending_capture_count` = 0 | `COMPLETED` | 주문 상태 확정 |
   | `COMPENSATING` | `HoldReleased` | `COMPENSATED` | 주문 `CANCELLED`(Phase 7 `OrderStatus` 이름, 사유 `HOLD_TIMEOUT`) 또는 `REJECTED` 유지 |
   | `COMPENSATING` | `CashHeld` (늦게 도착) | `COMPENSATING` | 매칭 엔진에 제출하지 않는다 |

   종료 상태는 `COMPLETED`, `COMPENSATED`, `REJECTED`, `STUCK`이다. `STUCK`은 사람이 확인해야 하는 상태로, ERROR 로그와 M8-5 메트릭 `saga_stuck`으로 드러낸다. 체결은 되돌릴 수 없는 피벗 단계이므로 `CaptureHold` 실패에는 보상이 아니라 재시도로 대응한다.
5. **타임아웃 감시**: 1초마다 `deadline_at`이 지난 `HOLD_REQUESTED` Saga를 찾아 전이시킨다. 시각은 `Clock` 빈으로 주입해 테스트에서 앞당긴다.
6. **불변식** (테스트마다 끝에서 공통 메서드로 검사):
   - I1 계좌별 `held_amount` = 그 계좌의 종료되지 않은 홀드 남은 금액 합계
   - I2 종료 상태(`COMPLETED`, `COMPENSATED`, `REJECTED`)인 Saga의 corebank 홀드 남은 금액 = 0원
   - I3 Saga 실행 전후 모든 계좌의 `balance` 합계가 같다 (Saga는 돈을 만들거나 없애지 않는다)
   - I4 Saga별 `captured_amount` = 그 주문 체결들의 (체결금액 + 수수료) 합계 = corebank에서 그 Saga로 `pending_settlement_amount`에 옮겨진 금액
   - I5 trading 보유수량 증가분 = 그 주문의 체결 수량 합계
7. **설계 문서** `docs/saga-design.md`: 상태 전이 다이어그램(Mermaid `stateDiagram-v2`), 위 전이표, 오케스트레이션 vs 코레오그래피 비교표(기준: 흐름을 한곳에서 볼 수 있는가, 서비스 간 결합, 새 단계 추가 시 수정할 서비스 수, 순환 의존 위험, 실패 추적 방법, 테스트 방법), 이 미션의 선택 근거 3줄 이상.

## 직접 작성할 테스트 시나리오

trading·corebank를 한 테스트에서 모두 띄우기 어렵다면 corebank 쪽 명령 처리기 테스트와 trading 쪽 Saga 테스트를 나누고, 메시지는 실제 Kafka(Testcontainers)를 거치게 한다. 최소 2개는 두 서비스와 Kafka를 모두 띄운 종단 테스트로 작성한다. 모든 테스트 끝에서 요구사항 6의 불변식 5개를 검사한다.

반드시 포함할 경우 (최소 12개):
- 정상: 71,000원 × 10주, 4주(70,900원) + 6주(71,000원) 체결 → `COMPLETED`, `captured_amount` 709,705, 해제 401, 홀드 0 (종단 테스트)
- 4주 체결 후 잔량 취소 → `COMPLETED`, 해제 426,464
- 가능 금액 289,894원 계좌에서 710,106원 홀드 요청 → `REJECTED`, 주문 `REJECTED`, 홀드 0
- 가능 금액 1,000,000원 계좌에서 710,106원 주문 2건 동시 접수 → 정확히 1건 `OPEN`, 1건 `REJECTED`
- corebank 컨슈머를 멈춘 상태에서 주문 → 10초 후 `COMPENSATING` → 컨슈머 재개 → `COMPENSATED`, 홀드 0 (종단 테스트)
- `COMPENSATING` 상태에서 늦은 `CashHeld` 도착 → 매칭 엔진 제출 0회
- `ReleaseHold`가 `HoldCash`보다 먼저 corebank에 도착 → 이후 `HoldCash` 거절(`SAGA_CLOSED`), 홀드 0
- 매칭 엔진 제출 실패 주입 → `COMPENSATED`, 주문 `REJECTED`
- `HoldCaptureFailed` 2회 후 성공 → `COMPLETED`, `retry_count` 2
- `HoldCaptureFailed` 5회 → `STUCK`, `saga_stuck` 1
- 모든 응답 메시지를 2번씩 전달 → 상태와 금액이 1번 전달과 같음
- 같은 `executionId`의 `CaptureHold` 2번 → `pending_settlement_amount` 1번만 증가
- 표에 없는 조합(`COMPLETED` 상태에서 `CashHeld`) → 상태 불변, WARN 로그 1줄

## 제약
- Saga 상태 변경과 다음 명령의 outbox INSERT는 같은 로컬 트랜잭션에서 한다. 상태만 바뀌고 명령이 안 나가거나, 명령만 나가고 상태가 안 바뀌는 구간을 만들지 않는다.
- trading이 corebank를 HTTP로 동기 호출하지 않는다. 이 미션의 목적은 메시지 기반 Saga의 중간 상태와 보상을 다루는 것이다.
- 금액은 Phase 1부터 쓴 `Money`(`BigDecimal`)로 다룬다. 메시지에는 문자열로 싣는다.
- 2PC(XA)와 Seata 같은 분산 트랜잭션 프레임워크를 쓰지 않는다.
- Saga 프레임워크(Axon, Eventuate Tram 등)를 쓰지 않는다. 상태 머신을 직접 만들어야 전이표와 코드가 1:1인지 리뷰할 수 있다.

## 힌트
<details>
<summary>힌트 1: 두 서비스를 한 테스트에서 띄우기</summary>

`SpringApplicationBuilder`로 corebank·trading 애플리케이션 컨텍스트를 같은 JVM에서 각각 다른 포트·다른 프로퍼티로 시작할 수 있다. 두 컨텍스트가 같은 Testcontainers MySQL의 서로 다른 스키마와 같은 Kafka를 바라보게 한다. 멀티 모듈에서 테스트 전용 모듈(예: `e2e-test`)이 두 모듈을 `testImplementation`으로 의존하게 하면 corebank·trading 본 모듈은 서로를 모른 채로 남는다.
</details>

## 완료 기준
- [ ] `./gradlew test`에서 이 미션의 테스트 12개 이상이 통과하고, 그중 2개 이상이 두 서비스와 Kafka를 모두 띄운 종단 테스트다
- [ ] 모든 Saga 테스트가 불변식 I1~I5 공통 검사 메서드를 호출한다 (`grep`으로 호출 횟수 = 테스트 수 확인)
- [ ] `docs/saga-design.md`에 Mermaid 상태 다이어그램, 전이표, 비교표(기준 6개), 선택 근거가 있다
- [ ] Compose 환경에서 매수 주문 API를 curl로 호출 → 5초 안에 그 주문의 `saga_instance.state`가 `OPEN`이 되고(반대 매도 주문이 없을 때), corebank 계좌 조회의 `held_amount`가 홀드 금액과 같다
- [ ] `workspace/docs/test-scenarios/M8-4.md`에 테스트 시나리오 표를 쓰고(PR 생성 스크립트가 PR 본문에 첨부한다) 리뷰를 먼저 받았다

## 생각해볼 질문
1. 이 미션의 Saga는 격리성(Isolation)이 없다. 홀드가 걸린 뒤 체결 전까지 고객이 계좌 화면에서 보는 "출금 가능 금액"은 얼마인가? 이 중간 상태가 고객에게 보이는 것이 문제가 되는 업무를 하나 들고, 시맨틱 락(semantic lock) 대응책을 조사해 적는다.
2. 코레오그래피로 바꾸면 위 전이표의 "타임아웃 감시"는 어느 서비스가 맡아야 하는가? 맡을 곳이 애매해지는 이유를 설명한다.
3. `STUCK` Saga가 하루에 3건 생긴다면 운영자는 무엇을 보고 어떻게 처리하는가? M6-6의 대사 작업을 corebank 홀드와 trading Saga 사이에 적용한다면 무엇과 무엇을 비교하겠는가?
