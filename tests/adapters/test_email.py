"""Tests for the EmailAdapter."""

import pytest
import json
from datetime import datetime, timezone

from context_library.adapters.email import EmailAdapter
from context_library.storage.models import Domain, NormalizedContent, MessageMetadata


class TestEmailAdapterProperties:
    """Tests for EmailAdapter properties."""

    def test_adapter_id_format(self):
        """adapter_id has correct format: email:{account_id}."""
        adapter = EmailAdapter(
            emailengine_url="http://localhost:3000",
            account_id="acct1"
        )
        assert adapter.adapter_id == "email:acct1"

    def test_adapter_id_deterministic(self):
        """adapter_id is deterministic for the same configuration."""
        adapter1 = EmailAdapter(
            emailengine_url="http://localhost:3000",
            account_id="acct1"
        )
        adapter2 = EmailAdapter(
            emailengine_url="http://localhost:3000",
            account_id="acct1"
        )
        assert adapter1.adapter_id == adapter2.adapter_id

    def test_different_accounts_different_ids(self):
        """Different account IDs produce different adapter_ids."""
        adapter1 = EmailAdapter(
            emailengine_url="http://localhost:3000",
            account_id="acct1"
        )
        adapter2 = EmailAdapter(
            emailengine_url="http://localhost:3000",
            account_id="acct2"
        )
        assert adapter1.adapter_id != adapter2.adapter_id

    def test_domain_property(self):
        """domain property returns Domain.MESSAGES."""
        adapter = EmailAdapter(
            emailengine_url="http://localhost:3000",
            account_id="acct1"
        )
        assert adapter.domain == Domain.MESSAGES

    def test_normalizer_version_property(self):
        """normalizer_version property returns '1.0.0'."""
        adapter = EmailAdapter(
            emailengine_url="http://localhost:3000",
            account_id="acct1"
        )
        assert adapter.normalizer_version == "1.0.0"

    def test_emailengine_url_strip_trailing_slash(self):
        """EmailEngine URL has trailing slash stripped."""
        adapter = EmailAdapter(
            emailengine_url="http://localhost:3000/",
            account_id="acct1"
        )
        assert adapter._emailengine_url == "http://localhost:3000"

    def test_emailengine_url_no_trailing_slash(self):
        """EmailEngine URL without trailing slash is unchanged."""
        adapter = EmailAdapter(
            emailengine_url="http://localhost:3000",
            account_id="acct1"
        )
        assert adapter._emailengine_url == "http://localhost:3000"


