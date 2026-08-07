import socket

DNS_CHECK_HOST = "8.8.8.8"  # Google public DNS — reliable, always up
DNS_CHECK_PORT = 53
CONNECT_TIMEOUT_S = 2


def is_wifi_connected() -> bool:
    """Returns True if a TCP connection to a known-reliable host succeeds."""
    try:
        socket.setdefaulttimeout(CONNECT_TIMEOUT_S)
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect(
            (DNS_CHECK_HOST, DNS_CHECK_PORT)
        )
        return True
    except OSError:
        return False