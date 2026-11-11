"""Pacote ZIP de uma execução: formato, montagem e validação.

Este módulo só sabe ler e escrever o ARQUIVO .zip. Tudo o que toca o projeto (escolher o
que entra, restaurar, reexecutar, registrar eventos) fica em `projetos.py`, que é o único
sistema de persistência. O manifesto do pacote é gerado por `manifesto.pacote()`, a partir do
manifesto da execução (que viaja intacto em `execucao/manifesto.json`).

Estrutura (formato `cientometria-pacote-execucao`, versão 1):

    manifesto.json            manifesto do pacote (SHA-256 de cada arquivo, omissões, versões)
    LEIA-ME.txt               o que é o pacote, o que foi omitido e como verificar
    execucao/<pasta>/...      a pasta da execução, byte a byte (inclui o manifesto da execução)
    entradas/<sha12>__<nome>  exportações bibliográficas originais (opcionais; licença das bases)

Garantias da validação (`inspecionar`), sem extrair nem executar nada:
- só ZIP comum (stored/deflated), sem criptografia, sem entradas duplicadas;
- nomes relativos, sem `..`, sem barra invertida, sem caracteres fora de [A-Za-z0-9._-];
- só arquivos regulares (links simbólicos e dispositivos são recusados pelos bits de modo);
- extensões permitidas por área; limites de tamanho do ZIP, do total descompactado, do número
  de entradas e da razão de compressão (zip bomb), conferidos também durante a leitura;
- cada arquivo listado no manifesto existe e tem o SHA-256 declarado; arquivos não listados
  são "inesperados". Os problemas de integridade são devolvidos (não lançados) para exibição.

O SHA-256 detecta alteração acidental ou parcial. O pacote não é assinado: quem altera um
arquivo E o manifesto produz um pacote coerente. A conferência cruzada com o manifesto da
execução (saídas e hash do corpus recalculado) é feita na restauração (projetos.py).
"""
from __future__ import annotations
import hashlib
import json
import os
import re
import stat
import uuid
import zipfile
import zlib
from pathlib import Path

FORMATO = "cientometria-pacote-execucao"
VERSAO_FORMATO = 1
NOME_MANIFESTO = "manifesto.json"
NOME_LEIA_ME = "LEIA-ME.txt"

MB = 1024 * 1024
MAX_PACOTE = int(os.environ.get("CIENTOMETRIA_MAX_MB_PACOTE", "512")) * MB
MAX_DESCOMPACTADO = int(os.environ.get("CIENTOMETRIA_MAX_MB_PACOTE_DESCOMPACTADO", "4096")) * MB
MAX_ENTRADAS = 5000
MAX_MANIFESTO = 50 * MB
RAZAO_MAXIMA = 200              # mesma regra das planilhas (ingestao.RAZAO_MAXIMA_COMPRESSAO)
RAZAO_A_PARTIR_DE = 1 * MB      # arquivos pequenos e repetitivos comprimem muito sem ser ataque

COMPONENTE_RX = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9._-]{0,159}$")
PASTA_EXEC_RX = re.compile(r"^\d{8}T\d{6}Z_[0-9a-f]{12}$")
EXT_EXECUCAO = {".csv", ".json", ".png", ".pdf", ".md", ".xlsx", ".txt"}
EXT_ENTRADAS = {".csv", ".tsv", ".txt", ".xlsx", ".xls", ".ris", ".bib", ".bibtex", ".nbib"}
SEM_COMPRESSAO = {".png", ".xlsx", ".pdf", ".xls"}   # já comprimidos


class PacoteInvalido(ValueError):
    """ZIP malformado, perigoso ou fora do formato (recusado sem extrair nada)."""


def _sha_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_arquivo(p) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


# ------------------------------------------------------------------ nomes e áreas
def area(nome: str) -> str:
    """Área de um caminho do pacote: 'raiz', 'execucao' ou 'entradas'. Recusa o resto."""
    if "\\" in nome or nome.startswith("/") or "\x00" in nome:
        raise PacoteInvalido(f"caminho não permitido no pacote: {nome!r}")
    partes = nome.split("/")
    if any(p in ("", ".", "..") for p in partes):
        raise PacoteInvalido(f"caminho não permitido no pacote: {nome!r}")
    if not all(COMPONENTE_RX.match(p) for p in partes):
        raise PacoteInvalido(f"caractere ou nome não permitido no pacote: {nome!r}")
    ext = Path(partes[-1]).suffix.lower()
    if len(partes) == 1:
        if nome in (NOME_MANIFESTO, NOME_LEIA_ME):
            return "raiz"
    elif partes[0] == "execucao" and len(partes) >= 3 and PASTA_EXEC_RX.match(partes[1]) and len(partes) <= 5:
        if ext in EXT_EXECUCAO:
            return "execucao"
    elif partes[0] == "entradas" and len(partes) == 2:
        if ext in EXT_ENTRADAS and re.match(r"^[0-9a-f]{12}__", partes[1]):
            return "entradas"
    raise PacoteInvalido(f"arquivo fora da estrutura do pacote: {nome!r}")


