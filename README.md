# Voice CRM (MVP) with a WebRTC softphone

A one-page CRM for inbound and outbound calls, with a SIP/WebRTC softphone that runs in the browser.

```
Browser (React CRM)
   ├── SIP over WSS + WebRTC audio ──► FreePBX (192.168.1.222) ──► existing routing ──► ElevenLabs / telecom
   └── HTTP REST ──► FastAPI ──► SQLite        (CRM data only, no audio ever passes through it)
```

FreePBX, the SIP trunks, the ElevenLabs integration and PBX routing already exist. This app only:

* registers a WebRTC extension in the browser,
* places and receives calls through that extension,
* logs the calls, customers, bookings and outcomes in SQLite.

While you are on the same LAN as FreePBX, no VPN is needed. The browser connects straight to `wss://192.168.1.222:8089/ws`.

---

## 1. Quick start (mock mode, no PBX needed)

### Backend (terminal 1)

macOS / Linux:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

Windows (PowerShell):

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload --port 8000
```

### Frontend (terminal 2)

```bash
cd frontend
npm install
cp .env.example .env        # Windows: copy .env.example .env
npm run dev
```

Open **http://localhost:5173**. The API docs are at http://localhost:8000/docs.

> Use `localhost`, not a LAN IP, to open the CRM. Browsers only allow microphone access on `https://` or `http://localhost`.

---

## 2. Database

* SQLite file: `backend/voice_crm.db`. It is created automatically on first start. Relative `DATABASE_URL` paths resolve against `backend/`.
* **Initialize:** starting the backend creates the tables. Alternatively run `python -m app.seed`.
* **Seed:** demo data is inserted automatically when the database is empty (`AUTO_SEED=true`): 6 brands, 7 demo queues, 10 customers, 10 inbound calls, 10 outbound calls and 5 bookings.
* **Reset and re-seed:** run `python -m app.seed --reset` (from `backend/`), or `POST /api/testing/reset`.
* There is no migration tool in this MVP. On start-up, new nullable columns are added to existing tables automatically (logged as `Added column ...`), so an existing `voice_crm.db` keeps its data. For anything bigger, delete `voice_crm.db` and restart.
* An existing database gets no demo queues. Run `python -m app.seed --reset` if you want them for mock demos. Real queues are created from the first call that carries `X-Queue`.

---

## 3. Mock mode (`VITE_SIP_MODE=mock`)

Mock mode needs no network connection to the PBX. The softphone pretends to be registered as extension 9001. Every call is still logged in the real backend and database.

**Simulate an incoming call:** click **Simulate Incoming Call** under the softphone.

1. The backend picks a random caller (`GET /api/testing/random-caller`). About 70% are existing customers.
2. The incoming-call popup shows the number, the matched customer (or *Unknown Customer*), the brand, the queue, the IVR path and how long the caller has been waiting. These are the same values FreePBX will send in real mode (see section 5).
3. Click **Answer**. The timer starts, and you can use Mute, Hold and Hang Up.
4. After hang-up, the **Call Wrap-up** panel lets you choose an outcome, add notes, **Save outcome** and **Book appointment**.
5. For an unknown caller, use **Create Customer** in the right panel. Earlier calls from that number are linked to the new customer automatically.

**Simulate an outbound call:** type a number (or click Dial / Call back / Redial in a table), pick a brand and purpose, then click **Call**. The call moves through Connecting → Calling → Ringing → On Call. Hang up to complete it. The remote side hangs up after 60 seconds if you don't.

Test numbers (matched on the last digits):

| Number ends with | Result |
|---|---|
| `0000` | fails (503, logged as `failed`) |
| `1111` | rings, no answer (logged as `missed`) |
| `2222` | declined (486, logged as `rejected`) |
| anything else | answered |

If you simulate an incoming call while already on a call, it is auto-rejected (486) and logged as `missed`. Real mode behaves the same way.

---

## 4. Switching to real SIP/WebRTC (`VITE_SIP_MODE=real`)

Edit `frontend/.env`, then restart `npm run dev`. Vite reads `.env` only at startup.

