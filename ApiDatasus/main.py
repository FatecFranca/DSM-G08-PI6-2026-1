"""
================================================================================
  DATASUS — Download de Dados para Saúde Gestacional
================================================================================
  Datasets cobertos:
    1. SINAN   — Agravos em Gestantes (SIFG, SIFC, TOXG, TOXC, DENG, ZIKA, HEPA, CHIK)
    2. SIM     — Mortalidade Materna (CID O00-O99)
    3. CNES    — Estabelecimentos de Saúde
    4. SIA     — Produção Pré-Natal (proxy SISPreNatal)
    5. SISVAN  — Estado Nutricional

  Notas:
    - Downloads são sequenciais (FTP do DATASUS rejeita conexões paralelas)
    - Arquivos já existentes são pulados (idempotente)
    - Limite de 60 GB em disco

  Uso:
    python main.py
================================================================================
"""

import logging
import time
import warnings
from datetime import datetime
from pathlib import Path

import pandas as pd

import manifest

warnings.filterwarnings("ignore")

# ──────────────────────────────────────────────────────────────────────────────
# 1. CONFIGURAÇÃO
# ──────────────────────────────────────────────────────────────────────────────

BASE_PATH = Path(__file__).parent / "dados_datasus"

LIMITE_BYTES   = 60 * 1_073_741_824   # 60 GB
MAX_TENTATIVAS = 3                     # retentativas por arquivo
ANOS_TENTATIVA = list(range(2026, 2013, -1))

ESTADOS = [
    "AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO",
    "MA", "MG", "MS", "MT", "PA", "PB", "PE", "PI", "PR",
    "RJ", "RN", "RO", "RR", "RS", "SC", "SE", "SP", "TO",
]

MESES = list(range(1, 13))

SINAN_AGRAVOS = {
    "SIFG": "Sífilis em Gestante",
    "SIFC": "Sífilis Congênita",
    "TOXG": "Toxoplasmose Gestacional",
    "TOXC": "Toxoplasmose Congênita",
    "DENG": "Dengue",
    "ZIKA": "Zika Vírus",
    "HEPA": "Hepatites Virais",
    "CHIK": "Febre de Chikungunya",
}

CNES_GRUPOS = ["ST", "DC"]

PROC_PRENATAL = {
    "0301010072", "0211010050", "0202010473", "0202010597",
    "0202050025", "0214010015", "0202050017", "0301060029",
    "0209010061", "0209010070", "0202010201", "0202030300",
}

# ──────────────────────────────────────────────────────────────────────────────
# 2. LOGGING
# ──────────────────────────────────────────────────────────────────────────────

log_dir = BASE_PATH / "logs"
log_dir.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(
            log_dir / f"download_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log",
            encoding="utf-8",
        ),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# 3. CONTROLE DE DISCO
# ──────────────────────────────────────────────────────────────────────────────

def tamanho_total_bytes() -> int:
    return sum(f.stat().st_size for f in BASE_PATH.rglob("*.parquet") if f.is_file())


def limite_atingido() -> bool:
    total = tamanho_total_bytes()
    if total >= LIMITE_BYTES:
        log.warning(f"Limite de 60 GB atingido ({total / 1_073_741_824:.2f} GB). Parando.")
        return True
    return False


# ──────────────────────────────────────────────────────────────────────────────
# 4. UTILITÁRIOS
# ──────────────────────────────────────────────────────────────────────────────

def criar_pastas(subdirs: list[str]) -> None:
    for d in subdirs:
        (BASE_PATH / d).mkdir(parents=True, exist_ok=True)


def salvar_parquet(df: pd.DataFrame, caminho: Path) -> None:
    if df is None or df.empty:
        return
    df.to_parquet(caminho, index=False)
    mb = caminho.stat().st_size / 1_048_576
    log.info(f"  ✓ {caminho.name}  ({len(df):,} reg | {mb:.1f} MB)")
    manifest.registrar_download(caminho)


def ja_existe(caminho: Path) -> bool:
    if manifest.ja_foi_baixado(caminho):
        log.info(f"  → skip (manifest): {caminho.name}")
        return True
    if caminho.exists():
        log.info(f"  → skip: {caminho.name}")
        return True
    return False


