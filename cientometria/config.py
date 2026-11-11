"""Configuração do método. Tudo que é decisão metodológica fica aqui, não no código."""
from __future__ import annotations
from dataclasses import dataclass, field, replace, asdict
from . import termos as T
from .versao import METODO_VERSOES

MODOS = ("original", "variante_exclusao", "corrigida")


@dataclass(frozen=True)
class Config:
    modo: str = "original"
    # Pesos do escore S = w1*C* + w2*R* + w3*T* + w4*A*
    pesos: tuple = (0.35, 0.20, 0.30, 0.15)
    # Cortes (escore 0-100): Núcleo A, Núcleo B, Periférico
    cortes: tuple = (70, 50, 30)
    nucleo: dict = field(default_factory=lambda: {k: list(v) for k, v in T.NUCLEO.items()})
    exclusao: tuple = tuple(T.EXCLUSAO)
    ml_especifico: tuple = tuple(T.ML_ESPECIFICO)
    saida: tuple = tuple(T.SAIDA)
    contexto: tuple = tuple(T.CONTEXTO)
    # Termos de exclusão casados como palavra inteira (vazio = tudo por trecho, como no original)
    exclusao_palavra_inteira: tuple = ()
    # False = comportamento original (descarta registros sem DOI na etapa de DOI)
    manter_sem_doi: bool = False
    # False = mapeamento de colunas original (fixo); True = aceita aliases de coluna
    mapeamento_tolerante: bool = False
    # False = DOI comparado como texto bruto (original); True = caixa baixa, sem prefixos
    normalizar_doi: bool = False
    # Identificação do conjunto de regras (preenchida pelas receitas; ver versao.py)
    metodo_versao: str = METODO_VERSOES["original"]

    # ---- receitas prontas -------------------------------------------------
    @classmethod
    def original(cls) -> "Config":
        """Reproduz exatamente o procedimento de jan/2026."""
        return cls(modo="original", metodo_versao=METODO_VERSOES["original"])

    @classmethod
    def variante_exclusao(cls) -> "Config":
        """Muda SOMENTE a exclusão dam/dike/levee (de trecho para palavra inteira)."""
        return cls(modo="variante_exclusao", exclusao_palavra_inteira=T.EXCLUSAO_CURTA,
                   metodo_versao=METODO_VERSOES["variante_exclusao"])

    @classmethod
    def corrigida(cls) -> "Config":
        """Corrige as falhas de implementação documentadas (muda os números)."""
        return cls(modo="corrigida", exclusao_palavra_inteira=T.EXCLUSAO_CURTA,
                   manter_sem_doi=True, mapeamento_tolerante=True, normalizar_doi=True,
                   metodo_versao=METODO_VERSOES["corrigida"])

    @classmethod
    def corrigida_v1(cls) -> "Config":
        """Versão anterior da corrigida (sem normalização de DOI), mantida para comparação."""
        return cls(modo="corrigida", exclusao_palavra_inteira=T.EXCLUSAO_CURTA,
                   manter_sem_doi=True, mapeamento_tolerante=True,
                   metodo_versao=METODO_VERSOES["corrigida_v1"])

    @classmethod
    def do_modo(cls, modo: str) -> "Config":
        receitas = {"original": cls.original, "variante_exclusao": cls.variante_exclusao,
                    "corrigida": cls.corrigida, "corrigida_v1": cls.corrigida_v1}
        if modo not in receitas:
            raise ValueError(f"Modo desconhecido: {modo!r}. Use um de {sorted(receitas)}")
        return receitas[modo]()

    def com(self, **kw) -> "Config":
        return replace(self, **kw)

    def _receita(self) -> "Config | None":
        if self.metodo_versao == METODO_VERSOES["corrigida_v1"]:
            return Config.corrigida_v1()
        try:
            return Config.do_modo(self.modo)
        except ValueError:
            return None

    def alteracoes_em_relacao_a_receita(self) -> dict:
        """Parâmetros que diferem da receita do modo (registrados no manifesto)."""
        base = self._receita()
        if base is None:
            return {"modo": {"receita": None, "usado": self.modo}}
        a, b = self.completa(), base.completa()
        return {k: {"receita": b[k], "usado": a[k]} for k in a if a[k] != b[k]}

    def personalizada(self) -> bool:
        return bool(self.alteracoes_em_relacao_a_receita())

    def descricao(self) -> dict:
        return {
            "modo": self.modo, "metodo_versao": self.metodo_versao,
            "personalizada": self.personalizada(),
            "pesos": list(self.pesos), "cortes": list(self.cortes),
            "exclusao_palavra_inteira": list(self.exclusao_palavra_inteira),
            "manter_sem_doi": self.manter_sem_doi,
            "mapeamento_tolerante": self.mapeamento_tolerante,
            "normalizar_doi": self.normalizar_doi,
            "n_termos": {k: len(v) for k, v in self.nucleo.items()} | {"exclusao": len(self.exclusao)},
        }

    def completa(self) -> dict:
        """Todos os parâmetros, inclusive listas de termos (para o manifesto)."""
        d = asdict(self)
        return {k: (list(v) if isinstance(v, tuple) else v) for k, v in d.items()}

    @classmethod
    def de_dict(cls, d: dict) -> "Config":
        """Reconstrói uma Config a partir de `completa()` (recuperação de execuções)."""
        kw = {}
        for k, v in d.items():
            if k in cls.__dataclass_fields__:
                kw[k] = tuple(v) if isinstance(v, list) else v
        return cls(**kw)
