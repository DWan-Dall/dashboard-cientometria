#!/usr/bin/env python3
"""Ponte entre o dashboard (PHP) e o pacote `cientometria` — sem regras próprias.

Uso: pipeline.py <payload.json>      (mesmo contrato JSON do script anterior)
payload = {"files": [caminhos], "names": [nomes originais, opcional], "params": {...}}
params.modo = "original" | "variante_exclusao" | "corrigida".

Correção de auditoria (nov/2026): esta ponte forçava `mapeamento_tolerante=True` e
processava os arquivos na ordem do upload, então o modo "original" do dashboard não
reproduzia o `Config.original()` do pacote. Agora a leitura, a ordem e o mapeamento são
decididos por `cientometria.ingestao.carregar_fontes` conforme o modo. O script anterior
foi preservado em scripts/pipeline_legado.py.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cientometria import executar
from cientometria.ingestao import carregar_fontes
from cientometria.parametros import config_de_parametros
from cientometria.saida import resumo


def main():
    if len(sys.argv) < 2:
        raise SystemExit("Uso: pipeline.py <payload.json>")
    payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    files = [Path(p) for p in payload.get("files", [])]
    if not files:
        raise SystemExit("Nenhum arquivo recebido")
    params = payload.get("params", {}) or {}
    cfg = config_de_parametros(params)
    bases, fontes = carregar_fontes(files, cfg, nomes=payload.get("names") or None)
    res = executar(bases, cfg)
    saida = resumo(res, fontes=fontes, bases=bases, n_sensibilidade=int(params.get("n_sensibilidade", 2000)))
    print(json.dumps(saida, ensure_ascii=False, default=float))


if __name__ == "__main__":
    main()
