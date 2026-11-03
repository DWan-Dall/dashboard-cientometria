"""Configuração do método. Tudo que é decisão metodológica fica aqui, não no código."""
from __future__ import annotations
from dataclasses import dataclass, field, replace
from . import termos as T


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

    # ---- receitas prontas -------------------------------------------------
    @classmethod
    def original(cls) -> "Config":
        """Reproduz exatamente o procedimento de jan/2026."""
        return cls(modo="original")

    @classmethod
    def variante_exclusao(cls) -> "Config":
        """Muda SOMENTE a exclusão dam/dike/levee (de trecho para palavra inteira)."""
        return cls(modo="variante_exclusao", exclusao_palavra_inteira=T.EXCLUSAO_CURTA)

    @classmethod
    def corrigida(cls) -> "Config":
        """Corrige as falhas de implementação documentadas (muda os números)."""
        return cls(modo="corrigida", exclusao_palavra_inteira=T.EXCLUSAO_CURTA,
                   manter_sem_doi=True, mapeamento_tolerante=True)

    def com(self, **kw) -> "Config":
        return replace(self, **kw)

    def descricao(self) -> dict:
        return {
            "modo": self.modo, "pesos": list(self.pesos), "cortes": list(self.cortes),
            "exclusao_palavra_inteira": list(self.exclusao_palavra_inteira),
            "manter_sem_doi": self.manter_sem_doi,
            "mapeamento_tolerante": self.mapeamento_tolerante,
            "n_termos": {k: len(v) for k, v in self.nucleo.items()} | {"exclusao": len(self.exclusao)},
        }
