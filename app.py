"""Soundpad da loja.

Roda no computador ligado à mesa de som. Os outros computadores da loja
abrem o endereço deste PC no navegador e disparam as chamadas.

Uso:
    python app.py                 # inicia o servidor
    python app.py --dispositivos  # lista as saídas de áudio disponíveis
"""
import asyncio
import hashlib
import json
import os
import queue
import random
import re
import sys
import threading
import time
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

from frases import (
    frase_repositores,
    frase_vendedor,
    frase_veiculo,
    nome_destino,
    placa_falada,
)

BASE = Path(__file__).resolve().parent

CONFIG_PADRAO = {
    "porta": 5000,
    "numero_de_caixas": 5,
    "pasta_audios": "audios",
    # Nome (ou parte do nome) da saída de áudio ligada à mesa de som.
    # Vazio = saída padrão do sistema. Veja os nomes com: python app.py --dispositivos
    "dispositivo_audio": "",
    "volume": 1.0,
    # Voz usada nas falas geradas (edge-tts). Para ouvir as opções:
    #   python gerar_falas.py --amostras
    "voz": "pt-BR-ThalitaMultilingualNeural",
    # Usada se a voz principal falhar (ex.: nome errado no config).
    "voz_reserva": "pt-BR-FranciscaNeural",
    # Velocidade da fala: "-10%" = 10% mais devagar, "+0%" = normal.
    "velocidade": "-10%",
    # Quantas falas geradas guardar em audios/cache (as mais antigas são apagadas).
    "limite_cache": 300,
}
EXTENSOES = (".mp3", ".wav", ".ogg")
LIMITE_TEXTO = 40


def carregar_config() -> dict:
    config = dict(CONFIG_PADRAO)
    arquivo = BASE / "config.json"
    if arquivo.exists():
        config.update(json.loads(arquivo.read_text(encoding="utf-8")))
    return config


CONFIG = carregar_config()
PASTA_AUDIOS = (BASE / CONFIG["pasta_audios"]).resolve()
PASTA_CACHE = PASTA_AUDIOS / "cache"


# --------------------------------------------------------------------------
# Saída de áudio
# --------------------------------------------------------------------------
def listar_dispositivos() -> list[str]:
    import pygame
    from pygame._sdl2 import audio

    pygame.init()
    return list(audio.get_audio_device_names(False))


def achar_dispositivo(trecho: str) -> str | None:
    if not trecho:
        return None
    for nome in listar_dispositivos():
        if trecho.lower() in nome.lower():
            return nome
    print(f"[aviso] Dispositivo de áudio '{trecho}' não encontrado; usando o padrão.")
    return None


# --------------------------------------------------------------------------
# Montagem das chamadas
# --------------------------------------------------------------------------
class ErroChamada(Exception):
    pass


def limpar_texto(valor, campo: str) -> str:
    texto = re.sub(r"[\x00-\x1f\x7f<>{}\[\]\\]", " ", str(valor or ""))
    texto = re.sub(r"\s+", " ", texto).strip(" ,.;")
    if not texto:
        raise ErroChamada(f"Preencha {campo}.")
    if len(texto) > LIMITE_TEXTO:
        raise ErroChamada(f"Texto muito longo (máximo {LIMITE_TEXTO} letras).")
    return texto


def limpar_placa(valor) -> str:
    placa = re.sub(r"[^A-Za-z0-9]", "", str(valor or "")).upper()
    if not placa:
        raise ErroChamada("Preencha a placa.")
    if len(placa) != 7:
        raise ErroChamada("A placa deve ter 7 letras e números (ex.: ABC1D23).")
    return placa


def ler_destino(dados: dict) -> tuple[str, str]:
    """Retorna (codigo, texto). Ex.: ('caixa_3', 'caixa 3') ou ('pacote', 'pacote')."""
    destino = dados.get("destino")
    if destino == "pacote":
        return "pacote", nome_destino("pacote")
    if destino == "caixa":
        try:
            numero = int(dados.get("numero"))
        except (TypeError, ValueError):
            raise ErroChamada("Escolha o número do caixa.")
        if not 1 <= numero <= int(CONFIG["numero_de_caixas"]):
            raise ErroChamada("Caixa inexistente.")
        return f"caixa_{numero}", nome_destino("caixa", numero)
    raise ErroChamada("Escolha Caixa ou Pacote.")


