"""Tests for the AppleRemindersAdapter."""

import pytest

import httpx

from context_library.adapters.apple_reminders import AppleRemindersAdapter
from context_library.storage.models import Domain, PollStrategy, NormalizedContent, TaskMetadata


class TestAppleRemindersAdapterInitialization:
    """Tests for AppleRemindersAdapter initialization."""

    def test_init_default_parameters(self):
        """__init__ uses default parameters when not provided."""
        adapter = AppleRemindersAdapter()
        assert adapter._api_url == "http://127.0.0.1:7123"
        assert adapter._api_key is None
        assert adapter._list_name is None
        assert adapter._account_id == "default"

    def test_init_custom_parameters(self):
        """__init__ accepts and stores custom parameters."""
        adapter = AppleRemindersAdapter(
            api_url="http://localhost:8000",
            api_key="test_key",
            list_name="My Reminders",
            account_id="work",
        )
        assert adapter._api_url == "http://localhost:8000"
        assert adapter._api_key == "test_key"
        assert adapter._list_name == "My Reminders"
        assert adapter._account_id == "work"

    def test_init_strips_trailing_slash_from_url(self):
        """__init__ strips trailing slash from api_url."""
        adapter = AppleRemindersAdapter(api_url="http://127.0.0.1:7123/")
        assert adapter._api_url == "http://127.0.0.1:7123"

    def test_init_no_trailing_slash(self):
        """__init__ leaves api_url unchanged if no trailing slash."""
        adapter = AppleRemindersAdapter(api_url="http://127.0.0.1:7123")
        assert adapter._api_url == "http://127.0.0.1:7123"


class TestAppleRemindersAdapterProperties:
    """Tests for AppleRemindersAdapter properties."""

    def test_adapter_id_format_default(self):
        """adapter_id has correct format: apple_reminders:{account_id}."""
        adapter = AppleRemindersAdapter()
        assert adapter.adapter_id == "apple_reminders:default"

    def test_adapter_id_format_custom_account(self):
        """adapter_id uses custom account_id."""
        adapter = AppleRemindersAdapter(account_id="work")
        assert adapter.adapter_id == "apple_reminders:work"

    def test_adapter_id_deterministic(self):
        """adapter_id is deterministic for the same configuration."""
        adapter1 = AppleRemindersAdapter(account_id="work")
        adapter2 = AppleRemindersAdapter(account_id="work")
        assert adapter1.adapter_id == adapter2.adapter_id

    def test_different_accounts_different_ids(self):
        """Different account IDs produce different adapter_ids."""
        adapter1 = AppleRemindersAdapter(account_id="work")
        adapter2 = AppleRemindersAdapter(account_id="personal")
        assert adapter1.adapter_id != adapter2.adapter_id

    def test_domain_property(self):
        """domain property returns Domain.TASKS."""
        adapter = AppleRemindersAdapter()
        assert adapter.domain == Domain.TASKS

    def test_poll_strategy_property(self):
        """poll_strategy property returns PollStrategy.PULL."""
        adapter = AppleRemindersAdapter()
        assert adapter.poll_strategy == PollStrategy.PULL

    def test_normalizer_version_property(self):
        """normalizer_version property returns '1.0.0'."""
        adapter = AppleRemindersAdapter()
        assert adapter.normalizer_version == "1.0.0"


