# M8-5 관측성

> 가이드 수준: L3 · 예상 시간: 6~8h · 선행: M8-1

## 목표
이 미션을 끝내면 다음을 할 수 있다.
- 이체 결과별 건수, 이체 지연 히스토그램, 락 대기 시간, outbox 적체, Saga 정체를 Micrometer 커스텀 메트릭으로 만들고 `/actuator/prometheus` 출력에서 이름과 태그를 보여준다
- `docker compose up -d`만으로 Prometheus가 두 서비스를 수집하고, Grafana에 패널 12개짜리 대시보드가 자동으로 올라오게 한다
- trading HTTP 요청 → Kafka → corebank 컨슈머 → Kafka → trading 컨슈머가 한 트레이스로 이어진 화면을 Jaeger에서 보여준다
- 로그 한 줄의 `traceId`로 Jaeger 트레이스를 찾고, 그 시각의 Grafana 패널 값을 함께 기록한다

## 배경
M8-4까지 오면 이체 한 건이 HTTP, MySQL, Kafka, 다른 서비스의 컨슈머를 거친다. "어제 14시에 이체가 느렸다"는 민원이 오면 로그만으로는 어느 구간이 느렸는지 알 수 없다. 금융 서비스 장애 보고서는 "몇 시 몇 분부터 몇 분 동안, 몇 %의 요청이, 어떤 원인으로" 실패했는지를 숫자로 요구한다. 이 미션은 README 6절의 세 기둥(메트릭, 로그, 트레이스)을 붙이고 `traceId`로 연결한다. 여기서 만든 대시보드가 M8-6 부하 테스트에서 병목의 근거가 된다.

## 요구사항
1. **노출**: 두 서비스에 `io.micrometer:micrometer-registry-prometheus`를 추가하고 `management.endpoints.web.exposure.include=health,info,prometheus`로 `/actuator/prometheus`를 노출한다. `management.metrics.distribution.percentiles-histogram.http.server.requests=true`로 HTTP 지연 히스토그램 버킷을 내보낸다.
2. **이체 메트릭 (corebank)**: 아래 이름·타입·태그를 지킨다. Prometheus 이름은 Micrometer가 점(`.`)을 밑줄로 바꾸고 단위 접미사를 붙인 결과다.

   | Micrometer 이름 | 타입 | 태그 | Prometheus에서 보이는 이름 |
   |---|---|---|---|
   | `transfer.requests` | Counter | `result` = `success`, `insufficient_funds`, `limit_exceeded`, `duplicate`, `error` | `transfer_requests_total` |
   | `transfer.latency` | Timer (percentiles histogram 켬) | `result` | `transfer_latency_seconds_bucket`, `_count`, `_sum` |
   | `transfer.lock.wait` | Timer (percentiles histogram 켬) | 없음 | `transfer_lock_wait_seconds_bucket` |

   `transfer.lock.wait`는 이체 트랜잭션에서 계좌 행 락을 얻는 쿼리(M6-3 "한 트랜잭션 규칙" 2번에서 고른 방식: `SELECT ... FOR UPDATE` 등)의 실행 시간만 잰다. `error`는 업무 규칙 거절이 아닌 예상하지 못한 예외(DB 연결 실패 등)다.
3. **비동기 메트릭 (두 서비스)**:

   | Micrometer 이름 | 타입 | 뜻 |
   |---|---|---|
   | `outbox.pending` | Gauge | `published_at IS NULL`인 outbox 행 수 (10초마다 조회한 값) |
   | `outbox.stuck` | Gauge | `attempt_count` ≥ 10인 미발행 행 수 |
   | `outbox.publish.lag` | Timer (histogram) | 발행 성공 시점 − `created_at` |
   | `saga.active` (trading) | Gauge, 태그 `state` | 종료되지 않은 Saga 수 |
   | `saga.stuck` (trading) | Gauge | `STUCK` 상태 Saga 수 |

