# Bruno Self-Hosted License Server

A self-hosted license activation server for [Bruno](https://github.com/usebruno/bruno/) API client.

> **⚠️ DISCLAIMER**: This project is for **development and educational purposes only**. If you like Bruno and use it professionally, please [purchase a legitimate license](https://www.usebruno.com/pricing) to support the developers.

## Overview

This project now provides a compatibility layer for both legacy v1 flows and newer v2-style flows.
It is intended to make local testing easier when Bruno clients or related integrations expect different license endpoints.

Supported flows:

- Legacy v1 endpoints under `/api/v1/license/*`
- v2 compatibility endpoints under `/api/v2/*`
- OTP-style activation completion
- subscription and capability discovery responses for v2-style clients

## Installation

Clone the repository and create a virtual environment:

```bash
git clone https://github.com/BearstOzawa/BrunoServer.git && cd BrunoServer
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
```

## Usage

Run the server with default settings (`127.0.0.1:5000`):

```bash
. .venv/bin/activate
python server.py
```

When deployed, you can also open the root path `/` to see a simple status page and use `/healthz` for machine-readable health checks.

Configure the server using environment variables:

```bash
export FLASK_HOST=0.0.0.0
export FLASK_PORT=8080
export FLASK_DEBUG=true
```

## Supported Endpoints

### Utility

- `GET /`
- `GET /healthz`

### v1

- `POST /api/v1/license/activate`
- `POST /api/v1/license/activate/<activation_id>`
- `POST /api/v1/license/verify`

### v2 compatibility

- `POST /api/v2/activations`
- `POST /api/v2/activations/<activation_id>/verify`
- `POST /api/v2/auth/otp/verify`
- `POST /api/v2/license/activate`
- `POST /api/v2/license/activate/<activation_id>`
- `POST /api/v2/license/verify`
- `GET|POST /api/v2/subscription`
- `GET /api/v2/capabilities`

## Example Requests

### v1 activation

```bash
curl -s http://127.0.0.1:5000/api/v1/license/activate \
  -H 'Content-Type: application/json' \
  -d '{
    "licenseKey": "demo-key",
    "deviceId": "dev-1",
    "deviceName": "MacBook",
    "email": "demo@example.com",
    "licenseServerUrl": "http://127.0.0.1:5000"
  }'
```

### v2 activation

```bash
curl -s http://127.0.0.1:5000/api/v2/activations \
  -H 'Content-Type: application/json' \
  -d '{
    "key": "demo-v2-key",
    "device": {"id": "dev-2", "name": "Studio"},
    "user": {"email": "v2@example.com", "organizationId": "org-1"},
    "source": {"licenseServerUrl": "http://127.0.0.1:5000", "workspaceId": "ws-1"},
    "challengeType": "otp"
  }'
```

### v2 OTP verification

```bash
curl -s http://127.0.0.1:5000/api/v2/auth/otp/verify \
  -H 'Content-Type: application/json' \
  -d '{
    "activationId": "<activation-id>",
    "code": "654321"
  }'
```

### v2 capabilities

```bash
curl -s http://127.0.0.1:5000/api/v2/capabilities
```

## Configure Bruno

To use this server with Bruno:

1. Start the server locally
2. In Bruno, configure the license server URL to point to your local server
3. Use the endpoint set that matches the client behavior you are testing

Default local URL:

- `http://127.0.0.1:5000`

## Open Source Publishing Notes

If you plan to publish this as a separate open-source project, it is recommended to:

- rename the repository to reflect its compatibility/testing focus
- keep the disclaimer and non-affiliation notice
- avoid implying official Bruno support or endorsement
- document clearly that the v2 layer is a compatibility implementation

## Legal Notice

This software is provided for educational and development purposes only. The authors do not condone piracy or license violations.

**Please support the Bruno project** by purchasing a legitimate license if you:

- Use Bruno for professional/commercial work
- Want to support ongoing development
- Need official support

Visit [Bruno's official website](https://www.usebruno.com/) to learn more and purchase a license.

## Disclaimer

This project is not affiliated with, endorsed by, or connected to the Bruno project or its developers. All trademarks and copyrights belong to their respective owners.
