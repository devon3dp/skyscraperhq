"""qsb_check_port — Wren+iQuest L8 collaboration."""
import socket as s
def check_port(host, port, timeout=1.5):
 try:
  s.create_connection((host, port), int(timeout))
  return True
 except (s.error, TimeoutError):
  return False

def check_ports(host_port_pairs: list) -> dict:
    return {pair: check_port(*pair) for pair in host_port_pairs}
