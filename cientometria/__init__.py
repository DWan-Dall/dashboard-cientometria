"""cientometria — plataforma de cientometria reproduzível.

O núcleo da triagem (escore composto C*, R*, T*, A*) é a ÚNICA implementação do método:
dashboard, CLI e análises usam este pacote. Ver METHODOLOGY.md e ARCHITECTURE.md.
"""
from .config import Config, MODOS
from .pipeline import executar, Resultado
from .entrada import ler_pasta, BASES_ESPERADAS
from .ingestao import carregar_fontes
from .versao import APP_VERSAO, METODO_VERSOES

__all__ = ["Config", "MODOS", "executar", "Resultado", "ler_pasta", "BASES_ESPERADAS", "carregar_fontes",
           "APP_VERSAO", "METODO_VERSOES"]
__version__ = APP_VERSAO
