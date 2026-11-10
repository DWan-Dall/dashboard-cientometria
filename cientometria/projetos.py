"""Projetos de análise: arquivos importados, configurações, execuções e histórico.

Estrutura em disco (raiz = $CIENTOMETRIA_PROJETOS ou ./projetos):

    <raiz>/<slug>/
        projeto.json            nome, descrição, fontes bibliográficas, configuração padrão
        arquivos.json           registro de arquivos importados (id, nome, sha256, data)
        arquivos/<sha12>__<nome>  cópia imutável (somente leitura) do arquivo importado
        execucoes/<data>_<id>/  uma pasta por execução concluída (NUNCA sobrescrita)
            manifesto.json, contagens.json, corpus.csv, consolidado.csv,
            diagnosticos/, bibliometria/, graficos/, relatorios/
        execucoes/.em_andamento_<id>/   execução em curso (renomeada ao terminar)
        execucoes/.falhas/<id>/         execução que falhou (com erro.txt)
        historico.jsonl         eventos (append-only)
        .trava                  trava de arquivo (fcntl) para alterações concorrentes

Garantias de persistência:
- alterações de `arquivos.json`, `projeto.json` e do histórico ocorrem sob trava exclusiva;
- JSON é gravado em arquivo temporário único, com fsync, e trocado atomicamente;
- a importação copia para um temporário, confere o SHA-256 da cópia com o da origem e
  só então publica o arquivo (somente leitura);
- antes de executar, o SHA-256 de cada arquivo de entrada é reconferido;
- uma execução só aparece na lista depois de completa (renomeação atômica); falhas
  ficam em `.falhas/` com o erro, e o evento é registrado;
- o manifesto guarda o SHA-256 de cada arquivo de saída (`verificar_execucao`).

Os arquivos das bases podem ter licença restrita: a pasta de projetos está no .gitignore.
"""
from __future__ import annotations
import contextlib
import fcntl
import json
import os
import re
import shutil
import traceback
import unicodedata
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from . import bibliometria, diagnostico, graficos, manifesto as M, relatorios, robustez
from .config import Config
from .entrada import normalizar_estendido
from .ingestao import carregar_fontes, sha256_arquivo, validar_conteudo, FORMATOS, ArquivoInvalido
from .pipeline import executar as executar_pipeline

SLUG_RX = re.compile(r"^[a-z0-9][a-z0-9-]{0,80}$")
PASTA_EXEC_RX = re.compile(r"^\d{8}T\d{6}Z_[0-9a-f]{12}$")
ID_EXEC_RX = re.compile(r"^[0-9a-f]{12}$")
ID_ARQ_RX = re.compile(r"^[0-9a-f]{12}(-\d+)?$")
MAX_SENSIBILIDADE = 20000


class IntegridadeErro(RuntimeError):
    """Arquivo de entrada ou saída diferente do registrado (SHA-256)."""


def raiz_padrao() -> Path:
    return Path(os.environ.get("CIENTOMETRIA_PROJETOS", "projetos")).resolve()


def _agora():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _slug(nome: str) -> str:
    s = unicodedata.normalize("NFKD", nome)
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:60] or "projeto"


def _nome_seguro(nome: str) -> str:
    n = re.sub(r"[^A-Za-z0-9._-]", "_", os.path.basename(str(nome))).lstrip(".")
    return n[:150] or "arquivo"


def _json(p: Path, obj):
    """Gravação atômica: temporário único + fsync + rename."""
    tmp = p.with_name(f".{p.name}.{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False, indent=1, default=str))
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, p)


