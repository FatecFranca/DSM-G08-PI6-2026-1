import os
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from pathlib import Path
import gc


def converter_para_parquet(base_path='dados_datasus'):
    """
    Converte e consolida arquivos parquet do DATASUS.

    Opções:
    1. Consolidar múltiplos arquivos mensais em um único arquivo anual
    2. Converter para outros formatos (CSV, Excel, etc.)
    3. Otimizar compressão dos parquets
    """

    base_path = Path(base_path)

    # Sistemas disponíveis
    sistemas = ['SINASC', 'SIM', 'SIH']

    for sistema in sistemas:
        caminho_sistema = base_path / sistema

        if not caminho_sistema.exists():
            continue

        print(f"\n{'='*50}")
        print(f"Processando: {sistema}")
        print(f"{'='*50}")

        # Lista todos os arquivos parquet
        arquivos_parquet = sorted(caminho_sistema.glob("*.parquet"))

        if not arquivos_parquet:
            print(f"Nenhum arquivo encontrado em {caminho_sistema}")
            continue

        print(f"Arquivos encontrados: {len(arquivos_parquet)}")

        # Para SIH (mensal), consolidar em arquivo anual
        if sistema == 'SIH':
            consolidar_sih_mensal(arquivos_parquet, caminho_sistema)

        # Gerar estatísticas dos dados
        gerar_estatisticas(arquivos_parquet, sistema)


def consolidar_sih_mensal(arquivos, caminho_destino):
    """Consolida arquivos mensais do SIH em um único arquivo anual."""

    # Agrupa arquivos por estado e ano
    grupos = {}
    for arquivo in arquivos:
        # Exemplo: SIH_SP_2021_01.parquet
        partes = arquivo.stem.split('_')
        if len(partes) == 4:
            _, estado, ano, mes = partes
            chave = f"{estado}_{ano}"
            if chave not in grupos:
                grupos[chave] = []
            grupos[chave].append(arquivo)

    # Consolida cada grupo
    for chave, lista_arquivos in grupos.items():
        estado, ano = chave.split('_')
        print(f"\nConsolidando SIH {estado} {ano}: {len(lista_arquivos)} meses")

        arquivo_consolidado = caminho_destino / f"SIH_{estado}_{ano}_CONSOLIDADO.parquet"

        # Processa em lotes para economizar memória
        writer = None
        total_registros = 0
        schema = None

        for arq in sorted(lista_arquivos):
            # Lê em chunks para não sobrecarregar memória
            parquet_file = pq.ParquetFile(arq)
            num_linhas = parquet_file.metadata.num_rows
            print(f"  - {arq.name}: {num_linhas:,} registros")

            # Processa em lotes de 100k linhas
            batch_size = 100000
            for batch in parquet_file.iter_batches(batch_size=batch_size):
                # Converte RecordBatch para Table
                table = pa.Table.from_batches([batch])

                if writer is None:
                    # Primeira escrita: cria o writer
                    schema = table.schema
                    writer = pq.ParquetWriter(arquivo_consolidado, schema, compression='snappy')

                # Escreve o batch
                writer.write_table(table)
                total_registros += len(table)

                del table
                gc.collect()

        # Fecha o writer
        if writer is not None:
            writer.close()

        print(f"\n✓ Consolidado: {arquivo_consolidado.name}")
        print(f"  Total de registros: {total_registros:,}")
        print(f"  Tamanho: {arquivo_consolidado.stat().st_size / 1024 / 1024:.2f} MB")


def gerar_estatisticas(arquivos, sistema):
    """Gera estatísticas básicas dos arquivos sem carregar dados na memória."""

    print(f"\n📊 Estatísticas {sistema}:")
    print(f"{'Arquivo':<40} {'Registros':>15} {'Tamanho (MB)':>15}")
    print("-" * 72)

    total_registros = 0
    total_tamanho = 0

    for arquivo in arquivos:
        # Usa pyarrow para ler apenas metadata, sem carregar dados
        parquet_file = pq.ParquetFile(arquivo)
        num_registros = parquet_file.metadata.num_rows
        tamanho_mb = arquivo.stat().st_size / 1024 / 1024

        print(f"{arquivo.name:<40} {num_registros:>15,} {tamanho_mb:>14.2f}")

        total_registros += num_registros
        total_tamanho += tamanho_mb

    print("-" * 72)
    print(f"{'TOTAL':<40} {total_registros:>15,} {total_tamanho:>14.2f}")


