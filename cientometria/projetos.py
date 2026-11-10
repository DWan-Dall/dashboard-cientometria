"""Projetos de análise: arquivos importados, configurações, execuções e histórico.

Estrutura em disco (raiz = $CIENTOMETRIA_PROJETOS ou ./projetos):

    <raiz>/<slug>/
        projeto.json            nome, descrição, fontes bibliográficas, configuração padrão
        arquivos.json           registro de arquivos importados (id, nome, sha256, data)
        arquivos/<sha12>__<nome>  cópia imutável do arquivo importado
        execucoes/<id>/         uma pasta por execução (NUNCA sobrescrita)
            manifesto.json, contagens.json, corpus.csv, consolidado.csv,
            diagnosticos/, bibliometria/, graficos/, relatorios/
        historico.jsonl         eventos (append-only)

Importar de novo um arquivo com o mesmo conteúdo não duplica; com conteúdo diferente
cria nova entrada. Nenhuma importação altera execuções anteriores.

Os arquivos das bases podem ter licença restrita: a pasta de projetos está no .gitignore.
"""
from __future__ import annotations
import json
import os
import re
import shutil
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from . import bibliometria, diagnostico, graficos, manifesto as M, relatorios, robustez
from .config import Config
from .entrada import normalizar_estendido
from .ingestao import carregar_fontes, sha256_arquivo, FORMATOS
from .pipeline import executar as executar_pipeline


def raiz_padrao() -> Path:
    return Path(os.environ.get("CIENTOMETRIA_PROJETOS", "projetos")).resolve()


def _agora():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _slug(nome: str) -> str:
    s = unicodedata.normalize("NFKD", nome)
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:60] or "projeto"


