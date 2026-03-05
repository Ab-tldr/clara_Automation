import argparse
from typing import Any, Dict

from utils import read_json, write_json, ensure_dir


def _val_or_unknown(v: Any, label: str) -> str:
    if v is None:
        return f"UNKNOWN ({label})"
    if isinstance(v, str) and not v.strip():
        return f"UNKNOWN ({label})"
    if isinstance(v, list) and len(v) == 0:
        return f"UNKNOWN ({label})"
    return str(v)


def build_prompt(memo: Dict) -> str:
    company = _val_or_unknown(memo.get("company_name"), "company_name")
    tz = _val_or_unknown(memo.get("business_hours", {}).get("timezone"), "timezone")
    days = memo.get("business_hours", {}).get("days", [])
    start = memo.get("business_hours", {}).get("start", "")
    end = memo.get("business_hours", {}).get("end", "")
    bh = _val_or_unknown(f"{days} {start}-{end}".strip(), "business_hours")
    addr = _val_or_unknown(memo.get("office_address"), "office_address")
    emergencies = memo.get("emergency_definition") or []
    emergencies_str = _val_or_unknown(", ".join(emergencies), "emergency_definition")

    office_route = memo.get("non_emergency_routing_rules", {}).get("office_hours", "")
    after_route = memo.get("non_emergency_routing_rules", {}).get("after_hours", "")

    timeout = memo.get("call_transfer_rules", {}).get("transfer_timeout_seconds")

    # Minimal but compliant script
    prompt = f"""
You are Clara, an AI phone assistant for {company}.
Be professional, calm, and efficient.

Context:
- Timezone: {tz}
- Business hours: {bh}
- Office address (if needed): {addr}
- Emergency triggers (if known): {emergencies_str}

Do NOT mention tools, functions, webhooks, or internal systems to the caller.
Ask only what is needed for routing and dispatch.

OFFICE HOURS FLOW:
1) Greet the caller and identify the business.
2) Ask the purpose of the call.
3) Collect caller name and callback number.
4) If the caller describes an emergency:
   - Collect name, callback number, address, and a brief issue summary.
   - Attempt to transfer according to emergency routing rules if available.
   - If you cannot transfer or routing is unknown, take a message and confirm urgent follow-up.
5) If non-emergency:
   - Route/transfer if a destination is known: "{office_route if office_route else "UNKNOWN (office-hours routing)"}"
   - If routing is unknown, collect brief details and confirm follow-up.
6) If transfer is attempted and fails:
   - Apologize, collect name/number and key details, and confirm next steps.
7) Ask if they need anything else.
8) Close the call politely.

AFTER HOURS FLOW:
1) Greet the caller and state you are answering after hours.
2) Ask the purpose of the call.
3) Confirm whether it is an emergency.
4) If emergency:
   - Immediately collect: name, callback number, service address, and a brief description.
   - Attempt transfer per emergency routing if available.
   - If transfer fails or routing is unknown:
     - Apologize and assure someone will follow up as soon as possible.
5) If non-emergency:
   - Collect name, callback number, and brief request details.
   - Confirm follow-up during business hours.
6) Ask if they need anything else.
7) Close the call.

TRANSFER & FALLBACK PROTOCOL:
- If a transfer is configured, attempt it.
- Transfer timeout (if known): {timeout if timeout is not None else "UNKNOWN (transfer timeout)"} seconds.
- If transfer fails: apologize, collect the minimum required details, and confirm follow-up.
""".strip()

    return prompt


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--memo_path", required=True)
    ap.add_argument("--out_path", required=True)
    ap.add_argument("--version", required=True, choices=["v1", "v2"])
    args = ap.parse_args()

    memo = read_json(args.memo_path)
    prompt = build_prompt(memo)

    company = memo.get("company_name") or memo.get("account_id")
    spec = {
        "agent_name": f"Clara - {company}",
        "voice_style": {"preset": "professional_calm", "speed": "normal"},
        "version": args.version,
        "key_variables": {
            "timezone": memo.get("business_hours", {}).get("timezone", ""),
            "business_hours": memo.get("business_hours", {}),
            "office_address": memo.get("office_address", ""),
            "emergency_definition": memo.get("emergency_definition", []),
            "emergency_routing_rules": memo.get("emergency_routing_rules", {}),
            "non_emergency_routing_rules": memo.get("non_emergency_routing_rules", {})
        },
        "system_prompt": prompt,
        "call_transfer_protocol": {
            "destinations": [],  # placeholder unless explicitly known
            "timeout_seconds": memo.get("call_transfer_rules", {}).get("transfer_timeout_seconds"),
            "retry_policy": {
                "max_retries": memo.get("call_transfer_rules", {}).get("max_retries"),
                "retry_delay_seconds": memo.get("call_transfer_rules", {}).get("retry_delay_seconds"),
            }
        },
        "fallback_protocol": {
            "if_transfer_fails": "Apologize, collect caller name and callback number, collect key details, and confirm follow-up.",
            "capture_fields": ["name", "callback_number", "address_if_emergency", "issue_summary"]
        },
        "tool_invocation_placeholders": {
            "create_job": "PLACEHOLDER",
            "lookup_customer": "PLACEHOLDER"
        },
        "notes": "Do not mention tools/functions to the caller."
    }

    ensure_dir(args.out_path.rsplit("/", 1)[0])
    write_json(args.out_path, spec)


if __name__ == "__main__":
    main()