"""
================================================================================
  Consolidador e Utilitário de Parquet — DATASUS Gestacional
================================================================================
  Operações sobre os arquivos parquet baixados pelo main.py:
    - Estatísticas sem carregar dados na memória
    - Consolidação de arquivos mensais (CNES, SIA_PRENATAL) em anuais
    - Exportação para CSV
    - Otimização de compressão

  Sistemas gerenciados:
    SINAN, SIM, CNES, SIA_PRENATAL, SISVAN

  Uso:
    python converter_parquet.py estatisticas         # exibe contagens
    python converter_parquet.py consolidar           # consolida mensais
    python converter_parquet.py csv [sistema]        # exporta para CSV
    python converter_parquet.py otimizar             # recomprime com GZIP
================================================================================
"""

import gc
import sys
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

BASE_PATH = Path(__file__).parent / "dados_gestacao_datasus"

# Sistemas e seus subdiretórios de dados
SISTEMAS = ["SINAN", "SIM", "CNES", "SIA_PRENATAL", "SISVAN"]

# Sistemas com arquivos mensais que podem ser consolidados por estado/ano
SISTEMAS_MENSAIS = ["CNES", "SIA_PRENATAL"]


# ── Estatísticas ───────────────────────────────────────────────────────────────

def gerar_estatisticas(arquivos: list[Path], sistema: str) -> None:
    print(f"\n{'Arquivo':<50} {'Registros':>12} {'Tamanho MB':>12}")
    print("-" * 76)

    total_reg = 0
    total_mb  = 0.0

    for arq in arquivos:
        parquet_file = pq.ParquetFile(arq)
        n_reg   = parquet_file.metadata.num_rows
        tam_mb  = arq.stat().st_size / 1_048_576

        nome = arq.name if len(arq.name) <= 50 else arq.name[:47] + "..."
        print(f"{nome:<50} {n_reg:>12,} {tam_mb:>11.2f}")

        total_reg += n_reg
        total_mb  += tam_mb

    print("-" * 76)
    print(f"{'TOTAL':<50} {total_reg:>12,} {total_mb:>11.2f}")


def exibir_estatisticas(base_path: Path = BASE_PATH) -> None:
    for sistema in SISTEMAS:
        caminho = base_path / sistema
        if not caminho.exists():
            continue

        arquivos = sorted(caminho.glob("*.parquet"))
        if not arquivos:
            continue

        print(f"\n{'=' * 55}")
        print(f"Sistema: {sistema}  ({len(arquivos)} arquivos)")
        print(f"{'=' * 55}")
        gerar_estatisticas(arquivos, sistema)


# ── Consolidação de Arquivos Mensais ──────────────────────────────────────────

def _extrair_chave_mensal(nome: str, sistema: str) -> tuple | None:
    """
    Extrai (chave_grupo, estado, ano) do nome do arquivo mensal.

    CNES_ST_SP_2023_01  → ('ST', 'SP', 2023)
    SIA_PRENATAL_SP_2023_01 → ('', 'SP', 2023)
    """
    partes = nome.split("_")
    try:
        if sistema == "CNES" and len(partes) >= 5:
            # CNES_{grupo}_{estado}_{ano}_{mes}
            grupo, estado, ano = partes[1], partes[2], int(partes[3])
            return (grupo, estado, ano)
        elif sistema == "SIA_PRENATAL" and len(partes) >= 5:
            # SIA_PRENATAL_{estado}_{ano}_{mes}
            estado, ano = partes[2], int(partes[3])
            return ("", estado, ano)
    except (ValueError, IndexError):
        pass
    return None