def _ler_json(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise IntegridadeErro(f"{p.name} corrompido ({e}); use Projeto.reconstruir_registro()") from e


def _dentro(caminho: Path, base: Path) -> bool:
    try:
        caminho.resolve().relative_to(base.resolve())
        return True
    except ValueError:
        return False


@contextlib.contextmanager
def _trava(pasta: Path):
    pasta.mkdir(parents=True, exist_ok=True)
    with open(pasta / ".trava", "a+") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def _sha_saidas(pasta: Path) -> dict:
    return {str(p.relative_to(pasta)): sha256_arquivo(p) for p in sorted(pasta.rglob("*"))
            if p.is_file() and p.name != "manifesto.json"}


class Projeto:
    def __init__(self, pasta: Path):
        self.pasta = Path(pasta)
        if not (self.pasta / "projeto.json").exists():
            raise FileNotFoundError(f"Projeto não encontrado: {self.pasta.name}")

    # ---------------- criação / listagem ----------------
    @classmethod
    def criar(cls, nome: str, descricao: str = "", fontes_bibliograficas: list | None = None,
              raiz: Path | None = None, configuracao: dict | None = None) -> "Projeto":
        nome = str(nome).strip()
        if not nome or len(nome) > 200:
            raise ValueError("Nome do projeto vazio ou longo demais (máx. 200).")
        raiz = Path(raiz or raiz_padrao())
        raiz.mkdir(parents=True, exist_ok=True)
        slug, i = _slug(nome), 1
        while True:  # mkdir é atômico: dois processos nunca ficam com a mesma pasta
            candidato = slug if i == 1 else f"{slug}-{i}"
            try:
                (raiz / candidato).mkdir()
                break
            except FileExistsError:
                i += 1
        pasta = raiz / candidato
        (pasta / "arquivos").mkdir()
        (pasta / "execucoes").mkdir()
        _json(pasta / "arquivos.json", [])
        _json(pasta / "projeto.json", {"slug": pasta.name, "nome": nome, "descricao": str(descricao)[:5000],
                                        "fontes_bibliograficas": [str(x)[:100] for x in (fontes_bibliograficas or [])][:50],
                                        "configuracao_padrao": configuracao or {"modo": "original"},
                                        "criado_em": _agora()})
        p = cls(pasta)
        p._evento("projeto_criado", nome=nome)
        return p

    @classmethod
    def abrir(cls, slug: str, raiz: Path | None = None) -> "Projeto":
        if not isinstance(slug, str) or not SLUG_RX.match(slug):
            raise ValueError("Identificador de projeto inválido.")
        raiz = Path(raiz or raiz_padrao())
        pasta = raiz / slug
        if not _dentro(pasta, raiz):
            raise ValueError("Identificador de projeto inválido.")
        return cls(pasta)

    @staticmethod
    def listar(raiz: Path | None = None) -> list:
        raiz = Path(raiz or raiz_padrao())
        if not raiz.exists():
            return []
        out = []
        for p in sorted(raiz.iterdir()):
            if p.is_dir() and SLUG_RX.match(p.name) and (p / "projeto.json").exists():
                try:
                    info = _ler_json(p / "projeto.json")
                    info["n_arquivos"] = len(_ler_json(p / "arquivos.json"))
                    info["n_execucoes"] = len([x for x in (p / "execucoes").iterdir()
                                               if x.is_dir() and PASTA_EXEC_RX.match(x.name)])
                except IntegridadeErro as e:
                    info = {"slug": p.name, "nome": p.name, "erro": str(e)}
                out.append(info)
        return out

    # ---------------- metadados ----------------
    @property
    def info(self) -> dict:
        return _ler_json(self.pasta / "projeto.json")

    def atualizar(self, **campos):
        permitidos = {"nome", "descricao", "fontes_bibliograficas", "configuracao_padrao"}
        with _trava(self.pasta):
            info = self.info
            info.update({k: v for k, v in campos.items() if k in permitidos})
            _json(self.pasta / "projeto.json", info)
        self._evento("projeto_atualizado", campos=sorted(set(campos) & permitidos))

    def _evento(self, tipo: str, **dados):
        linha = json.dumps({"quando": _agora(), "evento": tipo, **dados}, ensure_ascii=False, default=str) + "\n"
        with _trava(self.pasta), open(self.pasta / "historico.jsonl", "a", encoding="utf-8") as f:
            f.write(linha)
            f.flush()
            os.fsync(f.fileno())

    def historico(self) -> list:
        """Eventos; linhas ilegíveis (ex.: gravação interrompida) são sinalizadas, não descartadas em silêncio."""
        p = self.pasta / "historico.jsonl"
        out = []
        if p.exists():
            for n, linha in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                if not linha.strip():
                    continue
                try:
                    out.append(json.loads(linha))
                except json.JSONDecodeError:
                    out.append({"evento": "linha_ilegivel", "linha": n})
        return out

    # ---------------- arquivos ----------------
    def arquivos(self, incluir_removidos: bool = False) -> list:
        lista = _ler_json(self.pasta / "arquivos.json")
        return lista if incluir_removidos else [a for a in lista if a.get("ativo", True)]

    def importar(self, caminho, nome: str | None = None, base: str | None = None) -> dict:
        """Copia o arquivo para o projeto (imutável). `base` força o tipo de base (opcional).

        Se a variável CIENTOMETRIA_DIR_IMPORTACAO estiver definida (a API web a define),
        só arquivos dentro desse diretório podem ser importados."""
        caminho = Path(caminho)
        limite = os.environ.get("CIENTOMETRIA_DIR_IMPORTACAO")
        if limite and not _dentro(caminho, Path(limite)):
            raise ValueError("Arquivo fora do diretório de importação permitido.")
        if caminho.is_symlink():
            raise ArquivoInvalido("Links simbólicos não são aceitos.")
        nome = _nome_seguro(nome or caminho.name)
        if Path(nome).suffix.lower() not in FORMATOS:
            raise ArquivoInvalido(f"Formato não suportado: {nome}")
        if base is not None and base not in ("lens", "scopus", "ieee", "scielo", "wos", "openalex", "ris",
                                             "bibtex", "generico"):
            raise ValueError(f"Tipo de base inválido: {base}")
        validar_conteudo(caminho, nome)
        sha_origem = sha256_arquivo(caminho)
        pasta_arq = self.pasta / "arquivos"
        tmp = pasta_arq / f".importando_{uuid.uuid4().hex}"
        shutil.copyfile(caminho, tmp)
        try:
            sha = sha256_arquivo(tmp)
            if sha != sha_origem:
                raise IntegridadeErro(f"{nome}: o arquivo mudou durante a cópia")
            with _trava(self.pasta):
                lista = self.arquivos(incluir_removidos=True)
                for a in lista:
                    if a["sha256"] == sha and a["nome"] == nome:
                        if not a.get("ativo", True):
                            a["ativo"] = True
                            _json(self.pasta / "arquivos.json", lista)
                            self._evento_sem_trava("arquivo_reativado", id=a["id"])
                        return a
                destino = pasta_arq / f"{sha[:12]}__{nome}"
                if destino.exists():
                    if sha256_arquivo(destino) != sha:
                        raise IntegridadeErro(f"{destino.name} existe com conteúdo diferente")
                else:
                    os.chmod(tmp, 0o444)
                    os.replace(tmp, destino)
                reg = {"id": sha[:12], "nome": nome, "sha256": sha, "bytes": destino.stat().st_size,
                       "arquivo": destino.name, "base": base, "importado_em": _agora(), "ativo": True}
                if any(a["id"] == reg["id"] for a in lista):
                    reg["id"] = f"{sha[:12]}-{len(lista)}"
                lista.append(reg)
                _json(self.pasta / "arquivos.json", lista)
                self._evento_sem_trava("arquivo_importado", id=reg["id"], nome=nome, sha256=sha)
                return reg
        finally:
            if tmp.exists():
                os.chmod(tmp, 0o600)
                tmp.unlink()

    def _evento_sem_trava(self, tipo, **dados):
        """Igual a _evento, para uso quando a trava do projeto já está tomada (flock não é reentrante
        entre descritores diferentes)."""
        with open(self.pasta / "historico.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps({"quando": _agora(), "evento": tipo, **dados}, ensure_ascii=False, default=str) + "\n")
            f.flush()
            os.fsync(f.fileno())

    def remover_arquivo(self, id_: str):
        """Desativa (não apaga) — execuções antigas continuam referenciando o arquivo."""
        if not isinstance(id_, str) or not ID_ARQ_RX.match(id_):
            raise ValueError("Identificador de arquivo inválido.")
        with _trava(self.pasta):
            lista = self.arquivos(incluir_removidos=True)
            if not any(a["id"] == id_ for a in lista):
                raise ValueError(f"Arquivo inexistente no projeto: {id_}")
            for a in lista:
                if a["id"] == id_:
                    a["ativo"] = False
            _json(self.pasta / "arquivos.json", lista)
            self._evento_sem_trava("arquivo_desativado", id=id_)

    def _selecionar(self, ids: list | None):
        lista = self.arquivos()
        if ids:
            if not all(isinstance(i, str) and ID_ARQ_RX.match(i) for i in ids):
                raise ValueError("Identificador de arquivo inválido.")
            lista = [a for a in self.arquivos(incluir_removidos=True) if a["id"] in ids]
            faltam = set(ids) - {a["id"] for a in lista}
            if faltam:
                raise ValueError(f"Arquivos inexistentes no projeto: {sorted(faltam)}")
        if not lista:
            raise ValueError("Nenhum arquivo importado no projeto.")
        return lista

    def verificar_integridade(self, ids: list | None = None) -> list:
        """Reconfere o SHA-256 de cada arquivo importado. Devolve a lista de problemas."""
        problemas = []
        lista = self._selecionar(ids) if ids else self.arquivos(incluir_removidos=True)
        for a in lista:
            p = self.pasta / "arquivos" / a["arquivo"]
            if not p.exists():
                problemas.append({"id": a["id"], "nome": a["nome"], "problema": "arquivo ausente"})
            elif sha256_arquivo(p) != a["sha256"]:
                problemas.append({"id": a["id"], "nome": a["nome"], "problema": "SHA-256 diferente do registrado"})
        return problemas

    def carregar(self, cfg: Config, ids: list | None = None):
        lista = self._selecionar(ids)
        problemas = self.verificar_integridade([a["id"] for a in lista])
        if problemas:
            raise IntegridadeErro(f"Arquivos de entrada alterados ou ausentes: {problemas}")
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
        n_sensibilidade = max(0, min(int(n_sensibilidade), MAX_SENSIBILIDADE))
        bases, fontes = self.carregar(cfg, ids)
        res = executar_pipeline(bases, cfg)
        man = M.gerar(res, fontes, rotulo=str(rotulo)[:200], observacoes=str(observacoes)[:5000])
        man["arquivos_projeto"] = [a["id"] for a in self._selecionar(ids)]
        nome_final = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{man['id']}"
        execs = self.pasta / "execucoes"
        pasta = execs / f".em_andamento_{man['id']}"
        pasta.mkdir(parents=True, exist_ok=False)
        try:
            self._gravar_execucao(pasta, res, man, bases, cfg, bibliometria_, graficos_, relatorios_,
                                  n_sensibilidade, revisao_duplicatas)
            man["saidas_sha256"] = _sha_saidas(pasta)
            _json(pasta / "manifesto.json", man)
            final = execs / nome_final
            if final.exists():
                raise FileExistsError(f"Execução já existe: {nome_final}")
            os.rename(pasta, final)          # atômico no mesmo sistema de arquivos
        except BaseException as e:
            self._registrar_falha(pasta, man["id"], e)
            raise
        self._evento("execucao", id=man["id"], modo=cfg.modo, versao_metodo=cfg.metodo_versao,
                     corpus=res.contagens["corpus"], estratos=res.estratos())
        return {"id": man["id"], "pasta": str(final), "manifesto": man, "resultado": res}

    def _gravar_execucao(self, pasta, res, man, bases, cfg, bibliometria_, graficos_, relatorios_,
                         n_sensibilidade, revisao_duplicatas):
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

    def _registrar_falha(self, pasta: Path, id_: str, erro: BaseException):
        falhas = self.pasta / "execucoes" / ".falhas"
        falhas.mkdir(exist_ok=True)
        destino = falhas / f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{id_}"
        try:
            if pasta.exists():
                os.rename(pasta, destino)
            else:
                destino.mkdir()
            (destino / "erro.txt").write_text("".join(traceback.format_exception(erro)), encoding="utf-8")
        except OSError:
            pass
        try:
            self._evento("execucao_falhou", id=id_, erro=f"{type(erro).__name__}: {erro}"[:500])
        except OSError:
            pass

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

    def _pastas_execucao(self):
        return [p for p in sorted((self.pasta / "execucoes").iterdir()) if p.is_dir() and PASTA_EXEC_RX.match(p.name)]

    def execucoes(self) -> list:
        out = []
        for p in self._pastas_execucao():
            f = p / "manifesto.json"
            if f.exists():
                m = _ler_json(f)
                out.append({"id": m["id"], "pasta": p.name, "data_hora_utc": m["data_hora_utc"],
                            "rotulo": m.get("rotulo", ""), "modo": m["modo"], "versao_metodo": m["versao_metodo"],
                            "personalizada": m["configuracao_personalizada"], "contagens": m["contagens"],
                            "estratos": m["estratos"], "hash_corpus": m["hash_corpus"]})
        return out

    def pasta_execucao(self, id_: str) -> Path:
        if not isinstance(id_, str) or not (ID_EXEC_RX.match(id_) or PASTA_EXEC_RX.match(id_)):
            raise ValueError("Identificador de execução inválido.")
        for p in self._pastas_execucao():
            if p.name.endswith("_" + id_) or p.name == id_:
                return p
        raise FileNotFoundError(f"Execução não encontrada: {id_}")

    def manifesto(self, id_: str) -> dict:
        return _ler_json(self.pasta_execucao(id_) / "manifesto.json")

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

    # ---------------- verificação e recuperação ----------------
    def verificar_execucao(self, id_: str) -> dict:
        """Confere uma execução: manifesto legível, hashes das saídas, hash do corpus recalculado
        a partir de corpus.csv e hashes dos arquivos de entrada no projeto."""
        pasta = self.pasta_execucao(id_)
        out = {"id": id_, "pasta": pasta.name, "problemas": []}
        try:
            man = _ler_json(pasta / "manifesto.json")
        except (FileNotFoundError, IntegridadeErro) as e:
            out["problemas"].append(f"manifesto: {e}")
            out["ok"] = False
            return out
        registradas = man.get("saidas_sha256")
        if registradas is None:
            out["problemas"].append("manifesto sem saidas_sha256 (execução anterior a esta verificação)")
        else:
            atuais = _sha_saidas(pasta)
            for k in sorted(set(registradas) | set(atuais)):
                if registradas.get(k) != atuais.get(k):
                    out["problemas"].append(f"saída alterada, ausente ou acrescentada: {k}")
        c = pasta / "corpus.csv"
        if c.exists() and man.get("hash_corpus"):
            corpus = pd.read_csv(c, keep_default_na=False, dtype=str)
            for col in ("year", "citations", "C_norm", "R_norm", "T_score", "A_score", "score_final",
                        "score_final_100"):
                if col in corpus:
                    corpus[col] = pd.to_numeric(corpus[col], errors="coerce")
            if M.hash_tabela(corpus) != man["hash_corpus"]:
                out["problemas"].append("hash do corpus recalculado difere do manifesto")
        reg = {a["sha256"] for a in self.arquivos(incluir_removidos=True)}
        for f in man.get("fontes", []):
            if f["sha256"] not in reg:
                out["problemas"].append(f"entrada não registrada no projeto: {f['arquivo']}")
        for prob in self.verificar_integridade(man.get("arquivos_projeto")):
            out["problemas"].append(f"entrada {prob['nome']}: {prob['problema']}")
        out["ok"] = not out["problemas"]
        return out

    def recuperar(self) -> dict:
        """Após uma queda: move execuções interrompidas para .falhas, remove importações
        temporárias e relata registros/históricos ilegíveis. Não apaga resultados concluídos."""
        rel = {"execucoes_interrompidas": [], "temporarios_removidos": [], "problemas": []}
        with _trava(self.pasta):
            for p in (self.pasta / "execucoes").glob(".em_andamento_*"):
                id_ = p.name.removeprefix(".em_andamento_")
                falhas = self.pasta / "execucoes" / ".falhas"
                falhas.mkdir(exist_ok=True)
                destino = falhas / f"interrompida_{id_}"
                os.rename(p, destino)
                (destino / "erro.txt").write_text("Execução interrompida (encontrada por recuperar()).\n",
                                                  encoding="utf-8")
                rel["execucoes_interrompidas"].append(id_)
            for p in list((self.pasta / "arquivos").glob(".importando_*")) + list(self.pasta.glob(".*.tmp")):
                os.chmod(p, 0o600)
                p.unlink()
                rel["temporarios_removidos"].append(p.name)
            for nome in ("projeto.json", "arquivos.json"):
                try:
                    _ler_json(self.pasta / nome)
                except (IntegridadeErro, FileNotFoundError) as e:
                    rel["problemas"].append(str(e))
        ilegiveis = [e["linha"] for e in self.historico() if e.get("evento") == "linha_ilegivel"]
        if ilegiveis:
            rel["problemas"].append(f"historico.jsonl com linhas ilegíveis: {ilegiveis}")
        for e in rel["execucoes_interrompidas"]:
            self._evento("execucao_interrompida_recuperada", id=e)
        return rel

    def reconstruir_registro(self) -> list:
        """Recria arquivos.json a partir de arquivos/ (quando o registro foi corrompido).
        Preserva o arquivo corrompido como arquivos.json.corrompido-<data>."""
        with _trava(self.pasta):
            atual = self.pasta / "arquivos.json"
            if atual.exists():
                shutil.copy2(atual, self.pasta / f"arquivos.json.corrompido-{datetime.now().strftime('%Y%m%d%H%M%S')}")
            lista = []
            for p in sorted((self.pasta / "arquivos").iterdir()):
                if p.name.startswith(".") or "__" not in p.name:
                    continue
                sha = sha256_arquivo(p)
                prefixo, nome = p.name.split("__", 1)
                if not sha.startswith(prefixo):
                    raise IntegridadeErro(f"{p.name}: conteúdo não corresponde ao nome (SHA-256)")
                lista.append({"id": sha[:12], "nome": nome, "sha256": sha, "bytes": p.stat().st_size,
                              "arquivo": p.name, "base": None, "importado_em": None, "ativo": True,
                              "reconstruido": True})
            _json(atual, lista)
            self._evento_sem_trava("registro_reconstruido", n=len(lista))
        return lista
