# M8-6 부하 테스트와 튜닝 리포트

> 가이드 수준: L3, 예상 시간: 6~8h, 선행: M8-5

## 목표
이 미션을 끝내면 다음을 할 수 있다.
- k6 `constant-arrival-rate` 시나리오로 이체 API에 500 req/s를 5분 동안 걸고, p99, 에러율, `dropped_iterations`로 통과 여부를 k6 thresholds가 판정하게 한다
- 측정 전에 리틀의 법칙으로 필요한 DB 커넥션 수를 계산하고, 측정값과 비교한다
- M8-5 대시보드와 MySQL 상태 조회로 병목 1개 이상을 근거 지표 2개 이상과 함께 지목한다
- 한 번에 한 가지만 바꾼 측정 3회 이상을 고정된 열의 전후 비교표로 남긴다

## 배경
"이체 API는 빠르다"는 말은 검증할 수 없다. 금융사는 월급날 오전, 공모주 청약 마감 직전처럼 평소의 몇 배가 몰리는 시간대의 목표 처리량과 지연 상한을 정하고 출시 전에 부하 테스트로 확인한다. 목표를 못 넘으면 감으로 서버를 늘리는 대신 어느 자원이 먼저 포화되는지를 지표로 찾아야 한다. 이 미션은 M8-5에서 만든 대시보드를 근거 도구로 쓰고, README 7, 8절의 지표와 리틀의 법칙을 실제 숫자에 적용한다.

## 요구사항
1. **목표 (이 미션의 규칙)**: 시나리오 `uniform`에서 500 req/s × 5분 동안 이체 API(`POST` 당행이체, M6-3) p99 < 300ms, HTTP 실패율 < 0.1%, `dropped_iterations` = 0.
2. **테스트 데이터**: 부하 전용 프로파일 `loadtest`로 corebank를 띄운다. 계좌 1,000개, 계좌마다 잔액 100,000,000원. 이체 금액은 1,000원 고정. 1회, 1일 이체 한도(M6-4)는 `loadtest` 프로파일에서 1,000,000,000원으로 올린다. 5분 동안 한 계좌에서 나가는 금액의 기대값은 500 × 300 ÷ 1,000 × 1,000 = 150,000원이므로 잔액 부족 거절이 생기지 않는다. corebank는 Phase 6 규칙대로 인증 대신 `X-Customer-Id` 헤더로 요청자를 식별하고(Phase 6 README 1절), 이체 출금에는 M6-4의 계좌 비밀번호(`password`)가 필수다. 계좌별 고객 ID와 비밀번호를 k6 `setup()`에서 준비한다.
3. **k6 스크립트** `load-test/transfer.js`: 출금, 입금 계좌를 1,000개 중에서 서로 다르게 무작위로 고른다. `Idempotency-Key`는 `${RUN_ID}-${__VU}-${__ITER}`로 만들어 실행마다 겹치지 않게 한다(`RUN_ID`는 `-e`로 전달). 응답 상태가 200(또는 M6-3에서 정한 성공 코드)이 아니면 k6 `check` 실패로 센다. 시나리오와 thresholds는 아래 설정을 쓴다.
   ```javascript
   export const options = {
     scenarios: {
       warmup:  { executor: 'constant-arrival-rate', rate: 100, timeUnit: '1s', duration: '1m',
                  preAllocatedVUs: 50,  maxVUs: 200 },
       uniform: { executor: 'constant-arrival-rate', rate: 500, timeUnit: '1s', duration: '5m',
                  preAllocatedVUs: 200, maxVUs: 1000, startTime: '1m' },
     },
     thresholds: {
       'http_req_duration{scenario:uniform}': ['p(99)<300'],
       'http_req_failed{scenario:uniform}':   ['rate<0.001'],
       'dropped_iterations{scenario:uniform}': ['count==0'],
     },
   };
   ```