def consolidar_mensais(base_path: Path = BASE_PATH) -> None:
    """Consolida arquivos mensais de CNES e SIA_PRENATAL em anuais."""
    for sistema in SISTEMAS_MENSAIS:
        caminho = base_path / sistema
        if not caminho.exists():
            continue

        print(f"\n{'=' * 55}")
        print(f"Consolidando: {sistema}")
        print(f"{'=' * 55}")

        arquivos = sorted(caminho.glob("*.parquet"))
        if not arquivos:
            print(f"  Nenhum arquivo em {caminho}")
            continue

        # Agrupa por chave (grupo, estado, ano)
        grupos: dict[tuple, list[Path]] = {}
        for arq in arquivos:
            if "CONSOLIDADO" in arq.name:
                continue
            chave = _extrair_chave_mensal(arq.stem, sistema)
            if chave:
                grupos.setdefault(chave, []).append(arq)

        for chave, lista in grupos.items():
            grupo, estado, ano = chave
            prefixo = f"{sistema}_{grupo}_{estado}_{ano}" if grupo else f"{sistema}_{estado}_{ano}"
            destino = caminho / f"{prefixo}_CONSOLIDADO.parquet"

            if destino.exists():
                print(f"  → Já existe: {destino.name}")
                continue

            print(f"  Consolidando {prefixo}: {len(lista)} meses...")
            writer = None
            total = 0

            for arq in sorted(lista):
                parquet_file = pq.ParquetFile(arq)
                for batch in parquet_file.iter_batches(batch_size=100_000):
                    table = pa.Table.from_batches([batch])
                    if writer is None:
                        writer = pq.ParquetWriter(destino, table.schema, compression="snappy")
                    writer.write_table(table)
                    total += len(table)
                    del table
                    gc.collect()

            if writer:
                writer.close()
                tam_mb = destino.stat().st_size / 1_048_576
                print(f"    ✓ {destino.name} — {total:,} registros / {tam_mb:.1f} MB")


# ── Exportação para CSV ────────────────────────────────────────────────────────

def exportar_csv(base_path: Path = BASE_PATH, sistema: str = None) -> None:
    alvos = [sistema.upper()] if sistema else SISTEMAS

    for sist in alvos:
        caminho = base_path / sist
        if not caminho.exists():
            continue

        destino_csv = base_path / f"{sist}_CSV"
        destino_csv.mkdir(exist_ok=True)

        print(f"\nExportando {sist} → CSV...")

        for arq in sorted(caminho.glob("*.parquet")):
            arq_csv = destino_csv / arq.name.replace(".parquet", ".csv")
            print(f"  {arq.name}...")

            primeiro = True
            for batch in pq.ParquetFile(arq).iter_batches(batch_size=100_000):
                df = batch.to_pandas()
                df.to_csv(
                    arq_csv,
                    mode="w" if primeiro else "a",
                    header=primeiro,
                    index=False,
                    encoding="utf-8-sig",
                )
                primeiro = False
                del df
                gc.collect()

            print(f"    ✓ {arq_csv.name}")


# ── Otimização de Compressão ───────────────────────────────────────────────────

def otimizar_compressao(base_path: Path = BASE_PATH) -> None:
    for sist in SISTEMAS:
        caminho = base_path / sist
        if not caminho.exists():
            continue

        print(f"\nOtimizando: {sist}")

        for arq in sorted(caminho.glob("*.parquet")):
            if "OTIMIZADO" in arq.name:
                continue

            destino = arq.parent / arq.name.replace(".parquet", "_OTIMIZADO.parquet")
            print(f"  {arq.name}...")

            writer = None
            for batch in pq.ParquetFile(arq).iter_batches(batch_size=100_000):
                table = pa.Table.from_batches([batch])
                if writer is None:
                    writer = pq.ParquetWriter(
                        destino, table.schema, compression="gzip", compression_level=9
                    )
                writer.write_table(table)
                del table
                gc.collect()

            if writer:
                writer.close()

            orig_mb = arq.stat().st_size / 1_048_576
            otim_mb = destino.stat().st_size / 1_048_576
            reducao = (orig_mb - otim_mb) / orig_mb * 100
            print(f"    ✓ {orig_mb:.1f} MB → {otim_mb:.1f} MB ({reducao:.0f}% redução)")


# ── Entrada principal ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("UTILITÁRIO PARQUET — DATASUS Gestacional")
    print("=" * 60)

    cmd = sys.argv[1] if len(sys.argv) > 1 else "estatisticas"

    if cmd == "estatisticas":
        exibir_estatisticas()

    elif cmd == "consolidar":
        consolidar_mensais()

    elif cmd == "csv":
        sist = sys.argv[2] if len(sys.argv) > 2 else None
        exportar_csv(sistema=sist)

    elif cmd == "otimizar":
        otimizar_compressao()

    else:
        print(f"Comando desconhecido: {cmd}")
        print("\nComandos disponíveis:")
        print("  python converter_parquet.py estatisticas       — conta registros")
        print("  python converter_parquet.py consolidar         — consolida mensais")
        print("  python converter_parquet.py csv [sistema]      — exporta para CSV")
        print("  python converter_parquet.py otimizar           — recomprime com GZIP")
