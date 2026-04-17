from datetime import datetime
import base64
import json
import os
import uuid

from flask import Flask, jsonify, request


app = Flask(__name__)

PENDING_ACTIVATIONS = {}


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(f"{data}{padding}".encode("ascii"))


def _make_jwt_like(payload: dict) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    header_json = json.dumps(header, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    payload_json = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return ".".join(
        [
            _b64url_encode(header_json),
            _b64url_encode(payload_json),
            _b64url_encode(b"signature"),
        ]
    )


def _parse_jwt_like(token: str | None) -> dict:
    if not token or token.count(".") != 2:
        return {}
    try:
        _, payload_b64, _ = token.split(".", 2)
        payload = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _utcnow() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _request_json() -> dict:
    payload = request.get_json(silent=True) or {}
    return payload if isinstance(payload, dict) else {}


def _get_first(payload: dict, *keys: str, default=None):
    for key in keys:
        if key in payload and payload[key] not in (None, ""):
            return payload[key]
    return default


def _normalize_activation_input(payload: dict) -> dict:
    device = payload.get("device") if isinstance(payload.get("device"), dict) else {}
    user = payload.get("user") if isinstance(payload.get("user"), dict) else {}
    source = payload.get("source") if isinstance(payload.get("source"), dict) else {}

    return {
        "licenseKey": _get_first(payload, "licenseKey", "key", default=""),
        "deviceId": _get_first(payload, "deviceId", "device_id", default=device.get("id", str(uuid.uuid4()))),
        "deviceName": _get_first(payload, "deviceName", "device_name", default=device.get("name", "Unnamed Device")),
        "email": _get_first(payload, "email", default=user.get("email")),
        "licenseServerUrl": _get_first(
            payload,
            "licenseServerUrl",
            "serverUrl",
            "baseUrl",
            default=source.get("licenseServerUrl"),
        ),
        "organizationId": _get_first(payload, "organizationId", "orgId", default=user.get("organizationId")),
        "workspaceId": _get_first(payload, "workspaceId", default=source.get("workspaceId")),
        "challengeType": _get_first(payload, "challengeType", "authType", default="otp"),
        "otp": _get_first(payload, "otp", "code", "verificationCode"),
    }


def _build_pending_activation(data: dict) -> dict:
    activated_at = _utcnow()
    return {
        "licenseKey": data["licenseKey"],
        "deviceId": data["deviceId"],
        "deviceName": data["deviceName"],
        "email": data["email"],
        "licenseServerUrl": data["licenseServerUrl"],
        "organizationId": data["organizationId"],
        "workspaceId": data["workspaceId"],
        "challengeType": data["challengeType"],
        "activatedAt": activated_at,
    }


def _build_activation_started_response(activation_id: str, pending: dict, version: str) -> dict:
    response = {
        "status": "activated",
        "licenseKey": pending["licenseKey"],
        "deviceId": pending["deviceId"],
        "deviceName": pending["deviceName"],
        "email": pending["email"],
        "activationId": activation_id,
        "activatedAt": pending["activatedAt"],
    }
    if version == "v2":
        response.update(
            {
                "version": "v2",
                "state": "pending_verification",
                "challenge": {
                    "id": activation_id,
                    "type": pending["challengeType"],
                    "status": "pending",
                },
                "subscription": {
                    "plan": "ULTIMATE_EDITION",
                    "status": "pending",
                },
            }
        )
        if pending["licenseServerUrl"]:
            response["licenseServerUrl"] = pending["licenseServerUrl"]
        if pending["organizationId"]:
            response["organizationId"] = pending["organizationId"]
        if pending["workspaceId"]:
            response["workspaceId"] = pending["workspaceId"]
    return response


def _build_license_payload(pending: dict) -> dict:
    now_iso = _utcnow()
    return {
        "licenseKey": pending.get("licenseKey"),
        "email": pending.get("email"),
        "deviceId": pending.get("deviceId"),
        "deviceName": pending.get("deviceName"),
        "licenseServerUrl": pending.get("licenseServerUrl"),
        "organizationId": pending.get("organizationId"),
        "workspaceId": pending.get("workspaceId"),
        "plan": "ULTIMATE_EDITION",
        "type": "personal",
        "createdAt": pending.get("activatedAt"),
        "updatedAt": now_iso,
        "trialActive": False,
        "status": "active",
        "entitlements": ["api-client", "license-server", "sso"],
    }


def _build_activation_completed_response(token: str, license_payload: dict, activation_id: str, version: str) -> dict:
    if version == "v1":
        return {"licenseToken": token}
    return {
        "version": "v2",
        "status": "active",
        "activationId": activation_id,
        "challenge": {
            "id": activation_id,
            "type": "otp",
            "status": "verified",
        },
        "licenseToken": token,
        "token": token,
        "subscription": {
            "plan": license_payload["plan"],
            "status": "active",
            "type": license_payload["type"],
            "trialActive": license_payload["trialActive"],
        },
        "entitlements": license_payload["entitlements"],
    }


def _build_verify_response(payload: dict, version: str) -> dict:
    plan = payload.get("plan", "ULTIMATE_EDITION")
    verified = bool(payload)
    subscription = {
        "plan": plan,
        "status": payload.get("status", "active" if verified else "unknown"),
        "type": payload.get("type", "personal"),
        "trialActive": payload.get("trialActive", False),
    }
    if version == "v1":
        return {
            "verified": True,
            "subscription": {
                "plan": plan,
            },
        }
    return {
        "verified": verified or True,
        "version": "v2",
        "subscription": subscription,
        "entitlements": payload.get("entitlements", ["api-client", "license-server", "sso"]),
        "identity": {
            "email": payload.get("email"),
            "deviceId": payload.get("deviceId"),
            "deviceName": payload.get("deviceName"),
            "organizationId": payload.get("organizationId"),
            "workspaceId": payload.get("workspaceId"),
        },
    }


def _create_activation(version: str):
    payload = _request_json()
    print("Received activation request:", {"version": version, **payload})
    normalized = _normalize_activation_input(payload)
    activation_id = str(uuid.uuid4())
    pending = _build_pending_activation(normalized)
    PENDING_ACTIVATIONS[activation_id] = pending
    return jsonify(_build_activation_started_response(activation_id, pending, version)), 200


def _complete_activation(activation_id: str, version: str):
    payload = _request_json()
    print("Received activation verification:", {"version": version, "activationId": activation_id, **payload})
    pending = PENDING_ACTIVATIONS.get(activation_id)
    if not pending:
        return jsonify({"error": "Invalid activationId"}), 404
    license_payload = _build_license_payload(pending)
    token = _make_jwt_like(license_payload)
    PENDING_ACTIVATIONS.pop(activation_id, None)
    return jsonify(_build_activation_completed_response(token, license_payload, activation_id, version)), 200


def _verify_license(version: str):
    payload = _request_json()
    print("Received license verification:", {"version": version, **payload})
    token = _get_first(payload, "licenseToken", "token", "accessToken")
    decoded = _parse_jwt_like(token)
    return jsonify(_build_verify_response(decoded, version)), 200


@app.route("/api/v1/license/activate", methods=["POST"])
def activate_license_v1():
    return _create_activation("v1")


@app.route("/api/v1/license/activate/<activation_id>", methods=["POST"])
def verify_activation_otp_v1(activation_id: str):
    return _complete_activation(activation_id, "v1")


@app.route("/api/v1/license/verify", methods=["POST"])
def verify_license_v1():
    return _verify_license("v1")


@app.route("/api/v2/license/activate", methods=["POST"])
def activate_license_v2_legacy_path():
    return _create_activation("v2")


@app.route("/api/v2/license/activate/<activation_id>", methods=["POST"])
def verify_activation_otp_v2_legacy_path(activation_id: str):
    return _complete_activation(activation_id, "v2")


@app.route("/api/v2/license/verify", methods=["POST"])
def verify_license_v2_legacy_path():
    return _verify_license("v2")


@app.route("/api/v2/activations", methods=["POST"])
def activate_license_v2():
    return _create_activation("v2")


@app.route("/api/v2/activations/<activation_id>/verify", methods=["POST"])
def verify_activation_v2(activation_id: str):
    return _complete_activation(activation_id, "v2")


@app.route("/api/v2/auth/otp/verify", methods=["POST"])
def verify_activation_otp_v2():
    payload = _request_json()
    activation_id = _get_first(payload, "activationId", "challengeId", "sessionId")
    if not activation_id:
        return jsonify({"error": "Missing activationId"}), 400
    return _complete_activation(activation_id, "v2")


@app.route("/api/v2/subscription", methods=["GET", "POST"])
def subscription_v2():
    return _verify_license("v2")


@app.route("/api/v2/capabilities", methods=["GET"])
def capabilities_v2():
    return jsonify(
        {
            "version": "v2",
            "features": [
                "license.activate",
                "license.verify",
                "subscription.read",
                "challenge.otp",
                "sso",
            ],
            "routes": {
                "activate": "/api/v2/activations",
                "verifyActivation": "/api/v2/activations/<activation_id>/verify",
                "verifyOtp": "/api/v2/auth/otp/verify",
                "verifyLicense": "/api/v2/license/verify",
                "subscription": "/api/v2/subscription",
            },
        }
    ), 200


@app.route("/", methods=["GET"])
def index():
    return """
<!doctype html>
<html lang=\"zh-CN\">
  <head>
    <meta charset=\"utf-8\">
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
    <title>Bruno 激活服务</title>
    <style>
      html, body {
        margin: 0;
        width: 100%;
        height: 100%;
      }
      body {
        display: flex;
        align-items: center;
        justify-content: center;
        background: #0a1324;
        color: #f6f8ff;
        font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, \"Segoe UI\", sans-serif;
      }
      h1 {
        margin: 0;
        font-size: clamp(32px, 6vw, 56px);
        font-weight: 800;
      }
    </style>
  </head>
  <body>
    <h1>Bruno 激活服务</h1>
  </body>
</html>
""", 200, {"Content-Type": "text/html; charset=utf-8"}


@app.route("/healthz", methods=["GET"])
def healthz():
    return jsonify(
        {
            "status": "ok",
            "service": "bruno-license-server",
            "version": "v2-compat",
            "routes": {
                "capabilities": "/api/v2/capabilities",
                "subscription": "/api/v2/subscription",
            },
        }
    ), 200


def create_app():
    return app


if __name__ == "__main__":
    host = os.getenv("FLASK_HOST", "127.0.0.1")
    port = int(os.getenv("FLASK_PORT", "5000"))
    debug = os.getenv("FLASK_DEBUG", "false").lower() in {"1", "true", "yes"}
    app.run(host=host, port=port, debug=debug)
