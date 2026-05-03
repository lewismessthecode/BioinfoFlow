"""Tests for Renderer — human vs JSON output modes."""

from __future__ import annotations

import json
from io import StringIO
from unittest.mock import patch

from rich.console import Console

from app.cli.client import SSEEvent
from app.cli.render import Renderer
from tests.test_cli.conftest import make_envelope


class TestRendererHuman:
    def _make(self) -> tuple[Console, Renderer]:
        console = Console(file=StringIO(), no_color=True)
        return console, Renderer(console, "human")

    def test_table_with_rows(self) -> None:
        console, r = self._make()
        cols = [{"key": "name", "header": "Name"}, {"key": "id", "header": "ID"}]
        rows = [{"name": "Alpha", "id": "1"}, {"name": "Beta", "id": "2"}]
        resp = make_envelope(rows)
        r.table(cols, rows, resp)
        output = console.file.getvalue()
        assert "Alpha" in output
        assert "Beta" in output

    def test_table_empty(self) -> None:
        console, r = self._make()
        resp = make_envelope([])
        r.table([], [], resp)
        output = console.file.getvalue()
        assert "No results" in output

    def test_detail(self) -> None:
        console, r = self._make()
        resp = make_envelope({"id": "1"})
        r.detail({"Name": "Test", "ID": "1"}, title="Item", raw=resp)
        output = console.file.getvalue()
        assert "Test" in output

    def test_success(self) -> None:
        console, r = self._make()
        r.success("Done!")
        output = console.file.getvalue()
        assert "Done!" in output

    def test_error(self) -> None:
        console, r = self._make()
        r.error("Something broke", code="OOPS")
        output = console.file.getvalue()
        assert "OOPS" in output
        assert "Something broke" in output


class TestRendererJson:
    def test_table_emits_envelope(self) -> None:
        resp = make_envelope([{"id": "1"}])
        r = Renderer(Console(no_color=True), "json")
        with patch("sys.stdout", new_callable=StringIO) as mock_out:
            r.table([], [{"id": "1"}], resp)
            parsed = json.loads(mock_out.getvalue())
        assert parsed["success"] is True
        assert parsed["data"] == [{"id": "1"}]

    def test_detail_emits_envelope(self) -> None:
        resp = make_envelope({"id": "1"})
        r = Renderer(Console(no_color=True), "json")
        with patch("sys.stdout", new_callable=StringIO) as mock_out:
            r.detail({}, "", resp)
            parsed = json.loads(mock_out.getvalue())
        assert parsed["data"] == {"id": "1"}

    def test_stream_event_ndjson(self) -> None:
        r = Renderer(Console(no_color=True), "json")
        event = SSEEvent(id="e1", event="run.status", data='{"status": "running"}')
        with patch("sys.stdout", new_callable=StringIO) as mock_out:
            r.stream_event(event)
            parsed = json.loads(mock_out.getvalue())
        assert parsed["event"] == "run.status"
        assert parsed["data"]["status"] == "running"
        assert parsed["id"] == "e1"

    def test_stream_event_human(self) -> None:
        console = Console(file=StringIO(), no_color=True)
        r = Renderer(console, "human")
        event = SSEEvent(id="e1", event="run.log", data='{"line": "hello"}')
        r.stream_event(event)
        output = console.file.getvalue()
        assert "run.log" in output


class TestRendererPagination:
    def test_table_with_total_count(self) -> None:
        console = Console(file=StringIO(), no_color=True)
        r = Renderer(console, "human")
        resp = make_envelope(
            [{"id": "1"}],
            pagination={"total_count": 50, "has_more": False, "limit": 20},
        )
        r.table([{"key": "id", "header": "ID"}], [{"id": "1"}], resp)
        output = console.file.getvalue()
        assert "1 of 50" in output

    def test_table_with_has_more(self) -> None:
        console = Console(file=StringIO(), no_color=True)
        r = Renderer(console, "human")
        resp = make_envelope(
            [{"id": "1"}],
            pagination={"has_more": True, "next_cursor": "abc123", "limit": 20},
        )
        r.table([{"key": "id", "header": "ID"}], [{"id": "1"}], resp)
        output = console.file.getvalue()
        assert "abc123" in output
        assert "--cursor" in output


