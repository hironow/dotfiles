import socket
import pytest


@pytest.mark.parametrize("host,port", [("localhost", 9299)])
def test_eventarc_port_is_listening(host, port):
    # given: eventarc emulator host/port
    # when: attempt TCP connection
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(2)
    result = s.connect_ex((host, port))
    s.close()

    # then: port should be accepting connections
    assert result == 0, f"Connection to {host}:{port} failed"