def _nome_seguro(nome: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", os.path.basename(nome))


def _json(p: Path, obj):
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    tmp.replace(p)


class Projeto:
    def __init__(self, pasta: Path):
        self.pasta = Path(pasta)
        if not (self.pasta / "projeto.json").exists():
            raise FileNotFoundError(f"Projeto não encontrado: {self.pasta}")

    # ---------------- criação / listagem ----------------
    @classmethod
    def criar(cls, nome: str, descricao: str = "", fontes_bibliograficas: list | None = None,
              raiz: Path | None = None, configuracao: dict | None = None) -> "Projeto":
        raiz = Path(raiz or raiz_padrao())
        slug = _slug(nome)
        pasta, i = raiz / slug, 2
        while pasta.exists():
            pasta, i = raiz / f"{slug}-{i}", i + 1
        (pasta / "arquivos").mkdir(parents=True)
        (pasta / "execucoes").mkdir()
        _json(pasta / "projeto.json", {"slug": pasta.name, "nome": nome, "descricao": descricao,
                                        "fontes_bibliograficas": fontes_bibliograficas or [],
                                        "configuracao_padrao": configuracao or {"modo": "original"},
                                        "criado_em": _agora()})
        _json(pasta / "arquivos.json", [])
        p = cls(pasta)
        p._evento("projeto_criado", nome=nome)
        return p

    @classmethod
    def abrir(cls, slug: str, raiz: Path | None = None) -> "Projeto":
        return cls(Path(raiz or raiz_padrao()) / slug)

    @staticmethod
    def listar(raiz: Path | None = None) -> list:
        raiz = Path(raiz or raiz_padrao())
        if not raiz.exists():
            return []
        out = []
        for p in sorted(raiz.iterdir()):
            if (p / "projeto.json").exists():
                info = json.loads((p / "projeto.json").read_text(encoding="utf-8"))
                info["n_arquivos"] = len(json.loads((p / "arquivos.json").read_text(encoding="utf-8")))
                info["n_execucoes"] = len([x for x in (p / "execucoes").iterdir() if x.is_dir()])
                out.append(info)
        return out

    # ---------------- metadados ----------------
    @property
    def info(self) -> dict:
        return json.loads((self.pasta / "projeto.json").read_text(encoding="utf-8"))

    def atualizar(self, **campos):
        info = self.info
        permitidos = {"nome", "descricao", "fontes_bibliograficas", "configuracao_padrao"}
        info.update({k: v for k, v in campos.items() if k in permitidos})
        _json(self.pasta / "projeto.json", info)
        self._evento("projeto_atualizado", campos=sorted(campos))

    def _evento(self, tipo: str, **dados):
        with open(self.pasta / "historico.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps({"quando": _agora(), "evento": tipo, **dados}, ensure_ascii=False, default=str) + "\n")

    def historico(self) -> list:
        p = self.pasta / "historico.jsonl"
        return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()] if p.exists() else []

    # ---------------- arquivos ----------------
    def arquivos(self, incluir_removidos: bool = False) -> list:
        lista = json.loads((self.pasta / "arquivos.json").read_text(encoding="utf-8"))
        return lista if incluir_removidos else [a for a in lista if a.get("ativo", True)]

    def importar(self, caminho, nome: str | None = None, base: str | None = None) -> dict:
        """Copia o arquivo para o projeto (imutável). `base` força o tipo de base (opcional)."""
        caminho = Path(caminho)
        nome = _nome_seguro(nome or caminho.name)
        if Path(nome).suffix.lower() not in FORMATOS:
            raise ValueError(f"Formato não suportado: {nome}")
        sha = sha256_arquivo(caminho)
        lista = self.arquivos(incluir_removidos=True)
        for a in lista:
            if a["sha256"] == sha and a["nome"] == nome:
                if not a.get("ativo", True):
                    a["ativo"] = True
                    _json(self.pasta / "arquivos.json", lista)
                    self._evento("arquivo_reativado", id=a["id"])
                return a
        destino = self.pasta / "arquivos" / f"{sha[:12]}__{nome}"
        if not destino.exists():
            shutil.copy2(caminho, destino)
        reg = {"id": f"{sha[:12]}", "nome": nome, "sha256": sha, "bytes": destino.stat().st_size,
               "arquivo": destino.name, "base": base, "importado_em": _agora(), "ativo": True}
        if any(a["id"] == reg["id"] for a in lista):
            reg["id"] = f"{sha[:12]}-{len(lista)}"
        lista.append(reg)
        _json(self.pasta / "arquivos.json", lista)
        self._evento("arquivo_importado", id=reg["id"], nome=nome, sha256=sha)
        return reg

    def remover_arquivo(self, id_: str):
        """Desativa (não apaga) — execuções antigas continuam referenciando o arquivo."""
        lista = self.arquivos(incluir_removidos=True)
        for a in lista:
            if a["id"] == id_:
                a["ativo"] = False
        _json(self.pasta / "arquivos.json", lista)
        self._evento("arquivo_desativado", id=id_)

    def _selecionar(self, ids: list | None):
        lista = self.arquivos()
        if ids:
            lista = [a for a in self.arquivos(incluir_removidos=True) if a["id"] in ids]
            faltam = set(ids) - {a["id"] for a in lista}
            if faltam:
                raise ValueError(f"Arquivos inexistentes no projeto: {sorted(faltam)}")
        if not lista:
            raise ValueError("Nenhum arquivo importado no projeto.")
        return lista

    def carregar(self, cfg: Config, ids: list | None = None):
        lista = self._selecionar(ids)
        caminhos = [self.pasta / "arquivos" / a["arquivo"] for a in lista]
        tipos = {a["nome"]: a["base"] for a in lista if a.get("base")}
        return carregar_fontes(caminhos, cfg, nomes=[a["nome"] for a in lista], tipos=tipos)

    def diagnosticar(self, cfg: Config, ids: list | None = None) -> dict:
        bases, fontes = self.carregar(cfg, ids)
        return {"fontes": [f.como_dict() for f in fontes],
                "campos": diagnostico.relatorio_campos(bases, cfg).to_dict(orient="records"),
                "limitacoes": diagnostico.limitacoes(bases)}

    # ---------------- execuções ----------------
    def executar(self, cfg: Config, ids: list | None = None, rotulo: str = "", observacoes: str = "",
                 bibliometria_: bool = True, graficos_: bool = True, relatorios_: bool = True,
                 n_sensibilidade: int = 2000, revisao_duplicatas: bool = True) -> dict:
        bases, fontes = self.carregar(cfg, ids)
        res = executar_pipeline(bases, cfg)
        man = M.gerar(res, fontes, rotulo=rotulo, observacoes=observacoes)
        man["arquivos_projeto"] = [a["id"] for a in self._selecionar(ids)]
        pasta = self.pasta / "execucoes" / f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{man['id']}"
        pasta.mkdir(parents=True, exist_ok=False)
        diag = {"perdas_no_fluxo": diagnostico.perdas_no_fluxo(res),
                "exclusao_por_trecho": diagnostico.exclusao_por_trecho(res)}
        if len(res.corpus) and res.estratos()["Núcleo A"] and n_sensibilidade:
            diag["sensibilidade_pesos"] = robustez.sensibilidade_pesos(res, n=n_sensibilidade)
        (pasta / "diagnosticos").mkdir()
        diagnostico.relatorio_campos(bases, cfg).to_csv(pasta / "diagnosticos" / "campos.csv", index=False)
        _json(pasta / "diagnosticos" / "limitacoes.json", diagnostico.limitacoes(bases))
        _json(pasta / "diagnosticos" / "diagnosticos.json", diag)
        if revisao_duplicatas:
            from .consolidacao import correspondencias_duvidosas
            correspondencias_duvidosas(res.consolidado).to_csv(
                pasta / "diagnosticos" / "duplicatas_para_revisao.csv", index=False)
        _json(pasta / "contagens.json", res.contagens)
        res.corpus.to_csv(pasta / "corpus.csv", index=False)
        cols = [c for c in res.consolidado.columns if c not in ("abstract",)]
        res.consolidado[cols].to_csv(pasta / "consolidado.csv", index=False)
        biblio, imagens = {}, []
        if bibliometria_:
            biblio = bibliometria.analisar(self._estendido(bases, res), bruto=res.bruto)
            (pasta / "bibliometria").mkdir()
            for k, v in biblio.items():
                v.to_csv(pasta / "bibliometria" / f"{k}.csv", index=False)
        if graficos_:
            imagens = graficos.gerar_todos(res, biblio, pasta / "graficos")
        if relatorios_:
            relatorios.exportar(res, man, biblio, pasta / "relatorios", imagens=imagens, diagnosticos=diag)
        _json(pasta / "manifesto.json", man)
        self._evento("execucao", id=man["id"], modo=cfg.modo, versao_metodo=cfg.metodo_versao,
                     corpus=res.contagens["corpus"], estratos=res.estratos())
        return {"id": man["id"], "pasta": str(pasta), "manifesto": man, "resultado": res}

    @staticmethod
    def _estendido(bases: dict, res) -> pd.DataFrame:
        """Registros do corpus no esquema bibliométrico, ligados por arquivo/linha de origem."""
        ext = [normalizar_estendido(df, rot, tipo) for rot, (df, tipo) in bases.items() if len(df)]
        ext = pd.concat(ext, ignore_index=True) if ext else pd.DataFrame()
        corpus = res.corpus
        if ext.empty or corpus.empty:
            return corpus.copy()
        chave = ["arquivo_origem", "linha_origem"]
        manter = [c for c in ext.columns if c not in ("title", "year", "abstract", "citations", "doi", "source",
                                                       "source_db", "db_type")]
        ext = ext[manter].drop_duplicates(subset=chave)
        out = corpus.merge(ext, on=chave, how="left", suffixes=("", "_ext"), validate="many_to_one")
        return out[[c for c in out.columns if not c.endswith("_ext")]]

    def execucoes(self) -> list:
        out = []
        for p in sorted((self.pasta / "execucoes").iterdir()):
            f = p / "manifesto.json"
            if f.exists():
                m = json.loads(f.read_text(encoding="utf-8"))
                out.append({"id": m["id"], "pasta": p.name, "data_hora_utc": m["data_hora_utc"],
                            "rotulo": m.get("rotulo", ""), "modo": m["modo"], "versao_metodo": m["versao_metodo"],
                            "personalizada": m["configuracao_personalizada"], "contagens": m["contagens"],
                            "estratos": m["estratos"], "hash_corpus": m["hash_corpus"]})
        return out

    def pasta_execucao(self, id_: str) -> Path:
        for p in (self.pasta / "execucoes").iterdir():
            if p.name.endswith("_" + id_) or p.name == id_:
                return p
        raise FileNotFoundError(f"Execução não encontrada: {id_}")

    def manifesto(self, id_: str) -> dict:
        return json.loads((self.pasta_execucao(id_) / "manifesto.json").read_text(encoding="utf-8"))

    def comparar(self, a: str, b: str) -> dict:
        return M.comparar(self.manifesto(a), self.manifesto(b))

    def reproduzir(self, id_: str) -> dict:
        """Reexecuta com os MESMOS arquivos e parâmetros de uma execução e compara."""
        man = self.manifesto(id_)
        cfg = Config.de_dict(man["parametros"])
        nova = self.executar(cfg, ids=man.get("arquivos_projeto"), rotulo=f"reprodução de {id_}",
                             bibliometria_=False, graficos_=False, relatorios_=False, n_sensibilidade=0,
                             revisao_duplicatas=False)
        return M.comparar(man, nova["manifesto"])