class TestRendererEdgeCases:
    def test_success_json_with_raw(self) -> None:
        resp = make_envelope({"ok": True})
        r = Renderer(Console(no_color=True), "json")
        with patch("sys.stdout", new_callable=StringIO) as mock_out:
            r.success("Done!", raw=resp)
            parsed = json.loads(mock_out.getvalue())
        assert parsed["success"] is True

    def test_success_json_without_raw(self) -> None:
        console = Console(file=StringIO(), no_color=True)
        r = Renderer(console, "json")
        r.success("Done!")
        output = console.file.getvalue()
        assert "Done!" in output

    def test_success_quiet_suppresses_human_message(self) -> None:
        console = Console(file=StringIO(), no_color=True)
        r = Renderer(console, "human", quiet=True)
        r.success("Done!")
        assert console.file.getvalue() == ""

    def test_success_quiet_still_emits_json_envelope(self) -> None:
        from tests.test_cli.conftest import make_envelope

        resp = make_envelope({"ok": True})
        r = Renderer(Console(no_color=True), "json", quiet=True)
        with patch("sys.stdout", new_callable=StringIO) as mock_out:
            r.success("Done!", raw=resp)
            parsed = json.loads(mock_out.getvalue())
        # Quiet must NOT suppress the machine-readable envelope.
        assert parsed["success"] is True

    def test_error_json_with_raw(self) -> None:
        from tests.test_cli.conftest import make_error

        resp = make_error("OOPS", "broken", 500)
        r = Renderer(Console(no_color=True), "json")
        with patch("sys.stdout", new_callable=StringIO) as mock_out:
            r.error("broken", code="OOPS", raw=resp)
            parsed = json.loads(mock_out.getvalue())
        assert parsed["error"]["code"] == "OOPS"

    def test_error_json_without_raw(self) -> None:
        console = Console(file=StringIO(), no_color=True)
        r = Renderer(console, "json")
        r.error("broken", code="OOPS")
        output = console.file.getvalue()
        assert "OOPS" in output
        assert "broken" in output

    def test_error_without_code(self) -> None:
        console = Console(file=StringIO(), no_color=True)
        r = Renderer(console, "human")
        r.error("just a message")
        output = console.file.getvalue()
        assert "just a message" in output

    def test_spinner_json_mode(self) -> None:
        r = Renderer(Console(no_color=True), "json")
        with r.spinner("Loading..."):
            pass  # Should not raise

    def test_stream_event_no_id(self) -> None:
        r = Renderer(Console(no_color=True), "json")
        event = SSEEvent(id=None, event="run.log", data='{"line": "test"}')
        with patch("sys.stdout", new_callable=StringIO) as mock_out:
            r.stream_event(event)
            parsed = json.loads(mock_out.getvalue())
        assert "id" not in parsed

    def test_stream_event_long_preview(self) -> None:
        console = Console(file=StringIO(), no_color=True)
        r = Renderer(console, "human")
        long_data = json.dumps({"key": "x" * 300})
        event = SSEEvent(id="1", event="test.event", data=long_data)
        r.stream_event(event)
        output = console.file.getvalue()
        assert "..." in output

    def test_stream_event_non_json_data(self) -> None:
        console = Console(file=StringIO(), no_color=True)
        r = Renderer(console, "human")
        event = SSEEvent(id="1", event="test.event", data="plain text")
        r.stream_event(event)
        output = console.file.getvalue()
        assert "plain text" in output

    def test_emit_json_with_meta(self) -> None:
        resp = make_envelope({"id": "1"})
        r = Renderer(Console(no_color=True), "json")
        with patch("sys.stdout", new_callable=StringIO) as mock_out:
            r.emit_json(resp)
            parsed = json.loads(mock_out.getvalue())
        assert "meta" in parsed
        assert "request_id" in parsed["meta"]