4. **태그 카디널리티**: 계좌번호, 주문 ID, sagaId, traceId를 메트릭 태그로 쓰지 않는다. 태그 값 조합 1개마다 Prometheus 시계열이 1개 생기므로 계좌 10,000개면 시계열이 10,000배가 된다.
5. **관측 스택**: `compose.yaml`에 아래 3개 서비스를 추가한다(태그는 2026-11-10 확인).
   ```yaml
     prometheus:
       image: prom/prometheus:v3.16.0
       ports: ["9090:9090"]
       volumes:
         - ./docker/prometheus/prometheus.yml:/etc/prometheus/prometheus.yml:ro

     grafana:
       image: grafana/grafana:12.4.14
       ports: ["3000:3000"]
       environment:
         GF_SECURITY_ADMIN_PASSWORD: admin
       volumes:
         - ./docker/grafana/provisioning:/etc/grafana/provisioning:ro
         - ./docker/grafana/dashboards:/var/lib/grafana/dashboards:ro

     jaeger:
       image: cr.jaegertracing.io/jaegertracing/jaeger:2.23.0
       ports: ["16686:16686", "4318:4318"]   # UI, OTLP HTTP
   ```
   `docker/prometheus/prometheus.yml`:
   ```yaml
   global:
     scrape_interval: 5s
   scrape_configs:
     - job_name: corebank
       metrics_path: /actuator/prometheus
       static_configs: [{ targets: ["corebank:8081"] }]
     - job_name: trading
       metrics_path: /actuator/prometheus
       static_configs: [{ targets: ["trading:8082"] }]
   ```
   Grafana 데이터소스(Prometheus `http://prometheus:9090`, Jaeger `http://jaeger:16686`)와 대시보드 프로바이더는 `docker/grafana/provisioning/datasources/`, `docker/grafana/provisioning/dashboards/`의 YAML로 직접 작성한다(Grafana 문서 "Provision Grafana").
6. **대시보드**: `docker/grafana/dashboards/fintech.json` 하나에 아래 12개 패널을 만든다. 패널 제목 앞에 골든 시그널 분류를 붙인다(예: `[지연] 이체 p99`). 시간 범위 기본값은 최근 15분.

   | # | 분류 | 패널 | PromQL |
   |---|---|---|---|
   | 1 | 트래픽 | 결과별 이체 TPS | `sum by (result) (rate(transfer_requests_total[1m]))` |
   | 2 | 트래픽 | 서비스별 HTTP 요청률 | `sum by (job) (rate(http_server_requests_seconds_count[1m]))` |
   | 3 | 에러 | 이체 오류율 | `sum(rate(transfer_requests_total{result="error"}[1m])) / sum(rate(transfer_requests_total[1m]))` |
   | 4 | 에러 | 서비스별 HTTP 5xx 비율 | `sum by (job) (rate(http_server_requests_seconds_count{status=~"5.."}[1m])) / sum by (job) (rate(http_server_requests_seconds_count[1m]))` |
   | 5 | 지연 | 이체 p50/p95/p99 | `histogram_quantile(0.99, sum by (le) (rate(transfer_latency_seconds_bucket[1m])))` (0.5, 0.95도 같은 패널) |
   | 6 | 지연 | 락 대기 p99 | `histogram_quantile(0.99, sum by (le) (rate(transfer_lock_wait_seconds_bucket[1m])))` |
   | 7 | 지연 | 커넥션 획득 평균 대기 | `rate(hikaricp_connections_acquire_seconds_sum[1m]) / rate(hikaricp_connections_acquire_seconds_count[1m])` |
   | 8 | 포화도 | 커넥션 풀 active / pending / max | `hikaricp_connections_active`, `hikaricp_connections_pending`, `hikaricp_connections_max` |
   | 9 | 포화도 | GC 일시정지 시간 비율, 최대 일시정지 | `sum by (job) (rate(jvm_gc_pause_seconds_sum[1m]))`, `max by (job) (jvm_gc_pause_seconds_max)` |
   | 10 | 포화도 | 프로세스 CPU 사용률 | `process_cpu_usage` |
   | 11 | 비동기 | outbox 미발행 행, 발행 지연 p99 | `outbox_pending`, `histogram_quantile(0.99, sum by (le, job) (rate(outbox_publish_lag_seconds_bucket[1m])))` |
   | 12 | 비동기 | Saga 상태별 수, 정체 | `saga_active`, `saga_stuck` |

   패널 7~10의 메트릭 이름은 HikariCP·Micrometer JVM 바인더가 만드는 이름이다. 직접 `/actuator/prometheus` 출력에서 같은 이름이 있는지 확인하고, 다르면 출력에 있는 이름으로 고친 뒤 차이를 기록한다. Kafka 컨슈머 랙 패널을 13번으로 추가하고 싶다면 출력에서 `kafka_consumer_fetch_manager_records_lag`로 시작하는 이름을 찾아 쓴다.
