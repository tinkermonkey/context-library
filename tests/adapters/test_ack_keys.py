"""Tests for endpoint-keyed commit-acks (HelperAckMixin._ack_keys).

The helper's POST /collectors/{name}/ack is collector-global; multi-endpoint
adapters must ack only the cursor keys of endpoints that fetched successfully,
otherwise a partial fetch commits the failed endpoint's staged cursor and its
page is permanently skipped.
"""

from unittest.mock import MagicMock, patch

from context_library.adapters.apple_health import AppleHealthAdapter
from context_library.adapters.oura import OuraAdapter


def _oura():
    return OuraAdapter(api_url="http://helper:1", api_key="k")


def _health():
    return AppleHealthAdapter(api_url="http://helper:1", api_key="k")


class TestOuraAckKeys:
    def test_all_success_acks_everything(self):
        a = _oura()
        a._failed_endpoints = []
        assert a._ack_keys() is None  # None = commit all staged keys

    def test_partial_failure_excludes_failed_keys(self):
        a = _oura()
        a._failed_endpoints = ["/oura/heart_rate", "/oura/sleep"]
        keys = a._ack_keys()
        assert "oura_heart_rate" not in keys
        assert "oura_sleep" not in keys
        assert "oura_readiness" in keys
        assert len(keys) == 6

    def test_all_failed_returns_empty(self):
        a = _oura()
        a._failed_endpoints = [
            "/oura/sleep", "/oura/readiness", "/oura/activity", "/oura/workouts",
            "/oura/spo2", "/oura/tags", "/oura/sessions", "/oura/heart_rate",
        ]
        assert a._ack_keys() == []


class TestHealthAckKeys:
    def test_hyphenated_endpoint_maps_to_underscore_key(self):
        a = _health()
        a._failed_endpoints = ["/health/heart-rate"]
        keys = a._ack_keys()
        assert "health_heart_rate" not in keys
        assert "health_workouts" in keys
        assert len(keys) == 5

    def test_keys_match_helper_cursor_keys(self):
        # Must mirror HealthCollector.push_cursor_keys() on the mac
        assert AppleHealthAdapter._ALL_ACK_KEYS == [
            "health_workouts", "health_activity", "health_sleep",
            "health_heart_rate", "health_spo2", "health_mindfulness",
        ]


class TestAckPost:
    def test_ack_sends_keys_body_on_partial(self):
        a = _oura()
        a._failed_endpoints = ["/oura/sleep"]
        with patch("httpx.post", return_value=MagicMock(raise_for_status=lambda: None)) as post:
            a.ack()
        assert post.called
        body = post.call_args.kwargs["json"]
        assert "oura_sleep" not in body["keys"]
        assert "oura_heart_rate" in body["keys"]

    def test_ack_sends_no_body_on_full_success(self):
        a = _oura()
        a._failed_endpoints = []
        with patch("httpx.post", return_value=MagicMock(raise_for_status=lambda: None)) as post:
            a.ack()
        assert post.called
        assert "json" not in post.call_args.kwargs

    def test_ack_skipped_when_all_endpoints_failed(self):
        a = _oura()
        a._failed_endpoints = list(a._ALL_ACK_KEYS)  # any 8 entries mapping to all keys
        a._failed_endpoints = [
            "/oura/sleep", "/oura/readiness", "/oura/activity", "/oura/workouts",
            "/oura/spo2", "/oura/tags", "/oura/sessions", "/oura/heart_rate",
        ]
        with patch("httpx.post") as post:
            a.ack()
        post.assert_not_called()

    def test_ack_never_raises(self):
        a = _oura()
        a._failed_endpoints = []
        with patch("httpx.post", side_effect=ConnectionError("down")):
            a.ack()  # must not raise