```ini
VITE_SIP_MODE=real
VITE_SIP_WSS_URL=wss://192.168.1.222:8089/ws    # FreePBX WSS endpoint
VITE_SIP_DOMAIN=192.168.1.222
VITE_SIP_URI=                                   # optional; defaults to sip:<username>@<domain>
VITE_SIP_USERNAME=<webrtc extension>            # from the PBX owner
VITE_SIP_PASSWORD=<extension secret>            # from the PBX owner
VITE_SIP_AUTHORIZATION_USERNAME=                # only if different from the extension
VITE_SIP_DIAL_FORMAT=raw                        # raw | e164 | e164_no_plus | national
VITE_SIP_DIAL_PREFIX=                           # e.g. 9 if an outbound route needs a prefix
```

Real mode never silently falls back to mock. If the configuration is incomplete or the PBX can't be reached, the softphone shows the exact problem and a **Reconnect** button.

### FreePBX side (done by the PBX owner)

* A PJSIP extension with **WebRTC enabled**: Enable AVPF, ICE support, Media Encryption DTLS-SRTP, and transport `0.0.0.0-wss`.
* The built-in HTTP server with TLS enabled (Settings → Advanced Settings → `HTTPS Bind Port` / `Enable TLS for the mini-HTTP Server`). The default WSS URL is `wss://<pbx>:8089/ws`.
* A certificate the browser trusts.
* RTP ports (default 10000–20000/UDP) reachable from the agent's PC.
* Routing:
  * inbound DIDs → this extension (or a ring group containing it);
  * outbound routes that accept the number format you configure.

### Dial format

`normalizeDialNumber()` in `frontend/src/webrtc/config.ts` converts what the agent typed into what FreePBX expects. Set `VITE_SIP_DIAL_FORMAT` to match your outbound routes. With country code `971`:

| Format | Example result |
|---|---|
| `raw` | `+971501234567` |
| `e164` | `+971501234567` |
| `e164_no_plus` | `971501234567` |
| `national` | `0501234567` |

Extensions with 6 digits or fewer are always dialed as typed.

### STUN / TURN

These are usually not needed on the same LAN. Over a VPN or across NAT, set `VITE_STUN_URL` (e.g. `stun:stun.l.google.com:19302`). If audio is one-way or missing, set `VITE_TURN_URL`, `VITE_TURN_USERNAME` and `VITE_TURN_PASSWORD`.

### Call tones

* **Outbound:** while the call rings, the browser plays a ringback tone (400 Hz, UAE cadence). If FreePBX sends its own ringback as early media (SIP `183` with audio), that audio is played and the local tone stops once it is actually heard.
* **Inbound:** a ringtone plays until the call is answered, rejected or missed. If the CRM tab is in the background, a desktop notification is shown too (the browser asks for permission on your first click).

Tones need one click on the page first (browser autoplay policy).

### Microphone test

Go to **Settings → Test microphone**. It asks for permission and shows a live input level bar for 6 seconds.

### Diagnosing registration failures

| Message in the softphone | Likely cause and what to try |
|---|---|
| *SIP configuration incomplete* | A `VITE_SIP_*` value is missing. Fix `frontend/.env` and restart `npm run dev`. |
| *Cannot open WebSocket to wss://…* | The PBX is unreachable, port 8089 is closed, or the TLS certificate isn't trusted. Open `https://192.168.1.222:8089/ws` in the same browser, accept the certificate, then click **Reconnect**. |
| *Registration rejected: 401/403* | Wrong extension, password or authorization username. |
| *Registration rejected: 404* | The extension doesn't exist on that SIP domain. |
| *No answer to REGISTER* | Wrong `VITE_SIP_DOMAIN`, or a firewall is dropping SIP. |
| *Connection to the PBX lost* | The network or VPN dropped. Click **Reconnect**. |
| *Microphone permission denied* | Allow the microphone in the browser's site settings. Use `http://localhost` or HTTPS. |
| *Codec mismatch (488)* | Enable Opus or G.711 (ulaw/alaw) on the extension. |
| *Media connection failed (ICE)* | RTP ports are blocked or NAT is in the way. Configure STUN/TURN and check the RTP range. |
| *Browser blocked audio playback* | Click **Enable audio** (autoplay policy). |

The browser console (`[sip.js …]` lines) has more detail. Authorization headers are redacted, and SIP passwords are never logged.

---

