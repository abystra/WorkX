# Keycloak for WorkX (identity, AD-05)

`workx-realm.json` defines the `workx` realm: email as username, verified email required, the
confidential client `workx-web` (PKCE S256 required) whose redirect URI is the API callback, and one local
test user (`alex@example.com` / `workx-dev-password`). The client secret and password are local-only values.

## Real-service verification (B-02)

Not yet run: this environment does not permit starting a downloaded Keycloak server. On a machine with
Docker:

```bash
docker run --rm -p 8180:8080 -e KC_BOOTSTRAP_ADMIN_USERNAME=admin -e KC_BOOTSTRAP_ADMIN_PASSWORD=admin -v "$PWD/infra/keycloak:/opt/keycloak/data/import:ro" quay.io/keycloak/keycloak:26.0 start-dev --import-realm
```

```bash
scripts/dev/pg.sh start && eval "$(scripts/dev/pg.sh url)" && uv run workx db upgrade
```

```bash
WORKX_OIDC_ISSUER=http://127.0.0.1:8180/realms/workx WORKX_OIDC_ALLOW_INSECURE_ISSUER=true WORKX_OIDC_CLIENT_SECRET=workx-local-keycloak-secret WORKX_SESSION_COOKIE_SECURE=false WORKX_API_BASE_URL=http://127.0.0.1:8000 uv run workx api
```

```bash
uv run python scripts/verify/keycloak_login.py
```

Every line should read `PASS`. In production, use HTTPS for the issuer (`WORKX_OIDC_ALLOW_INSECURE_ISSUER`
unset), a generated client secret from the platform secret manager, and the deployed callback URL.
