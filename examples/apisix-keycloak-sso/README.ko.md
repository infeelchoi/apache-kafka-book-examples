# APISIX + Keycloak SSO 데모

이 예제는 [Apache APISIX](https://apisix.apache.org/)를 API 게이트웨이로 사용하고 [Keycloak](https://www.keycloak.org/)을 SSO(IdP)로 연동하여 백엔드 서비스를 보호하는 방법을 보여줍니다. 포함된 구성 요소는 다음과 같습니다.

* **Apache APISIX** – OIDC 클라이언트 역할을 수행하는 API 게이트웨이
* **Keycloak** – 인증을 제공하는 IdP 서버
* **Service A** – APISIX 뒤에 배치된 간단한 Flask 애플리케이션

브라우저에서 `http://localhost:9080/service-a/`로 이동하면 APISIX가 Keycloak 로그인 플로우로 리디렉션합니다. 로그인에 성공하면 APISIX가 요청을 Service A로 전달하면서 ID/Access 토큰 정보를 헤더에 추가하여 애플리케이션이 사용자 정보를 확인할 수 있습니다.

## 준비물

* Docker 및 Docker Compose
* `9080`, `9180`, `8000`, `8080` 포트가 비어 있어야 합니다.

## 실행 방법

1. 스택을 기동합니다.

   ```bash
   docker compose up --build
   ```

2. Keycloak 컨테이너에서 `Listening on: http://0.0.0.0:8080` 로그가 보이고 APISIX가 `apisix/apisix.yaml`에 정의된 라우트를 로드할 때까지 기다립니다. Keycloak 컨테이너는 부팅 시 `demo` realm과 샘플 사용자를 자동으로 가져오기 때문에 추가 설정이 필요 없습니다.

3. 브라우저에서 `http://localhost:9080/service-a/`를 열고 다음 계정으로 로그인합니다.

   * **Username:** `alice`
   * **Password:** `password`

   로그인 후 Service A로 다시 리디렉션되며, Keycloak 토큰에서 추출한 클레임이 화면에 표시됩니다.

4. 종료하려면 다음 명령을 실행합니다.

   ```bash
   docker compose down -v
   ```

### `curl`로 확인하기

브라우저에서 한 번 로그인하면 APISIX가 세션 쿠키를 저장합니다. 이후에는 `curl`로 보호된 엔드포인트를 호출하여 APISIX가 Service A로 전달하는 헤더를 확인할 수 있습니다.

```bash
curl -i http://localhost:9080/service-a/
```

JSON 응답에는 디코딩된 `userinfo` 페이로드와 Access/ID 토큰 헤더의 존재 여부가 포함됩니다. 이를 통해 APISIX가 기대한 대로 사용자 컨텍스트를 주입하는지 손쉽게 검증할 수 있습니다.

## 디렉터리 구성

```
examples/apisix-keycloak-sso/
├── README.md                # 영어 가이드
├── README.ko.md             # 한국어 가이드
├── docker-compose.yml       # APISIX, Keycloak, Service A를 오케스트레이션
├── apisix/
│   ├── apisix.yaml          # 라우트, 업스트림, 플러그인 설정
│   └── config.yaml          # 최소한의 APISIX 설정
├── keycloak/
│   └── realm-export.json    # 데모용 realm과 클라이언트 정의
└── service-a/
    ├── Dockerfile           # Flask 앱 이미지를 빌드
    ├── app.py               # 전달받은 인증 정보를 출력하는 애플리케이션
    └── requirements.txt     # Flask 의존성 고정
```

## 동작 방식

* APISIX `openid-connect` 플러그인은 Keycloak Discovery 엔드포인트로 토큰을 검증하고 로그인 리디렉션을 처리하며 `X-Userinfo`, `X-Access-Token`, `X-Id-Token` 같은 헤더를 업스트림으로 전달합니다.
* Service A는 `X-Userinfo` 헤더를 읽어 인증된 사용자 프로필을 응답에 보여줍니다.
* `http://localhost:9080/service-a/logout`으로 접속하면 APISIX가 세션을 종료하고 Keycloak 로그아웃 엔드포인트로 리디렉션합니다.

## 문제 해결 팁

* 인증서 오류가 발생하면 데모에서는 HTTPS가 아닌 HTTP를 사용하고 있는지 확인하세요.
* APISIX 라우트 및 업스트림 등록 상태는 `http://localhost:9180/apisix/admin/routes/`에서 확인할 수 있습니다. 기본 Admin Key는 `apisix/config.yaml`에 설정된 `adminkey`입니다.
* Keycloak 관리자 콘솔은 `docker-compose.yml`에 정의된 관리자 계정(기본값 `admin` / `admin`)으로 `http://localhost:8080/admin`에서 접속할 수 있습니다.