def _com_retry(fn, descricao: str, tentativas: int = MAX_TENTATIVAS):
    """Chama fn() com retentativas e backoff exponencial."""
    for i in range(1, tentativas + 1):
        try:
            return fn()
        except Exception as exc:
            if i == tentativas:
                log.error(f"  ✗ {descricao} — falhou após {tentativas}x: {exc}")
                return None
            espera = 2 ** i
            log.warning(f"  ⚠ {descricao} tentativa {i}/{tentativas}: {exc} — aguardando {espera}s")
            time.sleep(espera)
    return None


def _df_de_parquetset(parquetset) -> pd.DataFrame | None:
    from pysus.data.local import ParquetSet
    if parquetset is None:
        return None
    if isinstance(parquetset, list):
        frames = [ps.to_dataframe() for ps in parquetset if ps is not None]
        return pd.concat(frames, ignore_index=True) if frames else None
    try:
        return parquetset.to_dataframe()
    except Exception:
        return None


# ──────────────────────────────────────────────────────────────────────────────
# 5. SINAN — sequencial (arquivos nacionais, já quase completos)
# ──────────────────────────────────────────────────────────────────────────────

def baixar_sinan(anos: list[int]) -> None:
    from pysus.ftp.databases.sinan import SINAN
    sinan = SINAN().load()
    destino = BASE_PATH / "SINAN"

    log.info("\n" + "=" * 60)
    log.info("SINAN — Agravos em Gestantes")
    log.info("=" * 60)

    for agravo, descricao in SINAN_AGRAVOS.items():
        log.info(f"\n  [{agravo}] {descricao}")
        for ano in anos:
            if limite_atingido():
                return
            caminho = destino / f"SINAN_{agravo}_{ano}.parquet"
            if ja_existe(caminho):
                continue
            try:
                arquivos = sinan.get_files(dis_code=agravo, year=ano)
                if not arquivos:
                    log.info(f"  Sem dados: {agravo} {ano}")
                    continue
                log.info(f"  Baixando SINAN/{agravo} | {ano} ({len(arquivos)} arq.)...")
                parquetset = sinan.download(arquivos, local_dir=str(destino))
                df = _df_de_parquetset(parquetset)
                if df is None:
                    continue
                if agravo in ("DENG", "ZIKA", "CHIK", "HEPA"):
                    col = next((c for c in df.columns if "GESTANT" in c.upper()), None)
                    if col:
                        # HEPA usa valores com zero à esquerda ("01"–"04"); demais usam "1"–"4"
                        df = df[df[col].isin(["1", "2", "3", "4", "01", "02", "03", "04"])].copy()
                        log.info(f"    CS_GESTANT filtrado: {len(df):,} gestantes")
                salvar_parquet(df, caminho)
            except Exception as exc:
                log.error(f"  ✗ SINAN {agravo} {ano}: {exc}")
            time.sleep(0.5)


# ──────────────────────────────────────────────────────────────────────────────
# 6. SIM — sequencial por estado
# ──────────────────────────────────────────────────────────────────────────────

def baixar_sim(estados: list[str], anos: list[int]) -> None:
    from pysus.ftp.databases.sim import SIM

    log.info("\n" + "=" * 60)
    log.info("SIM — Mortalidade Materna (sequencial)")
    log.info("=" * 60)

    sim = SIM().load()
    destino = BASE_PATH / "SIM"

    for estado in estados:
        for ano in anos:
            if limite_atingido():
                return
            caminho = destino / f"SIM_MATERNO_{estado}_{ano}.parquet"
            if ja_existe(caminho):
                continue

            def _baixar(est=estado, a=ano):
                arquivos = sim.get_files(group="CID10", uf=est, year=a)
                if not arquivos:
                    return None
                log.info(f"  SIM | {est} | {a}...")
                parquetset = sim.download(arquivos, local_dir=str(destino))
                return _df_de_parquetset(parquetset)

            df = _com_retry(_baixar, f"SIM {estado} {ano}")
            if df is None:
                time.sleep(1)
                continue

            col_grav = next((c for c in df.columns if "GRAVID" in c.upper()), None)
            col_causa = next((c for c in df.columns if c.upper() in ("CAUSABAS", "CAUSABAS_O")), None)
            if col_grav:
                df = df[df[col_grav].notna()].copy()
            elif col_causa:
                prefixos = tuple(f"O{str(i).zfill(2)}" for i in range(100))
                df = df[df[col_causa].str.startswith(prefixos, na=False)].copy()
            salvar_parquet(df, caminho)
            time.sleep(0.5)


# ──────────────────────────────────────────────────────────────────────────────
# 7. CNES — sequencial por estado (snapshots jan + jul)
# ──────────────────────────────────────────────────────────────────────────────

