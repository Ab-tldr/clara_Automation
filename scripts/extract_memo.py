import argparse
import re
from typing import Dict, List, Optional, Tuple

from utils import now_iso, read_text, extract_account_id, file_hash


# -----------------------------
# Simple evidence-based helpers
# -----------------------------
def _find_first(patterns: List[re.Pattern], text: str) -> Optional[str]:
    for p in patterns:
        m = p.search(text)
        if m:
            return m.group(1).strip()
    return None


def _find_all(pattern: re.Pattern, text: str) -> List[str]:
    out = []
    for m in pattern.finditer(text):
        val = (m.group(1) or "").strip()
        if val:
            out.append(val)
    # de-dup preserving order
    seen = set()
    uniq = []
    for x in out:
        k = x.lower()
        if k not in seen:
            uniq.append(x)
            seen.add(k)
    return uniq


def _normalize_days(raw: str) -> List[str]:
    # very lightweight; only if transcript explicitly includes day words
    days_map = {
        "monday": "Mon", "mon": "Mon",
        "tuesday": "Tue", "tue": "Tue", "tues": "Tue",
        "wednesday": "Wed", "wed": "Wed",
        "thursday": "Thu", "thu": "Thu", "thurs": "Thu",
        "friday": "Fri", "fri": "Fri",
        "saturday": "Sat", "sat": "Sat",
        "sunday": "Sun", "sun": "Sun",
    }
    found = []
    for k, v in days_map.items():
        if re.search(rf"\b{k}\b", raw, re.IGNORECASE):
            found.append(v)
    # order in week
    order = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]
    found = sorted(set(found), key=lambda d: order.index(d))
    return found


def extract_demo_memo(transcript: str) -> Tuple[Dict, List[str]]:
    """
    Returns (fields, unknown_questions)
    """
    unknowns: List[str] = []
    t = transcript

    # Company name (common phrasing: "We are <X>", "This is <X>")
    company = _find_first([
        re.compile(r"\bwe are\s+([A-Z][\w &.'-]{2,})", re.IGNORECASE),
        re.compile(r"\bcompany(?: name)? is\s+([A-Z][\w &.'-]{2,})", re.IGNORECASE),
    ], t)

    # Address (very naive: looks for "address is ..." or "located at ..."
    address = _find_first([
        re.compile(r"\baddress is\s+(.+?)(?:\.|\n|$)", re.IGNORECASE),
        re.compile(r"\blocated at\s+(.+?)(?:\.|\n|$)", re.IGNORECASE),
    ], t)

    # Business hours / timezone (only if explicitly stated)
    # Examples caught: "we're open 8 to 5", "open from 8am to 5pm"
    bh_raw = _find_first([
        re.compile(r"\bopen (?:from )?(.+?)(?:\.|\n|$)", re.IGNORECASE),
        re.compile(r"\bbusiness hours (?:are|is)\s+(.+?)(?:\.|\n|$)", re.IGNORECASE),
        re.compile(r"\bhours (?:are|is)\s+(.+?)(?:\.|\n|$)", re.IGNORECASE),
    ], t)

    tz = _find_first([
        re.compile(r"\btime zone(?: is)?\s+([A-Za-z/_+-]{3,})", re.IGNORECASE),
        re.compile(r"\btimezone(?: is)?\s+([A-Za-z/_+-]{3,})", re.IGNORECASE),
    ], t)

    days = _normalize_days(bh_raw or "")
    start_time = ""
    end_time = ""
    if bh_raw:
        # try capture time ranges like "8am to 5pm" / "8:00 - 17:00"
        m = re.search(r"(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\s*(?:to|-|–)\s*(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)",
                      bh_raw, re.IGNORECASE)
        if m:
            start_time = m.group(1).strip()
            end_time = m.group(2).strip()

    # Services supported: look for "we do X, Y and Z" / "we handle"
    # Also capture obvious trade keywords if listed.
    services = []
    services_line = _find_first([
        re.compile(r"\bwe (?:do|handle|support)\s+(.+?)(?:\.|\n|$)", re.IGNORECASE),
        re.compile(r"\bour services include\s+(.+?)(?:\.|\n|$)", re.IGNORECASE),
    ], t)
    if services_line:
        parts = re.split(r",|/| and ", services_line, flags=re.IGNORECASE)
        services = [p.strip(" .;:") for p in parts if p.strip(" .;:")]

    # Emergency triggers: look for explicit "emergency" examples
    # captures phrases after "emergency" mentions
    emergency_examples = _find_all(
        re.compile(r"\bemergency(?: calls?)?(?: like| example| such as|:)?\s*(.+?)(?:\.|\n|$)", re.IGNORECASE),
        t
    )
    emergency_triggers = []
    for ex in emergency_examples:
        for p in re.split(r",|/| and ", ex, flags=re.IGNORECASE):
            x = p.strip(" .;:-")
            if x:
                emergency_triggers.append(x)
    # de-dup
    seen = set()
    emergency_triggers = [x for x in emergency_triggers if not (x.lower() in seen or seen.add(x.lower()))]

    # Routing rules (very minimal extraction)
    after_hours = _find_first([
        re.compile(r"\bafter hours(?: we)?\s+(?:route|forward|transfer|call)\s+(.+?)(?:\.|\n|$)", re.IGNORECASE),
        re.compile(r"\bafter-hours(?: we)?\s+(?:route|forward|transfer|call)\s+(.+?)(?:\.|\n|$)", re.IGNORECASE),
    ], t)

    office_hours_routing = _find_first([
        re.compile(r"\bduring business hours(?: we)?\s+(?:route|transfer|forward)\s+(.+?)(?:\.|\n|$)", re.IGNORECASE),
    ], t)

    integration_constraints = _find_all(
        re.compile(r"\bnever\s+(.+?)(?:\.|\n|$)", re.IGNORECASE),
        t
    )

    # Unknowns (only if not explicitly found)
    if not company:
        unknowns.append("company_name missing")
    if not bh_raw:
        unknowns.append("business_hours missing (days/start/end)")
    if not tz:
        unknowns.append("timezone missing")
    if not emergency_triggers:
        unknowns.append("emergency_definition missing (explicit triggers/examples)")
    if not after_hours:
        unknowns.append("after_hours routing not specified")
    # Transfer rules details often missing
    unknowns.append("transfer timeout/retry/fallback not confirmed (unless explicitly stated)")  # safe, common

    fields = {
        "company_name": company or "",
        "office_address": address or "",
        "business_hours": {
            "days": days,
            "start": start_time,
            "end": end_time,
            "timezone": tz or ""
        },
        "services_supported": services,
        "emergency_definition": emergency_triggers,
        "office_hours_routing_hint": office_hours_routing or "",
        "after_hours_routing_hint": after_hours or "",
        "integration_constraints": integration_constraints,
    }
    return fields, _dedup_questions(unknowns)


