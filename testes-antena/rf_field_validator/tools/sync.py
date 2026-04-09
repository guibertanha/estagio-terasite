#!/usr/bin/env python3
"""
sync.py — Baixa todos os logs do ESP32 e executa o parser automaticamente.

Uso:
    python tools/sync.py <IP_DO_ESP32>
    python tools/sync.py <IP_DO_ESP32> --campaign campo_2026-04-10
    python tools/sync.py <IP_DO_ESP32> --no-parse

Os CSVs são salvos em:
    testes-antena/rf_field_validator/campanhas/<campanha>/

O relatório HTML é gerado em:
    testes-antena/rf_field_validator/campanhas/<campanha>/report/report.html
"""

import sys, json, argparse, subprocess, urllib.request, urllib.parse
from pathlib import Path
from datetime import datetime

TOOLS_DIR     = Path(__file__).parent
CAMPAIGNS_DIR = TOOLS_DIR.parent / "campanhas"


def main():
    ap = argparse.ArgumentParser(description="Sync logs ESP32 → repositório + parser")
    ap.add_argument("esp_ip",
                    help="IP do ESP32 (ex: 192.168.0.42)")
    ap.add_argument("--campaign", default="",
                    help="Nome da campanha (padrão: data de hoje, ex: 2026-04-10)")
    ap.add_argument("--port", default=80, type=int,
                    help="Porta HTTP do ESP32 (padrão: 80)")
    ap.add_argument("--no-parse", action="store_true",
                    help="Não executa o parser após o download")
    args = ap.parse_args()

    base_url = f"http://{args.esp_ip}:{args.port}"
    campaign = args.campaign or datetime.now().strftime("%Y-%m-%d")
    dest     = CAMPAIGNS_DIR / campaign
    dest.mkdir(parents=True, exist_ok=True)

    print(f"\nRF Field Validator — Sync")
    print(f"ESP32 : {base_url}")
    print(f"Destino: {dest}")
    print(f"{'─'*50}\n")

    # ── Lista arquivos no ESP32 ───────────────────────────────
    try:
        with urllib.request.urlopen(f"{base_url}/logs", timeout=8) as r:
            data = json.loads(r.read().decode())
    except Exception as e:
        print(f"[ERRO] Não foi possível conectar ao ESP32: {e}")
        print(f"       Verifique o IP e se o ESP32 está na mesma rede.")
        sys.exit(1)

    files = data.get("files", [])
    if not files:
        print("Nenhum log encontrado no ESP32.")
        sys.exit(0)

    print(f"Arquivos disponíveis: {len(files)}\n")

    # ── Download ──────────────────────────────────────────────
    downloaded = 0
    skipped    = 0
    for f in files:
        name      = f["name"]
        dest_file = dest / name
        url       = f"{base_url}/download?f={urllib.parse.quote(name)}"

        # Pula se já existe com mesmo tamanho (evita baixar de novo)
        if dest_file.exists() and dest_file.stat().st_size == f.get("size", -1):
            print(f"  --  {name}  (já existe, pulando)")
            skipped += 1
            continue

        try:
            urllib.request.urlretrieve(url, dest_file)
            kb = dest_file.stat().st_size / 1024
            print(f"  OK  {name}  ({kb:.1f} KB)")
            downloaded += 1
        except Exception as e:
            print(f"  ERR {name}: {e}")

    print(f"\n{downloaded} baixado(s), {skipped} pulado(s) → {dest}")

    if downloaded == 0 and skipped == 0:
        print("Nenhum arquivo disponível.")
        return

    # ── Parser ────────────────────────────────────────────────
    if args.no_parse:
        return

    print(f"\n{'─'*50}")
    print("Executando parser...\n")
    parser = TOOLS_DIR / "parser.py"
    result = subprocess.run([sys.executable, str(parser), str(dest)])
    if result.returncode == 0:
        report = dest / "report" / "report.html"
        if report.exists():
            print(f"\nRelatório: {report}")
            # Abre automaticamente no navegador padrão
            import webbrowser
            webbrowser.open(report.as_uri())


if __name__ == "__main__":
    main()
