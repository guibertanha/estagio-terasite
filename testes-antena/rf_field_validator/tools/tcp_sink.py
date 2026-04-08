#!/usr/bin/env python3
"""
tcp_sink.py — Servidor TCP que descarta tudo que recebe.
Usado como alvo de throughput para o Perfil A (BURN).

Uso:
    python tools/tcp_sink.py [--port 5201] [--host 0.0.0.0]

Rodar no notebook/laptop conectado ao mesmo AP.
O firmware ESP32 conecta neste servidor durante a janela de 10 s de throughput.
"""
import socket
import argparse
import time
import threading

def handle(conn, addr):
    total = 0
    t0 = time.time()
    try:
        while True:
            data = conn.recv(4096)
            if not data:
                break
            total += len(data)
    except Exception:
        pass
    finally:
        conn.close()
    dt = time.time() - t0
    mbps = (total * 8 / dt / 1e6) if dt > 0 else 0
    print(f"  [{addr[0]}:{addr[1]}] {total/1024:.1f} KB em {dt:.1f}s → {mbps:.2f} Mbps")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=5201)
    ap.add_argument("--host", default="0.0.0.0")
    args = ap.parse_args()

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((args.host, args.port))
    srv.listen(5)
    print(f"tcp_sink ouvindo em {args.host}:{args.port}")
    print("Ctrl+C para encerrar\n")

    while True:
        try:
            conn, addr = srv.accept()
            t = threading.Thread(target=handle, args=(conn, addr), daemon=True)
            t.start()
        except KeyboardInterrupt:
            break

    srv.close()

if __name__ == "__main__":
    main()
