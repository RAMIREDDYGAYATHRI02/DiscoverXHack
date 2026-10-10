import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import mongomock
from django.test import SimpleTestCase
from rest_framework.test import APIClient

from . import domain
from .mongo import clear_test_collection, set_test_collection


class ShiftSwapTests(SimpleTestCase):
    def setUp(self):
        self.mongo = mongomock.MongoClient()
        set_test_collection(self.mongo.shiftswap.clinic_state)
        domain.ensure_seeded()
        self.client = APIClient()
        self.state = domain.read_state()

    def tearDown(self):
        clear_test_collection()
        self.mongo.close()

    def mutate(self, callback):
        collection = self.mongo.shiftswap.clinic_state
        document = collection.find_one({"_id": domain.STATE_ID})
        callback(document)
        collection.replace_one({"_id": domain.STATE_ID}, document)

    def listing(self, shift_id="SH001", owner="S2"):
        result, _ = domain.perform_action(owner, "POST", shift_id=shift_id)
        return result["listing"]["id"]

    @staticmethod
    def synthetic_state():
        staff = [
            {"id": "OWNER", "name": "Owner", "role": "STAFF", "certifications": []},
            {"id": "CLAIMANT", "name": "Claimant", "role": "STAFF", "certifications": []},
            {"id": "ICU", "name": "ICU Nurse", "role": "STAFF", "certifications": ["ICU"]},
            {"id": "MANAGER", "name": "Manager", "role": "MANAGER", "certifications": []},
        ]
        return {"staff": staff, "shifts": [], "listings": [], "history": []}

    @staticmethod
    def shift(shift_id, start, end, assigned="CLAIMANT", certification=None):
        return {"id": shift_id, "start": start, "end": end, "required_certification": certification, "assigned_to": assigned}

    def test_original_roster_is_preserved_exactly_and_seed_is_idempotent(self):
        with open(domain.SEED_FILE, encoding="utf-8") as seed_file:
            original = json.load(seed_file)
        state = domain.read_state()
        self.assertEqual(state["staff"], original["staff"])
        self.assertEqual(state["shifts"], original["shifts"])
        self.assertEqual(len(state["shifts"]), 61)
        self.mutate(lambda document: document["staff"][0].update({"name": "Edited Asha"}))
        with patch.object(domain, "SEED_FILE", Path("seed-file-should-not-be-read.json")):
            domain.ensure_seeded()
        self.assertEqual(domain.read_state()["staff"][0]["name"], "Edited Asha")

    def test_owner_reports_only_rule_one(self):
        state = self.synthetic_state()
        item = self.shift("T", "2026-03-02T07:00", "2026-03-02T15:00", "OWNER", "ICU")
        state["shifts"] = [item]
        self.assertEqual(domain.claim_violations(state, item, "OWNER"), [
            {"rule": 1, "message": "Rule 1: The claimant cannot be the shift owner."}
        ])

    def test_all_applicable_claim_rules_are_reported(self):
        state = self.synthetic_state()
        target = self.shift("TARGET", "2026-03-02T07:00", "2026-03-02T15:00", "OWNER", "ICU")
        state["shifts"] = [target,
            self.shift("OVERLAP", "2026-03-02T08:00", "2026-03-02T16:00"),
            self.shift("REST", "2026-03-02T18:00", "2026-03-02T23:00"),
        ]
        # Five further assigned shifts make the claim exceed 40 hours in the target week.
        for day in range(3, 8):
            date = f"2026-03-{day:02d}"
            state["shifts"].append(self.shift(f"WEEK{day}", f"{date}T07:00", f"{date}T15:00"))
        violations = domain.claim_violations(state, target, "CLAIMANT")
        self.assertEqual({entry["rule"] for entry in violations}, {2, 3, 4, 5})
        self.assertTrue(any(entry.get("shift_id") == "OVERLAP" for entry in violations))
        self.assertTrue(any(entry.get("shift_id") == "REST" for entry in violations))

    def test_eleven_hour_and_forty_hour_boundaries_are_allowed(self):
        state = self.synthetic_state()
        state["staff"][1]["certifications"] = ["ICU"]
        prior = self.shift("PRIOR", "2026-03-02T07:00", "2026-03-02T15:00")
        target = self.shift("TARGET", "2026-03-03T02:00", "2026-03-03T10:00", "OWNER", "ICU")
        state["shifts"] = [prior, target]
        self.assertNotIn(4, {entry["rule"] for entry in domain.claim_violations(state, target, "CLAIMANT")})
        # Four additional 8-hour assignments plus the target total exactly 40 hours.
        target = self.shift("TARGET", "2026-03-02T07:00", "2026-03-02T15:00", "OWNER")
        state["shifts"] = [target]
        for day in range(3, 7):
            date = f"2026-03-{day:02d}"
            state["shifts"].append(self.shift(f"WEEK{day}", f"{date}T07:00", f"{date}T15:00"))
        self.assertNotIn(5, {entry["rule"] for entry in domain.claim_violations(state, target, "CLAIMANT")})

    def test_overlap_definition_uses_strict_boundaries(self):
        state = self.synthetic_state()
        first = self.shift("FIRST", "2026-03-02T07:00", "2026-03-02T15:00")
        second = self.shift("SECOND", "2026-03-02T15:00", "2026-03-02T23:00", "OWNER")
        state["shifts"] = [first, second]
        self.assertNotIn(3, {entry["rule"] for entry in domain.claim_violations(state, second, "CLAIMANT")})
        self.assertIn(4, {entry["rule"] for entry in domain.claim_violations(state, second, "CLAIMANT")})

    def test_cross_midnight_duration_and_week_uses_shift_start(self):
        state = self.synthetic_state()
        state["staff"][1]["certifications"] = ["ICU"]
        overnight = self.shift("NIGHT", "2026-03-06T23:00", "2026-03-07T07:00")
        target = self.shift("NEXT", "2026-03-09T07:00", "2026-03-09T15:00", "OWNER")
        state["shifts"] = [overnight, target]
        for day in range(2, 7):
            date = f"2026-03-{day:02d}"
            state["shifts"].append(self.shift(f"PREV{day}", f"{date}T07:00", f"{date}T15:00"))
        self.assertEqual(domain._duration_hours(overnight), 8)
        violations = domain.claim_violations(state, target, "CLAIMANT")
        self.assertNotIn(5, {entry["rule"] for entry in violations})

    def test_concurrent_claims_cannot_both_win(self):
        document = self.mongo.shiftswap.clinic_state.find_one({"_id": domain.STATE_ID})
        document.update({
            "staff": [
                {"id": "OWNER", "name": "Owner", "role": "STAFF", "certifications": []},
                {"id": "A", "name": "A", "role": "STAFF", "certifications": []},
                {"id": "B", "name": "B", "role": "STAFF", "certifications": []},
                {"id": "MANAGER", "name": "Manager", "role": "MANAGER", "certifications": []},
            ],
            "shifts": [self.shift("TARGET", "2026-03-02T07:00", "2026-03-02T15:00", "OWNER")],
            "listings": [{"id": "LISTING", "shift_id": "TARGET", "posted_by": "OWNER", "claimed_by": None, "status": "OPEN"}],
            "history": [], "_rev": 0,
        })
        self.mongo.shiftswap.clinic_state.replace_one({"_id": domain.STATE_ID}, document)

        def claim(person_id):
            try:
                result, error_status = domain.perform_action(person_id, "CLAIM", listing_id="LISTING")
                return result["ok"], result.get("message"), error_status
            except domain.DomainError as error:
                return False, error.message, error.status

        with ThreadPoolExecutor(max_workers=2) as workers:
            results = list(workers.map(claim, ["A", "B"]))
        self.assertEqual(sum(result[0] for result in results), 1)
        self.assertEqual(sum(result[1] == "no longer available" and result[2] == 409 for result in results), 1, results)
        self.assertEqual(domain.read_state()["listings"][0]["status"], "CLAIMED")

    def test_post_duplicate_withdraw_claim_unclaim_reject_transitions(self):
        listing_id = self.listing()
        with self.assertRaises(domain.DomainError) as duplicate:
            domain.perform_action("S2", "POST", shift_id="SH001")
        self.assertEqual(duplicate.exception.status, 409)
        # S7 is eligible to pick up the Monday 07:00 shift.
        result, error_status = domain.perform_action("S7", "CLAIM", listing_id=listing_id)
        self.assertIsNone(error_status)
        self.assertEqual(result["listing"]["status"], "CLAIMED")
        domain.perform_action("S7", "UNCLAIM", listing_id=listing_id)
        self.assertEqual(domain.read_state()["listings"][0]["status"], "OPEN")
        domain.perform_action("S7", "CLAIM", listing_id=listing_id)
        domain.perform_action("M1", "REJECT", listing_id=listing_id)
        self.assertEqual(domain.read_state()["listings"][0]["status"], "OPEN")
        domain.perform_action("S2", "WITHDRAW", listing_id=listing_id)
        self.assertEqual(domain.read_state()["listings"][0]["status"], "WITHDRAWN")

    def test_stale_claim_returns_exact_message_before_rules(self):
        listing_id = self.listing()
        self.mutate(lambda document: document["listings"][0].update({"status": "APPROVED"}))
        response = self.client.post("/api/actions", {"actor_id": "S2", "action": "CLAIM", "listing_id": listing_id}, format="json")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["message"], "no longer available")
        self.assertNotIn("violations", response.data)

    def test_permissions_and_manager_approval_revalidation(self):
        listing_id = self.listing()
        denied = self.client.post("/api/actions", {"actor_id": "S7", "action": "POST", "shift_id": "SH001"}, format="json")
        self.assertEqual(denied.status_code, 403)
        manager_claim = self.client.post("/api/actions", {"actor_id": "M1", "action": "CLAIM", "listing_id": listing_id}, format="json")
        self.assertEqual(manager_claim.status_code, 403)
        staff_approval = self.client.post("/api/actions", {"actor_id": "S7", "action": "APPROVE", "listing_id": listing_id}, format="json")
        self.assertEqual(staff_approval.status_code, 403)
        domain.perform_action("S7", "CLAIM", listing_id=listing_id)
        # Add a conflicting assignment after claim, as if another manager edited the roster.
        def add_conflict(document):
            target = next(item for item in document["shifts"] if item["id"] == "SH019")
            target["start"], target["end"] = "2026-03-02T08:00", "2026-03-02T16:00"
        self.mutate(add_conflict)
        denied_approval = self.client.post("/api/actions", {"actor_id": "M1", "action": "APPROVE", "listing_id": listing_id}, format="json")
        self.assertEqual(denied_approval.status_code, 422)
        self.assertIn("Rule 3", denied_approval.data["message"])
        self.assertEqual(domain.read_state()["listings"][0]["status"], "CLAIMED")
        self.assertEqual(next(item for item in domain.read_state()["shifts"] if item["id"] == "SH001")["assigned_to"], "S2")

    def test_valid_approval_reassigns_and_records_history(self):
        listing_id = self.listing()
        domain.perform_action("S7", "CLAIM", listing_id=listing_id)
        response = self.client.post("/api/actions", {"actor_id": "M1", "action": "APPROVE", "listing_id": listing_id}, format="json")
        self.assertEqual(response.status_code, 200)
        state = domain.read_state()
        self.assertEqual(next(item for item in state["shifts"] if item["id"] == "SH001")["assigned_to"], "S7")
        self.assertEqual(next(item for item in state["listings"] if item["id"] == listing_id)["status"], "APPROVED")
        self.assertEqual([entry["what"] for entry in state["history"][:2]], ["Approved", "Claimed"])

    def test_resource_style_listing_endpoints(self):
        posted = self.client.post("/api/listings", {"actor_id": "S2", "shift_id": "SH001"}, format="json")
        self.assertEqual(posted.status_code, 200)
        listing_id = posted.data["listing"]["id"]
        claimed = self.client.post(f"/api/listings/{listing_id}/claim", {"actor_id": "S7"}, format="json")
        self.assertEqual(claimed.status_code, 200)
        approved = self.client.post(f"/api/listings/{listing_id}/approve", {"actor_id": "M1"}, format="json")
        self.assertEqual(approved.status_code, 200)

    def test_api_reads_and_data_survive_state_reload(self):
        listing_id = self.listing()
        self.assertEqual(self.client.get("/api/state").status_code, 200)
        self.assertEqual(self.client.get("/api/staff").status_code, 200)
        self.assertEqual(self.client.get("/api/shifts").status_code, 200)
        self.assertEqual(self.client.get("/api/listings").status_code, 200)
        self.assertEqual(self.client.get("/api/history").status_code, 200)
        # A fresh repository read sees the same saved state and never seeds over it.
        self.assertEqual(domain.read_state()["listings"][0]["id"], listing_id)
        self.assertEqual(domain.read_state()["history"][0]["what"], "Posted")

    def test_root_redirects_to_frontend(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "http://localhost:5173/")