## 5. Brands, queues and IVR

There are 6 seeded brands with **fake** DIDs (`+9714200010x`). Set the real ones with:

```bash
curl -X PATCH http://localhost:8000/api/brands/1 -H 'Content-Type: application/json' \
     -d '{"phone_number": "+9714XXXXXXX", "elevenlabs_agent_id": "agent_..."}'
```

* **Outbound:** the agent picks the brand in the softphone.
* **Inbound:** all brands share one public number (8000600), so the brand can't be taken from the DID alone. The FreePBX dialplan labels the call before it enters the queue, and the softphone reads these INVITE headers:

| Header | Example | Used for |
|---|---|---|
| `X-Brand` | `City Doctor` | Brand. Matched loosely, so `CityDoctor` also works. |
| `X-Queue` | `CD-Booking` | Queue. Unknown names are registered automatically on their first call. |
| `X-IVR-Path` | `ivr-7>ivr-8` | Shown in the popup and stored on the call. |
| `X-Called-Number` | `8000600` | Number the customer dialled (also tried: `X-DID`, `P-Called-Party-ID`, `Diversion`, `To`). |
| `X-Queue-Start` | `1791280000` | Unix time (`${EPOCH}`) the caller entered the queue, used for the wait time. |

Brand order: `X-Brand`, then the queue's brand, then the called DID. Every header is optional. Without them the call still works and shows *Unknown brand*. The browser console prints `[softphone] incoming call routing {...}` for every call, so you can check what arrived.

### FreePBX dialplan (done by the PBX admin)

FreePBX copies the `SIPHEADERS` hash onto the INVITE it sends to the extension (`func-apply-sipheaders`). Add this to `/etc/asterisk/extensions_custom.conf`:

```ini
; Label the call for the CRM, then return. ARG1 = brand, ARG2 = queue name.
[crm-labels]
exten => s,1,Set(HASH(__SIPHEADERS,X-Brand)=${ARG1})
 same => n,Set(HASH(__SIPHEADERS,X-Queue)=${ARG2})
 same => n,Set(HASH(__SIPHEADERS,X-Called-Number)=${FROM_DID})
 same => n,Set(HASH(__SIPHEADERS,X-IVR-Path)=${IVR_CONTEXT_${IVR_CONTEXT}}>${IVR_CONTEXT})
 same => n,Set(HASH(__SIPHEADERS,X-Queue-Start)=${EPOCH})
 same => n,Return()

; One entry per IVR option that leads to a queue.
[crm-route]
exten => cd-booking,1,Gosub(crm-labels,s,1(City Doctor,CD-Booking))
 same => n,Goto(ext-queues,400,1)        ; 400 = the FreePBX queue number
```

Then, in FreePBX:

1. **Admin → Custom Destinations:** add one per entry, e.g. target `crm-route,cd-booking,1`, description *CD Booking*.
2. **Applications → IVR:** point the option (e.g. ivr-8, key 1) at that custom destination instead of the extension or queue.
3. Click **Apply Config** (or run `fwconsole reload`).
4. Check it: in the Asterisk CLI run `pjsip set logger on`, call 8000600, and look for `X-Brand` / `X-Queue` in the INVITE sent to the agent's extension.

Keep the PBX and agent PCs on NTP. The wait time compares the PBX clock (`X-Queue-Start`) with the browser clock. Values more than 6 hours old or more than 60 seconds in the future are ignored, and the wait then counts from when the agent's phone started ringing.

### Queues in the CRM

* `GET /api/queues` lists them. A queue registered automatically takes its brand from the first call's brand. Set the brand, department or FreePBX number with `PATCH /api/queues/{id}`, or create queues up front with `POST /api/queues`:

```bash
curl -X POST http://localhost:8000/api/queues -H 'Content-Type: application/json' \
     -d '{"name": "CD-Booking", "brand_id": 1, "department": "Booking", "number": "400"}'
```

* `name` must match what FreePBX sends in `X-Queue`. Matching ignores case, spaces and dashes.
* **Wait time** of an inbound call: from `X-Queue-Start` (or, without it, from when the INVITE reached the browser) until the agent answered, or until the caller hung up.
* **Reports** (dashboard → Reports) show per queue or per brand: calls, answered, missed, answer rate, average wait of answered calls, longest wait (including abandoned calls), average talk time and bookings. They use the dashboard filters. Clicking a row filters the dashboard by that queue or brand.

