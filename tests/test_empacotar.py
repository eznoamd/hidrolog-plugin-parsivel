"""O pacote de distribuição (empacotar.py) traz a parsivelreader ao lado do
plugin, porque o app instalado não a tem, e o manifesto não a exige do app."""

import sys
import zipfile
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

import empacotar  # noqa: E402


def test_pacote_traz_a_parsivelreader_e_o_manifesto_nao_a_exige(tmp_path):
    zip_ = empacotar.empacotar(empacotar.pasta_parsivelreader(None), tmp_path)
    versao = tomllib.loads((RAIZ / "hidrolog-plugin.toml").read_text(encoding="utf-8"))["versao"]
    assert zip_.name == f"hidrolog-plugin-parsivel-{versao}.zip"
    with zipfile.ZipFile(zip_) as z:
        nomes = set(z.namelist())
        raiz = f"hidrolog-plugin-parsivel-{versao}/"
        assert raiz + "hidrolog-plugin.toml" in nomes
        assert raiz + "hidrolog_parsivel/__init__.py" in nomes
        assert raiz + "parsivelreader/__init__.py" in nomes
        assert not [n for n in nomes if "__pycache__" in n or n.endswith(".pyc") or "/tests/" in n]
        manifesto = tomllib.loads(z.read(raiz + "hidrolog-plugin.toml").decode("utf-8"))
    assert "parsivelreader" not in manifesto["requer"]