# ------------------------------------------------------------------ montagem
def montar(destino: Path, manifesto: dict, arquivos: list, leia_me: str) -> dict:
    """Grava o ZIP em `destino` (temporário + rename). `arquivos`: [(caminho_no_pacote, Path)].
    O `manifesto` recebe aqui o SHA-256 e o tamanho de cada arquivo efetivamente gravado."""
    destino = Path(destino)
    tmp = destino.with_name(f".{destino.name}.{uuid.uuid4().hex[:8]}.tmp")
    lista = {}
    try:
        with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            dados = leia_me.encode("utf-8")
            z.writestr(_info(NOME_LEIA_ME), dados)
            lista[NOME_LEIA_ME] = {"sha256": _sha_bytes(dados), "bytes": len(dados)}
            for nome, origem in sorted(arquivos):
                area(nome)
                origem = Path(origem)
                if origem.is_symlink() or not origem.is_file():
                    raise PacoteInvalido(f"origem não é arquivo regular: {nome}")
                h, n = hashlib.sha256(), 0
                info = _info(nome, Path(nome).suffix.lower() in SEM_COMPRESSAO)
                with open(origem, "rb") as f, z.open(info, "w", force_zip64=True) as w:
                    for bloco in iter(lambda: f.read(1 << 20), b""):
                        h.update(bloco)
                        n += len(bloco)
                        w.write(bloco)
                lista[nome] = {"sha256": h.hexdigest(), "bytes": n}
            manifesto["arquivos"] = dict(sorted(lista.items()))
            z.writestr(_info(NOME_MANIFESTO), json.dumps(manifesto, ensure_ascii=False, indent=1,
                                                         default=str).encode("utf-8"))
        with open(tmp, "rb") as f:
            os.fsync(f.fileno())
        os.replace(tmp, destino)
    finally:
        if tmp.exists():
            tmp.unlink()
    return {"arquivo": str(destino), "nome": destino.name, "sha256": sha256_arquivo(destino),
            "bytes": destino.stat().st_size}


def _info(nome: str, armazenar: bool = False) -> zipfile.ZipInfo:
    i = zipfile.ZipInfo(nome, date_time=(1980, 1, 1, 0, 0, 0))
    i.compress_type = zipfile.ZIP_STORED if armazenar else zipfile.ZIP_DEFLATED
    i.external_attr = (stat.S_IFREG | 0o644) << 16
    return i


# ------------------------------------------------------------------ validação
def _abrir(caminho: Path) -> zipfile.ZipFile:
    caminho = Path(caminho)
    if caminho.is_symlink() or not caminho.is_file():
        raise PacoteInvalido("o pacote não é um arquivo regular")
    if caminho.stat().st_size > MAX_PACOTE:
        raise PacoteInvalido(f"pacote maior que o limite ({MAX_PACOTE // MB} MiB; CIENTOMETRIA_MAX_MB_PACOTE)")
    try:
        return zipfile.ZipFile(caminho)
    except (zipfile.BadZipFile, OSError, ValueError) as e:
        raise PacoteInvalido(f"arquivo ZIP inválido ou corrompido ({e})") from e


