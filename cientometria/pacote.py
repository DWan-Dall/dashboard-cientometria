"""Exportação e importação de uma execução como arquivo .zip verificável.

Motivação (docs/AUDITORIA_RESULTADOS_BIBLIOMETRICOS.md, §2, §9 e recomendação 12): arquivos de
`relatorios/` entregues sem `manifesto.json` não podem ser verificados um a um. O .zip leva a
pasta INTEIRA da execução (o manifesto com o SHA-256 de cada saída incluído), um `LEIA-ME.txt`
com instruções e um `SHA256SUMS.txt` para `sha256sum -c`.

Estrutura do .zip:

    LEIA-ME.txt
    SHA256SUMS.txt                 derivado de manifesto.json["saidas_sha256"] (+ o próprio manifesto)
    <data>_<id>/manifesto.json     a pasta da execução, byte a byte
    <data>_<id>/...
    entradas/<sha12>__<nome>       SÓ se pedido: exportações de entrada (dados licenciados)

Importação (superfície de upload; ver docs/SEGURANCA.md, V11):
- o .zip é lido sem extrair nada antes de validar a lista de membros: nomes só com
  [A-Za-z0-9._-] separados por '/', sem caminho absoluto, '..', '\\', nomes duplicados
  (inclusive por caixa), links simbólicos, arquivos especiais ou membros cifrados;
- estrutura fixa (acima): uma única pasta de execução com nome válido e manifesto;
- limites de tamanho do .zip, de número de membros e de bytes descompactados (declarados e
  contados durante a extração — o cabeçalho não é confiável);
- extração para uma pasta oculta e temporária do projeto (não listada), conferência de TODAS as
  saídas contra `saidas_sha256` e do hash do corpus (`Projeto.conferir_saidas`) e das entradas
  (se houver) contra `manifesto.json["fontes"]`; só então a pasta é publicada por renomeação;
- nunca sobrescreve: se o projeto já tem execução com o mesmo ID, a importação é recusada;
- a execução importada fica somente leitura (0444) e registrada em `execucoes/.importadas/`.

Os hashes dentro do .zip provam a consistência INTERNA do pacote. Quem altera um arquivo e
recalcula todos os hashes (inclusive os do manifesto) produz um pacote consistente: a
autenticidade depende de comparar o SHA-256 do `manifesto.json` (ou o `hash_corpus`) com um valor
registrado por outro canal (artigo, ata de auditoria, repositório de dados).
"""
from __future__ import annotations
import json
import os
import re
import shutil
import stat
import uuid
import zipfile
from pathlib import Path

from .ingestao import sha256_arquivo
from .projetos import (ID_EXEC_RX, PASTA_EXEC_RX, IntegridadeErro, Projeto, _agora, _dentro, _json,
                       _ler_json, _trava)
from .versao import APP_VERSAO

LEIA_ME = "LEIA-ME.txt"
SOMAS = "SHA256SUMS.txt"
ENTRADAS = "entradas"
SUFIXO_ENTRADAS = "_com_entradas"
NOME_ZIP_RX = re.compile(r"^\d{8}T\d{6}Z_[0-9a-f]{12}(_com_entradas)?\.zip$")
_SEGMENTO_RX = re.compile(r"^[A-Za-z0-9_-][A-Za-z0-9._-]{0,199}$")
_SHA_RX = re.compile(r"^[0-9a-f]{64}$")
_BLOCO = 1024 * 1024


class PacoteInvalido(ValueError):
    """O .zip não é uma exportação de execução válida e segura."""


def _limite_mb(var: str, padrao: int) -> int:
    try:
        v = int(os.environ.get(var, padrao))
    except ValueError:
        v = padrao
    return max(1, v) * 1024 * 1024


