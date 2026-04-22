"""Tests for SSRF prevention in notification webhook delivery."""

from __future__ import annotations

from unittest.mock import patch

from app.services.notification_service import _is_private_url


class TestSsrfPrevention:
    """Test that _is_private_url correctly blocks private IP ranges."""

    def test_blocks_localhost_127(self):
        with patch("app.services.notification_service.socket.getaddrinfo") as mock:
            mock.return_value = [(2, 1, 0, "", ("127.0.0.1", 0))]
            assert _is_private_url("http://localhost/hook") is True

    def test_blocks_10_network(self):
        with patch("app.services.notification_service.socket.getaddrinfo") as mock:
            mock.return_value = [(2, 1, 0, "", ("10.0.0.5", 0))]
            assert _is_private_url("http://internal.corp/hook") is True

    def test_blocks_172_16_network(self):
        with patch("app.services.notification_service.socket.getaddrinfo") as mock:
            mock.return_value = [(2, 1, 0, "", ("172.16.0.1", 0))]
            assert _is_private_url("http://internal.corp/hook") is True

    def test_blocks_192_168_network(self):
        with patch("app.services.notification_service.socket.getaddrinfo") as mock:
            mock.return_value = [(2, 1, 0, "", ("192.168.1.1", 0))]
            assert _is_private_url("http://router.local/hook") is True

    def test_blocks_link_local_169_254(self):
        with patch("app.services.notification_service.socket.getaddrinfo") as mock:
            mock.return_value = [(2, 1, 0, "", ("169.254.169.254", 0))]
            assert _is_private_url("http://metadata.google/hook") is True

    def test_blocks_ipv6_loopback(self):
        with patch("app.services.notification_service.socket.getaddrinfo") as mock:
            mock.return_value = [(10, 1, 0, "", ("::1", 0, 0, 0))]
            assert _is_private_url("http://[::1]/hook") is True

    def test_allows_public_ip(self):
        with patch("app.services.notification_service.socket.getaddrinfo") as mock:
            mock.return_value = [(2, 1, 0, "", ("93.184.216.34", 0))]
            assert _is_private_url("https://example.com/hook") is False

    def test_blocks_on_dns_failure(self):
        """If DNS resolution fails, deny by default."""
        import socket

        with patch(
            "app.services.notification_service.socket.getaddrinfo",
            side_effect=socket.gaierror("DNS failed"),
        ):
            assert _is_private_url("http://doesnotexist.invalid/hook") is True

    def test_blocks_empty_hostname(self):
        assert _is_private_url("not-a-url") is True
