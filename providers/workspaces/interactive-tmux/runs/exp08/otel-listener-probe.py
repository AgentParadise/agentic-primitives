import socket, sys, time, os
PORT = int(os.environ.get('PORT', '4318'))
LOGF = '/host-events/otel-listener.log'
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
sock.bind(('0.0.0.0', PORT))
sock.listen(8)
sock.settimeout(60)
with open(LOGF, 'a') as out:
    out.write(f'\n=== listener up at {time.time()} on :{PORT} ===\n')
    out.flush()
    try:
        while True:
            try:
                conn, addr = sock.accept()
            except socket.timeout:
                break
            try:
                conn.settimeout(2)
                data = b''
                while True:
                    try:
                        chunk = conn.recv(4096)
                    except socket.timeout:
                        break
                    if not chunk:
                        break
                    data += chunk
                    if len(data) > 200_000:
                        break
                ts = time.time()
                out.write(f'\n--- conn from {addr} at {ts:.3f} ({len(data)} bytes) ---\n')
                # Try to dump as text up to 1500 chars; otherwise hex
                try:
                    head = data[:1500].decode('utf-8', errors='replace')
                    out.write(head)
                except Exception:
                    out.write(repr(data[:1500]))
                out.write('\n')
                out.flush()
                # Send a minimal HTTP 200 so OTel exporter sees a happy response
                conn.send(b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: 2\r\n\r\n{}')
            finally:
                conn.close()
    finally:
        out.write(f'=== listener down at {time.time()} ===\n')
        out.flush()
        sock.close()
