# M8-1 컨테이너 이미지와 Compose 전체 실행

> 가이드 수준: L3, 예상 시간: 6~8h, 선행: M7-8

## 목표
이 미션을 끝내면 다음을 할 수 있다.
- corebank와 trading을 하나의 Gradle 멀티 모듈 프로젝트로 합치고 `./gradlew build` 한 번으로 두 모듈의 테스트를 모두 실행한다
- 계층형(layered) JAR Dockerfile로 두 서비스의 이미지를 만들고, 소스 한 줄 수정 후 재빌드에서 의존성 레이어가 캐시로 재사용되는 것을 `docker build` 출력의 `CACHED` 줄로 보여준다
- `compose.yaml` 하나로 MySQL, Redis, Kafka, corebank, trading 5개 컨테이너를 띄우고, 두 서비스의 `/actuator/health`가 120초 안에 200을 돌려주는 것을 스크립트로 증명한다
- M0-3의 GitHub Actions CI에 이미지 빌드와 Compose 기동 스모크 테스트를 추가한다

## 배경
Phase 6, 7은 IDE에서 서비스 하나씩 실행했고, MySQL은 `docker run`으로 따로 띄웠다. 운영 환경의 서비스는 "내 노트북에서는 됐다"가 통하지 않는다. JDK 버전, 환경 변수, DB 주소, 기동 순서가 하나라도 다르면 이체 API가 뜨지 않거나, DB 마이그레이션 전에 요청을 받아 500을 돌려준다. 이 미션은 Phase 8의 모든 실험(장애 주입, 부하 테스트)이 같은 환경에서 재현되도록 실행 환경을 코드로 고정한다. M7-8까지 만든 두 서비스를 그대로 컨테이너에 넣는 것이 출발점이다.

## 요구사항
1. **멀티 모듈**: README "워크스페이스 만들기" 절대로 `phase-8-advanced/workspace/`를 만든다. `settings.gradle.kts`에 `common`, `corebank`, `trading`을 포함한다. `common`은 비워 두거나 서비스 간 메시지 `record`만 둔다(Spring 의존성 금지). corebank, trading은 서로의 모듈을 의존하지 않는다.
2. **실행 포트와 DB**: corebank는 8081, trading은 8082로 뜬다. MySQL 인스턴스 하나에 스키마 `corebank`, `trading` 두 개를 만들고, 서비스마다 자기 스키마 계정만 쓴다(`corebank_app`은 `trading` 스키마 권한 없음). Flyway 마이그레이션은 서비스 기동 시 자기 스키마에만 실행된다.
3. **Actuator**: 두 서비스 모두 `spring-boot-starter-actuator`를 추가하고 `/actuator/health`를 노출한다. DB 연결이 끊기면 health는 503(`DOWN`)을 돌려준다. corebank의 health에는 Redis 상태도 포함된다.
4. **이미지 빌드(주 방식: Dockerfile)**: 모듈마다 `Dockerfile`을 둔다. 빌드된 JAR를 `java -Djarmode=tools -jar application.jar extract --layers --destination extracted`로 풀고, `dependencies` → `spring-boot-loader` → `snapshot-dependencies` → `application` 순서로 레이어를 복사한다(Spring Boot 4.1 레퍼런스 "Dockerfiles" 절). 베이스 이미지는 `eclipse-temurin:21-jre-noble`.
5. **런타임 설정**: 컨테이너 프로세스는 UID 0이 아닌 사용자로 실행된다. JVM 힙은 `-XX:MaxRAMPercentage=75`로 컨테이너 메모리 제한(`mem_limit: 1g`)에 맞춘다. DB 주소, 계정, Kafka 주소는 이미지에 넣지 않고 환경 변수로 받는다.
6. **보조 방식(비교만)**: `./gradlew :corebank:bootBuildImage`로 Cloud Native Buildpacks 이미지를 한 번 만들어 보고, Dockerfile 이미지와 크기, 빌드 시간, 셸 유무를 `docs/image-comparison.md` 표로 비교한다. Spring Boot 4.1의 기본 빌더 `paketobuildpacks/builder-noble-java-tiny`로 만든 이미지에는 셸이 없어 Compose healthcheck에서 `curl`을 쓸 수 없다. 이것이 이 미션이 Dockerfile을 주 방식으로 고른 이유다.
7. **Compose**: 아래 `compose.yaml`을 기준으로 두 서비스 항목을 완성한다. 서비스는 `mysql`, `redis`, `kafka`가 `service_healthy`가 된 뒤에 시작한다. M8-1 시점에는 Kafka에 연결하는 코드가 없어도 된다(M8-2부터 사용).
8. **기동 대기 스크립트**: `scripts/wait-healthy.sh`는 2초 간격으로 `http://localhost:8081/actuator/health`와 `http://localhost:8082/actuator/health`를 호출하고, 둘 다 200이면 경과 초를 출력하고 종료 코드 0, 120초가 지나면 마지막 응답 코드를 출력하고 종료 코드 1로 끝난다.
9. **CI**: M0-3의 `.github/workflows/ci.yml`에 job 두 개를 추가한다. `build`(`./gradlew build`)가 성공하면 `smoke`가 `docker compose up -d --build` → `scripts/wait-healthy.sh` → 실패 시 `docker compose logs` 출력 → `docker compose down -v` 순서로 실행한다. 레포 루트가 아닌 `phase-8-advanced/workspace`에서 실행되도록 `working-directory`를 지정한다.