def extract_onboarding_updates(transcript: str) -> Dict:
    """
    Extract ONLY onboarding-confirmed updates. If not present, omit the field from updates entirely.
    """
    t = transcript
    updates: Dict = {}

    # Business hours and timezone
    bh_raw = _find_first([
        re.compile(r"\bbusiness hours (?:are|is)\s+(.+?)(?:\.|\n|$)", re.IGNORECASE),
        re.compile(r"\bhours (?:are|is)\s+(.+?)(?:\.|\n|$)", re.IGNORECASE),
        re.compile(r"\bopen (?:from )?(.+?)(?:\.|\n|$)", re.IGNORECASE),
    ], t)
    tz = _find_first([
        re.compile(r"\btime zone(?: is)?\s+([A-Za-z/_+-]{3,})", re.IGNORECASE),
        re.compile(r"\btimezone(?: is)?\s+([A-Za-z/_+-]{3,})", re.IGNORECASE),
    ], t)

    if bh_raw or tz:
        days = _normalize_days(bh_raw or "")
        start_time = ""
        end_time = ""
        if bh_raw:
            m = re.search(r"(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\s*(?:to|-|–)\s*(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)",
                          bh_raw, re.IGNORECASE)
            if m:
                start_time = m.group(1).strip()
                end_time = m.group(2).strip()
        updates["business_hours"] = {
            "days": days,
            "start": start_time,
            "end": end_time,
            "timezone": tz or ""
        }

    # Emergency definition (more explicit on onboarding)
    emergency_examples = _find_all(
        re.compile(r"\bemergency(?: is| means)?(?:\:)?\s*(.+?)(?:\.|\n|$)", re.IGNORECASE),
        t
    )
    if emergency_examples:
        triggers = []
        for ex in emergency_examples:
            for p in re.split(r",|/| and ", ex, flags=re.IGNORECASE):
                x = p.strip(" .;:-")
                if x:
                    triggers.append(x)
        triggers = _dedup_list(triggers)
        updates["emergency_definition"] = triggers

    # Transfer timeout
    timeout = _find_first([
        re.compile(r"\btransfer fails after\s+(\d{1,3})\s*seconds", re.IGNORECASE),
        re.compile(r"\btimeout(?: is|=)?\s*(\d{1,3})\s*seconds", re.IGNORECASE),
    ], t)
    if timeout:
        updates.setdefault("call_transfer_rules", {})
        updates["call_transfer_rules"]["transfer_timeout_seconds"] = int(timeout)

    # Integration constraints (explicit "never create ..." etc.)
    never_lines = _find_all(re.compile(r"\bnever\s+(.+?)(?:\.|\n|$)", re.IGNORECASE), t)
    if never_lines:
        updates["integration_constraints"] = _dedup_list(never_lines)

    # Routing rules (explicit statements)
    emergency_route = _find_first([
        re.compile(r"\ball emergency .*? must go\s+(.+?)(?:\.|\n|$)", re.IGNORECASE),
        re.compile(r"\bemergency .*? go directly to\s+(.+?)(?:\.|\n|$)", re.IGNORECASE),
    ], t)
    if emergency_route:
        updates.setdefault("emergency_routing_rules", {})
        updates["emergency_routing_rules"]["primary_destination"] = emergency_route

    return updates


