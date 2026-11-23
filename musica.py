"""Pausa a música de fundo (Spotify etc.) durante as chamadas e volta depois.

Usa o controle de mídia do Windows (o mesmo das teclas de mídia do teclado).
Só pausa o que estava tocando e só retoma o que o próprio Soundpad pausou:
se a música já estava parada, continua parada.
"""
import asyncio
import sys

TEMPO_LIMITE = 3  # segundos; se o Windows não responder, a chamada segue sem pausar

_pausados: list[str] = []  # apps que o Soundpad pausou (ex.: Spotify.exe)


def _rodar(corrotina):
    return asyncio.run(asyncio.wait_for(corrotina, timeout=TEMPO_LIMITE))


async def _sessoes():
    from winrt.windows.media.control import (
        GlobalSystemMediaTransportControlsSessionManager as Gerenciador,
    )

    gerenciador = await Gerenciador.request_async()
    return list(gerenciador.get_sessions())


def _tocando(sessao) -> bool:
    from winrt.windows.media.control import (
        GlobalSystemMediaTransportControlsSessionPlaybackStatus as Estado,
    )

    return sessao.get_playback_info().playback_status == Estado.PLAYING


async def _pausar() -> list[str]:
    pausados = []
    for sessao in await _sessoes():
        if _tocando(sessao) and await sessao.try_pause_async():
            pausados.append(sessao.source_app_user_model_id)
    return pausados


async def _retomar(apps: list[str]) -> None:
    for sessao in await _sessoes():
        if sessao.source_app_user_model_id in apps and not _tocando(sessao):
            await sessao.try_play_async()


def pausar() -> bool:
    """Pausa o que estiver tocando. Devolve True se pausou alguma coisa."""
    global _pausados
    if sys.platform != "win32":
        return False
    try:
        novos = _rodar(_pausar())
    except Exception as e:
        print(f"[aviso] Não consegui pausar a música: {type(e).__name__}: {e}")
        return False
    _pausados += [a for a in novos if a not in _pausados]
    return bool(novos)


def retomar() -> None:
    """Volta a tocar o que o Soundpad pausou."""
    global _pausados
    if not _pausados:
        return
    apps, _pausados = _pausados, []
    try:
        _rodar(_retomar(apps))
    except Exception as e:
        print(f"[aviso] Não consegui retomar a música: {type(e).__name__}: {e}")