### 제공하는 인프라 파일 (그대로 써도 된다)

`compose.yaml` (이미지 태그는 2026-11-10 Docker Hub에서 확인한 값):
```yaml
services:
  mysql:
    image: mysql:8.4
    environment:
      MYSQL_ROOT_PASSWORD: rootpw
    ports: ["3306:3306"]
    volumes:
      - ./docker/mysql/init:/docker-entrypoint-initdb.d:ro
      - mysql-data:/var/lib/mysql
    healthcheck:
      # 초기화 중의 임시 서버는 TCP를 열지 않으므로 127.0.0.1(TCP)로 확인한다
      test: ["CMD-SHELL", "mysql -h 127.0.0.1 -uroot -p$$MYSQL_ROOT_PASSWORD -e 'SELECT 1'"]
      interval: 5s
      timeout: 3s
      retries: 30

  redis:
    image: redis:8
    ports: ["6379:6379"]
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 10

  kafka:
    image: apache/kafka:4.3.2
    ports: ["29092:29092"]   # 호스트(IDE, 테스트)에서는 localhost:29092
    environment:
      KAFKA_NODE_ID: 1
      KAFKA_PROCESS_ROLES: broker,controller
      KAFKA_LISTENERS: PLAINTEXT://:9092,CONTROLLER://:9093,PLAINTEXT_HOST://:29092
      KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://kafka:9092,PLAINTEXT_HOST://localhost:29092
      KAFKA_LISTENER_SECURITY_PROTOCOL_MAP: CONTROLLER:PLAINTEXT,PLAINTEXT:PLAINTEXT,PLAINTEXT_HOST:PLAINTEXT
      KAFKA_CONTROLLER_LISTENER_NAMES: CONTROLLER
      KAFKA_INTER_BROKER_LISTENER_NAME: PLAINTEXT
      KAFKA_CONTROLLER_QUORUM_VOTERS: 1@kafka:9093
      KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR: 1
      KAFKA_TRANSACTION_STATE_LOG_REPLICATION_FACTOR: 1
      KAFKA_TRANSACTION_STATE_LOG_MIN_ISR: 1
      KAFKA_GROUP_INITIAL_REBALANCE_DELAY_MS: 0
      KAFKA_NUM_PARTITIONS: 3
    healthcheck:
      test: ["CMD-SHELL", "/opt/kafka/bin/kafka-broker-api-versions.sh --bootstrap-server localhost:9092 > /dev/null"]
      interval: 10s
      timeout: 10s
      retries: 12

  corebank:
    build: ./corebank
    ports: ["8081:8081"]
    mem_limit: 1g
    environment:
      SERVER_PORT: 8081
      SPRING_DATASOURCE_URL: jdbc:mysql://mysql:3306/corebank
      SPRING_DATASOURCE_USERNAME: corebank_app
      SPRING_DATASOURCE_PASSWORD: corebankpw
      SPRING_DATA_REDIS_HOST: redis
      SPRING_KAFKA_BOOTSTRAP_SERVERS: kafka:9092
      JAVA_TOOL_OPTIONS: -XX:MaxRAMPercentage=75
    depends_on:
      mysql: { condition: service_healthy }
      redis: { condition: service_healthy }
      kafka: { condition: service_healthy }
    # healthcheck: 직접 작성 (요구사항 4의 베이스 이미지에 curl이 있는지 먼저 확인)

  # trading: corebank와 같은 형식으로 직접 작성 (8082, trading 스키마, Redis 불필요)

volumes:
  mysql-data:
```

`docker/mysql/init/01-databases.sql`은 스키마 2개, 계정 2개, 스키마별 권한을 만드는 SQL을 직접 작성한다. 이 디렉터리의 SQL은 `mysql-data` 볼륨이 비어 있을 때 최초 1회만 실행된다. SQL을 고친 뒤에는 `docker compose down -v`로 볼륨을 지워야 다시 실행된다.