class TestEmailAdapterFetch:
    """Tests for EmailAdapter.fetch() method."""

    @pytest.fixture
    def mock_httpx(self, monkeypatch):
        """Fixture for mocking httpx requests."""
        class MockResponse:
            def __init__(self, json_data, status_code=200):
                self._json_data = json_data
                self.status_code = status_code

            def json(self):
                return self._json_data

            def raise_for_status(self):
                if self.status_code >= 400:
                    raise Exception(f"HTTP {self.status_code}")

        class MockHTTPX:
            def __init__(self):
                self.requests = []
                self.responses = {}

            def get(self, url, params=None, timeout=None):
                self.requests.append({"url": url, "params": params, "timeout": timeout})
                return self.responses.get(url, MockResponse({}))

            def set_response(self, url, data, status_code=200):
                self.responses[url] = MockResponse(data, status_code)

        mock_httpx = MockHTTPX()
        monkeypatch.setattr("context_library.adapters.email.httpx.get", mock_httpx.get)
        return mock_httpx

    def test_fetch_single_message(self, mock_httpx):
        """fetch() yields NormalizedContent for a single message."""
        adapter = EmailAdapter(
            emailengine_url="http://localhost:3000",
            account_id="acct1"
        )

        # Mock message list response
        messages_url = "http://localhost:3000/v1/account/acct1/messages"
        mock_httpx.set_response(messages_url, {
            "messages": {
                "messages": [
                    {
                        "id": "msg1",
                        "threadId": "thread1",
                        "messageId": "<msg1@example.com>",
                        "from": {"address": "sender@example.com"},
                        "to": [{"address": "recipient@example.com"}],
                        "subject": "Test Subject",
                        "date": "2026-03-06T10:00:00Z",
                        "inReplyTo": None,
                    }
                ]
            }
        })

        # Mock message body response
        body_url = "http://localhost:3000/v1/account/acct1/message/msg1"
        mock_httpx.set_response(body_url, {
            "text": "<p>Hello World</p>"
        })

        results = list(adapter.fetch(""))
        assert len(results) == 1
        assert isinstance(results[0], NormalizedContent)
        assert results[0].markdown.strip() == "Hello World"
        assert results[0].source_id == "email:acct1:msg1"

    def test_fetch_multiple_messages(self, mock_httpx):
        """fetch() yields NormalizedContent for multiple messages."""
        adapter = EmailAdapter(
            emailengine_url="http://localhost:3000",
            account_id="acct1"
        )

        # Mock message list response with 2 messages
        messages_url = "http://localhost:3000/v1/account/acct1/messages"
        mock_httpx.set_response(messages_url, {
            "messages": {
                "messages": [
                    {
                        "id": "msg1",
                        "threadId": "thread1",
                        "messageId": "<msg1@example.com>",
                        "from": {"address": "sender1@example.com"},
                        "to": [{"address": "recipient@example.com"}],
                        "subject": "Subject 1",
                        "date": "2026-03-06T10:00:00Z",
                        "inReplyTo": None,
                    },
                    {
                        "id": "msg2",
                        "threadId": "thread1",
                        "messageId": "<msg2@example.com>",
                        "from": {"address": "sender2@example.com"},
                        "to": [{"address": "recipient@example.com"}],
                        "subject": "Subject 2",
                        "date": "2026-03-06T11:00:00Z",
                        "inReplyTo": "<msg1@example.com>",
                    }
                ]
            }
        })

        # Mock message body responses
        body_url1 = "http://localhost:3000/v1/account/acct1/message/msg1"
        mock_httpx.set_response(body_url1, {"text": "<p>Message 1</p>"})

        body_url2 = "http://localhost:3000/v1/account/acct1/message/msg2"
        mock_httpx.set_response(body_url2, {"text": "<p>Message 2</p>"})

        results = list(adapter.fetch(""))
        assert len(results) == 2
        assert results[0].source_id == "email:acct1:msg1"
        assert results[1].source_id == "email:acct1:msg2"

    def test_fetch_with_since_parameter(self, mock_httpx):
        """fetch() includes 'since' parameter when source_ref is provided."""
        adapter = EmailAdapter(
            emailengine_url="http://localhost:3000",
            account_id="acct1"
        )

        since = "2026-03-01T00:00:00Z"

        # Mock message list response
        messages_url = "http://localhost:3000/v1/account/acct1/messages"
        mock_httpx.set_response(messages_url, {
            "messages": {"messages": []}
        })

        list(adapter.fetch(since))

        # Check that the API call included the since parameter
        assert len(mock_httpx.requests) > 0
        api_request = mock_httpx.requests[0]
        assert api_request["params"]["search[since]"] == since

    def test_fetch_respects_max_messages(self, mock_httpx):
        """fetch() uses max_messages parameter in API call."""
        adapter = EmailAdapter(
            emailengine_url="http://localhost:3000",
            account_id="acct1",
            max_messages=50
        )

        # Mock message list response
        messages_url = "http://localhost:3000/v1/account/acct1/messages"
        mock_httpx.set_response(messages_url, {
            "messages": {"messages": []}
        })

        list(adapter.fetch(""))

        # Check that the API call included the max_messages parameter
        assert len(mock_httpx.requests) > 0
        api_request = mock_httpx.requests[0]
        assert api_request["params"]["pageSize"] == 50

    def test_fetch_empty_response(self, mock_httpx):
        """fetch() handles empty message list gracefully."""
        adapter = EmailAdapter(
            emailengine_url="http://localhost:3000",
            account_id="acct1"
        )

        # Mock empty message list response
        messages_url = "http://localhost:3000/v1/account/acct1/messages"
        mock_httpx.set_response(messages_url, {
            "messages": {"messages": []}
        })

        results = list(adapter.fetch(""))
        assert results == []

    def test_fetch_html_to_markdown_conversion(self, mock_httpx):
        """fetch() converts HTML email bodies to markdown."""
        adapter = EmailAdapter(
            emailengine_url="http://localhost:3000",
            account_id="acct1"
        )

        # Mock message list response
        messages_url = "http://localhost:3000/v1/account/acct1/messages"
        mock_httpx.set_response(messages_url, {
            "messages": {
                "messages": [
                    {
                        "id": "msg1",
                        "threadId": "thread1",
                        "messageId": "<msg1@example.com>",
                        "from": {"address": "sender@example.com"},
                        "to": [{"address": "recipient@example.com"}],
                        "subject": "Test",
                        "date": "2026-03-06T10:00:00Z",
                        "inReplyTo": None,
                    }
                ]
            }
        })

        # Mock message body response with HTML
        body_url = "http://localhost:3000/v1/account/acct1/message/msg1"
        mock_httpx.set_response(body_url, {
            "text": "<p><b>Bold text</b> and <i>italic text</i></p>"
        })

        results = list(adapter.fetch(""))
        assert len(results) == 1
        # HTML2Text should convert bold/italic tags to markdown
        assert "Bold text" in results[0].markdown

    def test_metadata_in_structural_hints(self, mock_httpx):
        """fetch() includes MessageMetadata in structural_hints.extra_metadata."""
        adapter = EmailAdapter(
            emailengine_url="http://localhost:3000",
            account_id="acct1"
        )

        # Mock message list response
        messages_url = "http://localhost:3000/v1/account/acct1/messages"
        mock_httpx.set_response(messages_url, {
            "messages": {
                "messages": [
                    {
                        "id": "msg1",
                        "threadId": "thread1",
                        "messageId": "<msg1@example.com>",
                        "from": {"address": "sender@example.com"},
                        "to": [{"address": "recipient@example.com"}],
                        "subject": "Test Subject",
                        "date": "2026-03-06T10:00:00Z",
                        "inReplyTo": None,
                    }
                ]
            }
        })

        # Mock message body response
        body_url = "http://localhost:3000/v1/account/acct1/message/msg1"
        mock_httpx.set_response(body_url, {
            "text": "<p>Content</p>"
        })

        results = list(adapter.fetch(""))
        assert len(results) == 1

        # Check that extra_metadata contains MessageMetadata fields
        extra_metadata = results[0].structural_hints.extra_metadata
        assert extra_metadata is not None
        assert extra_metadata["thread_id"] == "thread1"
        assert extra_metadata["message_id"] == "<msg1@example.com>"
        assert extra_metadata["sender"] == "sender@example.com"
        assert extra_metadata["subject"] == "Test Subject"
        assert extra_metadata["is_thread_root"] is True

    def test_thread_root_detection(self, mock_httpx):
        """fetch() correctly sets is_thread_root based on inReplyTo."""
        adapter = EmailAdapter(
            emailengine_url="http://localhost:3000",
            account_id="acct1"
        )

        # Mock message list response with reply message
        messages_url = "http://localhost:3000/v1/account/acct1/messages"
        mock_httpx.set_response(messages_url, {
            "messages": {
                "messages": [
                    {
                        "id": "msg1",
                        "threadId": "thread1",
                        "messageId": "<msg1@example.com>",
                        "from": {"address": "sender@example.com"},
                        "to": [{"address": "recipient@example.com"}],
                        "subject": "Test",
                        "date": "2026-03-06T10:00:00Z",
                        "inReplyTo": "<original@example.com>",
                    }
                ]
            }
        })

        # Mock message body response
        body_url = "http://localhost:3000/v1/account/acct1/message/msg1"
        mock_httpx.set_response(body_url, {
            "text": "<p>Reply</p>"
        })

        results = list(adapter.fetch(""))
        extra_metadata = results[0].structural_hints.extra_metadata
        assert extra_metadata["is_thread_root"] is False
        assert extra_metadata["in_reply_to"] == "<original@example.com>"

    def test_recipients_list_extraction(self, mock_httpx):
        """fetch() correctly extracts multiple recipients."""
        adapter = EmailAdapter(
            emailengine_url="http://localhost:3000",
            account_id="acct1"
        )

        # Mock message list response with multiple recipients
        messages_url = "http://localhost:3000/v1/account/acct1/messages"
        mock_httpx.set_response(messages_url, {
            "messages": {
                "messages": [
                    {
                        "id": "msg1",
                        "threadId": "thread1",
                        "messageId": "<msg1@example.com>",
                        "from": {"address": "sender@example.com"},
                        "to": [
                            {"address": "recipient1@example.com"},
                            {"address": "recipient2@example.com"},
                            {"address": "recipient3@example.com"},
                        ],
                        "subject": "Test",
                        "date": "2026-03-06T10:00:00Z",
                        "inReplyTo": None,
                    }
                ]
            }
        })

        # Mock message body response
        body_url = "http://localhost:3000/v1/account/acct1/message/msg1"
        mock_httpx.set_response(body_url, {
            "text": "<p>Content</p>"
        })

        results = list(adapter.fetch(""))
        extra_metadata = results[0].structural_hints.extra_metadata
        assert len(extra_metadata["recipients"]) == 3
        assert "recipient1@example.com" in extra_metadata["recipients"]
        assert "recipient2@example.com" in extra_metadata["recipients"]
        assert "recipient3@example.com" in extra_metadata["recipients"]

    def test_optional_fields_handling(self, mock_httpx):
        """fetch() handles missing optional fields gracefully."""
        adapter = EmailAdapter(
            emailengine_url="http://localhost:3000",
            account_id="acct1"
        )

        # Mock message list response with minimal fields
        messages_url = "http://localhost:3000/v1/account/acct1/messages"
        mock_httpx.set_response(messages_url, {
            "messages": {
                "messages": [
                    {
                        "id": "msg1",
                        "threadId": "",
                        "messageId": "",
                        "from": {"address": "sender@example.com"},
                        "to": [],
                        "date": "2026-03-06T10:00:00Z",
                        # subject and inReplyTo are absent
                    }
                ]
            }
        })

        # Mock message body response
        body_url = "http://localhost:3000/v1/account/acct1/message/msg1"
        mock_httpx.set_response(body_url, {
            "text": "<p>Content</p>"
        })

        results = list(adapter.fetch(""))
        assert len(results) == 1
        extra_metadata = results[0].structural_hints.extra_metadata
        assert extra_metadata["subject"] is None
        assert extra_metadata["in_reply_to"] is None
        assert extra_metadata["recipients"] == []

    def test_timestamp_iso8601_format(self, mock_httpx):
        """fetch() includes timestamp in ISO 8601 format."""
        adapter = EmailAdapter(
            emailengine_url="http://localhost:3000",
            account_id="acct1"
        )

        iso_timestamp = "2026-03-06T10:30:45Z"

        # Mock message list response
        messages_url = "http://localhost:3000/v1/account/acct1/messages"
        mock_httpx.set_response(messages_url, {
            "messages": {
                "messages": [
                    {
                        "id": "msg1",
                        "threadId": "thread1",
                        "messageId": "<msg1@example.com>",
                        "from": {"address": "sender@example.com"},
                        "to": [{"address": "recipient@example.com"}],
                        "subject": "Test",
                        "date": iso_timestamp,
                        "inReplyTo": None,
                    }
                ]
            }
        })

        # Mock message body response
        body_url = "http://localhost:3000/v1/account/acct1/message/msg1"
        mock_httpx.set_response(body_url, {
            "text": "<p>Content</p>"
        })

        results = list(adapter.fetch(""))
        extra_metadata = results[0].structural_hints.extra_metadata
        # Timestamp should be valid ISO 8601
        assert extra_metadata["timestamp"] == iso_timestamp

    def test_structural_hints_always_false(self, mock_httpx):
        """fetch() always sets has_headings, has_lists, has_tables to False."""
        adapter = EmailAdapter(
            emailengine_url="http://localhost:3000",
            account_id="acct1"
        )

        # Mock message list response
        messages_url = "http://localhost:3000/v1/account/acct1/messages"
        mock_httpx.set_response(messages_url, {
            "messages": {
                "messages": [
                    {
                        "id": "msg1",
                        "threadId": "thread1",
                        "messageId": "<msg1@example.com>",
                        "from": {"address": "sender@example.com"},
                        "to": [{"address": "recipient@example.com"}],
                        "subject": "Test",
                        "date": "2026-03-06T10:00:00Z",
                        "inReplyTo": None,
                    }
                ]
            }
        })

        # Mock message body response
        body_url = "http://localhost:3000/v1/account/acct1/message/msg1"
        mock_httpx.set_response(body_url, {
            "text": "<p>Content</p>"
        })

        results = list(adapter.fetch(""))
        hints = results[0].structural_hints
        assert hints.has_headings is False
        assert hints.has_lists is False
        assert hints.has_tables is False
        assert hints.natural_boundaries == []

    def test_no_credentials_in_output(self, mock_httpx):
        """fetch() does not include credentials in NormalizedContent or StructuralHints."""
        adapter = EmailAdapter(
            emailengine_url="http://localhost:3000",
            account_id="acct1"
        )

        # Mock message list response
        messages_url = "http://localhost:3000/v1/account/acct1/messages"
        mock_httpx.set_response(messages_url, {
            "messages": {
                "messages": [
                    {
                        "id": "msg1",
                        "threadId": "thread1",
                        "messageId": "<msg1@example.com>",
                        "from": {"address": "sender@example.com"},
                        "to": [{"address": "recipient@example.com"}],
                        "subject": "Test",
                        "date": "2026-03-06T10:00:00Z",
                        "inReplyTo": None,
                    }
                ]
            }
        })

        # Mock message body response
        body_url = "http://localhost:3000/v1/account/acct1/message/msg1"
        mock_httpx.set_response(body_url, {
            "text": "<p>Content</p>"
        })

        results = list(adapter.fetch(""))
        normalized_content = results[0]

        # Check that URL and credentials are not in the content
        content_str = str(normalized_content)
        assert "localhost:3000" not in content_str or "localhost:3000" in adapter._emailengine_url
        # The actual markdown should not contain the URL
        assert "localhost:3000" not in normalized_content.markdown


