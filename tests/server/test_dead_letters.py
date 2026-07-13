"""Tests for the dead-letter inspection routes."""


class TestDeadLetterRoutes:
    def test_list_empty(self, client):
        resp = client.get("/dead-letters")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 0
        assert body["dead_letters"] == []

    def test_list_and_filter(self, client, ds):
        ds.record_dead_letter("oura:default", "oura/sleep/1", "ChunkingError", "boom")
        ds.record_dead_letter("apple_health:default", "apple_health/spo2/1", "StorageError", "x")

        resp = client.get("/dead-letters")
        assert resp.json()["total"] == 2

        resp = client.get("/dead-letters", params={"adapter_id": "oura:default"})
        body = resp.json()
        assert body["total"] == 1
        assert body["dead_letters"][0]["source_id"] == "oura/sleep/1"

    def test_clear(self, client, ds):
        ds.record_dead_letter("oura:default", "s1", "E", "m")
        ds.record_dead_letter("oura:default", "s2", "E", "m")

        resp = client.post("/dead-letters/clear", params={"adapter_id": "oura:default", "source_id": "s1"})
        assert resp.status_code == 200
        assert resp.json()["deleted"] == 1
        assert client.get("/dead-letters").json()["total"] == 1