def _dedup_list(items: List[str]) -> List[str]:
    seen = set()
    out = []
    for x in items:
        k = x.lower().strip()
        if k and k not in seen:
            out.append(x.strip())
            seen.add(k)
    return out


def _dedup_questions(items: List[str]) -> List[str]:
    # keep stable ordering, remove duplicates
    return _dedup_list(items)


def base_memo_skeleton(account_id: str, stage: str, source_file: str) -> Dict:
    return {
        "account_id": account_id,
        "company_name": "",
        "business_hours": {"days": [], "start": "", "end": "", "timezone": ""},
        "office_address": "",
        "services_supported": [],
        "emergency_definition": [],
        "emergency_routing_rules": {
            "routing_order": [],
            "primary_destination": "",
            "fallback_destination": "",
            "notes": ""
        },
        "non_emergency_routing_rules": {
            "office_hours": "",
            "after_hours": "",
            "notes": ""
        },
        "call_transfer_rules": {
            "transfer_timeout_seconds": None,
            "max_retries": None,
            "retry_delay_seconds": None,
            "transfer_fail_script": ""
        },
        "integration_constraints": [],
        "after_hours_flow_summary": "",
        "office_hours_flow_summary": "",
        "questions_or_unknowns": [],
        "notes": "",
        "version": "v1" if stage == "demo" else "v2",
        "sources": {
            "stage": stage,
            "source_file": source_file
        },
        "meta": {
            "generated_at": now_iso()
        }
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="Path to transcript .txt")
    ap.add_argument("--stage", required=True, choices=["demo", "onboarding"])
    args = ap.parse_args()

    transcript = read_text(args.input)
    account_id = extract_account_id(args.input)
    h = file_hash(args.input)

    if args.stage == "demo":
        fields, unknowns = extract_demo_memo(transcript)
        memo = base_memo_skeleton(account_id, "demo", args.input)
        memo["company_name"] = fields["company_name"]
        memo["office_address"] = fields["office_address"]
        memo["business_hours"] = fields["business_hours"]
        memo["services_supported"] = fields["services_supported"]
        memo["emergency_definition"] = fields["emergency_definition"]
        memo["integration_constraints"] = fields["integration_constraints"]

        # store routing hints in notes instead of guessing structured routing
        if fields["office_hours_routing_hint"]:
            memo["non_emergency_routing_rules"]["office_hours"] = fields["office_hours_routing_hint"]
        if fields["after_hours_routing_hint"]:
            memo["non_emergency_routing_rules"]["after_hours"] = fields["after_hours_routing_hint"]

        memo["questions_or_unknowns"] = unknowns
        memo["sources"]["input_hash"] = h
        print(memo)

    else:
        updates = extract_onboarding_updates(transcript)
        # Attach provenance
        updates["_meta"] = {"input_hash": h, "source_file": args.input, "generated_at": now_iso()}
        print(updates)


if __name__ == "__main__":
    main()