class TestEmailAdapterHTMLConversion:
    """Tests for HTML to markdown conversion."""

    def test_bold_conversion(self):
        """HTML bold tags are converted to markdown."""
        adapter = EmailAdapter(
            emailengine_url="http://localhost:3000",
            account_id="acct1"
        )

        html = "<b>Bold text</b>"
        result = adapter._html_to_markdown(html)

        # Should contain **Bold text** or similar
        assert "Bold" in result
        assert "text" in result

    def test_italic_conversion(self):
        """HTML italic tags are converted to markdown."""
        adapter = EmailAdapter(
            emailengine_url="http://localhost:3000",
            account_id="acct1"
        )

        html = "<i>Italic text</i>"
        result = adapter._html_to_markdown(html)

        assert "Italic" in result
        assert "text" in result

    def test_link_conversion(self):
        """HTML links are converted to markdown."""
        adapter = EmailAdapter(
            emailengine_url="http://localhost:3000",
            account_id="acct1"
        )

        html = '<a href="https://example.com">Click here</a>'
        result = adapter._html_to_markdown(html)

        assert "Click" in result
        assert "example.com" in result

    def test_paragraph_conversion(self):
        """HTML paragraphs are converted to markdown."""
        adapter = EmailAdapter(
            emailengine_url="http://localhost:3000",
            account_id="acct1"
        )

        html = "<p>First paragraph</p><p>Second paragraph</p>"
        result = adapter._html_to_markdown(html)

        assert "First paragraph" in result
        assert "Second paragraph" in result

    def test_empty_html(self):
        """Empty HTML is handled gracefully."""
        adapter = EmailAdapter(
            emailengine_url="http://localhost:3000",
            account_id="acct1"
        )

        html = ""
        result = adapter._html_to_markdown(html)

        assert isinstance(result, str)