7. **트레이싱**: 두 서비스에 `org.springframework.boot:spring-boot-starter-opentelemetry`를 추가하고 아래 설정을 쓴다(Spring Boot 4.1 기준 프로퍼티 이름, 3.x의 `management.otlp.tracing.*`와 다르다).
   ```yaml
   management:
     tracing:
       sampling:
         probability: 1.0        # 기본값은 0.1 (10%)
     opentelemetry:
       tracing:
         export:
           otlp:
             endpoint: http://jaeger:4318/v1/traces
   spring:
     kafka:
       template:
         observation-enabled: true   # 기본값 false
       listener:
         observation-enabled: true   # 기본값 false
   ```
8. **outbox를 건너는 트레이스**: outbox 릴레이는 요청 스레드가 아닌 스케줄러 스레드에서 나중에 발행하므로, 그대로 두면 Kafka 메시지가 원래 요청과 다른 새 트레이스로 시작된다. M8-3에서 만든 `trace_parent` 열에 INSERT 시점의 W3C `traceparent`를 저장하고, 릴레이가 그 값을 부모로 삼아 발행하게 한다. 완료 조건: Jaeger에서 trading의 매수 주문 `POST` 트레이스 하나를 열면 corebank의 `HoldCash` 처리 span과 trading의 `CashHeld` 처리 span이 같은 trace ID 아래에 보인다.
9. **로그 연결**: Spring Boot는 Micrometer Tracing이 있으면 로그에 `[traceId-spanId]` 형식의 상관 ID를 기본으로 넣는다. 이체 실패(`result != success`) 로그 1줄에 결과 코드와 상관 ID가 함께 찍히게 한다. Phase 4 M4-8의 MDC 요청 ID 필터는 지우거나, 남긴다면 요청 ID와 traceId를 둘 다 찍는 이유를 `docs/observability.md`에 적는다.

## 직접 작성할 테스트 시나리오

메트릭 이름·태그는 자동 테스트로, 대시보드·트레이스는 수동 검증 절차로 확인한다.

반드시 포함할 경우 (최소 8개):
- 성공 이체 3건, 잔액 부족 1건, 한도 초과 1건 → `MeterRegistry`에서 `transfer.requests`의 `result`별 값이 3, 1, 1 (테스트 컨텍스트의 `MeterRegistry` 빈 또는 직접 만든 `SimpleMeterRegistry` 사용)
- 잔액 부족 이체 → `transfer.latency{result="insufficient_funds"}` count 1
- 다른 트랜잭션이 계좌 행 락을 2초 잡고 있는 동안 이체 → `transfer.lock.wait` 최대값 ≥ 1.9초
- outbox 미발행 행 5개 → 10초 안에 `outbox.pending` 값 5
- `/actuator/prometheus` 응답 본문에 `transfer_requests_total{` 와 `transfer_latency_seconds_bucket{` 문자열이 있음 (`@SpringBootTest(webEnvironment = RANDOM_PORT)`. Spring Boot는 테스트에서 메트릭 내보내기를 기본으로 끈다. 엔드포인트가 404면 Spring Boot 4.1 레퍼런스 "Testing Spring Boot Applications" 장에서 observability 자동 구성을 켜는 테스트 어노테이션을 찾아 붙이고, 이름을 `docs/observability.md`에 적는다)
- 메트릭 태그 키 목록에 계좌번호·주문 ID가 없음 (`MeterRegistry.getMeters()`의 태그 키 전수 검사)
- (수동) Compose 기동 후 Prometheus `http://localhost:9090/targets`에서 `corebank`, `trading` 두 타깃이 `UP`
- (수동) 매수 주문 1건 → Jaeger에서 두 서비스 span이 한 트레이스에 있음, 스크린샷 저장

