"""
Parser canônico para logs de RSSI do ESP32 (Fase 1 e Fase 2).

Formato esperado das linhas de dados:
    <timestamp_ms>,RSSI,IP=<ip>,RSSI=<valor>
    <timestamp_ms>,DISCONNECTED,...
    <timestamp_ms>,START_OK,IP=<ip>,RSSI=<valor>
    <timestamp_ms>,CHANNEL=<n>,...
    <timestamp_ms>,...,BSSID=<mac>,...

Linhas de header do PuTTY e boot do ESP32 são ignoradas silenciosamente.
"""

import re
import os
import numpy as np

DISCONNECT_TAGS = ("DISCONNECTED", "NO_WIFI", "START_FAIL")


def resolve_existing_file(basepath: str) -> str | None:
    """Tenta resolver um basename sem extensão para .txt, .csv ou sem extensão."""
    for candidate in (basepath, basepath + ".txt", basepath + ".csv"):
        if os.path.exists(candidate):
            return candidate
    return None


def extract_rssi_samples(filepath: str) -> dict:
    """
    Lê um arquivo de log de RSSI e extrai:
    - samples: lista de valores RSSI (int, dBm)
    - disconnects: contagem de eventos de desconexão
    - total_lines: total de linhas lidas
    - channels: lista de canais observados
    - bssids: conjunto de BSSIDs observados
    """
    samples = []
    disconnects = 0
    total_lines = 0
    channels = []
    bssids = set()

    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            total_lines += 1
            line = line.strip()

            if any(tag in line for tag in DISCONNECT_TAGS):
                disconnects += 1

            m = re.search(r"RSSI=(-?\d+)", line)
            if m:
                samples.append(int(m.group(1)))

            m = re.search(r"CHANNEL=([0-9]+)", line)
            if m:
                channels.append(int(m.group(1)))

            m = re.search(r"BSSID=([0-9A-Fa-f:]+)", line)
            if m:
                bssids.add(m.group(1).upper())

    return {
        "samples": samples,
        "disconnects": disconnects,
        "total_lines": total_lines,
        "channels": channels,
        "bssids": sorted(bssids),
    }


def summarize_samples(samples: list) -> dict:
    """
    Calcula estatísticas descritivas sobre uma lista de amostras RSSI.
    Retorna np.nan em todos os campos se a lista estiver vazia.
    """
    if not samples:
        return {k: np.nan for k in ("n", "mean", "std", "min", "max", "median", "p10", "p90")}

    arr = np.array(samples, dtype=float)
    return {
        "n":      len(arr),
        "mean":   float(np.mean(arr)),
        "std":    float(np.std(arr, ddof=1)) if len(arr) > 1 else 0.0,
        "min":    float(np.min(arr)),
        "max":    float(np.max(arr)),
        "median": float(np.median(arr)),
        "p10":    float(np.percentile(arr, 10)),
        "p90":    float(np.percentile(arr, 90)),
    }