def limites() -> dict:
    """Limites da importação (bytes / quantidade), configuráveis por variável de ambiente."""
    return {"zip_bytes": _limite_mb("CIENTOMETRIA_MAX_MB_ZIP", 200),
            "descompactado_bytes": _limite_mb("CIENTOMETRIA_MAX_MB_DESCOMPACTADO", 1024),
            "membros": max(1, int(os.environ.get("CIENTOMETRIA_MAX_MEMBROS_ZIP", 5000)))}


# ------------------------------------------------------------------ exportação
def _arquivos_da_pasta(pasta: Path) -> list:
    out = []
    for p in sorted(pasta.rglob("*")):
        if p.is_symlink():
            raise IntegridadeErro(f"link simbólico na pasta da execução: {p.relative_to(pasta)}")
        if p.is_file():
            out.append(p)
    return out


def _entradas_para_exportar(projeto: Projeto, pasta: Path, man: dict) -> list:
    """(nome no zip, caminho) das exportações de entrada da execução, conferidas pelo SHA-256."""
    esperadas = {f["sha256"] for f in man.get("fontes", [])}
    imp = projeto.importacao(pasta.name)
    if imp is not None:
        base = projeto.pasta / "execucoes" / ".importadas" / pasta.name / ENTRADAS
        itens = [(n, base / n, s) for n, s in sorted((imp.get("entradas") or {}).items())]
    else:
        ids = set(man.get("arquivos_projeto") or [])
        itens = [(a["arquivo"], projeto.pasta / "arquivos" / a["arquivo"], a["sha256"])
                 for a in projeto.arquivos(incluir_removidos=True) if a["id"] in ids]
    out = []
    for nome, caminho, sha in itens:
        if not caminho.is_file() or caminho.is_symlink() or sha256_arquivo(caminho) != sha:
            raise IntegridadeErro(f"exportação de entrada ausente ou alterada: {nome}")
        out.append((nome, caminho, sha))
    if {s for _, _, s in out} != esperadas:
        raise IntegridadeErro("as exportações de entrada desta execução não estão disponíveis no projeto "
                              "(exporte sem as entradas)")
    return [(n, c) for n, c, _ in out]


def _leia_me(man: dict, pasta: str, sha_manifesto: str, entradas: list, exportado_em: str) -> str:
    fontes = "\n".join(f"    {f.get('sha256', '')}  {f.get('arquivo', '')}" for f in man.get("fontes", []))
    if entradas:
        sit_ent = (f"SIM ({len(entradas)} arquivo(s) em {ENTRADAS}/).\n"
                   "  ATENÇÃO: exportações de bases bibliográficas costumam ter licença restrita.\n"
                   "  Não publique nem repasse este .zip sem verificar a licença de cada base.")
    else:
        sit_ent = ("NÃO (padrão). As exportações das bases têm licença restrita e não foram incluídas.\n"
                   "  As saídas são verificáveis; para REPRODUZIR a execução é preciso obter as exportações\n"
                   "  originais e conferir o SHA-256 de cada uma com a lista abaixo.")
    return f"""EXECUÇÃO EXPORTADA — Plataforma de Cientometria
================================================

ID da execução ............ {man.get('id')}
Pasta ..................... {pasta}
Data/hora da execução ..... {man.get('data_hora_utc')} (UTC)
Rótulo .................... {man.get('rotulo') or '—'}
Modo / versão do método ... {man.get('modo')} / {man.get('versao_metodo')}
Configuração personalizada  {'sim' if man.get('configuracao_personalizada') else 'não'}
Versão da aplicação ....... {man.get('versao_aplicacao')} (que gerou a execução)
                            {APP_VERSAO} (que gerou este .zip)
Exportado em .............. {exportado_em} (UTC)
Hash do corpus ............ {man.get('hash_corpus')}
SHA-256 do manifesto.json . {sha_manifesto}
Exportações de entrada .... {sit_ent}

Exportações de entrada usadas (manifesto.json → fontes):
{fontes or '    —'}

CONTEÚDO
  {pasta}/manifesto.json   parâmetros, versões, contagens, estratos e o SHA-256 de cada saída
                           (campo "saidas_sha256")
  {pasta}/corpus.csv, consolidado.csv, contagens.json, diagnosticos/, bibliometria/,
  graficos/, relatorios/   saídas da execução, exatamente como gravadas
  {SOMAS}           SHA-256 de cada arquivo, no formato do sha256sum (gerado a partir do manifesto)

COMO VERIFICAR
  1. Integridade de cada arquivo (Linux / macOS / Git Bash), na pasta onde o .zip foi extraído:
         sha256sum -c {SOMAS}          (ou: shasum -a 256 -c {SOMAS})
     Todas as linhas devem terminar em "OK". A referência é manifesto.json → saidas_sha256;
     {SOMAS} é só uma cópia conveniente.
  2. Autenticidade: os hashes acima provam que os arquivos são coerentes ENTRE SI. Para provar que
     são os resultados publicados, compare o SHA-256 do manifesto.json (acima) ou o hash do corpus
     com o valor registrado por outro canal (artigo, ata de auditoria, repositório de dados).
  3. Na plataforma: seção "Execuções e comparação" → "Importar execução (.zip)", ou
         python -m cientometria importar-execucao <projeto> <arquivo.zip>
     A importação reconfere o SHA-256 de cada saída e recalcula o hash do corpus a partir de
     corpus.csv; um arquivo alterado faz a importação ser recusada.
  4. Reprodução: importe as exportações de entrada num projeto e execute com os parâmetros de
     manifesto.json → parametros (ou use "reproduzir" se as entradas vieram neste .zip).
"""