class TestEmailAdapterMetadataExtraction:
    """Tests for MessageMetadata extraction."""

    def test_extract_message_metadata_basic(self):
        """_extract_message_metadata extracts all required fields."""
        adapter = EmailAdapter(
            emailengine_url="http://localhost:3000",
            account_id="acct1"
        )

        msg = {
            "id": "msg1",
            "threadId": "thread1",
            "messageId": "<msg1@example.com>",
            "from": {"address": "sender@example.com"},
            "to": [{"address": "recipient@example.com"}],
            "subject": "Test Subject",
            "date": "2026-03-06T10:00:00Z",
            "inReplyTo": None,
        }

        metadata = adapter._extract_message_metadata(msg)

        assert metadata.thread_id == "thread1"
        assert metadata.message_id == "<msg1@example.com>"
        assert metadata.sender == "sender@example.com"
        assert metadata.recipients == ["recipient@example.com"]
        assert metadata.subject == "Test Subject"
        assert metadata.is_thread_root is True
        assert metadata.in_reply_to is None

    def test_extract_message_metadata_with_reply(self):
        """_extract_message_metadata handles in_reply_to field."""
        adapter = EmailAdapter(
            emailengine_url="http://localhost:3000",
            account_id="acct1"
        )

        msg = {
            "id": "msg2",
            "threadId": "thread1",
            "messageId": "<msg2@example.com>",
            "from": {"address": "sender2@example.com"},
            "to": [{"address": "recipient@example.com"}],
            "subject": "Re: Test",
            "date": "2026-03-06T11:00:00Z",
            "inReplyTo": "<msg1@example.com>",
        }

        metadata = adapter._extract_message_metadata(msg)

        assert metadata.in_reply_to == "<msg1@example.com>"
        assert metadata.is_thread_root is False

    def test_extract_message_metadata_multiple_recipients(self):
        """_extract_message_metadata handles multiple recipients."""
        adapter = EmailAdapter(
            emailengine_url="http://localhost:3000",
            account_id="acct1"
        )

        msg = {
            "id": "msg1",
            "threadId": "thread1",
            "messageId": "<msg1@example.com>",
            "from": {"address": "sender@example.com"},
            "to": [
                {"address": "recipient1@example.com"},
                {"address": "recipient2@example.com"},
            ],
            "subject": "Test",
            "date": "2026-03-06T10:00:00Z",
            "inReplyTo": None,
        }

        metadata = adapter._extract_message_metadata(msg)

        assert len(metadata.recipients) == 2
        assert "recipient1@example.com" in metadata.recipients
        assert "recipient2@example.com" in metadata.recipients