자주 쓰는 명령:
```bash
docker compose up -d --build          # 이미지 빌드 후 백그라운드 기동
docker compose ps                     # STATUS 열에 (healthy) 확인
docker compose logs -f corebank       # 서비스 로그
docker compose down -v                # 컨테이너와 볼륨 삭제
docker run --rm eclipse-temurin:21-jre-noble curl --version   # 베이스 이미지에 curl이 있는지 확인
docker history workspace-corebank     # 레이어별 크기. Compose v2 이미지 이름은 "{프로젝트=디렉터리 이름}-{서비스}" (docker images로 확인)
```

## 직접 작성할 테스트 시나리오

이 미션의 "테스트"는 JUnit 테스트가 아니라 실행 검증 절차다. `docs/compose-verification.md`에 표(번호, 준비, 실행 명령, 기대 결과, 실제 결과)로 적는다.

반드시 포함할 경우 (최소 7개):
- 볼륨이 빈 상태에서 `docker compose up -d --build` → `wait-healthy.sh` 종료 코드 0, 경과 초 기록
- `docker compose ps`에서 5개 컨테이너가 모두 `healthy`(앱 2개는 직접 작성한 healthcheck 기준)
- `corebank_app` 계정으로 `trading` 스키마 테이블을 `SELECT` → `ERROR 1142`(권한 없음) 계열 오류
- `docker compose stop mysql` 후 corebank `/actuator/health` → 503, `start mysql` 후 60초 안에 200 복귀
- `docker compose exec corebank id -u` → 0이 아닌 값
- `application` 패키지의 Java 파일 1줄 수정 후 `docker compose build corebank` → `dependencies` 레이어 COPY 단계가 `CACHED`
- MySQL healthcheck를 `mysqladmin ping`(소켓)으로 바꾸고 볼륨을 지운 뒤 기동 → 앱이 DB 초기화 완료 전에 연결을 시도하는지 로그로 관찰하고 결과 기록

## 제약
- `docker compose`(Compose v2)를 쓴다. `docker-compose`(v1)는 2023년에 지원이 끝났다.
- `depends_on`은 `condition: service_healthy`로 쓴다. 조건 없는 `depends_on`은 컨테이너 "시작"만 기다리고 MySQL이 연결을 받을 준비가 됐는지는 기다리지 않는다.
- 비밀번호는 학습용 값이라도 `application.yml`에 넣지 않는다. Compose 환경 변수 또는 `.env` 파일(`.gitignore`에 추가)로만 넘긴다.
- `latest` 태그를 쓰지 않는다. 다음 주에 같은 명령을 실행해도 같은 버전이 떠야 부하 테스트 전후 비교가 의미를 가진다.
- Spring Boot Gradle 플러그인은 `bootJar`와 함께 `-plain.jar`도 만든다. Dockerfile의 `COPY build/libs/*.jar`가 파일 2개와 일치하면 빌드가 실패하므로 하나만 남기는 방법을 정한다.

## 힌트
<details>
<summary>힌트 1: 앱 컨테이너의 healthcheck와 start_period</summary>

Compose healthcheck의 `start_period` 동안 실패한 검사는 `retries`에 세지 않는다. Spring Boot가 Flyway 마이그레이션까지 끝내는 데 몇 초가 걸리는지 로그의 `Started ...Application in N seconds`로 먼저 재고 값을 정한다.
</details>

## 완료 기준
- [ ] `./gradlew build`가 corebank, trading 두 모듈의 테스트를 모두 실행하고 성공한다 (출력에 `:corebank:test`, `:trading:test` 태스크가 보인다)
- [ ] `docker compose down -v && docker compose up -d --build && scripts/wait-healthy.sh`가 종료 코드 0으로 끝나고, 경과 시간이 120초 이하다
- [ ] `docs/compose-verification.md`에 시나리오 7개 이상과 실제 결과가 있다
- [ ] `docs/image-comparison.md`에 Dockerfile 이미지와 `bootBuildImage` 이미지의 크기(MB), 빌드 시간(초, 캐시 없음/있음), 셸 유무 3개 열이 있다
- [ ] GitHub Actions에서 `build`, `smoke` job이 초록색이고, `smoke` 로그에 `wait-healthy.sh`의 경과 초가 찍힌다

## 생각해볼 질문
1. `KAFKA_ADVERTISED_LISTENERS`에 `kafka:9092`와 `localhost:29092`를 둘 다 둔 이유는 무엇인가? 하나만 두면 IDE에서 실행한 테스트와 컨테이너 안의 corebank 중 어느 쪽이 연결에 실패하는가?
2. Kubernetes의 liveness probe와 readiness probe에 `/actuator/health` 하나를 똑같이 쓰면, DB가 30초 끊겼을 때 무슨 일이 생기는가? Spring Boot의 `/actuator/health/liveness`, `/actuator/health/readiness` 그룹과 비교한다.
3. 이 미션은 서비스 두 개가 MySQL 인스턴스 하나를 스키마로 나눠 쓴다. 인스턴스를 서비스마다 따로 두면 M8-2의 이중 쓰기 문제는 사라지는가, 그대로인가?
