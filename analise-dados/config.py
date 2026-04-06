"""
Caminhos centralizados para o projeto de análise de antenas.
Todos os paths são resolvidos relativamente à raiz do repositório,
eliminando caminhos absolutos hardcoded nos scripts.
"""

from pathlib import Path

# Raiz do repositório (dois níveis acima deste arquivo)
REPO_ROOT = Path(__file__).parent.parent

# Diretórios de dados de entrada
FASE1_DIR = REPO_ROOT / "dados-brutos" / "rssi-fase1"
FASE2_DIR = REPO_ROOT / "dados-brutos" / "rssi-fase2"
PING_DIR  = REPO_ROOT / "dados-brutos" / "ping"

# Diretórios de saída (criados automaticamente pelos scripts)
OUTPUT_RSSI      = REPO_ROOT / "relatorios" / "rssi-completo"
OUTPUT_PING      = REPO_ROOT / "relatorios" / "ping-tecnico"
OUTPUT_ATENUACAO = REPO_ROOT / "relatorios" / "rssi-atenuacao"
