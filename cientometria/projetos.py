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
        execucoes/.importando_<id>_<x>/ restauração de pacote em curso (renomeada ao terminar)
        execucoes/.importadas/<id>.json registro de procedência das execuções restauradas de pacote
        pacotes/<token>.zip     pacote ZIP recebido e validado, aguardando confirmação
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

from . import bibliometria, diagnostico, graficos, manifesto as M, pacote as PK, relatorios, robustez
from .config import Config
from .entrada import normalizar_estendido
from .ingestao import carregar_fontes, sha256_arquivo, validar_conteudo, FORMATOS, ArquivoInvalido
from .pipeline import executar as executar_pipeline

SLUG_RX = re.compile(r"^[a-z0-9][a-z0-9-]{0,80}$")
PASTA_EXEC_RX = re.compile(r"^\d{8}T\d{6}Z_[0-9a-f]{12}$")
ID_EXEC_RX = re.compile(r"^[0-9a-f]{12}$")
ID_ARQ_RX = re.compile(r"^[0-9a-f]{12}(-\d+)?$")
TOKEN_RX = re.compile(r"^[0-9a-f]{32}$")
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


def _leia_me(manp: dict) -> str:
    ex, rep = manp["execucao"], manp["reprodutibilidade"]
    linhas = [
        "PACOTE DE EXECUÇÃO — plataforma cientometria",
        "",
        f"Execução {ex['id']} ({ex['pasta']}), modo {ex['modo']}, método {ex['versao_metodo']}.",
        f"Projeto de origem: {manp['projeto_origem'].get('nome')} ({manp['projeto_origem'].get('slug')}).",
        f"Exportado em {manp['exportado_em']} pela aplicação {manp['versao_aplicacao_exportacao']}.",
        "",
        "Conteúdo:",
        "  manifesto.json   SHA-256 de cada arquivo, parâmetros, contagens, versões, omissões",
        f"  execucao/{ex['pasta']}/   resultados da execução, byte a byte (com o manifesto da execução)",
        "  entradas/        exportações bibliográficas originais (se incluídas)",
        "",
        "Reprodutibilidade: " + rep["declaracao"],
        "",
    ]
    omit = [o for o in manp["omitidos"] if o.get("sha256")]
    if omit:
        linhas.append("Arquivos omitidos (com o SHA-256 para conferência):")
        linhas += [f"  {o['arquivo']}  {o['sha256']}  — {o['motivo']}" for o in omit]
        linhas.append("")
    linhas += [
        "Verificar sem importar:  python -m cientometria verificar-pacote <este.zip>",
        "Restaurar num projeto:   python -m cientometria importar-pacote <projeto> <este.zip>",
        "Na interface: Execuções > Importar ZIP (mostra o inventário antes de confirmar).",
        "",
        manp["licenca"],
        "",
        "O SHA-256 detecta alteração acidental ou parcial; o pacote não é assinado digitalmente.",
    ]
    return "\n".join(linhas) + "\n"


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

    @staticmethod
    def _validar_campos(campos: dict) -> dict:
        """Tipos e tamanhos dos metadados editáveis (vindos da interface)."""
        from .config import Config
        out = {}
        for k, v in campos.items():
            if k == "nome":
                if not isinstance(v, str) or not v.strip() or len(v) > 200:
                    raise ValueError("Nome do projeto: texto de 1 a 200 caracteres.")
                out[k] = v.strip()
            elif k == "descricao":
                if not isinstance(v, str) or len(v) > 5000:
                    raise ValueError("Descrição: texto de até 5.000 caracteres.")
                out[k] = v
            elif k == "fontes_bibliograficas":
                if (not isinstance(v, list) or len(v) > 50
                        or not all(isinstance(x, str) and len(x) <= 100 for x in v)):
                    raise ValueError("Fontes bibliográficas: até 50 textos de até 100 caracteres.")
                out[k] = v
            elif k == "configuracao_padrao":
                if not isinstance(v, dict) or set(v) - {"modo"}:
                    raise ValueError("Configuração padrão: só a chave 'modo'.")
                Config.do_modo(v.get("modo", "original"))
                out[k] = v
            else:
                raise ValueError(f"Campo não editável: {k}")
        return out

    def atualizar(self, **campos):
        campos = self._validar_campos(campos)
        with _trava(self.pasta):
            info = self.info
            info.update(campos)
            _json(self.pasta / "projeto.json", info)
        self._evento("projeto_atualizado", campos=sorted(campos))

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
        return self._copiar_entrada(caminho, nome, base)

    def _copiar_entrada(self, caminho: Path, nome: str, base: str | None) -> dict:
        """Validação de conteúdo + cópia imutável + registro (comum à importação e à restauração)."""
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
                 n_sensibilidade: int = 2000, revisao_duplicatas: bool = True, origem: dict | None = None) -> dict:
        n_sensibilidade = max(0, min(int(n_sensibilidade), MAX_SENSIBILIDADE))
        bases, fontes = self.carregar(cfg, ids)
        res = executar_pipeline(bases, cfg)
        man = M.gerar(res, fontes, rotulo=str(rotulo)[:200], observacoes=str(observacoes)[:5000])
        man["arquivos_projeto"] = [a["id"] for a in self._selecionar(ids)]
        if origem:
            man["origem_execucao"] = origem
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
                     corpus=res.contagens["corpus"], estratos=res.estratos(),
                     **({"origem_execucao": origem.get("id")} if origem else {}))
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
                imp = self._registro_importacao(m["id"])
                out.append({"id": m["id"], "pasta": p.name, "data_hora_utc": m["data_hora_utc"],
                            "rotulo": m.get("rotulo", ""), "modo": m["modo"], "versao_metodo": m["versao_metodo"],
                            "personalizada": m["configuracao_personalizada"], "contagens": m["contagens"],
                            "estratos": m["estratos"], "hash_corpus": m["hash_corpus"],
                            "importada": imp is not None,
                            "projeto_origem": (imp or {}).get("projeto_origem", {}).get("slug"),
                            "origem_execucao": (m.get("origem_execucao") or {}).get("id")})
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
    @staticmethod
    def _conferir_saidas(pasta: Path, man: dict) -> list:
        """Saídas atuais × `saidas_sha256` do manifesto; e hash do corpus recalculado de corpus.csv."""
        problemas = []
        registradas = man.get("saidas_sha256")
        if registradas is None:
            problemas.append("manifesto sem saidas_sha256 (execução anterior a esta verificação)")
        else:
            atuais = _sha_saidas(pasta)
            for k in sorted(set(registradas) | set(atuais)):
                if registradas.get(k) != atuais.get(k):
                    problemas.append(f"saída alterada, ausente ou acrescentada: {k}")
        c = pasta / "corpus.csv"
        if c.exists() and man.get("hash_corpus"):
            corpus = pd.read_csv(c, keep_default_na=False, dtype=str)
            for col in ("year", "citations", "C_norm", "R_norm", "T_score", "A_score", "score_final",
                        "score_final_100"):
                if col in corpus:
                    corpus[col] = pd.to_numeric(corpus[col], errors="coerce")
            if M.hash_tabela(corpus) != man["hash_corpus"]:
                problemas.append("hash do corpus recalculado difere do manifesto")
        return problemas

    def _entradas_da_execucao(self, man: dict) -> list:
        """Para cada fonte do manifesto: o arquivo do projeto com o mesmo SHA-256 (ou None) e o problema."""
        lista = self.arquivos(incluir_removidos=True)
        out = []
        for f in man.get("fontes", []):
            cands = [a for a in lista if a["sha256"] == f["sha256"]]
            cands.sort(key=lambda a: (a["nome"] != f["arquivo"], not a.get("ativo", True)))
            rec = cands[0] if cands else None
            prob = None
            if rec is None:
                prob = "não está no projeto"
            else:
                arq = self.pasta / "arquivos" / rec["arquivo"]
                if not arq.exists():
                    prob = "arquivo ausente no projeto"
                elif sha256_arquivo(arq) != f["sha256"]:
                    prob = "SHA-256 no projeto difere do registrado"
            out.append({"fonte": f, "registro": rec, "problema": prob})
        return out

    def _registro_importacao(self, id_: str) -> dict | None:
        p = self.pasta / "execucoes" / ".importadas" / f"{id_}.json"
        return _ler_json(p) if ID_EXEC_RX.match(id_) and p.exists() else None

    def verificar_execucao(self, id_: str) -> dict:
        """Confere uma execução: manifesto legível, hashes das saídas, hash do corpus recalculado
        a partir de corpus.csv e hashes dos arquivos de entrada no projeto.

        Execução restaurada de pacote sem as exportações de origem: a ausência das entradas é
        um aviso (reexecução impossível), não uma falha de integridade dos resultados."""
        pasta = self.pasta_execucao(id_)
        out = {"id": id_, "pasta": pasta.name, "problemas": [], "avisos": []}
        try:
            man = _ler_json(pasta / "manifesto.json")
        except (FileNotFoundError, IntegridadeErro) as e:
            out["problemas"].append(f"manifesto: {e}")
            out["ok"] = False
            out["reexecucao_possivel"] = False
            return out
        out["problemas"] += self._conferir_saidas(pasta, man)
        imp = self._registro_importacao(man["id"])
        out["importada"] = imp is not None
        entradas = self._entradas_da_execucao(man)
        for e in entradas:
            if e["problema"] is None:
                continue
            nome = e["fonte"]["arquivo"]
            if imp is not None and e["problema"] == "não está no projeto":
                out["avisos"].append(f"entrada {nome} não acompanha a execução importada: reexecução impossível "
                                     f"(SHA-256 {e['fonte']['sha256'][:16]}…)")
            elif e["problema"] == "não está no projeto":
                out["problemas"].append(f"entrada não registrada no projeto: {nome}")
            else:
                out["problemas"].append(f"entrada {nome}: {e['problema']}")
        out["reexecucao_possivel"] = bool(entradas) and all(e["problema"] is None for e in entradas)
        out["ok"] = not out["problemas"]
        return out

    # ---------------- exportação / importação de execuções (pacote ZIP) ----------------
    def _plano_exportacao(self, id_: str, incluir_entradas: bool) -> dict:
        pasta = self.pasta_execucao(id_)
        man = _ler_json(pasta / "manifesto.json")
        problemas_saida = self._conferir_saidas(pasta, man)
        bloqueantes = [p for p in problemas_saida if not p.startswith("manifesto sem saidas_sha256")]
        arquivos = [(f"execucao/{pasta.name}/{p.relative_to(pasta).as_posix()}", p)
                    for p in sorted(pasta.rglob("*")) if p.is_file() and not p.is_symlink()]
        fontes, omitidos = [], []
        for e in self._entradas_da_execucao(man):
            f = {k: e["fonte"].get(k) for k in ("arquivo", "sha256", "bytes", "formato", "tipo", "rotulo",
                                                "registros", "leitura", "deteccao", "canonico")}
            f["base_forcada"] = e["fonte"]["tipo"] if e["fonte"].get("deteccao") == "definido pelo usuário" else None
            if not incluir_entradas:
                motivo = "omitida por escolha na exportação (licença das bases bibliográficas)"
            elif e["problema"]:
                motivo = e["problema"]
            else:
                motivo = None
            if motivo is None:
                f["incluido"] = True
                f["caminho_no_pacote"] = f"entradas/{f['sha256'][:12]}__{_nome_seguro(f['arquivo'])}"
                arquivos.append((f["caminho_no_pacote"], self.pasta / "arquivos" / e["registro"]["arquivo"]))
            else:
                f["incluido"] = False
                f["motivo_omissao"] = motivo
                omitidos.append({"arquivo": f["arquivo"], "sha256": f["sha256"], "bytes": f["bytes"],
                                 "motivo": motivo})
            fontes.append(f)
        omitidos.append({"arquivo": f"execucao/{pasta.name}/consolidado.csv (coluna abstract)", "sha256": None,
                         "bytes": None, "motivo": "a execução nunca grava os resumos no consolidado "
                                                  "(texto das bases); não é omissão do pacote"})
        info = self.info
        projeto = {k: info.get(k) for k in ("slug", "nome", "descricao", "fontes_bibliograficas")}
        verif = {"saidas_conferidas": man.get("saidas_sha256") is not None, "problemas": problemas_saida}
        return {"pasta": pasta, "man": man, "arquivos": arquivos, "omitidos": omitidos, "projeto": projeto, "verificacao": verif, "bloqueantes": bloqueantes,
                "_fontes": fontes}

    def inventario_execucao(self, id_: str, incluir_entradas: bool = True) -> dict:
        """Prévia do que a exportação incluiria (nada é gravado)."""
        pl = self._plano_exportacao(id_, incluir_entradas)
        return {"id": pl["man"]["id"], "pasta": pl["pasta"].name,
                "arquivos": [{"caminho": n, "bytes": p.stat().st_size} for n, p in pl["arquivos"]],
                "bytes_total": sum(p.stat().st_size for _, p in pl["arquivos"]),
                "fontes": pl["_fontes"], "omitidos": pl["omitidos"], "verificacao": pl["verificacao"],
                "exportavel": not pl["bloqueantes"], "problemas": pl["bloqueantes"],
                "reexecucao_possivel_so_com_o_pacote": bool(pl["_fontes"]) and all(
                    f["incluido"] for f in pl["_fontes"])}

    def exportar_execucao(self, id_: str, destino, incluir_entradas: bool = True) -> dict:
        """Grava `destino/execucao_<id>_<slug>.zip`. Recusa exportar resultados alterados.

        Se CIENTOMETRIA_DIR_EXPORTACAO estiver definida (a API web a define), o destino deve
        estar dentro dela."""
        destino = Path(destino)
        limite = os.environ.get("CIENTOMETRIA_DIR_EXPORTACAO")
        if limite and not _dentro(destino, Path(limite)):
            raise ValueError("Destino fora do diretório de exportação permitido.")
        if not destino.is_dir() or destino.is_symlink():
            raise ValueError("Destino da exportação não é um diretório.")
        pl = self._plano_exportacao(id_, incluir_entradas)
        if pl["bloqueantes"]:
            raise IntegridadeErro("execução com resultados diferentes do manifesto; exportação recusada: "
                                  + "; ".join(pl["bloqueantes"][:10]))
        man = pl["man"]
        manp = M.pacote(man, pl["pasta"].name, pl["_fontes"], pl["omitidos"], pl["projeto"], pl["verificacao"])
        sufixo = "" if incluir_entradas else "_sem-entradas"
        nome = f"execucao_{man['id']}_{self.pasta.name}{sufixo}.zip"
        r = PK.montar(destino / nome, manp, pl["arquivos"], _leia_me(manp))
        r["reprodutibilidade"] = manp["reprodutibilidade"]
        r["omitidos"] = manp["omitidos"]
        self._evento("execucao_exportada", id=man["id"], pacote_sha256=r["sha256"], bytes=r["bytes"],
                     entradas_incluidas=manp["reprodutibilidade"]["entradas_incluidas"],
                     entradas_total=manp["reprodutibilidade"]["entradas_total"])
        return r

    def _pacote_recebido(self, token: str) -> Path:
        if not isinstance(token, str) or not TOKEN_RX.match(token):
            raise ValueError("Identificador de pacote inválido.")
        p = self.pasta / "pacotes" / f"{token}.zip"
        if not p.is_file() or p.is_symlink():
            raise FileNotFoundError("Pacote não encontrado (descartado ou já restaurado).")
        return p

    def _situacao_no_projeto(self, inv: dict) -> dict:
        """O que o pacote encontraria neste projeto: conflito de ID e entradas já presentes."""
        id_ = inv["execucao"]["id"]
        existente = [p for p in self._pastas_execucao() if p.name.endswith("_" + id_)]
        sit = {"execucao_existente": existente[0].name if existente else None}
        if existente:
            atuais = _sha_saidas(existente[0])
            pref = f"execucao/{inv['execucao']['pasta']}/"
            do_pacote = {r["caminho"][len(pref):]: r.get("sha256") for r in inv["arquivos"]
                         if r["caminho"].startswith(pref) and not r["caminho"].endswith("/manifesto.json")}
            sit["identica"] = do_pacote == atuais
        shas = {a["sha256"] for a in self.arquivos(incluir_removidos=True)}
        disp = [f for f in inv["fontes"] if f.get("incluido") or f["sha256"] in shas]
        sit["entradas_ja_no_projeto"] = sum(1 for f in inv["fontes"] if f["sha256"] in shas)
        sit["reexecucao_possivel_apos_restaurar"] = bool(inv["fontes"]) and len(disp) == len(inv["fontes"])
        return sit

    def receber_pacote(self, caminho) -> dict:
        """Valida um ZIP e o guarda em `pacotes/<token>.zip` para confirmação. Não extrai nada.

        Com CIENTOMETRIA_DIR_IMPORTACAO definida (API web), só aceita arquivos dentro dela."""
        caminho = Path(caminho)
        limite = os.environ.get("CIENTOMETRIA_DIR_IMPORTACAO")
        if limite and not _dentro(caminho, Path(limite)):
            raise ValueError("Arquivo fora do diretório de importação permitido.")
        if caminho.is_symlink():
            raise PK.PacoteInvalido("Links simbólicos não são aceitos.")
        inv = PK.inspecionar(caminho)
        sha = sha256_arquivo(caminho)
        token = uuid.uuid4().hex
        pasta = self.pasta / "pacotes"
        pasta.mkdir(exist_ok=True)
        tmp = pasta / f".recebendo_{token}"
        shutil.copyfile(caminho, tmp)
        try:
            if sha256_arquivo(tmp) != sha:
                raise IntegridadeErro("o pacote mudou durante a cópia")
            os.chmod(tmp, 0o444)
            os.replace(tmp, pasta / f"{token}.zip")
        finally:
            if tmp.exists():
                os.chmod(tmp, 0o600)
                tmp.unlink()
        inv.update({"token": token, "pacote_sha256": sha, "situacao_no_projeto": self._situacao_no_projeto(inv)})
        self._evento("pacote_recebido", token=token, pacote_sha256=sha, execucao=inv["execucao"]["id"],
                     ok=inv["ok"], problemas=len(inv["problemas"]))
        return inv

    def inspecionar_pacote(self, token: str) -> dict:
        p = self._pacote_recebido(token)
        inv = PK.inspecionar(p)
        inv.update({"token": token, "pacote_sha256": sha256_arquivo(p), "situacao_no_projeto":
                    self._situacao_no_projeto(inv)})
        return inv

    def descartar_pacote(self, token: str) -> dict:
        p = self._pacote_recebido(token)
        os.chmod(p, 0o600)
        p.unlink()
        self._evento("pacote_descartado", token=token)
        return {"descartado": token}

    def restaurar_pacote(self, token: str, importar_entradas: bool = True) -> dict:
        """RESTAURAR: recupera os resultados e metadados de uma execução exportada, sem recalcular nada.

        Preserva o ID, o nome da pasta e o manifesto originais. Confere o SHA-256 de cada arquivo
        na extração, as saídas contra o manifesto da execução e o hash do corpus. A execução só
        aparece na lista depois de completa (renomeação atômica sob a trava do projeto).
        A procedência fica em execucoes/.importadas/<id>.json e no evento `execucao_restaurada`."""
        zipp = self._pacote_recebido(token)
        sha_pacote = sha256_arquivo(zipp)
        inv = PK.inspecionar(zipp)
        if not inv["ok"]:
            raise IntegridadeErro("pacote com problemas de integridade: " + "; ".join(inv["problemas"][:10]))
        with PK._abrir(zipp) as z:
            manp = PK.ler_manifesto(z, PK._conferir_entradas(z))
        ex = manp["execucao"]
        id_, nome_pasta = ex["id"], ex["pasta"]
        sit = self._situacao_no_projeto(inv)
        if sit["execucao_existente"] and not sit.get("identica"):
            raise IntegridadeErro(f"já existe neste projeto uma execução {id_} com conteúdo diferente; "
                                  "restauração recusada (o ID original não é reaproveitado)")
        execs = self.pasta / "execucoes"
        staging = execs / f".importando_{id_}_{uuid.uuid4().hex[:8]}"
        tmp_ent = self.pasta / f".pacote_{uuid.uuid4().hex[:8]}"
        entradas_importadas = []
        try:
            staging.mkdir()
            pref = f"execucao/{nome_pasta}/"
            PK.extrair(zipp, staging, pref, manp["arquivos"], pref)
            man = _ler_json(staging / "manifesto.json")
            if man.get("id") != id_:
                raise IntegridadeErro("o manifesto da execução não corresponde ao manifesto do pacote")
            problemas = [p for p in self._conferir_saidas(staging, man)
                         if not p.startswith("manifesto sem saidas_sha256")]
            if problemas:
                raise IntegridadeErro("resultados não conferem com o manifesto da execução: "
                                      + "; ".join(problemas[:10]))
            if importar_entradas and any(f.get("incluido") for f in manp["fontes"]):
                tmp_ent.mkdir()
                PK.extrair(zipp, tmp_ent, "entradas/", manp["arquivos"], "entradas/")
                for f in manp["fontes"]:
                    if f.get("incluido"):
                        arq = tmp_ent / f["caminho_no_pacote"].removeprefix("entradas/")
                        if sha256_arquivo(arq) != f["sha256"]:
                            raise IntegridadeErro(f"entrada {f['arquivo']}: SHA-256 difere da fonte da execução")
                        reg = self._copiar_entrada(arq, _nome_seguro(f["arquivo"]), f.get("base_forcada"))
                        entradas_importadas.append(reg["id"])
            with _trava(self.pasta):
                existente = [p for p in self._pastas_execucao() if p.name.endswith("_" + id_)]
                if existente:
                    if _sha_saidas(existente[0]) != _sha_saidas(staging):
                        raise IntegridadeErro(f"já existe neste projeto uma execução {id_} com conteúdo diferente")
                    estado, final = "ja_existia", existente[0]
                else:
                    final = execs / nome_pasta
                    os.rename(staging, final)
                    estado = "restaurada"
                    reg_imp = {"id": id_, "pasta": nome_pasta, "restaurada_em": _agora(),
                               "pacote_sha256": sha_pacote, "formato": manp["formato"],
                               "versao_formato": manp["versao_formato"], "exportado_em": manp.get("exportado_em"),
                               "versao_aplicacao_exportacao": manp.get("versao_aplicacao_exportacao"),
                               "projeto_origem": manp.get("projeto_origem", {}),
                               "fontes": [{k: f.get(k) for k in ("arquivo", "sha256", "incluido", "motivo_omissao")}
                                          for f in manp["fontes"]],
                               "reprodutibilidade": manp.get("reprodutibilidade", {}),
                               "entradas_importadas": entradas_importadas}
                    (execs / ".importadas").mkdir(exist_ok=True)
                    _json(execs / ".importadas" / f"{id_}.json", reg_imp)
                self._evento_sem_trava("execucao_restaurada" if estado == "restaurada" else "pacote_ja_restaurado",
                                       id=id_, pacote_sha256=sha_pacote,
                                       projeto_origem=manp.get("projeto_origem", {}).get("slug"),
                                       entradas_importadas=entradas_importadas, recalculo=False)
        finally:
            for d in (staging, tmp_ent):
                if d.exists():
                    shutil.rmtree(d)
        os.chmod(zipp, 0o600)
        zipp.unlink()
        return {"id": id_, "pasta": final.name, "estado": estado, "entradas_importadas": entradas_importadas,
                "verificacao": self.verificar_execucao(id_)}

    def reexecutar(self, id_: str) -> dict:
        """REEXECUTAR: nova execução (novo ID) com os arquivos e parâmetros registrados numa execução,
        referenciando-a em `origem_execucao`. Exige as exportações de origem no projeto (por SHA-256)
        e a mesma versão do método; nunca substitui a execução de origem."""
        from .versao import METODO_VERSOES
        man = self.manifesto(id_)
        versao = man.get("versao_metodo")
        if versao not in set(METODO_VERSOES.values()):
            raise ValueError(f"versão do método '{versao}' não existe nesta aplicação; reexecução recusada "
                             "(restaurar continua possível)")
        cfg = Config.de_dict(man["parametros"])
        if cfg.metodo_versao != versao:
            raise ValueError("parâmetros registrados não reconstroem a mesma versão do método; reexecução recusada")
        entradas = self._entradas_da_execucao(man)
        faltam = [f"{e['fonte']['arquivo']} ({e['problema']}; SHA-256 {e['fonte']['sha256'][:16]}…)"
                  for e in entradas if e["problema"]]
        if not entradas or faltam:
            raise ValueError("reexecução impossível sem as exportações de origem: " + "; ".join(faltam)
                             + ". Importe os arquivos originais (mesmo SHA-256) ou um pacote que os contenha.")
        avisos = [f"{e['fonte']['arquivo']} está no projeto como {e['registro']['nome']} (mesmo SHA-256); "
                  "o nome influencia a ordem de processamento" for e in entradas
                  if e["registro"]["nome"] != e["fonte"]["arquivo"]]
        imp = self._registro_importacao(man["id"])
        origem = {"id": man["id"], "versao_metodo": versao, "hash_corpus": man.get("hash_corpus"),
                  "importada": imp is not None, "projeto_origem": (imp or {}).get("projeto_origem", {}).get("slug")}
        nova = self.executar(cfg, ids=[e["registro"]["id"] for e in entradas], rotulo=f"reexecução de {id_}",
                             origem=origem)
        return {"id": nova["id"], "origem": man["id"], "avisos": avisos,
                "comparacao": M.comparar(man, nova["manifesto"])}

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
            # restaurações de pacote interrompidas: nunca chegaram à lista (renomeação não ocorreu)
            for p in list((self.pasta / "execucoes").glob(".importando_*")) + list(self.pasta.glob(".pacote_*")) \
                    + list((self.pasta / "pacotes").glob(".recebendo_*")):
                if p.is_dir() and not p.is_symlink():
                    shutil.rmtree(p)
                else:
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
