import base64
import json
from typing import Any, Dict, Optional

from flask import Flask, jsonify, request

app = Flask(__name__)


def _load_userinfo(raw: Optional[str]) -> Optional[Dict[str, Any]]:
    """Attempt to decode the APISIX X-Userinfo header."""
    if not raw:
        return None

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    try:
        decoded = base64.b64decode(raw).decode("utf-8")
        return json.loads(decoded)
    except Exception:  # pragma: no cover - defensive path
        return {"raw": raw}


@app.route("/")
def index():
    userinfo = _load_userinfo(request.headers.get("X-Userinfo"))
    access_token = request.headers.get("X-Access-Token")
    id_token = request.headers.get("X-Id-Token")

    if not userinfo:
        payload = {
            "message": "Hello from Service A! The request did not include user info headers.",
            "received_headers": [
                header for header in [
                    "X-Userinfo",
                    "X-Access-Token",
                    "X-Id-Token",
                ]
                if header in request.headers
            ],
        }
    else:
        payload = {
            "message": f"Hello, {userinfo.get('preferred_username', userinfo.get('sub', 'mystery user'))}!",
            "userinfo": userinfo,
            "tokens_present": {
                "access_token": bool(access_token),
                "id_token": bool(id_token),
            },
        }

    return jsonify(payload)


@app.route("/healthz")
def healthz():
    return {"status": "ok"}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=False)