---

## 6. ElevenLabs data

ElevenLabs is integrated with FreePBX, not with this app. The CRM only stores optional fields, which can be filled in later:

```bash
curl -X PATCH http://localhost:8000/api/calls/42 -H 'Content-Type: application/json' -d '{
  "elevenlabs_conversation_id": "conv_...", "summary": "...", "transcript": "AI: ...\nCustomer: ...",
  "recording_url": "https://..."}'
```

---

## 6b. AI call summaries (Azure OpenAI)

Set in `backend/.env` and restart the backend:

```ini
AZURE_API_KEY=<key from Azure AI Foundry>
Azure_open_ai_endpoint=https://<resource>.services.ai.azure.com/api/projects/<project>
AZURE_OPENAI_DEPLOYMENT=gpt-4.1-mini        # deployment name in Azure AI Foundry
AZURE_OPENAI_API_VERSION=2024-10-21
```

A project endpoint is accepted (the `/api/projects/...` part is stripped to the resource URL).
An **AI summary** button then appears next to *Save outcome* (call wrap-up panel and Call Details).
It sends the call metadata, the agent's notes and the transcript (if any) to Azure OpenAI - never audio, never the
key to the browser - saves the summary on the call and pre-selects the suggested outcome for the agent to confirm.

API: `GET /api/ai/status`, `POST /api/calls/{id}/ai-summary` (`{"notes": "..."}` optional).

## 7. Environment variables

### `backend/.env`

| Variable | Default | Purpose |
|---|---|---|
| `APP_ENV` | `development` | Label shown in `/api/health` |
| `APP_HOST` / `APP_PORT` | `0.0.0.0` / `8000` | For reference; pass `--host/--port` to uvicorn |
| `DATABASE_URL` | `sqlite:///./voice_crm.db` | Resolves to `backend/voice_crm.db` |
| `FRONTEND_URL` | `http://localhost:5173` | Added to CORS |
| `CORS_ORIGINS` | `http://localhost:5173,…` | Allowed browser origins |
| `LOG_LEVEL` | `INFO` | Python logging level |
| `AUTO_SEED` | `true` | Seed demo data into an empty database |
| `AZURE_API_KEY` / `Azure_open_ai_endpoint` / `AZURE_OPENAI_DEPLOYMENT` / `AZURE_OPENAI_API_VERSION` | empty / empty / `gpt-4.1-mini` / `2024-10-21` | Optional AI call summaries (Azure OpenAI) |

No SIP or VPN credentials belong in the backend.

### `frontend/.env`

| Variable | Purpose |
|---|---|
| `VITE_API_BASE_URL` | Backend URL (`http://localhost:8000`). Leave empty to use the Vite proxy. |
| `VITE_SIP_MODE` | `mock` or `real` |
| `VITE_SIP_WSS_URL` | e.g. `wss://192.168.1.222:8089/ws` |
| `VITE_SIP_DOMAIN` | e.g. `192.168.1.222` |
| `VITE_SIP_URI` | `sip:<ext>@<domain>` (optional) |
| `VITE_SIP_USERNAME` / `VITE_SIP_PASSWORD` | WebRTC extension credentials |
| `VITE_SIP_AUTHORIZATION_USERNAME` | Only if it differs from the username |
| `VITE_SIP_DISPLAY_NAME` | Caller display name |
| `VITE_SIP_CONTACT_URI` | Optional custom Contact |
| `VITE_SIP_DIAL_FORMAT` / `VITE_SIP_DIAL_PREFIX` / `VITE_DEFAULT_COUNTRY_CODE` | Dial-number normalization |
| `VITE_STUN_URL`, `VITE_TURN_URL`, `VITE_TURN_USERNAME`, `VITE_TURN_PASSWORD` | ICE servers |

---

## 8. API

