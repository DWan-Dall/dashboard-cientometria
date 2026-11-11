#!/usr/bin/env python3
"""Validações básicas do repositório (usadas no CI).

1. Arquivos CONGELADOS do modo original (docs/congelados.sha256) não mudaram.
   Mudá-los exige decisão metodológica: nova versão em cientometria/versao.py,
   METHODOLOGY.md §3 e atualização deliberada do arquivo de somas.
2. Nenhum dado tabular/bibliográfico versionado fora da lista permitida (as exportações
   das bases têm licença e não podem ser publicadas).
3. Nenhum diretório de dados de projetos versionado.
"""
import hashlib
import pathlib
import subprocess  # nosec B404
import sys

RAIZ = pathlib.Path(__file__).resolve().parents[1]
PERMITIDOS = {"docs/log_buscas_template.csv", "exemplos/referencias_dias2025.csv"}
EXT_DADOS = {".csv", ".tsv", ".xlsx", ".xls", ".ris", ".bib", ".bibtex", ".nbib",
             ".zip"}  # .zip: pacotes de execução podem conter as exportações das bases


def main() -> int:
    erros = []
    for linha in (RAIZ / "docs" / "congelados.sha256").read_text().splitlines():
        esperado, caminho = linha.split(maxsplit=1)
        p = RAIZ / caminho.strip()
        atual = hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else "ausente"
        if atual != esperado:
            erros.append(f"arquivo congelado alterado: {caminho.strip()} (ver CLAUDE.md e METHODOLOGY.md §3)")
    # subprocess só com o comando fixo `git ls-files`, sem entrada externa
    saida = subprocess.run(["git", "ls-files"], cwd=RAIZ, capture_output=True, text=True, check=True)  # nosec B603 B607
    arquivos = saida.stdout.split()
    for a in arquivos:
        if pathlib.Path(a).suffix.lower() in EXT_DADOS and a not in PERMITIDOS:
            erros.append(f"dado tabular/bibliográfico versionado (possível dado licenciado): {a}")
        if a.startswith(("projetos/", "tmp_uploads/")):
            erros.append(f"dados de projeto/upload versionados: {a}")
    for e in erros:
        print("ERRO:", e)
    print("ok" if not erros else f"{len(erros)} problema(s)")
    return 1 if erros else 0


if __name__ == "__main__":
    sys.exit(main())
