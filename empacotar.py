#!/usr/bin/env python3
"""Gera o pacote de distribuição do plugin, para importar no app pelo gerenciador
(Configurações → Plugins → Importar plugin → Do computador):

    python empacotar.py                       # dist/hidrolog-plugin-parsivel-<versão>.zip
    python empacotar.py --parsivelreader ../parsivelreader/parsivelreader

O .zip traz o manifesto, o pacote hidrolog_parsivel e, ao lado dele, a
parsivelreader: o app instalado não tem essa biblioteca, e o gerenciador põe a
raiz do plugin no caminho de importação, então ela é importada de dentro do
pacote. Sem --parsivelreader, usa a que estiver instalada no ambiente.
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
import zipfile
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib

RAIZ = Path(__file__).resolve().parent
IGNORAR = {"__pycache__", ".pytest_cache"}


def pasta_parsivelreader(indicada: str | None) -> Path:
    if indicada:
        pasta = Path(indicada).resolve()
    else:
        spec = importlib.util.find_spec("parsivelreader")
        if spec is None or not spec.submodule_search_locations:
            raise SystemExit("parsivelreader não encontrada: instale-a no ambiente ou use --parsivelreader PASTA")
        pasta = Path(next(iter(spec.submodule_search_locations))).resolve()
    if not (pasta / "__init__.py").is_file():
        raise SystemExit(f"{pasta} não é o pacote parsivelreader (falta __init__.py)")
    return pasta


def arquivos(pasta: Path):
    for arq in sorted(pasta.rglob("*")):
        if arq.is_file() and not IGNORAR & set(arq.parts) and arq.suffix not in (".pyc", ".pyo"):
            yield arq


def empacotar(parsivelreader: Path, destino: Path) -> Path:
    versao = tomllib.loads((RAIZ / "hidrolog-plugin.toml").read_text(encoding="utf-8"))["versao"]
    nome = f"hidrolog-plugin-parsivel-{versao}"
    destino.mkdir(parents=True, exist_ok=True)
    zip_ = destino / f"{nome}.zip"
    with zipfile.ZipFile(zip_, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(RAIZ / "hidrolog-plugin.toml", f"{nome}/hidrolog-plugin.toml")
        for arq in arquivos(RAIZ / "hidrolog_parsivel"):
            z.write(arq, f"{nome}/{arq.relative_to(RAIZ).as_posix()}")
        for arq in arquivos(parsivelreader):
            z.write(arq, f"{nome}/parsivelreader/{arq.relative_to(parsivelreader).as_posix()}")
    return zip_


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--parsivelreader", help="pasta do pacote parsivelreader (a que tem __init__.py)")
    ap.add_argument("--destino", default=str(RAIZ / "dist"), help="pasta do .zip (padrão: dist/)")
    args = ap.parse_args(argv)
    zip_ = empacotar(pasta_parsivelreader(args.parsivelreader), Path(args.destino))
    print(zip_)
    return 0


if __name__ == "__main__":
    sys.exit(main())