def baixar_cnes(estados: list[str], anos: list[int]) -> None:
    from pysus.ftp.databases.cnes import CNES

    log.info("\n" + "=" * 60)
    log.info("CNES — Estabelecimentos (sequencial)")
    log.info("=" * 60)

    cnes = CNES().load()
    destino = BASE_PATH / "CNES"
    meses_snapshot = [1, 7]

    for estado in estados:
        for grupo in CNES_GRUPOS:
            for ano in anos:
                if limite_atingido():
                    return
                for mes in meses_snapshot:
                    if limite_atingido():
                        return
                    caminho = destino / f"CNES_{grupo}_{estado}_{ano}_{mes:02d}.parquet"
                    if ja_existe(caminho):
                        continue

                    def _baixar(est=estado, g=grupo, a=ano, m=mes):
                        arquivos = cnes.get_files(group=g, uf=est, year=a, month=m)
                        if not arquivos:
                            return None
                        log.info(f"  CNES/{g} | {est} | {a}/{m:02d}...")
                        parquetset = cnes.download(arquivos, local_dir=str(destino))
                        return _df_de_parquetset(parquetset)

                    df = _com_retry(_baixar, f"CNES/{grupo} {estado} {ano}/{mes:02d}")
                    if df is not None:
                        salvar_parquet(df, caminho)
                    time.sleep(0.5)


# ──────────────────────────────────────────────────────────────────────────────
# 8. SIA — sequencial por estado (maior volume: 3888 arquivos potenciais)
# ──────────────────────────────────────────────────────────────────────────────

def baixar_sia_prenatal(estados: list[str], anos: list[int]) -> None:
    from pysus.ftp.databases.sia import SIA

    log.info("\n" + "=" * 60)
    log.info("SIA — Pré-Natal (sequencial)")
    log.info("=" * 60)

    sia = SIA().load()
    destino = BASE_PATH / "SIA_PRENATAL"

    for estado in estados:
        for ano in anos:
            if limite_atingido():
                return
            for mes in MESES:
                if limite_atingido():
                    return
                caminho = destino / f"SIA_PRENATAL_{estado}_{ano}_{mes:02d}.parquet"
                if ja_existe(caminho):
                    continue

                def _baixar(est=estado, a=ano, m=mes):
                    arquivos = sia.get_files(group="PA", uf=est, year=a, month=m)
                    if not arquivos:
                        return None
                    log.info(f"  SIA/PA | {est} | {a}/{m:02d}...")
                    parquetset = sia.download(arquivos, local_dir=str(destino))
                    return _df_de_parquetset(parquetset)

                df = _com_retry(_baixar, f"SIA/PA {estado} {ano}/{mes:02d}")
                if df is None or df.empty:
                    time.sleep(0.5)
                    continue

                col_proc = next(
                    (c for c in df.columns if "PROC" in c.upper() and "ID" in c.upper()),
                    next((c for c in df.columns if "PROC" in c.upper()), None),
                )
                col_sexo = next((c for c in df.columns if "SEXO" in c.upper()), None)
                df_pre = df[df[col_proc].isin(PROC_PRENATAL)].copy() if col_proc else df.copy()
                if col_sexo and not df_pre.empty:
                    df_pre = df_pre[df_pre[col_sexo].isin(["F", "3"])].copy()
                if not df_pre.empty:
                    log.info(f"    Pré-natal: {len(df_pre):,} de {len(df):,} proc.")
                    salvar_parquet(df_pre, caminho)
                time.sleep(0.5)


# ──────────────────────────────────────────────────────────────────────────────
# 9. SISVAN — sequencial via S3
# ──────────────────────────────────────────────────────────────────────────────

