#!/usr/bin/env python3
"""Gera tests/regressao/esperado.json — retrato do processamento sobre dados SINTÉTICOS.

Só rode isto quando uma mudança de resultado for INTENCIONAL e documentada (nova versão em
cientometria/versao.py + METHODOLOGY.md §3). O teste de regressão compara com este arquivo;
o modo original também é protegido pela equivalência com referencia/ (dados sintéticos).
Nada aqui valida a reprodução do artigo: isso exige as exportações originais."""
import json
import pathlib
import sys
import tempfile

RAIZ = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

from cientometria import Config, executar, ler_pasta  # noqa: E402
from cientometria.diagnostico import relatorio_campos  # noqa: E402
from cientometria.ingestao import carregar_fontes  # noqa: E402
from cientometria.manifesto import hash_tabela  # noqa: E402
from tests.sinteticos import gerar  # noqa: E402

MODOS = {"original": Config.original, "variante_exclusao": Config.variante_exclusao,
         "corrigida": Config.corrigida, "corrigida_v1": Config.corrigida_v1}
CENARIOS = {"padrao": {"n": 300, "seed": 7}, "maior": {"n": 1500, "seed": 11}}


def retrato(pasta):
    out = {}
    for nome, receita in MODOS.items():
        cfg = receita()
        bases = ler_pasta(pasta) if nome != "corrigida" else carregar_fontes(sorted(pathlib.Path(pasta).glob("*.csv")), cfg)[0]
        r = executar(bases, cfg)
        top = r.corpus.sort_values(["score_final_100", "doi"], ascending=[False, True]).head(10)
        out[nome] = {"versao_metodo": cfg.metodo_versao, "contagens": r.contagens, "estratos": r.estratos(),
                     "hash_corpus": hash_tabela(r.corpus), "top10_doi": top["doi"].astype(str).tolist(),
                     "soma_escore": round(float(r.corpus["score_final_100"].sum()), 4)}
    cfg = Config.original()
    bases, fontes = carregar_fontes(sorted(pathlib.Path(pasta).glob("*.csv")), cfg)
    out["importacao"] = {"fontes": [{"arquivo": f.arquivo, "tipo": f.tipo, "rotulo": f.rotulo, "registros": f.registros,
                                     "sha256": f.sha256} for f in fontes],
                         "campos": relatorio_campos(bases, cfg).to_dict(orient="records")}
    return out


def gerar_tudo():
    res = {}
    for nome, p in CENARIOS.items():
        with tempfile.TemporaryDirectory() as d:
            res[nome] = retrato(gerar(d, **p))
    return res


if __name__ == "__main__":
    destino = pathlib.Path(__file__).with_name("esperado.json")
    destino.write_text(json.dumps(gerar_tudo(), ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    print("gravado", destino)