def _conferir_entradas(z: zipfile.ZipFile) -> dict:
    """Checagens estruturais sobre o diretório central. Devolve {nome: ZipInfo} (só arquivos)."""
    infos = z.infolist()
    if len(infos) > MAX_ENTRADAS:
        raise PacoteInvalido(f"pacote com entradas demais ({len(infos)} > {MAX_ENTRADAS})")
    vistos, minusculos, total = {}, set(), 0
    for i in infos:
        nome = i.filename
        if i.flag_bits & 0x1:
            raise PacoteInvalido(f"entrada criptografada não é aceita: {nome!r}")
        if i.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
            raise PacoteInvalido(f"método de compressão não aceito: {nome!r}")
        modo = i.external_attr >> 16
        if i.is_dir():
            if nome.rstrip("/") not in ("execucao", "entradas"):
                area(nome.rstrip("/") + "/x.txt")      # mesma regra de nomes dos arquivos
            continue
        # sem bits de tipo (comum em ZIPs do Windows e do zipfile) = arquivo comum; com tipo, só regular
        if stat.S_IFMT(modo) and stat.S_IFMT(modo) != stat.S_IFREG:
            raise PacoteInvalido(f"entrada não é arquivo regular (link simbólico ou especial): {nome!r}")
        area(nome)
        if nome.lower() in minusculos:   # duplicata exata ou só na caixa (colide em alguns sistemas)
            raise PacoteInvalido(f"entrada duplicada no pacote: {nome!r}")
        minusculos.add(nome.lower())
        total += i.file_size
        if total > MAX_DESCOMPACTADO:
            raise PacoteInvalido(f"conteúdo descompactado maior que o limite ({MAX_DESCOMPACTADO // MB} MiB)")
        if i.file_size > RAZAO_A_PARTIR_DE and i.file_size > RAZAO_MAXIMA * max(i.compress_size, 1):
            raise PacoteInvalido(f"razão de compressão suspeita (zip bomb): {nome!r}")
        vistos[nome] = i
    return vistos


def _ler_limitado(z: zipfile.ZipFile, info: zipfile.ZipInfo, saida=None, limite: int | None = None):
    """Lê uma entrada em blocos, sem confiar no tamanho declarado; devolve (sha256, bytes)."""
    limite = info.file_size if limite is None else min(limite, info.file_size)
    h, n = hashlib.sha256(), 0
    try:
        with z.open(info) as f:
            while True:
                bloco = f.read(1 << 20)
                if not bloco:
                    break
                n += len(bloco)
                if n > limite:
                    raise PacoteInvalido(f"entrada maior que o declarado/limite: {info.filename!r}")
                h.update(bloco)
                if saida is not None:
                    saida.write(bloco)
    except (zipfile.BadZipFile, zlib.error, EOFError, OSError, ValueError, RuntimeError) as e:
        if isinstance(e, PacoteInvalido):
            raise
        raise PacoteInvalido(f"entrada corrompida: {info.filename!r} ({e})") from e
    return h.hexdigest(), n