class TestAppleRemindersAdapterFetch:
    """Tests for AppleRemindersAdapter.fetch() method."""

    @pytest.fixture
    def mock_httpx(self, monkeypatch):
        """Fixture for mocking httpx requests via httpx.Client."""
        class MockResponse:
            def __init__(self, json_data, status_code=200, url=""):
                self._json_data = json_data
                self.status_code = status_code
                self.url = url

            def json(self):
                return self._json_data

            def raise_for_status(self):
                if self.status_code >= 400:
                    raise httpx.HTTPStatusError(
                        f"HTTP {self.status_code}",
                        request=None,
                        response=self,
                    )

        class MockClient:
            """Mock httpx.Client that tracks requests and returns configured responses."""
            def __init__(self, *args, **kwargs):
                self.requests = []
                self.responses = {}
                self.timeout = kwargs.get("timeout")

            def get(self, url, params=None, headers=None, timeout=None):
                self.requests.append({"url": url, "params": params, "headers": headers})
                key = (url, tuple(sorted(params.items())) if params else ())
                return self.responses.get(url, MockResponse({}, url=url))

            def set_response(self, url, data, status_code=200):
                self.responses[url] = MockResponse(data, status_code, url=url)

            def close(self):
                """No-op for mock client."""
                pass

        mock_client = MockClient()

        monkeypatch.setattr(
            "context_library.adapters.apple_reminders.httpx.Client",
            lambda *args, **kwargs: mock_client
        )

        return mock_client

    def test_fetch_single_reminder(self, mock_httpx):
        """fetch() yields NormalizedContent for a single reminder."""
        adapter = AppleRemindersAdapter(api_url="http://127.0.0.1:7123")

        # Mock reminders response
        reminders_url = "http://127.0.0.1:7123/reminders"
        mock_httpx.set_response(reminders_url, [
            {
                "id": "reminder-1",
                "title": "Buy milk",
                "notes": "Get 2% milk",
                "list": "Shopping",
                "completed": False,
                "completionDate": None,
                "dueDate": "2026-03-08T18:00:00Z",
                "priority": 5,
                "modifiedAt": "2026-03-06T10:00:00Z",
                "collaborators": [],
            }
        ])

        results = list(adapter.fetch(""))
        assert len(results) == 1
        assert isinstance(results[0], NormalizedContent)
        assert results[0].source_id == "Shopping/reminder-1"
        assert "Buy milk" in results[0].markdown

    def test_fetch_multiple_reminders(self, mock_httpx):
        """fetch() yields NormalizedContent for multiple reminders."""
        adapter = AppleRemindersAdapter(api_url="http://127.0.0.1:7123")

        reminders_url = "http://127.0.0.1:7123/reminders"
        mock_httpx.set_response(reminders_url, [
            {
                "id": "reminder-1",
                "title": "Task 1",
                "notes": None,
                "list": "Work",
                "completed": False,
                "completionDate": None,
                "dueDate": None,
                "priority": 0,
                "modifiedAt": "2026-03-06T10:00:00Z",
                "collaborators": [],
            },
            {
                "id": "reminder-2",
                "title": "Task 2",
                "notes": None,
                "list": "Work",
                "completed": True,
                "completionDate": "2026-03-06T09:00:00Z",
                "dueDate": None,
                "priority": 1,
                "modifiedAt": "2026-03-06T09:00:00Z",
                "collaborators": [],
            },
        ])

        results = list(adapter.fetch(""))
        assert len(results) == 2
        assert results[0].source_id == "Work/reminder-1"
        assert results[1].source_id == "Work/reminder-2"

    def test_fetch_incremental_with_since(self, mock_httpx):
        """fetch() passes 'since' query parameter for incremental fetch."""
        adapter = AppleRemindersAdapter(api_url="http://127.0.0.1:7123")

        reminders_url = "http://127.0.0.1:7123/reminders"
        mock_httpx.set_response(reminders_url, [])

        list(adapter.fetch("2026-03-06T10:00:00Z"))

        # Verify the request was made with the 'since' parameter
        request = mock_httpx.requests[0]
        assert request["params"]["since"] == "2026-03-06T10:00:00Z"

    def test_fetch_with_list_filter(self, mock_httpx):
        """fetch() passes 'list' query parameter when list_name is set."""
        adapter = AppleRemindersAdapter(
            api_url="http://127.0.0.1:7123",
            list_name="Shopping"
        )

        reminders_url = "http://127.0.0.1:7123/reminders"
        mock_httpx.set_response(reminders_url, [])

        list(adapter.fetch(""))

        # Verify the request was made with the 'list' parameter
        request = mock_httpx.requests[0]
        assert request["params"]["list"] == "Shopping"

    def test_fetch_with_api_key_auth(self, mock_httpx):
        """fetch() sends Authorization header when api_key is provided."""
        adapter = AppleRemindersAdapter(
            api_url="http://127.0.0.1:7123",
            api_key="test_token_123"
        )

        reminders_url = "http://127.0.0.1:7123/reminders"
        mock_httpx.set_response(reminders_url, [])

        list(adapter.fetch(""))

        # Verify the request was made with Authorization header
        request = mock_httpx.requests[0]
        assert request["headers"]["Authorization"] == "Bearer test_token_123"

    def test_fetch_without_api_key_no_auth_header(self, mock_httpx):
        """fetch() omits Authorization header when api_key is None."""
        adapter = AppleRemindersAdapter(api_url="http://127.0.0.1:7123")

        reminders_url = "http://127.0.0.1:7123/reminders"
        mock_httpx.set_response(reminders_url, [])

        list(adapter.fetch(""))

        # Verify the request was made without Authorization header
        request = mock_httpx.requests[0]
        assert "Authorization" not in (request["headers"] or {})

    def test_fetch_completed_reminder_status(self, mock_httpx):
        """fetch() maps completed=true to status='completed'."""
        adapter = AppleRemindersAdapter(api_url="http://127.0.0.1:7123")

        reminders_url = "http://127.0.0.1:7123/reminders"
        mock_httpx.set_response(reminders_url, [
            {
                "id": "reminder-1",
                "title": "Done task",
                "notes": None,
                "list": "Work",
                "completed": True,
                "completionDate": "2026-03-06T09:00:00Z",
                "dueDate": None,
                "priority": 0,
                "modifiedAt": "2026-03-06T09:00:00Z",
                "collaborators": [],
            }
        ])

        results = list(adapter.fetch(""))
        metadata = TaskMetadata.model_validate(results[0].structural_hints.extra_metadata)
        assert metadata.status == "completed"

    def test_fetch_open_reminder_status(self, mock_httpx):
        """fetch() maps completed=false to status='open'."""
        adapter = AppleRemindersAdapter(api_url="http://127.0.0.1:7123")

        reminders_url = "http://127.0.0.1:7123/reminders"
        mock_httpx.set_response(reminders_url, [
            {
                "id": "reminder-1",
                "title": "Open task",
                "notes": None,
                "list": "Work",
                "completed": False,
                "completionDate": None,
                "dueDate": None,
                "priority": 0,
                "modifiedAt": "2026-03-06T10:00:00Z",
                "collaborators": [],
            }
        ])

        results = list(adapter.fetch(""))
        metadata = TaskMetadata.model_validate(results[0].structural_hints.extra_metadata)
        assert metadata.status == "open"

    def test_fetch_priority_mapping(self, mock_httpx):
        """fetch() maps EventKit priority values correctly."""
        adapter = AppleRemindersAdapter(api_url="http://127.0.0.1:7123")

        reminders_url = "http://127.0.0.1:7123/reminders"
        mock_httpx.set_response(reminders_url, [
            {
                "id": "r1",
                "title": "High priority",
                "notes": None,
                "list": "Work",
                "completed": False,
                "completionDate": None,
                "dueDate": None,
                "priority": 1,  # high
                "modifiedAt": "2026-03-06T10:00:00Z",
                "collaborators": [],
            },
            {
                "id": "r2",
                "title": "Medium priority",
                "notes": None,
                "list": "Work",
                "completed": False,
                "completionDate": None,
                "dueDate": None,
                "priority": 5,  # medium
                "modifiedAt": "2026-03-06T10:00:00Z",
                "collaborators": [],
            },
            {
                "id": "r3",
                "title": "Low priority",
                "notes": None,
                "list": "Work",
                "completed": False,
                "completionDate": None,
                "dueDate": None,
                "priority": 9,  # low
                "modifiedAt": "2026-03-06T10:00:00Z",
                "collaborators": [],
            },
            {
                "id": "r4",
                "title": "No priority",
                "notes": None,
                "list": "Work",
                "completed": False,
                "completionDate": None,
                "dueDate": None,
                "priority": 0,  # none
                "modifiedAt": "2026-03-06T10:00:00Z",
                "collaborators": [],
            },
        ])

        results = list(adapter.fetch(""))

        # High priority (1) -> internal 1
        m1 = TaskMetadata.model_validate(results[0].structural_hints.extra_metadata)
        assert m1.priority == 1

        # Medium priority (5) -> internal 3
        m2 = TaskMetadata.model_validate(results[1].structural_hints.extra_metadata)
        assert m2.priority == 3

        # Low priority (9) -> internal 4
        m3 = TaskMetadata.model_validate(results[2].structural_hints.extra_metadata)
        assert m3.priority == 4

        # No priority (0) -> None
        m4 = TaskMetadata.model_validate(results[3].structural_hints.extra_metadata)
        assert m4.priority is None

    def test_fetch_with_collaborators(self, mock_httpx):
        """fetch() extracts collaborators list."""
        adapter = AppleRemindersAdapter(api_url="http://127.0.0.1:7123")

        reminders_url = "http://127.0.0.1:7123/reminders"
        mock_httpx.set_response(reminders_url, [
            {
                "id": "reminder-1",
                "title": "Team task",
                "notes": None,
                "list": "Work",
                "completed": False,
                "completionDate": None,
                "dueDate": None,
                "priority": 0,
                "modifiedAt": "2026-03-06T10:00:00Z",
                "collaborators": ["alice@example.com", "bob@example.com"],
            }
        ])

        results = list(adapter.fetch(""))
        metadata = TaskMetadata.model_validate(results[0].structural_hints.extra_metadata)
        assert metadata.collaborators == ("alice@example.com", "bob@example.com")

    def test_fetch_with_due_date(self, mock_httpx):
        """fetch() extracts due date."""
        adapter = AppleRemindersAdapter(api_url="http://127.0.0.1:7123")

        reminders_url = "http://127.0.0.1:7123/reminders"
        mock_httpx.set_response(reminders_url, [
            {
                "id": "reminder-1",
                "title": "Task with deadline",
                "notes": None,
                "list": "Work",
                "completed": False,
                "completionDate": None,
                "dueDate": "2026-03-10T17:00:00Z",
                "priority": 0,
                "modifiedAt": "2026-03-06T10:00:00Z",
                "collaborators": [],
            }
        ])

        results = list(adapter.fetch(""))
        metadata = TaskMetadata.model_validate(results[0].structural_hints.extra_metadata)
        assert metadata.due_date == "2026-03-10T17:00:00Z"

    def test_fetch_task_metadata_contains_required_fields(self, mock_httpx):
        """fetch() produces TaskMetadata that passes model_validate."""
        adapter = AppleRemindersAdapter(api_url="http://127.0.0.1:7123")

        reminders_url = "http://127.0.0.1:7123/reminders"
        mock_httpx.set_response(reminders_url, [
            {
                "id": "reminder-1",
                "title": "Test task",
                "notes": "Notes here",
                "list": "Work",
                "completed": False,
                "completionDate": None,
                "dueDate": "2026-03-10T17:00:00Z",
                "priority": 3,
                "modifiedAt": "2026-03-06T10:00:00Z",
                "collaborators": ["user@example.com"],
            }
        ])

        results = list(adapter.fetch(""))
        metadata_dict = results[0].structural_hints.extra_metadata

        # This should not raise if TaskMetadata validation passes
        metadata = TaskMetadata.model_validate(metadata_dict)
        assert metadata.task_id == "reminder-1"
        assert metadata.title == "Test task"
        assert metadata.status == "open"

    def test_fetch_http_error_propagates(self, mock_httpx):
        """fetch() propagates HTTP errors."""
        adapter = AppleRemindersAdapter(api_url="http://127.0.0.1:7123")

        reminders_url = "http://127.0.0.1:7123/reminders"
        mock_httpx.set_response(reminders_url, {}, status_code=500)

        with pytest.raises(httpx.HTTPStatusError):
            list(adapter.fetch(""))

    def test_fetch_invalid_response_schema_raises(self, mock_httpx):
        """fetch() raises ValueError if response is not a list."""
        adapter = AppleRemindersAdapter(api_url="http://127.0.0.1:7123")

        reminders_url = "http://127.0.0.1:7123/reminders"
        mock_httpx.set_response(reminders_url, {"reminders": []})  # Should be a list, not dict

        with pytest.raises(ValueError, match="must be a list"):
            list(adapter.fetch(""))

    def test_fetch_missing_required_field_raises(self, mock_httpx):
        """fetch() raises KeyError if reminder is missing required field."""
        adapter = AppleRemindersAdapter(api_url="http://127.0.0.1:7123")

        reminders_url = "http://127.0.0.1:7123/reminders"
        mock_httpx.set_response(reminders_url, [
            {
                "id": "reminder-1",
                # Missing 'title'
                "notes": None,
                "list": "Work",
                "completed": False,
                "completionDate": None,
                "dueDate": None,
                "priority": 0,
                "modifiedAt": "2026-03-06T10:00:00Z",
                "collaborators": [],
            }
        ])

        with pytest.raises(KeyError, match="title"):
            list(adapter.fetch(""))

    def test_fetch_invalid_field_type_raises(self, mock_httpx):
        """fetch() raises TypeError if reminder field has wrong type."""
        adapter = AppleRemindersAdapter(api_url="http://127.0.0.1:7123")

        reminders_url = "http://127.0.0.1:7123/reminders"
        mock_httpx.set_response(reminders_url, [
            {
                "id": "reminder-1",
                "title": "Task",
                "notes": None,
                "list": "Work",
                "completed": "not a bool",  # Should be bool
                "completionDate": None,
                "dueDate": None,
                "priority": 0,
                "modifiedAt": "2026-03-06T10:00:00Z",
                "collaborators": [],
            }
        ])

        with pytest.raises(TypeError, match="completed"):
            list(adapter.fetch(""))

    def test_context_manager_closes_client(self, mock_httpx):
        """Adapter supports context manager and closes client on exit."""
        with AppleRemindersAdapter(api_url="http://127.0.0.1:7123") as adapter:
            assert adapter._client is not None
        # Client should be closed after exiting context (close() is called)


