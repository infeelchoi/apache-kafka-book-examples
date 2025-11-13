# Q-KMS 기반 PQC CA API 설계서

## 1. 개요
Q-KMS는 양자내성(PQC) 키 관리와 인증서 수명주기를 단일 플랫폼에서 통합 제공합니다. 본 문서는 APISIX, Keycloak, 내부 API 서버가 공통으로 사용할 RESTful API 인터페이스를 정의해 Q-KMS가 Root/Intermediate CA, 키 관리, 토큰 서명 서비스를 동시에 수행할 수 있게 합니다.

주요 설계 목표는 다음과 같습니다.
- **단일 신뢰 앵커**: Root/Intermediate CA 키, 서버·클라이언트 인증서, JWT 서명키를 Q-KMS가 일원화.
- **PQC 우선**: Dilithium, Falcon 등 PQC 알고리즘을 1급 시민으로 취급하고, 필요 시 하이브리드 모드 지원.
- **자동화된 수명주기**: CSR 처리부터 발급·폐기·갱신, JWKS 노출까지 API 기반으로 자동화.
- **정책 중심 제어**: 테넌트, 서비스, 환경 별로 정책을 선언적으로 정의하여 재사용.

## 2. 아키텍처 역할
- **Root CA 모듈**: 오프라인 보관. Intermediate CA 발급에만 사용되며 API로는 읽기 전용 메타정보만 노출.
- **Intermediate/Issuing CA**: Q-KMS 온라인 모듈에서 운용. CSR 검증, 인증서 발급/폐기 제공.
- **Key Vault**: PQC 키 생성/저장, 키 버전 관리, 키 회전 정책 수행.
- **Token Service**: Keycloak, APISIX가 사용할 JWT/JWS 서명을 PQC 키로 제공하고 JWKS 엔드포인트 노출.
- **CRL/OCSP**: 인증서 상태 관리. 외부 캐시와 동기화 가능하도록 이벤트 발행.

## 3. API 엔드포인트 요약
| 영역 | 메서드 | 경로 | 설명 |
| --- | --- | --- | --- |
| CA 메타 | `GET` | `/v1/ca/intermediates` | 운영 중인 Intermediate CA 리스트 조회.
| | `POST` | `/v1/ca/intermediates` | Root CA로부터 새 Intermediate 생성(관리자용).
| CSR 처리 | `POST` | `/v1/csr` | CSR 제출 및 정책 평가 후 발급 파이프라인 시작.
| 인증서 발급 | `POST` | `/v1/certificates/issue` | CSR ID 기반으로 최종 인증서 발급.
| | `GET` | `/v1/certificates/{serial}` | 특정 인증서 메타 및 PEM 조회.
| 인증서 상태 | `POST` | `/v1/certificates/{serial}:revoke` | 사유 코드와 함께 폐기.
| | `GET` | `/v1/crl` | 최신 CRL 다운로드(PQC 서명).
| | `POST` | `/v1/ocsp` | OCSP 상태 질의/응답.
| 키 관리 | `POST` | `/v1/keys` | PQC 키 생성. 알고리즘·용도 지정.
| | `POST` | `/v1/keys/{id}:rotate` | 키 버전 롤오버.
| | `GET` | `/v1/keys/{id}` | 키 메타, 활성 버전.
| 토큰 서명 | `POST` | `/v1/tokens/sign` | 입력 클레임을 PQC 키로 서명해 JWT/JWS 생성.
| | `GET` | `/v1/jwks/{realm}` | Keycloak/서비스별 JWKS 노출.

## 4. 데이터 모델
```json
// CSR 제출 예시
{
  "csr": "-----BEGIN CERTIFICATE REQUEST-----...",
  "profile": "apisix-edge",
  "subject_alt_names": ["gateway.q", "10.0.0.5"],
  "token": "opaque-req-auth"
}
```

```json
// 키 생성 요청
{
  "usage": "TLS_SERVER",
  "algorithm": "CRYSTALS-DILITHIUM-3",
  "exportable": false,
  "tags": {
    "service": "apisix",
    "env": "prod"
  }
}
```

