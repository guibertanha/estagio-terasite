#!/usr/bin/env python3
"""
watch.py — Monitora o ESP32 e gerencia o tcp_sink automaticamente.

Inicia tcp_sink.py quando a placa entra em RUNNING_BURN ou RUNNING_BURN3.
Encerra o tcp_sink quando o teste termina.

Uso:
    python tools/watch.py <IP_ESP32> [--port 5201]
    python tools/watch.py --find          # busca o ESP32 na rede automaticamente

Deixe rodando no notebook durante toda a sessão de testes.
"""
import sys
import os
import time
import signal
import argparse
import subprocess
import urllib.request
import urllib.error
import json
import socket
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

BURN_STATES         = {"RUNNING_BURN", "RUNNING_BURN3"}
POLL_INTERVAL       = 2   # segundos
CONNECT_TIMEOUT     = 3
SINK_STOP_AFTER_FAILS = 3  # falhas consecutivas antes de matar o tcp_sink
                             # evita que uma oscilação de 2-4 s mate o sink no meio de um BURN

_sink_proc = None


# ── tcp_sink ─────────────────────────────────────────────────────────────────

def start_sink(port: int):
    global _sink_proc
    if _sink_proc and _sink_proc.poll() is None:
        return  # já rodando
    script = os.path.join(os.path.dirname(__file__), "tcp_sink.py")
    _sink_proc = subprocess.Popen(
        [sys.executable, script, "--port", str(port)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    print(f"[watch] tcp_sink iniciado — porta {port} (PID {_sink_proc.pid})")


def stop_sink():
    global _sink_proc
    if _sink_proc and _sink_proc.poll() is None:
        _sink_proc.terminate()
        try:
            _sink_proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            _sink_proc.kill()
        print("[watch] tcp_sink encerrado")
    _sink_proc = None


# ── HTTP ──────────────────────────────────────────────────────────────────────

def fetch_status(url: str):
    """Retorna o JSON de /status ou None. Mostra erro real na primeira falha."""
    try:
        with urllib.request.urlopen(url, timeout=CONNECT_TIMEOUT) as r:
            return json.loads(r.read())
    except urllib.error.URLError as e:
        return ("url_error", str(e.reason))
    except Exception as e:
        return ("error", str(e))


# ── Auto-discovery ────────────────────────────────────────────────────────────

def _probe(ip: str) -> str | None:
    """Retorna o IP se /status responder com JSON válido do ESP32."""
    try:
        url = f"http://{ip}/status"
        with urllib.request.urlopen(url, timeout=1) as r:
            data = json.loads(r.read())
            if "state" in data:
                return ip
    except Exception:
        pass
    return None


def find_esp32() -> str | None:
    """Varre a subnet local em busca do endpoint /status do ESP32."""
    # Pega todos os IPs locais e deriva as subnets /24
    subnets = set()
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None):
            ip = info[4][0]
            if ip.startswith("192.168.") or ip.startswith("10.") or ip.startswith("172."):
                prefix = ".".join(ip.split(".")[:3])
                subnets.add(prefix)
    except Exception:
        pass

    if not subnets:
        print("[find] Não foi possível determinar a subnet local.")
        return None

    for prefix in sorted(subnets):
        print(f"[find] Varrendo {prefix}.1-254 ...")
        candidates = [f"{prefix}.{i}" for i in range(1, 255)]
        found = None
        with ThreadPoolExecutor(max_workers=64) as ex:
            futures = {ex.submit(_probe, ip): ip for ip in candidates}
            for f in as_completed(futures):
                result = f.result()
                if result:
                    found = result
                    break
        if found:
            return found

    return None


# ── Labels ────────────────────────────────────────────────────────────────────

def state_label(d: dict) -> str:
    s   = d.get("state", "?")
    cfg = d.get("cfg", "")
    labels = {
        "IDLE":          "aguardando Wi-Fi",
        "READY":         f"pronto — {cfg}",
        "RUNNING_WALK":  "WALK em andamento",
        "RUNNING_CLOCK": "CLOCK em andamento",
        "RUNNING_BURN":  f"BURN em andamento ← tcp_sink ativo",
        "RUNNING_BURN3": f"BURN 3×60 — bloco {d.get('block', 1)}/3 ← tcp_sink ativo",
        "FLUSHING":      "gravando dados no flash...",
    }
    return labels.get(s, s)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description="Gerencia tcp_sink automaticamente com base no estado do ESP32."
    )
    ap.add_argument("ip", nargs="?", help="IP do ESP32 (ex: 192.168.0.107)")
    ap.add_argument("--port", type=int, default=5201,
                    help="Porta do tcp_sink (padrão: 5201)")
    ap.add_argument("--find", action="store_true",
                    help="Busca o ESP32 automaticamente na rede local")
    args = ap.parse_args()

    # Resolução do IP
    esp_ip = args.ip
    if args.find or not esp_ip:
        print("[watch] Buscando ESP32 na rede local...")
        esp_ip = find_esp32()
        if not esp_ip:
            print("[watch] ESP32 não encontrado. Verifique se a placa está ligada e na mesma rede.")
            sys.exit(1)
        print(f"[watch] ESP32 encontrado em {esp_ip}\n")

    url = f"http://{esp_ip}/status"

    # Teste inicial de conectividade com diagnóstico detalhado
    print(f"[watch] Testando conexão com {url} ...")
    result = fetch_status(url)
    if isinstance(result, tuple):
        kind, detail = result
        print(f"[watch] ERRO ao conectar: {detail}")
        print(f"[watch] Verifique:")
        print(f"         1. A placa está ligada e conectada ao Wi-Fi?")
        print(f"         2. O notebook está na mesma rede que a placa?")
        print(f"         3. O IP {esp_ip} está correto? (tente --find para buscar)")
        sys.exit(1)
    print(f"[watch] Conectado! Estado atual: {result.get('state', '?')}")
    print(f"[watch] Ctrl+C para encerrar\n")
    start_sink(args.port)

    def cleanup(sig=None, frame=None):
        stop_sink()
        print("\n[watch] Encerrado.")
        sys.exit(0)

    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    last_state  = None
    fail_count  = 0

    while True:
        data = fetch_status(url)

        if isinstance(data, tuple) or data is None:
            fail_count += 1
            if fail_count == 1:
                kind, detail = data if isinstance(data, tuple) else ("error", "resposta vazia")
                print(f"[watch] Conexão perdida: {detail} (aguardando {SINK_STOP_AFTER_FAILS}× antes de parar sink)")
            if fail_count >= SINK_STOP_AFTER_FAILS:
                stop_sink()
            time.sleep(POLL_INTERVAL)
            continue

        if fail_count > 0:
            print(f"[watch] Reconectado após {fail_count} falha(s)")
            fail_count = 0
            start_sink(args.port)  # sempre relança o sink ao reconectar

        state = data.get("state", "?")
        if state != last_state:
            print(f"[watch] {state_label(data)}")
            last_state = state

        if state in BURN_STATES:
            start_sink(args.port)  # no-op se já estiver rodando

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