4. **핫 계좌 시나리오** `load-test/transfer-hot.js`: 200 req/s × 3분, 입금 계좌는 항상 1번 계좌, 출금 계좌는 나머지 999개 중 무작위. 통과 기준은 없고, `uniform`과 지표를 비교하는 데 쓴다(락 경합 관찰용).
5. **실행 환경 기록**: 리포트 맨 위에 JDK 버전(`java -version`), CPU 모델, 코어 수, RAM, OS, Docker Desktop에 할당한 CPU, 메모리, 컨테이너 `mem_limit`, k6 버전(`k6 version`), k6 실행 위치(호스트 또는 컨테이너), Prometheus, Grafana, Jaeger를 함께 띄웠는지 여부를 적는다. k6와 서버가 같은 머신이면 k6가 쓰는 CPU도 기록한다.
6. **측정 규칙 (이 미션의 규칙)**: 설정 1개당 `warmup` 1분 + `uniform` 5분을 3회 실행하고, 지표마다 3회의 중앙값을 기록한다. 실행 사이에 `docker compose restart corebank`를 하지 않는다면 그 사실을 적는다. 1회가 6분이라 템플릿 기본값(워밍업 3회 + 측정 5회)을 따르면 설정 1개에 48분이 걸리므로 횟수를 줄였다.
7. **사전 계산**: 측정 전에 리포트에 리틀의 법칙 계산을 적는다. 기준선 측정 1회에서 이체 1건이 커넥션을 점유하는 평균 시간(`hikaricp_connections_usage_seconds`의 `_sum / _count`)을 읽고, 500 req/s에 필요한 커넥션 수 = 500 × 평균 점유 시간(초)을 계산해 현재 `maximum-pool-size`와 비교한다. 같은 방식으로 CPU도 계산한다. 이체마다 M6-4의 `BCryptPasswordEncoder`(기본 strength 10) 비밀번호 검증이 1회 실행된다. 검증 1회 시간을 먼저 재고 500 × 검증 시간(초) = 필요한 CPU 코어 수를 Docker에 할당한 코어 수와 비교한다. 참고값: Apple M3 Pro, JDK 21에서 strength 10 `matches()` 1회 평균 60ms → 500 × 0.06 = 30코어(2026-11-10 측정).
8. **병목 근거**: 병목을 지목할 때 아래 표의 근거 중 2개 이상을 수치로 적는다. 임계값은 이 미션의 판정 기준이다.

   | 의심 병목 | 근거 1 (Grafana 패널, M8-5) | 근거 2 (다른 출처) | 판정 기준 |
   |---|---|---|---|
   | 커넥션 풀 | 패널 8 `hikaricp_connections_pending` | 패널 7 획득 평균 대기 | pending > 0이 30초 이상 지속, 획득 대기 > 10ms |
   | DB 행 락 | 패널 6 락 대기 p99 | `SHOW GLOBAL STATUS LIKE 'Innodb_row_lock%'`의 실행 전후 `Innodb_row_lock_waits`, `Innodb_row_lock_time` 차이 | 락 대기 p99 > 이체 p99의 30% |
   | GC | 패널 9 GC 일시정지 시간 비율 | `jvm_gc_pause_seconds_max` | 비율 > 0.05 (1초당 50ms) 또는 최대 일시정지 > 200ms |
   | CPU | 패널 10 `process_cpu_usage` | `docker stats` CPU % | 0.8 이상이 1분 이상 지속 |
   | outbox 적체 | 패널 11 `outbox_pending` | 발행 지연 p99 | 측정 5분 동안 단조 증가 |
   | 부하 발생기 | k6 `dropped_iterations` | k6 `vus` 최대값 = `maxVUs` | `dropped_iterations` > 0이면 그 실행은 무효 |

9. **한 번에 한 가지 변경**: 기준선 이후 측정마다 변경을 정확히 1개만 한다. 아래 후보 중에서 근거 지표가 가리키는 것부터 고른다. 후보: HikariCP `maximum-pool-size`, 이체 락 방식(M5-8의 3종 중 다른 방식), 인덱스 추가, `spring.threads.virtual.enabled`, outbox 릴레이 배치 크기, 트레이싱 샘플링 비율 1.0 → 0.1, 컨테이너 `mem_limit`, `loadtest` 프로파일의 BCrypt strength(이 값을 바꾸면 운영 설정과 다르다는 것을 리포트 표의 "변경" 칸에 적는다). 샘플링 비율 변경 1행은 반드시 포함한다(M8-5 제약).
10. **리포트** `docs/load-test-report.md`의 비교표는 아래 열을 이 순서로 쓴다.

    | # | 변경 1가지 | 가설 | 근거 지표(변경 전 값) | 처리량(req/s) | p50(ms) | p95(ms) | p99(ms) | k6 p99와 PromQL p99 차이(ms) | 실패율(%) | dropped_iterations | pending 최대 | 락 대기 p99(ms) | GC 비율 | 결론 |
    |---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|

    1행은 "기준선(변경 없음)"이다. "결론"에는 가설이 맞았는지와 다음 변경을 무엇으로 할지 적는다. 표 아래에 `uniform`과 핫 계좌 시나리오의 지표 비교(처리량, p99, 락 대기 p99, `Innodb_row_lock_waits` 차이)를 별도 표로 둔다.
11. **목표 미달 시**: 측정 3회 이상 후에도 요구사항 1을 만족하지 못하면, 마지막 측정의 포화 지표 값과 남은 변경 후보를 적고 마친다. 목표를 낮추지 않는다.