def montar_chamada(dados: dict) -> dict:
    """Valida o pedido e devolve o que anunciar.

    chave      identifica a chamada na fila (evita repetir a mesma)
    texto      o que aparece na tela
    falado     o que a voz lê (a placa sai letra por letra)
    fixo       prefixo de um áudio gravado em audios/, se houver
    """
    tipo = dados.get("tipo")
    if tipo == "repositores":
        codigo, destino = ler_destino(dados)
        texto = frase_repositores(destino)
        return {
            "chave": f"repositores ({destino})",
            "texto": texto,
            "falado": texto,
            "fixo": f"repositores_{codigo}",
        }
    if tipo == "vendedor":
        nome = limpar_texto(dados.get("nome"), "o nome do vendedor")
        _, destino = ler_destino(dados)
        texto = frase_vendedor(nome, destino)
        return {
            "chave": f"vendedor {nome} ({destino})",
            "texto": texto,
            "falado": texto,
            "fixo": None,
        }
    if tipo == "veiculo":
        modelo = limpar_texto(dados.get("modelo"), "o modelo do veículo")
        cor = limpar_texto(dados.get("cor"), "a cor")
        placa = limpar_placa(dados.get("placa"))
        return {
            "chave": f"veículo {placa}",
            "texto": frase_veiculo(modelo, cor, placa),
            "falado": frase_veiculo(modelo, cor, placa_falada(placa)),
            "fixo": None,
        }
    raise ErroChamada("Tipo de chamada inválido.")


# --------------------------------------------------------------------------
# Arquivos de áudio (gravados ou gerados na hora)
# --------------------------------------------------------------------------
def arquivos_fixos(prefixo: str) -> list[Path]:
    """repositores_caixa_3.mp3, repositores_caixa_3_b.mp3 ... (sorteia se houver vários)."""
    achados = []
    for ext in EXTENSOES:
        achados += PASTA_AUDIOS.glob(f"{prefixo}{ext}")
        achados += PASTA_AUDIOS.glob(f"{prefixo}_*{ext}")
    return sorted(achados)


_lock_geracao = threading.Lock()


def sintetizar(texto: str, destino: Path, voz: str, velocidade: str) -> None:
    """Gera a fala com a voz neural (precisa de internet)."""
    import edge_tts

    async def _gerar():
        await edge_tts.Communicate(texto, voz, rate=velocidade).save(str(destino))

    asyncio.run(asyncio.wait_for(_gerar(), timeout=25))


def sintetizar_com_reserva(texto: str, destino: Path) -> None:
    vozes = [CONFIG["voz"]]
    if CONFIG.get("voz_reserva") and CONFIG["voz_reserva"] != CONFIG["voz"]:
        vozes.append(CONFIG["voz_reserva"])
    ultimo_erro = None
    for voz in vozes:
        try:
            sintetizar(texto, destino, voz, CONFIG["velocidade"])
            if destino.exists() and destino.stat().st_size > 0:
                return
            ultimo_erro = RuntimeError("a voz não retornou áudio")
        except ImportError:
            raise
        except Exception as e:
            ultimo_erro = e
        print(f"[aviso] Voz '{voz}' falhou: {type(ultimo_erro).__name__}: {ultimo_erro}")
    raise ultimo_erro


def limpar_cache() -> None:
    arquivos = sorted(PASTA_CACHE.glob("*.mp3"), key=lambda p: p.stat().st_mtime, reverse=True)
    for velho in arquivos[int(CONFIG["limite_cache"]):]:
        try:
            velho.unlink()
        except OSError:
            pass


def audio_gerado(texto: str) -> Path:
    chave = f"{CONFIG['voz']}|{CONFIG['velocidade']}|{texto}"
    nome = hashlib.sha1(chave.encode("utf-8")).hexdigest()[:20]
    arquivo = PASTA_CACHE / f"{nome}.mp3"
    with _lock_geracao:
        if arquivo.exists() and arquivo.stat().st_size > 0:
            arquivo.touch()  # marca como usado recentemente
            return arquivo
        PASTA_CACHE.mkdir(parents=True, exist_ok=True)
        temporario = arquivo.with_suffix(".tmp")
        try:
            sintetizar_com_reserva(texto, temporario)
            os.replace(temporario, arquivo)
        except ImportError:
            raise ErroChamada("Falta o pacote edge-tts. Rode: pip install -r requirements.txt")
        except Exception as e:
            print(f"[erro] Falha ao gerar a fala: {type(e).__name__}: {e}")
            raise ErroChamada(
                "Não consegui gerar a fala. Confira se o computador da mesa de som está com internet."
            )
        finally:
            if temporario.exists():
                try:
                    temporario.unlink()
                except OSError:
                    pass
        limpar_cache()
    return arquivo


def arquivo_da_chamada(chamada: dict) -> Path:
    if chamada["fixo"]:
        fixos = arquivos_fixos(chamada["fixo"])
        if fixos:
            return random.choice(fixos)
    return audio_gerado(chamada["falado"])