def exportar_para_csv(base_path='dados_datasus', sistema=None):
    """Exporta arquivos parquet para CSV em lotes."""

    base_path = Path(base_path)

    if sistema:
        sistemas = [sistema]
    else:
        sistemas = ['SINASC', 'SIM', 'SIH']

    for sist in sistemas:
        caminho_sistema = base_path / sist
        caminho_csv = base_path / f"{sist}_CSV"
        caminho_csv.mkdir(exist_ok=True)

        print(f"\nExportando {sist} para CSV...")

        for arquivo in caminho_sistema.glob("*.parquet"):
            print(f"  Processando {arquivo.name}...")
            arquivo_csv = caminho_csv / arquivo.name.replace('.parquet', '.csv')

            # Processa em chunks para economizar memória
            parquet_file = pq.ParquetFile(arquivo)
            batch_size = 100000

            first_batch = True
            for batch in parquet_file.iter_batches(batch_size=batch_size):
                df_batch = batch.to_pandas()

                # Primeira escrita inclui header, demais fazem append
                df_batch.to_csv(arquivo_csv, mode='w' if first_batch else 'a',
                              header=first_batch, index=False, encoding='utf-8-sig')
                first_batch = False

                del df_batch
                gc.collect()

            print(f"    ✓ {arquivo_csv.name}")


def otimizar_compressao(base_path='dados_datasus'):
    """Otimiza a compressão dos arquivos parquet em lotes."""

    base_path = Path(base_path)

    for sistema in ['SINASC', 'SIM', 'SIH']:
        caminho_sistema = base_path / sistema

        if not caminho_sistema.exists():
            continue

        print(f"\nOtimizando compressão: {sistema}")

        for arquivo in caminho_sistema.glob("*.parquet"):
            if 'OTIMIZADO' in arquivo.name:
                continue

            print(f"  Processando {arquivo.name}...")
            arquivo_otimizado = arquivo.parent / arquivo.name.replace('.parquet', '_OTIMIZADO.parquet')

            # Processa em chunks para não sobrecarregar memória
            parquet_file = pq.ParquetFile(arquivo)
            batch_size = 100000

            writer = None
            schema = None

            for batch in parquet_file.iter_batches(batch_size=batch_size):
                # Converte RecordBatch para Table
                table = pa.Table.from_batches([batch])

                if writer is None:
                    # Primeira escrita: cria o writer
                    schema = table.schema
                    writer = pq.ParquetWriter(
                        arquivo_otimizado,
                        schema,
                        compression='gzip',
                        compression_level=9
                    )

                # Escreve o batch
                writer.write_table(table)
                del table
                gc.collect()

            # Fecha o writer
            if writer is not None:
                writer.close()

            tamanho_original = arquivo.stat().st_size / 1024 / 1024
            tamanho_otimizado = arquivo_otimizado.stat().st_size / 1024 / 1024
            reducao = ((tamanho_original - tamanho_otimizado) / tamanho_original) * 100

            print(f"    ✓ {arquivo.name}")
            print(f"      Original: {tamanho_original:.2f} MB -> Otimizado: {tamanho_otimizado:.2f} MB")
            print(f"      Redução: {reducao:.1f}%")


if __name__ == "__main__":
    import sys

    print("=" * 70)
    print("CONVERSOR E CONSOLIDADOR DE DADOS DATASUS")
    print("=" * 70)

    if len(sys.argv) > 1:
        comando = sys.argv[1]

        if comando == 'consolidar':
            converter_para_parquet()

        elif comando == 'csv':
            sistema = sys.argv[2] if len(sys.argv) > 2 else None
            exportar_para_csv(sistema=sistema)

        elif comando == 'otimizar':
            otimizar_compressao()

        elif comando == 'estatisticas':
            converter_para_parquet()

        else:
            print(f"Comando desconhecido: {comando}")
            print("\nComandos disponíveis:")
            print("  python converter_parquet.py consolidar    - Consolida arquivos mensais")
            print("  python converter_parquet.py csv [sistema] - Exporta para CSV")
            print("  python converter_parquet.py otimizar      - Otimiza compressão")
            print("  python converter_parquet.py estatisticas  - Mostra estatísticas")
    else:
        # Execução padrão: mostra estatísticas e consolida SIH
        converter_para_parquet()
