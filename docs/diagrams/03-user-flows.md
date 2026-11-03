# 03 — User flows (API call flows per caller)

service นี้ไม่มีหน้า UI สำหรับผู้ใช้ยกเว้นหน้า unsubscribe; "user flow" จึงเป็นลำดับการเรียก API ของแต่ละ caller

## Flow A — caller ส่งข้อความและติดตามสถานะ

```mermaid
flowchart TD
  A1["Get token from identity: aud communication-api, scope messages:write messages:read"] --> A2["POST /v1/messages + Idempotency-Key"]
  A2 -->|"202"| A3["Store returned id"]
  A2 -->|"401 / 403"| AX["Fix token or scope"]
  A2 -->|"422 Invalid message"| AY["Fix payload"]
  A2 -->|"409 Idempotency conflict"| AZ["Same key, different payload: pick a new key"]
  A2 -->|"429 Outbox capacity reached"| AW["Back off; exact replays still succeed"]
  A2 -->|"503 Delivery unavailable"| AV["Channel adapter not configured"]
  A3 --> A4["GET /v1/messages/{id}"]
  A4 --> A5{"status"}
  A5 -->|"queued / leased / sending"| A4
  A5 -->|"delivered"| A6["Accepted by provider (not proof of receipt)"]
  A5 -->|"dead / suppressed"| A7["Terminal: do not resend blindly"]
  A5 -->|"uncertain"| A8["Reconcile with provider logs before any new send"]
```

## Flow B — caller บันทึก opt-out

```mermaid
flowchart TD
  B1["POST /v1/opt-outs channel recipient source event_id (scope opt-outs:write)"] --> B2{"result"}
  B2 -->|"201 created"| B3["Later sends to that hash are suppressed"]
  B2 -->|"200 existing"| B3
  B2 -->|"409"| B4["event_id already bound to another channel or address"]
  B2 -->|"422"| B5["Invalid channel / recipient / source, or reserved prefix unsubscribe: or provider:"]
```

## Flow C — recipient กด unsubscribe ในอีเมล

```mermaid
flowchart TD
  C1["Email carries List-Unsubscribe and List-Unsubscribe-Post headers"] --> C2{"Client type"}
  C2 -->|"Mail client one-click"| C4["POST /v1/unsubscribe?t= body List-Unsubscribe=One-Click"]
  C2 -->|"Browser"| C3["GET /v1/unsubscribe?t= shows confirm page"]
  C3 --> C4
  C4 -->|"200"| C5["You are unsubscribed: opt-out email.list_unsubscribe"]
  C4 -->|"400"| C6["Invalid request body"]
  C4 -->|"404"| C7["Link not valid"]
```

## Flow D — operator ติดตั้งและรัน

```mermaid
flowchart LR
  D1["python -m platform_communication migrate (DDL role)"] --> D2["Grant runtime role table privileges"]
  D2 --> D3["python -m platform_communication serve"]
  D2 --> D4["python -m platform_communication worker + COMMUNICATION_WORKSPACE_ID"]
  D3 --> D5["GET /readyz 200"]
```

Sources: `src/platform_communication/app.py`, `src/platform_communication/store.py`, `src/platform_communication/keys.py`, `src/platform_communication/adapters.py` (`ResendAdapter`, `unsubscribe_link`), `src/platform_communication/__main__.py`, `docs/runtime.md` (Staging plan, Outbox API and workers, Keyed hashes and one-click unsubscribe)

## Open questions

- ยังไม่มี consumer จริงใน repo; Flow A คือสัญญาตามโค้ด ไม่ใช่ journey ที่วัดจาก production
- `COMMUNICATION_PUBLIC_URL` ตั้งใน production แล้วหรือไม่ (ถ้าไม่ตั้ง อีเมลจะไม่มี List-Unsubscribe header และ Flow C ไม่เกิด)
