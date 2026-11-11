"""Limites de recursos para processos iniciados pela interface web (contra negação de serviço).

- memória: CIENTOMETRIA_MEMORIA_MAX_MB (padrão 6144) -> RLIMIT_AS do processo;
- tempo:   CIENTOMETRIA_TEMPO_MAX_S (padrão 3600)    -> alarme que encerra com erro claro.

Não altera nenhum resultado: só interrompe processos que excedam os limites.
Usado por `api.principal_api` e `scripts/pipeline.py` (não pela CLI de linha de comando).
"""
from __future__ import annotations
import os
import signal


class LimiteExcedido(RuntimeError):
    pass


def _alarme(signum, frame):  # noqa: ARG001
    raise LimiteExcedido("tempo máximo de processamento excedido (CIENTOMETRIA_TEMPO_MAX_S)")


def aplicar() -> dict:
    aplicados = {}
    try:
        import resource
        mb = int(os.environ.get("CIENTOMETRIA_MEMORIA_MAX_MB", "6144"))
        if mb > 0:
            limite = mb * 1024 * 1024
            _, rigido = resource.getrlimit(resource.RLIMIT_AS)
            if rigido != resource.RLIM_INFINITY:
                limite = min(limite, rigido)
            resource.setrlimit(resource.RLIMIT_AS, (limite, rigido))
            aplicados["memoria_mb"] = mb
    except (ImportError, ValueError, OSError):
        pass
    s = int(os.environ.get("CIENTOMETRIA_TEMPO_MAX_S", "3600"))
    if s > 0 and hasattr(signal, "SIGALRM"):
        signal.signal(signal.SIGALRM, _alarme)
        signal.alarm(s)
        aplicados["tempo_s"] = s
    return aplicados