def baixar_sisvan_csv(anos: list[int]) -> None:
    import urllib.request
    import gzip
    import shutil

    log.info("\n" + "=" * 60)
    log.info("SISVAN — Download (múltiplos padrões de URL)")
    log.info("=" * 60)
    destino = BASE_PATH / "SISVAN"

    # Padrões conhecidos — testa em ordem até encontrar um que funcione
    URL_PATTERNS = [
        (
            "https://storage.googleapis.com/basedosdados-public/"
            "one-click-download/br_ms_sisvan/microdados_gestante/"
            "microdados_gestante_{ano}.csv.gz"
        ),
        (
            "https://s3.sa-east-1.amazonaws.com/ckan.saude.gov.br/"
            "SISVAN/microdados_sisvan_gestante_{ano}.csv.gz"
        ),
        (
            "https://s3.sa-east-1.amazonaws.com/ckan.saude.gov.br/"
            "SISVAN/SISVAN_Gestante_{ano}.csv.gz"
        ),
    ]

    for ano in anos:
        if limite_atingido():
            return
        caminho_pq = destino / f"sisvan_gestante_{ano}.parquet"
        if ja_existe(caminho_pq):
            continue

        baixado = False
        for padrao in URL_PATTERNS:
            url = padrao.format(ano=ano)
            caminho_gz  = destino / f"sisvan_gestante_{ano}.csv.gz"
            caminho_csv = destino / f"sisvan_gestante_{ano}.csv"
            try:
                log.info(f"  SISVAN {ano} — tentando: {url[:70]}...")
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=30) as resp, open(caminho_gz, "wb") as f:
                    shutil.copyfileobj(resp, f)
                with gzip.open(caminho_gz, "rb") as f_in, open(caminho_csv, "wb") as f_out:
                    shutil.copyfileobj(f_in, f_out)
                caminho_gz.unlink(missing_ok=True)
                df = pd.read_csv(caminho_csv, low_memory=False, encoding="utf-8")
                salvar_parquet(df, caminho_pq)
                caminho_csv.unlink(missing_ok=True)
                baixado = True
                break
            except Exception as exc:
                log.warning(f"    ✗ {exc}")
                for p in [caminho_gz, caminho_csv]:
                    if p.exists():
                        p.unlink(missing_ok=True)

        if not baixado:
            log.error(
                f"  ✗ SISVAN {ano}: nenhuma URL funcionou. "
                "Verifique manualmente em opendatasus.saude.gov.br"
            )


# ──────────────────────────────────────────────────────────────────────────────
# 10. RELATÓRIO
# ──────────────────────────────────────────────────────────────────────────────

def gerar_relatorio() -> None:
    log.info("\n" + "=" * 60)
    log.info("RELATÓRIO FINAL")
    log.info("=" * 60)
    total_arqs = total_bytes = 0
    rows = []
    for pasta in sorted(BASE_PATH.iterdir()):
        if not pasta.is_dir() or pasta.name == "logs":
            continue
        arquivos = list(pasta.glob("*.parquet"))
        n = len(arquivos)
        tam = sum(f.stat().st_size for f in arquivos)
        total_arqs  += n
        total_bytes += tam
        rows.append({"Sistema": pasta.name, "Arquivos": n, "MB": round(tam / 1_048_576, 1)})
    df = pd.DataFrame(rows)
    log.info(f"\n{df.to_string(index=False)}")
    log.info(f"\nTOTAL: {total_arqs} arquivos | {total_bytes / 1_073_741_824:.2f} GB")
    df.to_csv(BASE_PATH / "relatorio_download.csv", index=False)


# ──────────────────────────────────────────────────────────────────────────────
# 11. MAIN
# ──────────────────────────────────────────────────────────────────────────────

def main():
    inicio = datetime.now()
    log.info("=" * 70)
    log.info("  DATASUS — Download Dados Gestacionais (sequencial)")
    log.info(f"  Início : {inicio:%d/%m/%Y %H:%M:%S}")
    log.info(f"  Anos   : {ANOS_TENTATIVA[0]} → {ANOS_TENTATIVA[-1]}")
    log.info("=" * 70)

    criar_pastas(["SINAN", "SIM", "CNES", "SIA_PRENATAL", "SISVAN", "logs"])

    if not limite_atingido():
        baixar_sinan(ANOS_TENTATIVA)

    if not limite_atingido():
        baixar_sim(ESTADOS, ANOS_TENTATIVA)

    if not limite_atingido():
        baixar_cnes(ESTADOS, ANOS_TENTATIVA)

    if not limite_atingido():
        baixar_sia_prenatal(ESTADOS, ANOS_TENTATIVA)

    if not limite_atingido():
        baixar_sisvan_csv(ANOS_TENTATIVA)

    gerar_relatorio()

    dur = datetime.now() - inicio
    h, r = divmod(int(dur.total_seconds()), 3600)
    m, s = divmod(r, 60)
    gb = tamanho_total_bytes() / 1_073_741_824
    log.info(f"\nConcluído em {h:02d}h {m:02d}m {s:02d}s | {gb:.2f} GB baixados")


if __name__ == "__main__":
    main()
