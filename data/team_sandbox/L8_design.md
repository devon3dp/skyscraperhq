# L8 — qsb_check_port

One-file tool that exposes check_port(host, port, timeout=1.5) -> bool.
Uses socket.create_connection. Returns True if port is listening, False otherwise.
Use case: boardroom health probes across the tower.