def exportar(projeto: Projeto, id_: str, destino: Path, incluir_entradas: bool = False) -> dict:
    """Grava `<pasta>.zip` (ou `<pasta>_com_entradas.zip`) em `destino`. Recusa exportar uma
    execução cujas saídas não conferem com o manifesto."""
    pasta = projeto.pasta_execucao(id_)
    man = _ler_json(pasta / "manifesto.json")
    problemas = projeto.conferir_saidas(pasta, man)
    if problemas:
        raise IntegridadeErro(f"execução com saídas que não conferem com o manifesto: {problemas[:5]}")
    entradas = _entradas_para_exportar(projeto, pasta, man) if incluir_entradas else []
    arquivos = _arquivos_da_pasta(pasta)
    sha_man = sha256_arquivo(pasta / "manifesto.json")
    agora = _agora()
    somas = [f"{sha_man}  {pasta.name}/manifesto.json"]
    somas += [f"{s}  {pasta.name}/{k}" for k, s in sorted(man["saidas_sha256"].items())]
    somas += [f"{sha256_arquivo(c)}  {ENTRADAS}/{n}" for n, c in entradas]
    destino = Path(destino)
    destino.mkdir(parents=True, exist_ok=True)
    nome = f"{pasta.name}{SUFIXO_ENTRADAS if incluir_entradas else ''}.zip"
    tmp = destino / f".{nome}.{uuid.uuid4().hex[:8]}.tmp"
    # data dos membros = data da execução (nome da pasta), não a da exportação
    data = (int(pasta.name[0:4]), int(pasta.name[4:6]), int(pasta.name[6:8]),
            int(pasta.name[9:11]), int(pasta.name[11:13]), int(pasta.name[13:15]))

    def _info(nome_zip: str) -> zipfile.ZipInfo:
        zi = zipfile.ZipInfo(nome_zip, date_time=data)
        zi.compress_type = zipfile.ZIP_DEFLATED
        zi.external_attr = (stat.S_IFREG | 0o444) << 16
        return zi

    try:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr(_info(LEIA_ME), _leia_me(man, pasta.name, sha_man, entradas, agora))
            z.writestr(_info(SOMAS), "\n".join(somas) + "\n")
            for p in arquivos:
                with open(p, "rb") as src, z.open(_info(f"{pasta.name}/{p.relative_to(pasta).as_posix()}"),
                                                  "w") as dst:
                    shutil.copyfileobj(src, dst, _BLOCO)
            for n, c in entradas:
                with open(c, "rb") as src, z.open(_info(f"{ENTRADAS}/{n}"), "w") as dst:
                    shutil.copyfileobj(src, dst, _BLOCO)
        os.replace(tmp, destino / nome)
    finally:
        if tmp.exists():
            tmp.unlink()
    final = destino / nome
    projeto._evento("execucao_exportada", id=man["id"], arquivo=nome, entradas_incluidas=bool(entradas),
                    sha256_zip=sha256_arquivo(final))
    return {"id": man["id"], "pasta": pasta.name, "arquivo": nome, "bytes": final.stat().st_size,
            "sha256": sha256_arquivo(final), "sha256_manifesto": sha_man,
            "entradas_incluidas": len(entradas)}