def ler_manifesto(z: zipfile.ZipFile, infos: dict) -> dict:
    if NOME_MANIFESTO not in infos:
        raise PacoteInvalido("pacote sem manifesto.json (não é um pacote de execução)")
    from io import BytesIO
    buf = BytesIO()
    _ler_limitado(z, infos[NOME_MANIFESTO], buf, MAX_MANIFESTO)
    try:
        man = json.loads(buf.getvalue().decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise PacoteInvalido(f"manifesto.json ilegível ({e})") from e
    if not isinstance(man, dict) or man.get("formato") != FORMATO:
        raise PacoteInvalido("manifesto.json não é de um pacote de execução da cientometria")
    v = man.get("versao_formato")
    if not isinstance(v, int) or v < 1:
        raise PacoteInvalido("versão do formato do pacote ausente ou inválida")
    if v > VERSAO_FORMATO:
        raise PacoteInvalido(f"pacote no formato {v}, mais novo que o suportado ({VERSAO_FORMATO}); "
                             "atualize a aplicação")
    for chave, tipo in (("arquivos", dict), ("execucao", dict), ("fontes", list), ("omitidos", list)):
        if not isinstance(man.get(chave), tipo):
            raise PacoteInvalido(f"manifesto.json sem o campo obrigatório '{chave}'")
    ex = man["execucao"]
    if not (isinstance(ex.get("id"), str) and re.match(r"^[0-9a-f]{12}$", ex["id"])
            and isinstance(ex.get("pasta"), str) and PASTA_EXEC_RX.match(ex["pasta"])
            and ex["pasta"].endswith("_" + ex["id"])):
        raise PacoteInvalido("identificação da execução inválida no manifesto do pacote")
    for nome, d in man["arquivos"].items():
        area(nome)
        if not (isinstance(d, dict) and isinstance(d.get("sha256"), str) and re.match(r"^[0-9a-f]{64}$", d["sha256"])):
            raise PacoteInvalido(f"SHA-256 inválido no manifesto para {nome!r}")
    return man


def inspecionar(caminho) -> dict:
    """Valida o pacote sem extrair. Lança PacoteInvalido para ZIP malformado/perigoso;
    devolve o inventário com `problemas` (integridade) e `avisos`."""
    with _abrir(caminho) as z:
        infos = _conferir_entradas(z)
        man = ler_manifesto(z, infos)
        declarados = man["arquivos"]
        problemas, inventario = [], []
        pasta = man["execucao"]["pasta"]
        for nome in sorted(set(infos) | set(declarados)):
            if nome == NOME_MANIFESTO:
                continue
            reg = {"caminho": nome, "area": area(nome)}
            if nome.startswith("execucao/") and not nome.startswith(f"execucao/{pasta}/"):
                problemas.append(f"arquivo de outra execução no pacote: {nome}")
            if nome not in infos:
                reg["estado"] = "ausente"
                problemas.append(f"arquivo listado no manifesto e ausente no pacote: {nome}")
            elif nome not in declarados:
                reg["estado"] = "inesperado"
                reg["bytes"] = infos[nome].file_size
                problemas.append(f"arquivo inesperado (não listado no manifesto): {nome}")
            else:
                sha, n = _ler_limitado(z, infos[nome])
                reg.update({"bytes": n, "sha256": sha})
                if sha != declarados[nome]["sha256"]:
                    reg["estado"] = "alterado"
                    problemas.append(f"SHA-256 diferente do manifesto (arquivo alterado): {nome}")
                else:
                    reg["estado"] = "ok"
            inventario.append(reg)
        if f"execucao/{pasta}/manifesto.json" not in declarados:
            problemas.append("o pacote não contém o manifesto da execução (execucao/<pasta>/manifesto.json)")
        incluidas = {f.get("caminho_no_pacote") for f in man["fontes"] if f.get("incluido")}
        for c in sorted(x for x in incluidas if x):
            if c not in declarados:
                problemas.append(f"entrada declarada como incluída e não listada: {c}")
        avisos = []
        omitidas = [f for f in man["fontes"] if not f.get("incluido")]
        if omitidas:
            avisos.append(f"{len(omitidas)} exportação(ões) original(is) omitida(s): os resultados podem ser "
                          "restaurados e conferidos, mas a análise NÃO pode ser reexecutada só com este pacote.")
        return {"formato": man["formato"], "versao_formato": man["versao_formato"],
                "ok": not problemas, "problemas": problemas, "avisos": avisos,
                "execucao": man["execucao"], "projeto_origem": man.get("projeto_origem", {}),
                "contagens_por_etapa": man.get("contagens_por_etapa", {}), "estratos": man.get("estratos", {}),
                "fontes": man["fontes"], "omitidos": man["omitidos"],
                "reprodutibilidade": man.get("reprodutibilidade", {}),
                "exportado_em": man.get("exportado_em"), "versao_aplicacao_exportacao":
                    man.get("versao_aplicacao_exportacao"),
                "arquivos": inventario, "n_arquivos": len(inventario),
                "bytes_descompactados": sum(r.get("bytes", 0) for r in inventario)}


def extrair(caminho, destino: Path, prefixo: str, manifesto_arquivos: dict, remover_prefixo: str) -> list:
    """Extrai as entradas com `prefixo` para `destino`, conferindo o SHA-256 enquanto grava.
    Nunca usa o nome do ZIP como caminho sem validação; nunca segue links; não sobrescreve."""
    destino = Path(destino)
    base = destino.resolve()
    gravados = []
    with _abrir(caminho) as z:
        infos = _conferir_entradas(z)
        for nome in sorted(infos):
            if not nome.startswith(prefixo):
                continue
            if nome not in manifesto_arquivos:
                raise PacoteInvalido(f"arquivo inesperado: {nome}")
            rel = nome[len(remover_prefixo):]
            alvo = destino / rel
            if not alvo.resolve().is_relative_to(base):
                raise PacoteInvalido(f"caminho escapa do destino: {nome!r}")
            alvo.parent.mkdir(parents=True, exist_ok=True)
            with open(alvo, "xb") as f:
                sha, _ = _ler_limitado(z, infos[nome], f)
                f.flush()
                os.fsync(f.fileno())
            if sha != manifesto_arquivos[nome]["sha256"]:
                raise PacoteInvalido(f"SHA-256 diferente do manifesto durante a extração: {nome}")
            gravados.append(rel)
    return gravados
