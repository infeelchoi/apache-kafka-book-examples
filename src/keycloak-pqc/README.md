# Keycloak PQC Token Validation Demo

This example bundles together the operational steps that were provided for testing Luna HSM signed Keycloak tokens and their hybrid Post-Quantum Cryptography (PQC) verification flow.  It is split into two reproducible paths:

1. **Path A – Hardware backed**: runs Keycloak against a Thales Luna HSM using the official SPI module so that Keycloak signs its tokens inside the HSM.
2. **Path B – Dry run**: keeps Keycloak signing tokens with RS256 as usual, and layers on top an optional Dilithium signature that can be checked locally.  This path is great when hardware access is not immediately available but teams want to wire PQC validation logic into their services.

Both paths reuse the sequence from the *Thales Luna HSM Keycloak Integration Guide Rev C* and add scripts that keep the process repeatable.

## Repository layout

```
src/keycloak-pqc
├── README.md                # This guide
├── install.sh               # Helper to provision a Keycloak container and patch java.security
├── verify.py                # RS256 + optional PQC validator used by both paths
├── docker-compose.yml       # Container layout for Keycloak + Luna artefacts (Path A)
└── requirements.txt         # Python dependencies for verify.py
```

## 1. Path A – Luna HSM backed tokens

> ⚠️  You need access to a Luna HSM partition, the Luna Client libraries, and the Keycloak SPI package released by Thales to complete the hardware path.  The steps below assume the Luna client is installed under `/usr/safenet/lunaclient` as in the guide.

### 1.1. HSM preparation (performed once per environment)

Follow the *Prerequisites* chapter of the Thales guide to: initialise the HSM, create a partition, register the Keycloak host through NTLS, enrol the CO/CU accounts, and install the Luna client.  On Linux make sure the `keycloak` system user belongs to the `hsmusers` group:

```bash
sudo gpasswd --add keycloak hsmusers
```

### 1.2. Patch the JDK security providers

Adapt `JAVA_HOME` and run the helper script from this repository.  It appends the Luna provider entries to `java.security` in a reversible way (a backup is stored next to the file).

```bash
cd src/keycloak-pqc
sudo ./install.sh --java-home /opt/jdk-11 --enable-luna-provider
```

The script will ensure the following block is present in `<JAVA_HOME>/conf/security/java.security`:

```
security.provider.11=SunPKCS11
security.provider.12=com.safenetinc.luna.provider.LunaProvider
security.provider.13=SunRsaSign
```

### 1.3. Generate or import the signing key inside the HSM

Use `keytool` exactly as documented in the guide to create an RSA or PQC-capable key inside the Luna partition.  For example, to generate an RSA key pair labelled `lunakey`:

```bash
keytool -genkeypair -alias lunakey -keyalg RSA -keysize 2048 -sigalg SHA256withRSA \
  -keypass <USER_PIN> -keystore /opt/lunastore -storetype luna -storepass <USER_PIN> \
  -providerpath "/usr/safenet/lunaclient/jsp/lib/LunaProvider.jar" \
  -providerclass com.safenetinc.luna.provider.LunaProvider \
  -J-Djava.library.path=/usr/safenet/lunaclient/jsp/lib/ \
  -J-cp -J/usr/safenet/lunaclient/jsp/lib/LunaProvider.jar
```

Finish the CSR/CA import round-trip so that the keystore contains the full certificate chain, then note the alias and partition label.  Those values are required in the Keycloak console.

### 1.4. Deploy Keycloak with the Luna SPI module

The `docker-compose.yml` file shows how to layer the Luna SPI onto the official Keycloak container.  Mount the SPI module, Luna client libraries, and configuration files that you prepared following the Thales guide:

```bash
LUNA_CLIENT_ROOT=/usr/safenet/lunaclient \
KEYCLOAK_ADMIN=admin KEYCLOAK_ADMIN_PASSWORD=change_me \
docker compose -f docker-compose.yml up -d
```

Check the Keycloak logs; a successful load prints a line that contains `luna-keystore ... implementing the internal SPI keys`.

### 1.5. Enable the HSM keystore in the admin console