# ------------------------------------------------------------------ importação
def _validar_membros(z: zipfile.ZipFile, lim: dict) -> tuple:
    """Valida a lista de membros SEM extrair nada. Devolve (pasta_execucao, membros_arquivo)."""
    infos = z.infolist()
    if not infos:
        raise PacoteInvalido("o .zip está vazio")
    if len(infos) > lim["membros"]:
        raise PacoteInvalido(f"o .zip tem {len(infos)} membros (máximo {lim['membros']})")
    vistos, pastas, arquivos, total = set(), set(), [], 0
    for zi in infos:
        nome = zi.filename
        if "\\" in nome or "\x00" in nome or nome.startswith("/") or re.match(r"^[A-Za-z]:", nome):
            raise PacoteInvalido(f"caminho absoluto ou inválido no .zip: {nome!r}")
        partes = nome.rstrip("/").split("/")
        if any(p in ("", ".", "..") for p in partes):
            raise PacoteInvalido(f"caminho com '..' ou segmento vazio no .zip: {nome!r}")
        if not all(_SEGMENTO_RX.match(p) for p in partes):
            raise PacoteInvalido(f"nome de membro não permitido no .zip: {nome!r}")
        if zi.flag_bits & 0x1:
            raise PacoteInvalido(f"membro cifrado no .zip: {nome}")
        modo = zi.external_attr >> 16
        if zi.create_system == 3 and modo:          # atributos Unix presentes
            tipo = stat.S_IFMT(modo)
            if stat.S_ISLNK(modo):
                raise PacoteInvalido(f"link simbólico no .zip: {nome}")
            if tipo and tipo not in (stat.S_IFREG, stat.S_IFDIR):
                raise PacoteInvalido(f"arquivo especial no .zip: {nome}")
        chave = "/".join(partes).lower()
        if chave in vistos:
            raise PacoteInvalido(f"membro duplicado no .zip: {nome}")
        vistos.add(chave)
        if zi.is_dir():
            continue
        topo = partes[0]
        if len(partes) == 1:
            if topo not in (LEIA_ME, SOMAS):
                raise PacoteInvalido(f"arquivo inesperado na raiz do .zip: {nome}")
            continue
        if topo == ENTRADAS:
            if len(partes) != 2:
                raise PacoteInvalido(f"subpasta não permitida em {ENTRADAS}/: {nome}")
        elif PASTA_EXEC_RX.match(topo):
            pastas.add(topo)
        else:
            raise PacoteInvalido(f"pasta inesperada no .zip: {topo}/")
        if zi.file_size < 0:
            raise PacoteInvalido(f"tamanho inválido: {nome}")
        total += zi.file_size
        if total > lim["descompactado_bytes"]:
            raise PacoteInvalido("conteúdo descompactado excede o limite "
                                 f"({lim['descompactado_bytes'] // (1024 * 1024)} MiB)")
        arquivos.append(zi)
    # nenhum arquivo pode ter o mesmo nome de uma pasta (ex.: 'a' e 'a/b')
    prefixos = {"/".join(zi.filename.split("/")[:i]).lower() for zi in arquivos
                for i in range(1, zi.filename.count("/") + 1)}
    if prefixos & {zi.filename.lower() for zi in arquivos}:
        raise PacoteInvalido("o .zip tem um arquivo e uma pasta com o mesmo nome")
    if len(pastas) != 1:
        raise PacoteInvalido("o .zip deve conter exatamente uma pasta de execução (<AAAAMMDDTHHMMSSZ>_<id>/); "
                             f"encontradas: {len(pastas)}")
    pasta = pastas.pop()
    if not any(zi.filename == f"{pasta}/manifesto.json" for zi in arquivos):
        raise PacoteInvalido(f"o .zip não contém {pasta}/manifesto.json")
    return pasta, arquivos


