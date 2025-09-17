# APISIX + Keycloak SSO Demo

This example shows how to secure a backend service that sits behind [Apache APISIX](https://apisix.apache.org/) using [Keycloak](https://www.keycloak.org/) for Single Sign-On (SSO).  The stack contains:

> 한국어 가이드가 필요하다면 [`README.ko.md`](README.ko.md)를 참고하세요.

* **Apache APISIX** acting as the API gateway and OIDC client.
* **Keycloak** providing the identity provider (IdP) capabilities.
* **Service A**, a simple Flask application that is protected by APISIX.

When a user navigates to `http://localhost:9080/service-a/`, APISIX forces the browser through the Keycloak authentication flow.  After a successful login, APISIX forwards the request to Service A and enriches it with ID/Access token headers so the application can personalize the response.

## Prerequisites

* Docker and Docker Compose
* Make sure the local ports `9080`, `9180`, `8000`, and `8080` are available.

## Getting started

1. Boot the stack:

   ```bash
   docker compose up --build
   ```

2. Wait until Keycloak prints `Listening on: http://0.0.0.0:8080` and APISIX finishes loading the route defined in `apisix/apisix.yaml`. The Keycloak container automatically imports the `demo` realm and the sample user on startup, so there is no manual configuration required.

3. Open `http://localhost:9080/service-a/` in a browser. You will be redirected to Keycloak. Log in with:

   * **Username:** `alice`
   * **Password:** `password`

   After logging in you should be redirected back to Service A, which displays the claims extracted from the Keycloak tokens.

4. To shut everything down:

   ```bash
   docker compose down -v
   ```

### Verifying with `curl`

After signing in once through the browser, APISIX stores your session cookies. You can then call the protected endpoint with `curl`
to inspect the headers that APISIX forwards to Service A:

```bash
curl -i http://localhost:9080/service-a/
```

The JSON response includes the decoded `userinfo` payload along with boolean flags that indicate whether access and ID tokens were
present on the request. This is a useful way to confirm that APISIX is injecting identity context as expected.

## Layout

```
examples/apisix-keycloak-sso/
├── README.md                # This guide
├── docker-compose.yml       # Orchestrates APISIX, Keycloak, and Service A
├── apisix/
│   ├── apisix.yaml          # Route, upstream, and plugin configuration
│   └── config.yaml          # Minimal APISIX configuration
├── keycloak/
│   └── realm-export.json    # Realm and client definition for the demo
└── service-a/
    ├── Dockerfile           # Builds the Flask app image
    ├── app.py               # Simple application that shows incoming identity
    └── requirements.txt     # Flask dependency pin
```

## How it works

* The APISIX `openid-connect` plugin uses the Keycloak discovery endpoint to validate tokens, initiates the login redirect, and injects headers such as `X-Userinfo`, `X-Access-Token`, and `X-Id-Token` into the upstream request.
* Service A reads the `X-Userinfo` header to display the authenticated user's profile data.
* You can sign out from Keycloak at `http://localhost:9080/service-a/logout`. APISIX will terminate the local session and redirect back to Keycloak's logout endpoint.

## Troubleshooting

* If you encounter certificate errors, make sure you are using HTTP (not HTTPS) for the demo.
* To inspect the APISIX route and upstream registrations, access the Admin API at `http://localhost:9180/apisix/admin/routes/`. The default admin key is `adminkey` as set in `apisix/config.yaml`.
* You can access the Keycloak administration console at `http://localhost:8080/admin` with the admin credentials declared in `docker-compose.yml` (defaults to `admin` / `admin`).