1. Open the Keycloak admin console → *Realm Settings* → *Keys*.
2. Add a new keystore provider and select `luna-keystore`.
3. Enter the keystore path (e.g. `/opt/lunastore`), the alias created earlier, and the user pin.  Set the priority to **100** so it becomes the default signing key.
4. Restart Keycloak.  New tokens from that realm now carry the HSM backed key identifier (kid).

### 1.6. Issue a test token and verify

Request a client credentials token and store it in `token.jwt`:

```bash
curl -sS -X POST "https://<KEYCLOAK>/realms/<REALM>/protocol/openid-connect/token" \
  -d "client_id=<CLIENT_ID>" \
  -d "client_secret=<CLIENT_SECRET>" \
  -d "grant_type=client_credentials" | jq -r .access_token > token.jwt
```

Run the validator.  It verifies the RS256 signature and, if you supply the PQC envelope (see Path B), it validates the hybrid portion too.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python verify.py --token token.jwt --issuer "https://<KEYCLOAK>/realms/<REALM>"
```

Expected output:

```
✅ RS256 verification succeeded: sub=...
ℹ️ No PQC artefacts supplied; skipping PQC verification.
```

## 2. Path B – PQC dry run without the HSM

This path retains Keycloak’s regular RS256 signing keys yet lets you practice attaching and verifying an additional Dilithium signature.

### 2.1. Generate a Dilithium key pair (software)

Using liboqs’ Python bindings:

```bash
python - <<'PY'
import base64, oqs
with oqs.Signature('Dilithium2') as signer:
    public_key = signer.generate_keypair()
    secret_key = signer.export_secret_key()
    print('Public key (base64url):', base64.urlsafe_b64encode(public_key).decode())
    print('Secret key stored in dilithium.sk')
    open('dilithium.sk', 'wb').write(secret_key)
PY
```

### 2.2. Sign a freshly issued Keycloak token

```bash
TOKEN=$(cat token.jwt)
HEADER=$(echo "$TOKEN" | cut -d. -f1)
PAYLOAD=$(echo "$TOKEN" | cut -d. -f2)
MESSAGE="$HEADER.$PAYLOAD"
python - <<'PY'
import base64, oqs, os
message = os.environ['MESSAGE'].encode()
with oqs.Signature('Dilithium2') as signer:
    signer.import_secret_key(open('dilithium.sk','rb').read())
    signature = signer.sign(message)
    print(base64.urlsafe_b64encode(signature).decode())
PY
```

Attach the resulting signature and the base64url public key to the token header (e.g. `pqc_sig`, `pqc_alg`, `pqc_pub`).  This can be done by packaging the token and the PQC artefacts together in a JSON envelope that your services understand.

### 2.3. Verify both layers

```bash
python verify.py --token token.jwt --issuer "https://<KEYCLOAK>/realms/<REALM>" \
  --pqc-sig <BASE64URL_SIGNATURE> --pqc-public <BASE64URL_PUBLIC_KEY> --pqc-alg Dilithium2
```

The script first validates RS256 using the realm JWKS endpoint, then resolves the PQC verifier.  If `python-oqs` is not present you will get a friendly message explaining how to install it.

## 3. Files in this folder

### install.sh

Shell helper that can:

- backup and patch `java.security` to add the Luna provider entries;
- copy the Luna SPI artefacts into the Keycloak modules directory;
- restart a Keycloak container (when running under docker compose).

Run `./install.sh --help` for the full list of options.  Each action is idempotent so it is safe to re-run when refreshing an environment.

### verify.py

Python script that:

- downloads the JWKS from the issuer and verifies RS256 tokens;
- optionally checks a PQC signature (Dilithium via `python-oqs`) when `--pqc-*` flags are provided;
- prints structured log style output so that CI jobs can assert success by grepping for `✅`.

### docker-compose.yml

Shows how to bootstrap Keycloak with the Luna SPI module mounted from the host.  Update the volume paths to match the layout created while following the Thales guide.

## 4. Cleaning up

```bash
docker compose -f docker-compose.yml down
rm -rf .venv token.jwt dilithium.sk
```

You can now repeat the experiment end-to-end using the same scripts.