```json
// 발급 응답
{
  "serial": "0x71AF...",
  "certificate": "-----BEGIN CERTIFICATE-----...",
  "chain": ["-----BEGIN CERTIFICATE----- Root ..."],
  "status": "ISSUED",
  "expires_at": "2024-12-31T23:59:59Z"
}
```

## 5. 시퀀스 다이어그램 개요
1. 서비스가 `/v1/keys`로 PQC 키를 생성하고 키 핸들을 획득.
2. 해당 키로 CSR 생성 후 `/v1/csr` 제출.
3. 정책 엔진이 SAN, 알고리즘, 테넌트 정보를 검증.
4. 승인 시 `/v1/certificates/issue`를 호출해 인증서 PEM/체인을 수령.
5. 발급된 인증서는 `/v1/crl`, `/v1/ocsp` 대상에 자동 등록.
6. Keycloak은 `/v1/keys`로 JWT 서명키를 요청, `/v1/jwks/{realm}`에서 공개키를 서비스에 제공.

## 6. 보안·정책 고려사항
- **정책 엔진**: 프로필별 허용 알고리즘, SAN 패턴, 만료 기간, Key Usage 비트 필수화.
- **하이브리드 모드**: 필요 시 PQC + ECC 이중 서명 인증서 발급을 지원. `algorithm` 필드에 `HYBRID:DILITHIUM3+P256` 표기.
- **검증 토큰**: CSR 제출, 키 생성 등 민감 API는 mTLS + OAuth2 Client Credentials 조합으로 보호.
- **감사 로깅**: 모든 발급/폐기 이벤트는 Kafka 토픽 `qkms.audit.ca`로 발행.
- **키 백업**: Root/Intermediate 키는 Q-KMS 전용 하드웨어 슬롯(HSM Equivalent)에 저장하고, 버전별 백업 암호화.

## 7. 운영 자동화 훅
- **Webhook**: 인증서 발급/폐기 시 APISIX, Keycloak에 핫 리로드 트리거를 전송.
- **Scheduler**: 만료 30일 전 자동 갱신 요청 생성.
- **JWKS 캐시**: Keycloak realm별로 ETag/Cache-Control 헤더 제공.
- **CRL 파티셔닝**: 대규모 폐기를 대비해 프로파일 단위 incremental CRL 세그먼트 지원.

## 8. 에러 모델
| 코드 | 의미 | 해결 방안 |
| --- | --- | --- |
| `40001` | 프로파일 정책 위반 | SAN/알고리즘을 정책과 맞추어 재요청 |
| `40005` | CSR 서명검증 실패 | CSR 생성 시 키 일치 여부 확인 |
| `40301` | 권한 부족 | OAuth Scope 또는 mTLS 클라이언트 인증서 확인 |
| `40901` | 중복 발급 요청 | 기존 CSR 상태 확인 후 재사용 |
| `50010` | PQC 서명 모듈 오류 | 시스템 로그 확인, 페일오버 노드로 전환 |

## 9. 통합 체크리스트
- [ ] Root/Intermediate 키 HSM Import 완료
- [ ] 프로파일(apisix-edge, keycloak-jwt, internal-mtls) 정의
- [ ] 각 서비스 mTLS 클라이언트 인증서 Q-KMS 등록
- [ ] Keycloak JWKS URL을 `/v1/jwks/{realm}`으로 교체
- [ ] APISIX cert watcher가 Q-KMS 웹훅 이벤트 수신하는지 확인
- [ ] PQC 알고리즘 별 모듈 헬스체크 구성

## 10. 향후 확장
- **ACME 호환성**: 외부 호스트 자동 발급을 위해 ACME v2 인터페이스 추가 가능.
- **다중 Region 동기화**: Kafka 스트림으로 CRL/키 메타 정보를 다른 리전에 복제.
- **비밀관리 통합**: Vault, AWS Secrets Manager와 키 핸들 교환 가능하도록 플러그인 설계.

---
이 설계서는 Q-All-In-One 환경에서 Q-KMS가 CA, 키 관리, 토큰 서명을 단일 정책 기반으로 제공하도록 하는 기본 API 스펙입니다.