class TestAppleRemindersAdapterImportGuard:
    """Tests for import guard and error handling."""

    def test_import_error_without_httpx(self, monkeypatch):
        """AppleRemindersAdapter raises ImportError if httpx is not installed."""
        # Simulate httpx not being available
        import sys
        original_httpx = sys.modules.get('httpx')
        sys.modules['httpx'] = None

        try:
            # Need to reload the module to pick up the missing dependency
            monkeypatch.setattr(
                "context_library.adapters.apple_reminders.HAS_HTTPX",
                False
            )

            with pytest.raises(ImportError, match="httpx is required"):
                AppleRemindersAdapter()
        finally:
            # Restore original httpx module
            if original_httpx:
                sys.modules['httpx'] = original_httpx
            else:
                sys.modules.pop('httpx', None)


class TestAppleRemindersAdapterMarkdownGeneration:
    """Tests for markdown generation in fetch()."""

    @pytest.fixture
    def mock_httpx(self, monkeypatch):
        """Fixture for mocking httpx."""
        class MockResponse:
            def __init__(self, json_data, status_code=200, url=""):
                self._json_data = json_data
                self.status_code = status_code
                self.url = url

            def json(self):
                return self._json_data

            def raise_for_status(self):
                if self.status_code >= 400:
                    raise httpx.HTTPStatusError(
                        f"HTTP {self.status_code}",
                        request=None,
                        response=self,
                    )

        class MockClient:
            def __init__(self, *args, **kwargs):
                self.responses = {}

            def get(self, url, params=None, headers=None, timeout=None):
                return self.responses.get(url, MockResponse({}, url=url))

            def set_response(self, url, data, status_code=200):
                self.responses[url] = MockResponse(data, status_code, url=url)

            def close(self):
                pass

        mock_client = MockClient()

        monkeypatch.setattr(
            "context_library.adapters.apple_reminders.httpx.Client",
            lambda *args, **kwargs: mock_client
        )

        return mock_client

    def test_markdown_includes_title(self, mock_httpx):
        """Generated markdown includes reminder title."""
        adapter = AppleRemindersAdapter()

        reminders_url = "http://127.0.0.1:7123/reminders"
        mock_httpx.set_response(reminders_url, [
            {
                "id": "reminder-1",
                "title": "Buy groceries",
                "notes": None,
                "list": "Shopping",
                "completed": False,
                "completionDate": None,
                "dueDate": None,
                "priority": 0,
                "modifiedAt": "2026-03-06T10:00:00Z",
                "collaborators": [],
            }
        ])

        results = list(adapter.fetch(""))
        assert "Buy groceries" in results[0].markdown

    def test_markdown_includes_status(self, mock_httpx):
        """Generated markdown includes status."""
        adapter = AppleRemindersAdapter()

        reminders_url = "http://127.0.0.1:7123/reminders"
        mock_httpx.set_response(reminders_url, [
            {
                "id": "reminder-1",
                "title": "Task",
                "notes": None,
                "list": "Work",
                "completed": False,
                "completionDate": None,
                "dueDate": None,
                "priority": 0,
                "modifiedAt": "2026-03-06T10:00:00Z",
                "collaborators": [],
            }
        ])

        results = list(adapter.fetch(""))
        assert "open" in results[0].markdown

    def test_markdown_includes_priority(self, mock_httpx):
        """Generated markdown includes priority when set."""
        adapter = AppleRemindersAdapter()

        reminders_url = "http://127.0.0.1:7123/reminders"
        mock_httpx.set_response(reminders_url, [
            {
                "id": "reminder-1",
                "title": "Task",
                "notes": None,
                "list": "Work",
                "completed": False,
                "completionDate": None,
                "dueDate": None,
                "priority": 1,  # high
                "modifiedAt": "2026-03-06T10:00:00Z",
                "collaborators": [],
            }
        ])

        results = list(adapter.fetch(""))
        assert "Priority" in results[0].markdown

    def test_markdown_includes_notes(self, mock_httpx):
        """Generated markdown includes notes when present."""
        adapter = AppleRemindersAdapter()

        reminders_url = "http://127.0.0.1:7123/reminders"
        mock_httpx.set_response(reminders_url, [
            {
                "id": "reminder-1",
                "title": "Task",
                "notes": "Important note",
                "list": "Work",
                "completed": False,
                "completionDate": None,
                "dueDate": None,
                "priority": 0,
                "modifiedAt": "2026-03-06T10:00:00Z",
                "collaborators": [],
            }
        ])

        results = list(adapter.fetch(""))
        assert "Important note" in results[0].markdown
