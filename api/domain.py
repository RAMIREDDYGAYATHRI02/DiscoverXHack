"""ShiftSwap rules and atomic state transitions."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import time
import uuid

from django.conf import settings
from pymongo.errors import DuplicateKeyError, PyMongoError

from .mongo import state_collection

STATE_ID = "citycare-roster"
ACTIVE_STATUSES = {"OPEN", "CLAIMED"}
SEED_FILE = Path(settings.BASE_DIR) / "seed.json"


class DomainError(Exception):
    def __init__(self, message, *, status=400, violations=None):
        super().__init__(message)
        self.message = message
        self.status = status
        self.violations = violations or []


def seed_state():
    with SEED_FILE.open("r", encoding="utf-8") as seed_file:
        original = json.load(seed_file)
    # Do not normalize the roster: the provided seed values remain authoritative.
    return {**original, "listings": [], "history": []}


def ensure_seeded():
    collection = state_collection()
    existing = collection.find_one({"_id": STATE_ID})
    if existing is not None:
        return existing
    document = {"_id": STATE_ID, **seed_state(), "_rev": 0}
    try:
        collection.insert_one(document)
    except DuplicateKeyError:
        # Another worker initialized the roster after our first read.
        pass
    return collection.find_one({"_id": STATE_ID})


def read_state():
    return ensure_seeded()


def _parse(value):
    """Interpret a timezone-free clinic timestamp without host timezone rules."""
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def _overlaps(a, b):
    return _parse(a["start"]) < _parse(b["end"]) and _parse(b["start"]) < _parse(a["end"])


def _duration_hours(item):
    return (_parse(item["end"]) - _parse(item["start"])).total_seconds() / 3600


def _week_start(timestamp):
    parsed = _parse(timestamp)
    return (parsed - timedelta(days=parsed.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)


def claim_violations(state, candidate_shift, candidate_id):
    owner_id = candidate_shift["assigned_to"]
    # The owner exception intentionally suppresses every other rule result.
    if candidate_id == owner_id:
        return [{"rule": 1, "message": "Rule 1: The claimant cannot be the shift owner."}]

    candidate = next((staff for staff in state["staff"] if staff["id"] == candidate_id), None)
    if candidate is None or candidate["role"] != "STAFF":
        return [{"rule": None, "message": "Only staff members can claim shifts."}]

    assigned = [item for item in state["shifts"] if item["assigned_to"] == candidate_id]
    violations = []
    required = candidate_shift.get("required_certification")
    if required and required not in candidate["certifications"]:
        violations.append({"rule": 2, "message": f"Rule 2: {required} certification is required."})

    overlaps = [item for item in assigned if _overlaps(candidate_shift, item)]
    for item in overlaps:
        violations.append({"rule": 3, "shift_id": item["id"], "message": f"Rule 3: overlaps assigned shift {item['id']}."})

    starts_at = _parse(candidate_shift["start"])
    ends_at = _parse(candidate_shift["end"])
    for item in assigned:
        if item in overlaps:
            continue
        other_start = _parse(item["start"])
        other_end = _parse(item["end"])
        gap = starts_at - other_end if other_end <= starts_at else other_start - ends_at
        if gap < timedelta(hours=11):
            violations.append({"rule": 4, "shift_id": item["id"], "message": f"Rule 4: less than 11 hours of rest from shift {item['id']}."})

    target_week = _week_start(candidate_shift["start"])
    weekly_hours = sum(
        _duration_hours(item)
        for item in assigned
        if _week_start(item["start"]) == target_week
    ) + _duration_hours(candidate_shift)
    if weekly_hours > 40:
        violations.append({"rule": 5, "message": f"Rule 5: {weekly_hours:g} weekly hours would exceed the 40-hour limit."})
    return violations


def _person(state, person_id):
    return next((member for member in state["staff"] if member["id"] == person_id), None)


def _shift(state, shift_id):
    return next((item for item in state["shifts"] if item["id"] == shift_id), None)


def _listing(state, listing_id):
    return next((item for item in state["listings"] if item["id"] == listing_id), None)


def _active_listing(state, shift_id):
    return next((item for item in state["listings"] if item["shift_id"] == shift_id and item["status"] in ACTIVE_STATUSES), None)


def _history(state, actor, action, item, outcome, detail=""):
    state["history"].insert(0, {
        "id": str(uuid.uuid4()),
        "at": datetime.now(timezone.utc).isoformat(),
        "who": actor["name"],
        "actor_id": actor["id"],
        "what": action,
        "shift_id": item["id"],
        "outcome": outcome,
        "detail": detail,
    })


def _commit(transform, attempts=20):
    """Optimistic compare-and-set keeps related state transitions atomic across workers."""
    collection = state_collection()
    for _ in range(attempts):
        current = ensure_seeded()
        revision = current.get("_rev", 0)
        updated = deepcopy(current)
        updated.pop("_id", None)
        updated.pop("_rev", None)
        result = transform(updated)
        saved = collection.update_one(
            {"_id": STATE_ID, "_rev": revision},
            {"$set": updated, "$inc": {"_rev": 1}},
        )
        if saved.modified_count == 1:
            updated["_rev"] = revision + 1
            updated["_id"] = STATE_ID
            return result, updated
    raise DomainError("The roster changed at the same time. Please try again.", status=409)


def perform_action(actor_id, action, *, shift_id=None, listing_id=None):
    def transition(state):
        actor = _person(state, actor_id)
        if actor is None:
            raise DomainError("Choose a valid staff member or manager.", status=404)

        listing = _listing(state, listing_id) if listing_id else None
        item = _shift(state, shift_id) if shift_id else None
        if listing is not None:
            item = _shift(state, listing["shift_id"])
        if item is None:
            raise DomainError("That shift could not be found.", status=404)

        if action == "POST":
            if actor["role"] != "STAFF" or item["assigned_to"] != actor_id:
                raise DomainError("Only the assigned staff member can post this shift.", status=403)
            if _active_listing(state, item["id"]):
                raise DomainError("This shift already has an active listing.", status=409)
            created = {
                "id": str(uuid.uuid4()), "shift_id": item["id"], "posted_by": actor_id,
                "claimed_by": None, "status": "OPEN", "created_at": datetime.now(timezone.utc).isoformat(),
            }
            state["listings"].insert(0, created)
            _history(state, actor, "Posted", item, "Listing opened")
            return {"ok": True, "message": "Shift posted for cover.", "listing": created}

        if action == "CLAIM":
            # Availability is checked first; no other rule is evaluated for a stale listing.
            if not listing or listing["status"] != "OPEN":
                if listing is not None:
                    _history(state, actor, "Tried to claim", item, "Declined", "no longer available")
                    return {"ok": False, "message": "no longer available", "_error_status": 409}
                raise DomainError("no longer available", status=409)
            if actor["role"] != "STAFF":
                raise DomainError("Only staff members can claim shifts.", status=403)
            violations = claim_violations(state, item, actor_id)
            if violations:
                message = " ".join(v["message"] for v in violations)
                _history(state, actor, "Tried to claim", item, "Declined", message)
                return {"ok": False, "message": message, "violations": violations, "_error_status": 422}
            listing.update({"claimed_by": actor_id, "status": "CLAIMED"})
            _history(state, actor, "Claimed", item, "Awaiting manager approval")
            return {"ok": True, "message": "Claim submitted for manager approval.", "listing": listing}

        if action == "WITHDRAW":
            if not listing or listing["status"] != "OPEN" or listing["posted_by"] != actor_id:
                raise DomainError("Only the poster can withdraw an open listing.", status=403)
            listing["status"] = "WITHDRAWN"
            _history(state, actor, "Withdrew", item, "Listing withdrawn")
            return {"ok": True, "message": "Listing withdrawn.", "listing": listing}

        if action == "UNCLAIM":
            if not listing or listing["status"] != "CLAIMED" or listing["claimed_by"] != actor_id:
                raise DomainError("Only the current claimer can release this claim.", status=403)
            listing.update({"status": "OPEN", "claimed_by": None})
            _history(state, actor, "Unclaimed", item, "Listing reopened")
            return {"ok": True, "message": "Claim released; listing is open again.", "listing": listing}

        if action in {"APPROVE", "REJECT"}:
            if actor["role"] != "MANAGER":
                raise DomainError("Only a manager can review claims.", status=403)
            if not listing or listing["status"] != "CLAIMED":
                raise DomainError("This listing is not awaiting approval.", status=409)
            if action == "REJECT":
                listing.update({"status": "OPEN", "claimed_by": None})
                _history(state, actor, "Rejected", item, "Listing reopened")
                return {"ok": True, "message": "Claim rejected; listing is open again.", "listing": listing}
            claimant_id = listing["claimed_by"]
            # Rules 2-5 are recomputed from the latest CAS revision before reassignment.
            violations = [v for v in claim_violations(state, item, claimant_id) if v["rule"] != 1]
            if violations:
                message = " ".join(v["message"] for v in violations)
                _history(state, actor, "Tried to approve", item, "Still claimed; rules no longer pass", message)
                return {"ok": False, "message": f"Approval declined. {message}", "violations": violations, "_error_status": 422}
            item["assigned_to"] = claimant_id
            listing["status"] = "APPROVED"
            _history(state, actor, "Approved", item, f"Assigned to {_person(state, claimant_id)['name']}")
            return {"ok": True, "message": "Claim approved and shift reassigned.", "listing": listing}

        raise DomainError("That action is not supported.")

    result, _ = _commit(transition)
    error_status = result.pop("_error_status", None)
    return result, error_status


def close_mongo_client():
    if _client := getattr(state_collection, "_client", None):
        _client.close()