실행 명령:
```bash
brew install k6                         # macOS. 또는 컨테이너: docker run --rm -i grafana/k6:2.3.0 run -e BASE_URL=http://host.docker.internal:8081 -e RUN_ID=$(date +%s) - < load-test/transfer.js
                                        # (컨테이너 안의 localhost는 k6 컨테이너 자신이다. host.docker.internal은 Docker Desktop 기준)
k6 version                              # 2026-11-10 기준 최신 v2.3.0
k6 run -e BASE_URL=http://localhost:8081 -e RUN_ID=$(date +%s) \
       --summary-trend-stats="med,p(95),p(99),max" load-test/transfer.js
docker compose exec mysql mysql -uroot -prootpw -e "SHOW GLOBAL STATUS LIKE 'Innodb_row_lock%'"
docker stats --no-stream
```
k6 v2.0.0부터 `legacy` 요약 모드와 `--no-summary` 플래그가 없어졌다. 요약을 파일로 남기려면 k6 문서 "Custom summary"의 `handleSummary`를 쓴다.

## 직접 작성할 테스트 시나리오

이 미션의 테스트는 부하 실행 자체와 리포트 검증이다. 각 실행은 리포트의 비교표 1행이 된다.

반드시 포함할 경우 (최소 6개):
- 기준선: 변경 없이 `uniform` 3회, 중앙값 기록
- 샘플링 비율 1.0 → 0.1 변경 1행
- 근거 지표가 가리킨 병목에 대한 변경 1행 이상 (가설과 근거 지표 값 포함)
- 핫 계좌 시나리오 1회, `uniform`과의 비교표
- `dropped_iterations` > 0이 나온 실행이 있었다면 그 실행을 무효로 표시하고 `maxVUs`를 조정해 다시 실행한 기록 (없었다면 `vus` 최대값을 적어 근거로 남긴다)
- 부하 종료 직후 corebank 원장 검증: 모든 계좌 잔액 합계 = 1,000 × 100,000,000원 = 100,000,000,000원, 차변 합계 = 대변 합계 (M6-6 대사 Job 실행 결과 첨부)

## 제약
- 같은 측정에서 두 가지 이상을 바꾸지 않는다. 두 개를 바꾸면 어느 쪽이 효과를 냈는지 알 수 없다.
- closed model(`constant-vus`, `ramping-vus`)로 목표를 판정하지 않는다. 서버가 느려지면 요청 수도 줄어 p99가 낮게 나온다(README 7절).
- 평균(`avg`)으로 결론을 내리지 않는다. 비교는 p50, p95, p99로 한다.
- 스크린샷 없이 숫자만 적지 않는다. 기준선과 마지막 측정의 Grafana 패널 5, 6, 8 스크린샷을 `docs/load-test/`에 둔다.
- 부하 테스트 중 재시작이나 OOM이 있었다면 그 실행은 무효로 표시하고 원인을 적는다.

## 힌트
없음. README 8절의 계산 예시와 요구사항 8의 판정표로 가설을 세운다.

## 완료 기준
- [ ] `load-test/transfer.js`, `load-test/transfer-hot.js`가 레포에 있고, `k6 run`의 thresholds 판정 결과(`✓`/`✗`)가 리포트에 붙어 있다
- [ ] `docs/load-test-report.md` 맨 위에 요구사항 5의 실행 환경 항목이 모두 있다
- [ ] 비교표에 기준선 포함 4행 이상(변경 3회 이상)이 요구사항 10의 열 순서대로 있고, 각 행이 3회 중앙값이다
- [ ] 병목 1개 이상에 대해 요구사항 8의 근거 2개 이상이 수치로 적혀 있다
- [ ] 리틀의 법칙 사전 계산과 실제 측정값(커넥션 점유 시간, pending 최대) 비교가 있다
- [ ] 부하 후 원장 검증 결과가 "잔액 합계 100,000,000,000원, 차변 = 대변"이다
- [ ] 마지막 행이 요구사항 1을 만족하거나, 요구사항 11에 따라 미달 이유가 포화 지표 값으로 적혀 있다

## 생각해볼 질문
1. 커넥션 풀을 10에서 50으로 늘렸더니 p99가 오히려 나빠졌다면, MySQL 쪽에서 무슨 일이 일어났을 가능성이 있는가? HikariCP 위키 "About Pool Sizing"의 공식(코어 수 × 2 + 유효 스핀들 수)과 비교한다.
2. 핫 계좌 시나리오에서 락 대기를 줄이는 방법 3가지(예: 입금 기록을 먼저 쌓고 잔액은 나중에 합산, 계좌 샤딩, 큐로 직렬화)를 정합성 관점에서 비교한다. Phase 7의 M7-4 단일 스레드 이벤트 루프는 어느 쪽에 가까운가?
3. 이 미션의 결과는 노트북 1대에서 측정한 값이다. 운영 서버 용량을 정할 때 이 숫자를 그대로 쓸 수 없는 이유 2가지를 적는다.