def _extrair(z: zipfile.ZipFile, membros: list, destino: Path, lim: dict):
    """Extrai contando os bytes REAIS (não confia no tamanho declarado no cabeçalho)."""
    total = 0
    for zi in membros:
        alvo = destino / zi.filename
        if not _dentro(alvo, destino):
            raise PacoteInvalido(f"caminho fora da pasta de extração: {zi.filename}")
        alvo.parent.mkdir(parents=True, exist_ok=True)
        lidos = 0
        with z.open(zi) as src, open(alvo, "xb") as dst:
            while True:
                bloco = src.read(_BLOCO)
                if not bloco:
                    break
                lidos += len(bloco)
                total += len(bloco)
                if lidos > zi.file_size or total > lim["descompactado_bytes"]:
                    raise PacoteInvalido("conteúdo descompactado maior que o declarado ou que o limite")
                dst.write(bloco)


def _validar_manifesto(man, pasta: str) -> dict:
    if not isinstance(man, dict):
        raise PacoteInvalido("manifesto.json não é um objeto JSON")
    id_ = man.get("id")
    if not isinstance(id_, str) or not ID_EXEC_RX.match(id_) or not pasta.endswith("_" + id_):
        raise PacoteInvalido("o ID do manifesto não corresponde ao nome da pasta da execução")
    saidas = man.get("saidas_sha256")
    if not isinstance(saidas, dict) or not all(isinstance(k, str) and isinstance(v, str) and _SHA_RX.match(v)
                                               for k, v in saidas.items()):
        raise PacoteInvalido("manifesto.json sem 'saidas_sha256' válido: os arquivos não podem ser verificados")
    fontes = man.get("fontes", [])
    if not isinstance(fontes, list) or not all(isinstance(f, dict) and isinstance(f.get("sha256"), str)
                                               for f in fontes):
        raise PacoteInvalido("manifesto.json com 'fontes' inválido")
    for chave in ("data_hora_utc", "modo", "versao_metodo", "contagens", "estratos", "hash_corpus"):
        if chave not in man:
            raise PacoteInvalido(f"manifesto.json sem o campo '{chave}'")
    return man


def _somente_leitura(pasta: Path):
    for p in pasta.rglob("*"):
        if p.is_file() and not p.is_symlink():
            os.chmod(p, 0o444)


def _remover(p: Path):
    """Remove uma árvore temporária (inclusive arquivos já marcados como somente leitura)."""
    if not p.exists():
        return
    for x in p.rglob("*"):
        if not x.is_symlink():
            os.chmod(x, 0o700 if x.is_dir() else 0o600)
    shutil.rmtree(p)