## 제약
- 메트릭 이름에 서비스 이름을 넣지 않는다(`corebank_transfer_total` 금지). 서비스 구분은 Prometheus `job` 라벨로 한다.
- 지연 백분위를 애플리케이션에서 계산해 Gauge로 내보내지 않는다(`publishPercentiles`만 켠 Timer 포함). 인스턴스 2대의 p99를 평균 내면 전체 p99가 되지 않는다. 버킷 히스토그램을 내보내고 PromQL `histogram_quantile`로 합친다.
- 샘플링 1.0은 이 Phase의 로컬 환경 값이다. M8-6 부하 테스트에서 이 값이 결과에 주는 영향을 따로 측정한다.
- Grafana 대시보드를 UI에서만 만들고 끝내지 않는다. JSON을 레포에 넣어 `docker compose down -v` 후에도 같은 대시보드가 올라와야 한다.

## 힌트
<details>
<summary>힌트 1: 저장해 둔 traceparent를 부모로 이어 붙이기</summary>

Micrometer Tracing의 `Propagator`는 헤더 맵에서 span 컨텍스트를 꺼내는 `extract`를 제공하고, `Tracer`로 그 컨텍스트를 부모로 하는 span을 시작해 현재 범위로 만들 수 있다(`Tracer.withSpan`). 그 범위 안에서 `KafkaTemplate.send`를 호출하면 observation이 현재 span을 기준으로 헤더를 넣는다. 확인 질문: INSERT 시점에 `traceparent` 문자열은 어떤 API로 만들 수 있는가?
</details>

## 완료 기준
- [ ] `./gradlew test`에서 이 미션의 자동 테스트 6개 이상이 통과한다
- [ ] `docker compose down -v && docker compose up -d` 후 Grafana(`http://localhost:3000`)에 수동 조작 없이 패널 12개짜리 대시보드가 있다
- [ ] 이체 1,000건을 보내는 스크립트(curl 반복 또는 k6) 실행 중 패널 1·5·8에 값이 그려진 스크린샷이 `docs/observability/`에 있다
- [ ] Jaeger에서 trading → corebank → trading 세 구간이 한 trace ID로 이어진 스크린샷과 그 trace ID가 찍힌 로그 줄(`docker compose logs`에서 복사)이 `docs/observability.md`에 있다
- [ ] `docs/observability.md`에 요구사항 6의 메트릭 이름 확인 결과(문서와 실제 이름이 다른 경우 그 차이)가 있다

## 생각해볼 질문
1. 패널 3은 업무 거절(잔액 부족)을 오류에서 뺐다. 잔액 부족 비율이 평소 0.5%에서 갑자기 30%가 되면 이것은 장애인가? 이 신호를 잡으려면 어떤 패널과 알림 조건(임계값, 지속 시간)을 추가하겠는가?
2. 샘플링을 10%로 낮추면 "느린 요청 1건의 트레이스를 꼭 보고 싶다"는 요구를 어떻게 만족시키는가? head 샘플링과 tail 샘플링(OpenTelemetry Collector)의 차이로 설명한다.
3. Prometheus 단일 인스턴스의 보존 기간이 끝나면 지난달 장애 지표를 볼 수 없다. 장기 보관이 필요하다면 어떤 구성 요소를 추가하겠는가? (Phase 8 이후 학습 주제로 이어진다)
