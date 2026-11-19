"""Geração das falas (texto -> mp3), com cache em disco."""
import asyncio
import hashlib
import os
import threading
import urllib.error
import urllib.request
from pathlib import Path
from xml.sax.saxutils import escape

from ajustes import PASTA_CACHE

# Usadas quando não dá para buscar a lista completa na internet.
VOZES_CONHECIDAS = [
    {"id": "pt-BR-ThalitaMultilingualNeural", "nome": "Thalita (feminina, mais natural)"},
    {"id": "pt-BR-FranciscaNeural", "nome": "Francisca (feminina)"},
    {"id": "pt-BR-AntonioNeural", "nome": "Antonio (masculina)"},
]


class ErroVoz(Exception):
    pass


def _taxa(config: dict) -> str:
    return f"{int(config['velocidade']):+d}%"


# ------------------------------------------------------------------ motores
def _edge(texto: str, destino: Path, voz: str, taxa: str) -> None:
    try:
        import edge_tts
    except ImportError:
        raise ErroVoz("Falta o pacote edge-tts. Rode: pip install -r requirements.txt")

    async def _gerar():
        await edge_tts.Communicate(texto, voz, rate=taxa).save(str(destino))

    asyncio.run(asyncio.wait_for(_gerar(), timeout=25))


def _azure(texto: str, destino: Path, voz: str, taxa: str, chave: str, regiao: str) -> None:
    ssml = (
        "<speak version='1.0' xml:lang='pt-BR'>"
        f"<voice name='{escape(voz)}'><prosody rate='{taxa}'>{escape(texto)}</prosody></voice>"
        "</speak>"
    )
    pedido = urllib.request.Request(
        f"https://{regiao}.tts.speech.microsoft.com/cognitiveservices/v1",
        data=ssml.encode("utf-8"),
        method="POST",
        headers={
            "Ocp-Apim-Subscription-Key": chave,
            "Content-Type": "application/ssml+xml",
            "X-Microsoft-OutputFormat": "audio-24khz-96kbitrate-mono-mp3",
            "User-Agent": "Soundpad",
        },
    )
    try:
        with urllib.request.urlopen(pedido, timeout=25) as resposta:
            destino.write_bytes(resposta.read())
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise ErroVoz("Chave ou região do Azure incorreta.")
        raise


def sintetizar(texto: str, destino: Path, config: dict, voz: str | None = None) -> None:
    """Gera a fala; se a voz escolhida falhar, tenta a voz reserva."""
    vozes = [voz] if voz else [config["voz"]]
    if not voz and config.get("voz_reserva") and config["voz_reserva"] != config["voz"]:
        vozes.append(config["voz_reserva"])
    taxa = _taxa(config)
    ultimo_erro: Exception | None = None
    for v in vozes:
        try:
            if config["motor_voz"] == "azure":
                _azure(texto, destino, v, taxa, config["azure_chave"], config["azure_regiao"])
            else:
                _edge(texto, destino, v, taxa)
            if destino.exists() and destino.stat().st_size > 0:
                return
            ultimo_erro = ErroVoz("a voz não retornou áudio")
        except ErroVoz as e:
            ultimo_erro = e
            if "Falta o pacote" in str(e) or "Azure" in str(e):
                break
        except Exception as e:
            ultimo_erro = e
        print(f"[aviso] Voz '{v}' falhou: {type(ultimo_erro).__name__}: {ultimo_erro}")
    if isinstance(ultimo_erro, ErroVoz):
        raise ultimo_erro
    raise ErroVoz("Não consegui gerar a fala. Confira se o computador da mesa de som está com internet.")


def listar_vozes(config: dict) -> list[dict]:
    """Vozes pt-BR disponíveis (busca na internet; se falhar, usa a lista conhecida)."""
    if config["motor_voz"] == "edge":
        try:
            import edge_tts

            async def _lista():
                return await edge_tts.list_voices()

            todas = asyncio.run(asyncio.wait_for(_lista(), timeout=10))
            vozes = [
                {"id": v["ShortName"],
                 "nome": f"{v['ShortName'].split('-')[-1].replace('Neural', '')} "
                         f"({'feminina' if v.get('Gender') == 'Female' else 'masculina'})"}
                for v in todas if v.get("Locale") == "pt-BR"
            ]
            if vozes:
                return vozes
        except Exception as e:
            print(f"[aviso] Não consegui buscar a lista de vozes: {e}")
    return list(VOZES_CONHECIDAS)


# ------------------------------------------------------------------ cache
_travas: dict[str, threading.Lock] = {}
_travas_lock = threading.Lock()
_cache_lock = threading.Lock()


def _trava(nome: str) -> threading.Lock:
    with _travas_lock:
        return _travas.setdefault(nome, threading.Lock())


def caminho_no_cache(texto: str, config: dict, voz: str | None = None) -> Path:
    chave = f"{config['motor_voz']}|{voz or config['voz']}|{_taxa(config)}|{texto}"
    return PASTA_CACHE / f"{hashlib.sha1(chave.encode('utf-8')).hexdigest()[:20]}.mp3"


def limpar_cache(limite: int) -> None:
    with _cache_lock:
        arquivos = sorted(PASTA_CACHE.glob("*.mp3"), key=lambda p: p.stat().st_mtime, reverse=True)
        for velho in arquivos[limite:]:
            try:
                velho.unlink()
            except OSError:
                pass


def audio(texto: str, config: dict, voz: str | None = None) -> Path:
    """Devolve o mp3 da fala, gerando só se ainda não estiver no cache."""
    arquivo = caminho_no_cache(texto, config, voz)
    with _trava(arquivo.name):
        if arquivo.exists() and arquivo.stat().st_size > 0:
            try:
                arquivo.touch()
            except OSError:
                pass
            return arquivo
        PASTA_CACHE.mkdir(parents=True, exist_ok=True)
        temporario = arquivo.with_name(f"{arquivo.stem}_{threading.get_ident()}.tmp")
        try:
            sintetizar(texto, temporario, config, voz)
            os.replace(temporario, arquivo)
        except ErroVoz:
            raise
        except Exception as e:
            print(f"[erro] Falha ao gerar a fala: {type(e).__name__}: {e}")
            raise ErroVoz("Não consegui gerar a fala. Confira se o computador da mesa de som está com internet.")
        finally:
            if temporario.exists():
                try:
                    temporario.unlink()
                except OSError:
                    pass
    limpar_cache(int(config["limite_cache"]))
    return arquivo