# --------------------------------------------------------------------------
# Fila de reprodução
# --------------------------------------------------------------------------
class Tocador:
    """Toca as chamadas uma de cada vez, em ordem, sem cortar a anterior."""

    def __init__(self) -> None:
        self.fila: "queue.Queue[tuple[str, Path]]" = queue.Queue()
        self.chaves_pendentes: set[str] = set()
        self.tocando: str | None = None
        self.erro: str | None = None
        self.lock = threading.Lock()
        self.parar_agora = threading.Event()
        threading.Thread(target=self._loop, daemon=True).start()

    def ja_pendente(self, chave: str) -> bool:
        with self.lock:
            return chave in self.chaves_pendentes

    def adicionar(self, chave: str, arquivo: Path) -> bool:
        """Retorna False se a mesma chamada já está tocando ou na fila."""
        with self.lock:
            if chave in self.chaves_pendentes:
                return False
            self.chaves_pendentes.add(chave)
        self.fila.put((chave, arquivo))
        return True

    def parar(self) -> None:
        with self.lock:
            while not self.fila.empty():
                try:
                    self.fila.get_nowait()
                except queue.Empty:
                    break
            self.chaves_pendentes.clear()
        self.parar_agora.set()

    def estado(self) -> dict:
        with self.lock:
            return {
                "tocando": self.tocando,
                "na_fila": sorted(self.chaves_pendentes - {self.tocando}),
                "erro": self.erro,
            }

    def _iniciar_mixer(self):
        import pygame

        dispositivo = achar_dispositivo(CONFIG["dispositivo_audio"])
        if dispositivo:
            pygame.mixer.init(devicename=dispositivo)
        else:
            pygame.mixer.init()
        pygame.mixer.music.set_volume(float(CONFIG["volume"]))
        return pygame

    def _loop(self) -> None:
        pygame = None
        while True:
            chave, arquivo = self.fila.get()
            try:
                if pygame is None:
                    pygame = self._iniciar_mixer()
                with self.lock:
                    self.tocando = chave
                    self.erro = None
                self.parar_agora.clear()
                pygame.mixer.music.load(str(arquivo))
                pygame.mixer.music.play()
                while pygame.mixer.music.get_busy():
                    if self.parar_agora.is_set():
                        pygame.mixer.music.stop()
                        break
                    time.sleep(0.05)
                pygame.mixer.music.unload()  # libera o arquivo (o cache pode apagá-lo)
                time.sleep(0.4)  # pequena pausa entre chamadas
            except Exception as e:  # sem placa de som, arquivo corrompido etc.
                with self.lock:
                    self.erro = f"{type(e).__name__}: {e}"
                print(f"[erro] {self.erro}")
            finally:
                with self.lock:
                    self.chaves_pendentes.discard(chave)
                    self.tocando = None


app = Flask(__name__, static_folder=str(BASE / "static"), static_url_path="/static")
tocador = Tocador()


@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.get("/api/config")
def api_config():
    n = int(CONFIG["numero_de_caixas"])
    return jsonify({"caixas": list(range(1, n + 1)), "limite_texto": LIMITE_TEXTO})


@app.post("/api/previa")
def api_previa():
    """Mostra a frase que será anunciada, sem tocar nada."""
    try:
        chamada = montar_chamada(request.get_json(silent=True) or {})
    except ErroChamada as e:
        return jsonify({"ok": False, "mensagem": str(e)})
    return jsonify({"ok": True, "texto": chamada["texto"]})


@app.get("/api/status")
def api_status():
    return jsonify(tocador.estado())


@app.post("/api/chamar")
def api_chamar():
    try:
        chamada = montar_chamada(request.get_json(silent=True) or {})
        chave = chamada["chave"]
        if tocador.ja_pendente(chave):
            return jsonify({"ok": True, "mensagem": f"'{chave}' já está tocando ou na fila."})
        arquivo = arquivo_da_chamada(chamada)
    except ErroChamada as e:
        return jsonify({"ok": False, "mensagem": str(e)}), 400

    if not tocador.adicionar(chave, arquivo):
        return jsonify({"ok": True, "mensagem": f"'{chave}' já está tocando ou na fila."})
    return jsonify({"ok": True, "mensagem": f"Chamando {chave}…"})


@app.post("/api/parar")
def api_parar():
    tocador.parar()
    return jsonify({"ok": True, "mensagem": "Áudio interrompido."})


if __name__ == "__main__":
    if "--dispositivos" in sys.argv:
        print("Saídas de áudio disponíveis:")
        for nome in listar_dispositivos():
            print(f"  - {nome}")
        sys.exit(0)

    PASTA_AUDIOS.mkdir(exist_ok=True)
    porta = int(os.environ.get("PORT", CONFIG["porta"]))
    print(f"Soundpad rodando na porta {porta}. Pasta de áudios: {PASTA_AUDIOS}")
    app.run(host="0.0.0.0", port=porta, threaded=True)
