# Phase 3 — Spring Core: IoC / DI / AOP (2주)

## 학습 목표
- Spring이 **없을 때의 고통**을 먼저 겪고, Spring이 그걸 어떻게 해결하는지 이해한다.
- 빈 등록·주입·스코프·라이프사이클을 설명할 수 있다.
- 프록시 → AOP의 원리를 이해한다. (Phase 5 `@Transactional`을 이해하기 위한 필수 선행)

## 주제
| 주 | 주제 |
|---|---|
| 1주 | 직접 만든 DI 컨테이너 → `ApplicationContext`, `@Component`/`@Bean`, 생성자 주입, 빈 스코프, `@PostConstruct`, `@Configuration`의 CGLIB 프록시 |
| 2주 | 프록시 패턴 직접 구현 → JDK 동적 프록시 → CGLIB → Spring AOP(`@Aspect`), 포인트컷 표현식, `@ConfigurationProperties`, Profile, `@SpringBootTest` vs 슬라이스 테스트 |

## 미션 (상세 문서는 Phase 2 완료 후 작성)
- **M3-1 나만의 DI 컨테이너**: 리플렉션으로 `@MyComponent`가 붙은 클래스를 찾아 생성자 주입하는 미니 컨테이너 (순환 참조 감지 포함)
- **M3-2 Spring으로 이식**: Phase 2 이체 엔진을 Spring Boot 프로젝트로 옮기기. `main`의 수동 조립 코드가 사라지는 걸 확인
- **M3-3 빈 라이프사이클 실험**: 싱글톤 빈에 상태를 두면 생기는 동시성 문제 재현 (Phase 2 지식 연결)
- **M3-4 프록시 직접 만들기**: 실행 시간 측정 프록시를 (1) 수동 데코레이터 (2) JDK 동적 프록시 (3) CGLIB로 각각 구현
- **M3-5 감사 로그 AOP**: `@Audited`가 붙은 금융 거래 메서드의 호출자·인자(마스킹)·결과·소요시간을 기록. **self-invocation 시 AOP가 안 걸리는 문제를 재현**
- **M3-6 설정 외부화**: 이체 한도, 락 타임아웃을 `application.yml` + `@ConfigurationProperties`(+ 검증)로 분리, `local`/`test` 프로파일

## 완료 기준
- [ ] `@Configuration` 클래스에서 `@Bean` 메서드를 두 번 호출해도 같은 객체가 나오는 이유를 프록시로 설명
- [ ] "Spring AOP는 프록시 기반이라 같은 클래스 내부 호출에는 적용되지 않는다"를 테스트로 증명
- [ ] 싱글톤 빈이 왜 무상태(stateless)여야 하는지 설명
