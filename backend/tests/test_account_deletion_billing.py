import asyncio
import base64
import json

from routers import auth as auth_router
from routers import billing as billing_router


class FakeCollection:
    def __init__(self, find_result=None):
        self.find_result = find_result
        self.update_many_calls = []
        self.update_one_calls = []
        self.delete_many_calls = []
        self.delete_one_calls = []
        self.insert_one_calls = []

    async def find_one(self, *args, **kwargs):
        return self.find_result

    async def update_many(self, query, update):
        self.update_many_calls.append((query, update))

    async def update_one(self, query, update, **kwargs):
        self.update_one_calls.append((query, update, kwargs))

    async def delete_many(self, query):
        self.delete_many_calls.append(query)

    async def delete_one(self, query):
        self.delete_one_calls.append(query)

    async def insert_one(self, document):
        self.insert_one_calls.append(document)


class FakeDB:
    def __init__(self):
        self.collections = {}

    def collection(self, name):
        if name not in self.collections:
            self.collections[name] = FakeCollection()
        return self.collections[name]

    def __getitem__(self, name):
        return self.collection(name)

    def __getattr__(self, name):
        return self.collection(name)


def test_delete_account_removes_billing_data_and_tombstones_token(monkeypatch):
    fake = FakeDB()
    fake.users.find_result = {
        "id": "deleted-user",
        "auth_provider": "google",
    }

    monkeypatch.setattr(auth_router, "db", fake)

    result = asyncio.run(
        auth_router.delete_account(body=None, uid="deleted-user")
    )

    assert result == {"ok": True, "deleted": True}

    assert len(fake.purchase_tokens.update_many_calls) == 1
    query, update = fake.purchase_tokens.update_many_calls[0]

    assert query == {"user_id": "deleted-user"}
    assert update["$set"]["state"] == "account_deleted"
    assert update["$set"]["auto_renewing"] is False
    assert "account_deleted_at" in update["$set"]
    assert "encrypted_purchase_token" in update["$unset"]
    assert "linked_purchase_token_hash" in update["$unset"]

    expected_deleted = {
        "entitlements",
        "entitlement_grants",
        "entitlement_audit",
        "usage_cycles",
        "usage_ledger",
        "cost_ledger",
        "monetization_events",
        "purchase_events",
        "subscription_audit",
    }

    for name in expected_deleted:
        assert fake[name].delete_many_calls == [{"user_id": "deleted-user"}]

    assert fake.users.delete_one_calls == [{"id": "deleted-user"}]


class FakeRequest:
    query_params = {"token": "verification-token"}

    async def json(self):
        data = {
            "subscriptionNotification": {
                "purchaseToken": "raw-play-token",
                "notificationType": 3,
            }
        }
        return {
            "message": {
                "messageId": "deleted-account-rtdn",
                "data": base64.b64encode(
                    json.dumps(data).encode("utf-8")
                ).decode("ascii"),
            }
        }


def test_rtdn_does_not_recreate_deleted_account_entitlement(monkeypatch):
    fake = FakeDB()
    fake.rtdn_events.find_result = None
    fake.purchase_tokens.find_result = {
        "user_id": "deleted-user",
        "purchase_token_hash": billing_router._token_hash("raw-play-token"),
        "account_deleted_at": "2026-07-28T20:00:00+00:00",
    }

    monkeypatch.setattr(billing_router, "db", fake)
    monkeypatch.setattr(
        billing_router.config,
        "PUBSUB_VERIFICATION_TOKEN",
        "verification-token",
    )
    monkeypatch.setattr(billing_router.config, "BILLING_ENABLED", True)

    result = asyncio.run(
        billing_router.billing_rtdn(
            FakeRequest(),
            authorization="",
        )
    )

    assert result == {"ok": True, "account_deleted": True}
    assert fake.entitlements.update_one_calls == []
    assert fake.rtdn_events.update_one_calls

    _, update, _ = fake.rtdn_events.update_one_calls[-1]
    assert update["$set"]["processed"] is True
    assert update["$set"]["ignored_reason"] == "account_deleted"
