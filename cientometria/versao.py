"""Versões da aplicação e do método.

A versão do MÉTODO identifica o conjunto de regras de triagem (o que muda resultados).
A versão da APLICAÇÃO identifica o software (o que pode mudar sem mudar resultados).
Toda alteração em `nucleo.py`, `termos.py`, `pipeline.consolidar` ou em receitas de
`Config` que mude números deve criar uma nova entrada em METODO_HISTORICO.
"""

APP_VERSAO = "0.3.0"  # 0.3.0: exportação/importação de execuções em ZIP (não altera resultados)
#                      0.2.1: fidelidade do modo original com títulos ausentes (achado 11)

# modo -> versão vigente do conjunto de regras
METODO_VERSOES = {
    "original": "original-2026.01",           # procedimento do artigo (jan/2026), congelado
    "variante_exclusao": "variante-1",         # só a exclusão dam/dike/levee muda
    "corrigida": "corrigida-2",                # correções técnicas (ver METHODOLOGY.md)
    "corrigida_v1": "corrigida-1",             # versão anterior da corrigida, para comparação
    "personalizado": "personalizado",          # parâmetros alterados pelo usuário
}

METODO_HISTORICO = [
    {"versao": "original-2026.01", "data": "2026-01",
     "descricao": "Scripts originais (referencia/fase2..5). Congelado: não deve mudar."},
    {"versao": "variante-1", "data": "2026-11-03",
     "descricao": "Igual ao original, exceto dam/dike/levee casados como palavra inteira."},
    {"versao": "corrigida-1", "data": "2026-11-03",
     "descricao": "Variante + mapeamento tolerante de colunas + registros sem DOI mantidos."},
    {"versao": "corrigida-2", "data": "2026-11-10",
     "descricao": "corrigida-1 + DOI normalizado (caixa, prefixos doi.org/doi:) antes da "
                  "deduplicação. Motivo: 27 pares de DOIs que diferem só na caixa no corpus "
                  "publicado de 2.068 registros (ver docs/AUDITORIA.md)."},
]
