#!/usr/bin/env bash
# ============================================================
#  Pipeline completo: download DATASUS → carga PostgreSQL
#  Idempotente: só carrega sistemas com arquivos novos e
#  tabela vazia (usa --reset só no sinan para limpar dados
#  duplicados de execuções anteriores).
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON=".venv/bin/python"
LOG_DIR="dados_datasus/logs"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
PIPELINE_LOG="$LOG_DIR/pipeline_${TIMESTAMP}.log"
PG="PGPASSWORD=GaFeMaPa_2025 psql -h 127.0.0.1 -p 5435 -U postgres -d maternar -t -c"

cd "$SCRIPT_DIR"
mkdir -p "$LOG_DIR"

log() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$PIPELINE_LOG"; }

db_count() {
  # Retorna número de linhas na tabela datasus.$1
  eval "$PG \"SELECT COUNT(*) FROM datasus.$1;\"" 2>/dev/null | tr -d ' \n' || echo "0"
}

# ── 1. Aguardar ou iniciar download ──────────────────────────
MAIN_PID=$(pgrep -f "python main.py" || true)
if [ -n "$MAIN_PID" ]; then
  log "Download em andamento (PID $MAIN_PID) — aguardando..."
  wait "$MAIN_PID" 2>/dev/null || true
  log "Download concluído."
else
  log "Iniciando download (main.py)..."
  DOWNLOAD_LOG="$LOG_DIR/stdout_${TIMESTAMP}.log"
  $PYTHON main.py > "$DOWNLOAD_LOG" 2>&1
  log "Download concluído. Log: $DOWNLOAD_LOG"
fi

# ── 2. Carga no banco ────────────────────────────────────────
log ""
log "======================================================"
log "  Carga no PostgreSQL (db_loader.py)"
log "======================================================"

# (sistema  diretório    padrão_glob              tabela_datasus)
declare -a SISTEMAS=(
  "sinan  SINAN          SINAN_*.parquet              sinan_agravos_gestantes"
  "sim    SIM            SIM_MATERNO_*.parquet        sim_mortalidade_materna"
  "cnes   CNES           CNES_*.parquet               cnes_estabelecimentos"
  "sia    SIA_PRENATAL   SIA_PRENATAL_*.parquet       sia_prenatal"
  "sisvan SISVAN         sisvan_gestante_*.parquet    sisvan_gestante"
  "sisvan SISVAN         sisvan_estado_nutricional_*.csv sisvan_gestante"
)

for entry in "${SISTEMAS[@]}"; do
  read -r sistema dir padrao tabela <<< "$entry"

  N_ARQS=$(find "dados_datasus/$dir/" -maxdepth 1 -name "$padrao" -not -type d 2>/dev/null | wc -l)
  N_DB=$(db_count "$tabela")

  log ""
  log "  [$sistema] arquivos=$N_ARQS  linhas_db=$N_DB"

  if [ "$N_ARQS" -eq 0 ]; then
    log "  [$sistema] Sem arquivos — pulando."
    continue
  fi

  if [ "$N_DB" -gt 0 ] && [ "$sistema" != "sinan" ]; then
    log "  [$sistema] Tabela já populada — pulando."
    continue
  fi

  # SINAN: sempre faz --reset para garantir dados limpos
  if [ "$sistema" = "sinan" ]; then
    log "  [sinan] Recarregando com --reset (limpa duplicatas)..."
    $PYTHON db_loader.py --reset sinan 2>&1 | tee -a "$PIPELINE_LOG"
  else
    $PYTHON db_loader.py "$sistema" 2>&1 | tee -a "$PIPELINE_LOG"
  fi

  log "  [$sistema] Carga concluída."
done

# ── 3. Relatório final ───────────────────────────────────────
log ""
log "======================================================"
log "  REGISTROS NO BANCO"
log "======================================================"
PGPASSWORD=GaFeMaPa_2025 psql -h 127.0.0.1 -p 5435 -U postgres -d maternar << 'SQL' | tee -a "$PIPELINE_LOG"
SELECT
  tablename AS tabela,
  (xpath('/row/c/text()',
    query_to_xml('SELECT COUNT(*) AS c FROM datasus.' || tablename,
                 false, true, '')))[1]::text::bigint AS registros
FROM pg_tables
WHERE schemaname = 'datasus'
ORDER BY tablename;
SQL

log ""
log "Pipeline concluído. Log: $PIPELINE_LOG"
