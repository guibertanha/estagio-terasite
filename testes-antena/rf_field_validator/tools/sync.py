#!/usr/bin/env python3
"""
sync.py — Organiza logs de campo e executa o parser automaticamente.

Modos de uso:

  1. Baixar direto do ESP32:
       python tools/sync.py 192.168.0.42
       python tools/sync.py 192.168.0.42 --campaign campo-externo

  2. Extrair um ZIP baixado pelo painel web:
       python tools/sync.py logs.zip
       python tools/sync.py logs.zip --campaign campo-externo

  3. Analisar todas as campanhas de uma vez:
       python tools/sync.py --all

Os CSVs ficam em:
    campanhas/<campanha>/

O relatório de cada campanha fica em:
    campanhas/<campanha>/report/report.html

O relatório global (--all) fica em:
    campanhas/report/report.html
"""

import sys, json, argparse, subprocess, zipfile, urllib.request, urllib.parse
from pathlib import Path
from datetime import datetime

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

TOOLS_DIR     = Path(__file__).parent
CAMPAIGNS_DIR = TOOLS_DIR.parent / "campanhas"
FILENAME_RE   = r"^(WALK|CLOCK|BURN)_"


def _run_parser(folder: Path, no_open: bool = False):
    print(f"\n{'─'*50}")
    print("Executando parser...\n")
    parser = TOOLS_DIR / "parser.py"
    result = subprocess.run([sys.executable, str(parser), str(folder)])
    if result.returncode == 0 and not no_open:
        report = folder / "report" / "report.html"
        if report.exists():
            print(f"\nRelatório: {report}")
            import webbrowser
            webbrowser.open(report.as_uri())


def _sync_esp32(ip: str, port: int, campaign: str, no_parse: bool):
    base_url = f"http://{ip}:{port}"
    dest     = CAMPAIGNS_DIR / campaign
    dest.mkdir(parents=True, exist_ok=True)

    print(f"ESP32  : {base_url}")
    print(f"Destino: {dest}\n")

    try:
        with urllib.request.urlopen(f"{base_url}/logs", timeout=8) as r:
            data = json.loads(r.read().decode())
    except Exception as e:
        print(f"[ERRO] Não conectou ao ESP32: {e}")
        print(f"       Verifique o IP e se está na mesma rede.")
        sys.exit(1)

    files = data.get("files", [])
    if not files:
        print("Nenhum log no ESP32.")
        sys.exit(0)

    print(f"Arquivos disponíveis: {len(files)}\n")

    downloaded = skipped = 0
    for f in files:
        name      = f["name"]
        dest_file = dest / name
        url       = f"{base_url}/download?f={urllib.parse.quote(name)}"

        if dest_file.exists() and dest_file.stat().st_size == f.get("size", -1):
            print(f"  --  {name}  (já existe)")
            skipped += 1
            continue

        try:
            urllib.request.urlretrieve(url, dest_file)
            kb = dest_file.stat().st_size / 1024
            print(f"  OK  {name}  ({kb:.1f} KB)")
            downloaded += 1
        except Exception as e:
            print(f"  ERR {name}: {e}")

    print(f"\n{downloaded} baixado(s), {skipped} pulado(s)")

    if not no_parse and (downloaded + skipped) > 0:
        _run_parser(dest)


def _sync_zip(zip_path: Path, campaign: str, no_parse: bool):
    dest = CAMPAIGNS_DIR / campaign
    dest.mkdir(parents=True, exist_ok=True)

    print(f"ZIP    : {zip_path.name}")
    print(f"Destino: {dest}\n")

    if not zip_path.exists():
        print(f"[ERRO] Arquivo não encontrado: {zip_path}")
        sys.exit(1)

    extracted = skipped = 0
    with zipfile.ZipFile(zip_path) as zf:
        for name in zf.namelist():
            if not name.upper().endswith(".CSV"):
                continue
            dest_file = dest / Path(name).name  # ignora subpastas dentro do zip
            data = zf.read(name)

            if dest_file.exists() and dest_file.stat().st_size == len(data):
                print(f"  --  {dest_file.name}  (já existe)")
                skipped += 1
                continue

            dest_file.write_bytes(data)
            kb = len(data) / 1024
            print(f"  OK  {dest_file.name}  ({kb:.1f} KB)")
            extracted += 1

    print(f"\n{extracted} extraído(s), {skipped} pulado(s)")

    if not no_parse and (extracted + skipped) > 0:
        _run_parser(dest)


def _sync_all():
    """Analisa todas as campanhas juntas."""
    # Coleta todos os CSVs de todas as subpastas de campanhas/
    import re
    pattern = re.compile(r"^(WALK|CLOCK|BURN)_", re.IGNORECASE)
    csvs = [f for f in CAMPAIGNS_DIR.rglob("*.csv")
            if pattern.match(f.name) and "report" not in f.parts]

    if not csvs:
        print("[ERRO] Nenhum CSV encontrado em campanhas/")
        sys.exit(1)

    camps = sorted(set(f.parent for f in csvs))
    print(f"Campanhas encontradas: {len(camps)}")
    for c in camps:
        n = sum(1 for f in c.glob("*.csv") if pattern.match(f.name))
        print(f"  {c.name}  ({n} arquivos)")

    print()
    _run_parser(CAMPAIGNS_DIR)


def main():
    ap = argparse.ArgumentParser(description="Sync e análise de logs RF")
    ap.add_argument("source", nargs="?", default="",
                    help="IP do ESP32 (192.168.x.x) ou caminho de um logs.zip")
    ap.add_argument("--campaign", default="",
                    help="Nome da campanha (padrão: data de hoje)")
    ap.add_argument("--port", default=80, type=int)
    ap.add_argument("--no-parse", action="store_true",
                    help="Só baixa/extrai, sem gerar relatório")
    ap.add_argument("--all", action="store_true",
                    help="Analisa todas as campanhas juntas")
    args = ap.parse_args()

    print(f"\nRF Field Validator — Sync")
    print(f"{'─'*50}")

    campaign = args.campaign or datetime.now().strftime("%Y-%m-%d")

    if args.all:
        _sync_all()
    elif args.source.endswith(".zip") or (args.source and Path(args.source).suffix == ".zip"):
        _sync_zip(Path(args.source), campaign, args.no_parse)
    elif args.source:
        _sync_esp32(args.source, args.port, campaign, args.no_parse)
    else:
        ap.print_help()
        sys.exit(0)


if __name__ == "__main__":
    main()
