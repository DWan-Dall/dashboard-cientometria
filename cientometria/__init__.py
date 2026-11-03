"""cientometria — triagem cientométrica replicável (escore composto C*, R*, T*, A*)."""
from .config import Config
from .pipeline import executar, Resultado
from .entrada import ler_pasta, BASES_ESPERADAS

__all__ = ["Config", "executar", "Resultado", "ler_pasta", "BASES_ESPERADAS"]
__version__ = "0.1.0"