| Method | Path | Notes |
|---|---|---|
| GET | `/api/health` | |
| GET | `/api/stats` | Total, inbound, outbound, answered, missed, failed, bookings, average duration, average wait. Accepts the call filters. |
| GET | `/api/stats/breakdown?by=queue\|brand` | Report rows per queue (inbound only) or per brand. Accepts the call filters. |
| GET | `/api/brands` | |
| GET | `/api/queues` | `active_only`, `brand_id` |
| POST | `/api/queues` | `{name, brand_id?, department?, number?}`; `name` = FreePBX `X-Queue` value |
| PATCH | `/api/queues/{id}` | Brand, department, number, name or active flag |
| PATCH | `/api/brands/{id}` | DID, ElevenLabs agent ID, active flag |
| GET | `/api/customers?search=` | |
| GET | `/api/customers/{id}` | |
| GET | `/api/customers/by-phone/{phone}` | Customer plus recent calls and bookings. Returns 404 for an unknown caller. Tolerant of number format. |
| POST | `/api/customers` | |
| PATCH | `/api/customers/{id}` | |
| GET | `/api/calls` | Filters: `direction`, `status`, `outcome`, `brand_id`, `queue_id`, `search`, `date_from`, `date_to`, `limit` |
| POST | `/api/calls` | Softphone logs a call (`ringing` inbound / `calling` outbound). Inbound also sends `brand_name`, `queue_name`, `ivr_path` and `queue_entered_at` from the INVITE headers. |
| GET | `/api/calls/{id}` | |
| PATCH | `/api/calls/{id}` | Status updates and ElevenLabs fields. `answered_at`, `ended_at` and duration are filled automatically. |
| POST | `/api/calls/{id}/outcome` | `{ "outcome": "booked", "notes": "..." }` |
| GET | `/api/availability?date=2026-10-05&service=doctor` | Returns `["09:00","10:30","14:00","16:30"]` minus booked slots |
| GET | `/api/bookings` | |
| POST | `/api/bookings` | `{customer_id, call_id?, service, appointment_date, appointment_time}`. Linking a call sets its outcome to `booked`. |
| GET | `/api/bookings/{id}` | Accepts `7` or `BK-1007` |
| PUT | `/api/bookings/{id}` | |
| DELETE | `/api/bookings/{id}` | |
| GET | `/api/testing/random-caller` | Used by Simulate Incoming Call |
| POST | `/api/testing/reset` | Drops and re-seeds demo data |

Call statuses: `ringing`, `calling`, `answered`, `completed`, `missed`, `rejected`, `failed`, `transferred`.

Outcomes: `booked`, `inquiry`, `interested`, `not_interested`, `callback`, `transferred`, `completed`, `failed`.

---

## 9. Code map

```
backend/app/
  main.py               FastAPI app, CORS, startup (create tables + auto-seed)
  config.py, database.py, models.py, schemas.py, seed.py
  routers/              calls.py (+ /api/stats, /api/stats/breakdown), customers.py, bookings.py, brands.py,
                        queues.py, testing.py
  services/             call_service.py (filters, stats, lifecycle rules), booking_service.py
frontend/src/
  webrtc/
    types.ts            Call/registration state machines and the SipClient interface
    config.ts           ONLY place SIP settings are read, plus normalizeDialNumber()
    SipClient.ts        MockSipClient and RealSipClient (SIP.js): connect, disconnect, call, answer,
                        reject, hangup, mute, unmute, hold, resume, DTMF, events
    SipContext.tsx      React provider and useSip(); components never import SIP.js
  lib/useCallLogger.ts  Maps softphone events to POST/PATCH /api/calls
  lib/routing.ts        Brand/queue of a live call (X-Brand > queue's brand > DID)
  components/           SoftPhone, DialPad, IncomingCallModal, ActiveCallPanel, CustomerPanel,
                        InboundCallsTable, OutboundCallsTable, CallDetailsModal, BookingModal, ReportsSection, ...
```

---

## 10. Security notes (MVP)

* There is no login in this MVP. Run it on a trusted network only.
* **Every `VITE_*` value is compiled into the JavaScript bundle.** Static SIP credentials in `frontend/.env` are fine for development but must not ship in a public build. For production, replace `getSipConfig()` in `frontend/src/webrtc/config.ts` with a backend call that returns short-lived, per-agent credentials. Nothing else needs to change.
* SIP and VPN credentials are never stored in SQLite, never shown in the UI (Settings shows only "configured"), and never logged.
* `.env` files and `*.db` files are git-ignored.
