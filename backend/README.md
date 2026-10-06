# KRONOS Backend

FastAPI service for network-flow classification. The current detector is a mock that returns the planned model response contract so API consumers can be developed before the XGBoost model is ready.

## Requirements

- Python 3.10 or newer

## Install

From the `backend` directory, create and activate a virtual environment, then install the pinned dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## Run

Start the development server from the `backend` directory:

```powershell
uvicorn app.main:app --reload
```

The API is available at `http://127.0.0.1:8000`. Interactive OpenAPI documentation is at `/docs`.

`GET /health` returns the service status, UTC timestamp, and version. `POST /predict` accepts a JSON object whose keys are feature names and whose values are finite numbers:

```json
{
  "flow_duration": 123.4,
  "packet_rate": 88.2,
  "byte_count": 640.0
}
```

The prediction response includes `prediction`, `confidence`, `top_features`, and `latency_ms`, plus a `request_id` and UTC `timestamp`. The mock adds a short simulated inference delay and randomly selects a supported attack class.

## OTP email delivery

Without `RESEND_API_KEY`, the backend uses DEV MODE and logs OTPs in this format:

```text
[DEV MODE - NO EMAIL SENT] OTP for user@example.com: 123456 (expires in 10 minutes)
```

To send real email, copy `.env.example` to `.env`, set your Resend API key, and set `KRONOS_RESEND_FROM_EMAIL` to an address on a domain you own and have verified in Resend. Restart Uvicorn after changing `.env`. The backend logs the provider's rejection reason if delivery fails.

## Tests

Run the tests from the `backend` directory:

```powershell
python -m pytest
```

## Configuration and logs

Settings use the `KRONOS_` environment-variable prefix and may also be loaded from a `.env` file in the working directory. The default version is `0.1.0`; the default log file is resolved relative to the backend package at `logs/app.log`. Logs are JSON-formatted and written to both the console and a rotating file.