def importar(projeto: Projeto, caminho, nome: str | None = None) -> dict:
    """Importa um .zip gerado por `exportar` como execução somente leitura do projeto.

    Se CIENTOMETRIA_DIR_IMPORTACAO estiver definida (a API web a define), só arquivos dentro
    desse diretório podem ser importados."""
    caminho = Path(caminho)
    limite_dir = os.environ.get("CIENTOMETRIA_DIR_IMPORTACAO")
    if limite_dir and not _dentro(caminho, Path(limite_dir)):
        raise ValueError("Arquivo fora do diretório de importação permitido.")
    if caminho.is_symlink() or not caminho.is_file():
        raise PacoteInvalido("o pacote deve ser um arquivo comum (links simbólicos não são aceitos)")
    nome = os.path.basename(str(nome or caminho.name))[:200]
    if not nome.lower().endswith(".zip"):
        raise PacoteInvalido("o pacote deve ter extensão .zip")
    lim = limites()
    if caminho.stat().st_size > lim["zip_bytes"]:
        raise PacoteInvalido(f"o .zip excede o limite de {lim['zip_bytes'] // (1024 * 1024)} MiB")
    sha_zip = sha256_arquivo(caminho)
    if not zipfile.is_zipfile(caminho):
        raise PacoteInvalido("o arquivo não é um .zip válido")

    execs = projeto.pasta / "execucoes"
    tmp = execs / f".importando_{uuid.uuid4().hex}"
    tmp.mkdir(parents=True)
    try:
        try:
            with zipfile.ZipFile(caminho) as z:
                pasta, membros = _validar_membros(z, lim)
                _extrair(z, membros, tmp, lim)
        except (zipfile.BadZipFile, zipfile.LargeZipFile, NotImplementedError, EOFError) as e:
            raise PacoteInvalido(f"o .zip está corrompido ou usa recurso não suportado: {e}") from e
        try:
            man = _validar_manifesto(json.loads((tmp / pasta / "manifesto.json").read_text(encoding="utf-8")),
                                     pasta)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise PacoteInvalido(f"manifesto.json ilegível: {e}") from e
        problemas = projeto.conferir_saidas(tmp / pasta, man)
        if problemas:
            raise IntegridadeErro("pacote recusado: arquivos não conferem com manifesto.json "
                                  f"({len(problemas)} problema(s)): {problemas[:10]}")
        esperadas = {f["sha256"] for f in man.get("fontes", [])}
        entradas = {}
        if (tmp / ENTRADAS).is_dir():
            for f in sorted((tmp / ENTRADAS).iterdir()):
                s = sha256_arquivo(f)
                if s not in esperadas:
                    raise IntegridadeErro(f"pacote recusado: entrada {f.name} não consta do manifesto (SHA-256)")
                entradas[f.name] = s
        _somente_leitura(tmp)
        registro = {"importada_em": _agora(), "arquivo_zip": nome, "sha256_zip": sha_zip,
                    "id": man["id"], "pasta": pasta, "versao_aplicacao_importacao": APP_VERSAO,
                    "versao_aplicacao_origem": man.get("versao_aplicacao"), "entradas": entradas,
                    "leia_me": (tmp / LEIA_ME).is_file()}
        with _trava(projeto.pasta):
            existentes = [p.name for p in projeto._pastas_execucao() if p.name.endswith("_" + man["id"])]
            if existentes or (execs / pasta).exists():
                raise FileExistsError(f"o projeto já tem uma execução com o ID {man['id']} "
                                      f"({(existentes or [pasta])[0]}); nada foi importado nem sobrescrito")
            reg_dir = execs / ".importadas"
            reg_dir.mkdir(exist_ok=True)
            reg_arq = reg_dir / f"{pasta}.json"
            try:
                if entradas:
                    (reg_dir / pasta).mkdir()
                    os.rename(tmp / ENTRADAS, reg_dir / pasta / ENTRADAS)
                _json(reg_arq, registro)
                os.rename(tmp / pasta, execs / pasta)     # publicação atômica
            except BaseException:
                reg_arq.unlink(missing_ok=True)
                _remover(reg_dir / pasta)
                raise
            projeto._evento_sem_trava("execucao_importada", id=man["id"], pasta=pasta, arquivo=nome,
                                      sha256_zip=sha_zip, entradas_incluidas=len(entradas))
    finally:
        _remover(tmp)
    verif = projeto.verificar_execucao(man["id"])
    return {"id": man["id"], "pasta": pasta, "importacao": registro, "verificacao": verif}
