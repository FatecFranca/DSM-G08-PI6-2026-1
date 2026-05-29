"""
Registro persistente de downloads e cargas no pipeline DATASUS.

Arquivo: dados_datasus/pipeline_manifest.json
  {
    "downloaded": ["SINAN/SINAN_SIFG_2020.parquet", ...],
    "loaded":     ["SINAN/SINAN_SIFG_2020.parquet", ...]
  }

  downloaded = arquivo baixado com sucesso (mesmo que já excluído do disco)
  loaded     = arquivo inserido no banco (parquet pode/deve ser excluído)
"""

import json
from pathlib import Path

BASE_PATH     = Path(__file__).parent / "dados_datasus"
MANIFEST_FILE = BASE_PATH / "pipeline_manifest.json"

_cache: dict | None = None


def _load() -> dict:
    global _cache
    if _cache is not None:
        return _cache
    if MANIFEST_FILE.exists():
        try:
            with open(MANIFEST_FILE) as f:
                raw = json.load(f)
            _cache = {
                "downloaded": set(raw.get("downloaded", [])),
                "loaded":     set(raw.get("loaded",     [])),
            }
            return _cache
        except Exception:
            pass
    _cache = {"downloaded": set(), "loaded": set()}
    return _cache


def _save() -> None:
    m = _load()
    MANIFEST_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(MANIFEST_FILE, "w") as f:
        json.dump(
            {
                "downloaded": sorted(m["downloaded"]),
                "loaded":     sorted(m["loaded"]),
            },
            f,
            indent=2,
            ensure_ascii=False,
        )


def _rel(caminho: Path) -> str:
    try:
        return caminho.relative_to(BASE_PATH).as_posix()
    except ValueError:
        return caminho.name


def ja_foi_baixado(caminho: Path) -> bool:
    """True se o arquivo foi baixado ou carregado (mesmo que excluído do disco)."""
    rel = _rel(caminho)
    m = _load()
    return rel in m["downloaded"] or rel in m["loaded"]


def ja_foi_carregado(caminho: Path) -> bool:
    """True se o arquivo já foi inserido no banco."""
    return _rel(caminho) in _load()["loaded"]


def registrar_download(caminho: Path) -> None:
    rel = _rel(caminho)
    m = _load()
    if rel not in m["downloaded"] and rel not in m["loaded"]:
        m["downloaded"].add(rel)
        _save()


def registrar_carga(caminho: Path) -> None:
    rel = _rel(caminho)
    m = _load()
    m["downloaded"].add(rel)
    m["loaded"].add(rel)
    _save()


def limpar_carga_prefixo(prefixo: str) -> None:
    """Remove de 'loaded' arquivos do sistema (usado em --reset para permitir recarga)."""
    m = _load()
    antes = len(m["loaded"])
    m["loaded"] = {p for p in m["loaded"] if not p.startswith(prefixo)}
    if len(m["loaded"]) != antes:
        _save()
