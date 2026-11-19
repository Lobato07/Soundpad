"""Soundpad — chamadas por voz nas caixas de som.

Roda no computador ligado à mesa de som. Os outros computadores abrem o
endereço deste PC no navegador e disparam as chamadas.

    python app.py                 # inicia (abre o navegador)
    python app.py --segundo-plano # inicia sem abrir o navegador (início com o Windows)
    python app.py --dispositivos  # lista as saídas de áudio
"""
import os
import queue
import random
import re
import socket
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

import ajustes
from ajustes import (
    EMPACOTADO,
    NOME_PRODUTO,
    PASTA_DADOS,
    PASTA_GRAVACOES,
    PASTA_PROGRAMA,
    VERSAO,
    AjusteInvalido,
)


# No programa instalado não há janela de terminal: o registro vai para um arquivo.
def _redirecionar_registro() -> None:
    if EMPACOTADO or sys.stdout is None:
        PASTA_DADOS.mkdir(parents=True, exist_ok=True)
        arquivo = PASTA_DADOS / "soundpad.log"
        if arquivo.exists() and arquivo.stat().st_size > 1_000_000:
            arquivo.replace(arquivo.with_suffix(".log.old"))
        saida = open(arquivo, "a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stderr = saida


_redirecionar_registro()

from flask import Flask, abort, jsonify, request, send_file, send_from_directory  # noqa: E402

import voz  # noqa: E402
from voz import ErroVoz  # noqa: E402

LIMITE_TEXTO = 40
MAX_PRE_GERADOS = 30  # números por local preparados com antecedência

_config_lock = threading.Lock()
_config = ajustes.carregar()


def cfg() -> dict:
    with _config_lock:
        return _config


def trocar_config(novo: dict) -> None:
    global _config
    ajustes.salvar(novo)
    with _config_lock:
        _config = novo


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
    try:
        for nome in listar_dispositivos():
            if trecho.lower() in nome.lower():
                return nome
    except Exception as e:
        print(f"[aviso] Não consegui listar as saídas de áudio: {e}")
    print(f"[aviso] Saída de áudio '{trecho}' não encontrada; usando a padrão.")
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


def placa_falada(placa: str) -> str:
    """'ABC1D23' -> 'A, B, C, 1, D, 2, 3', para a voz ler letra por letra."""
    return ", ".join(placa)


def texto_local(destino: dict, numero: int | None) -> str:
    nome = destino["nome"].lower()
    if destino["numerado"]:
        return f"{destino['preposicao']} {nome} {numero}"
    return f"{destino['preposicao']} {nome}"


def ler_destino(dados: dict, config: dict) -> tuple[str, str]:
    """Retorna (codigo, texto). Ex.: ('caixa_3', 'ao caixa 3')."""
    destinos = config["destinos"]
    try:
        indice = int(dados.get("destino"))
        destino = destinos[indice]
    except (TypeError, ValueError, IndexError):
        nomes = " ou ".join(d["nome"] for d in destinos)
        raise ErroChamada(f"Escolha {nomes}.")
    base = re.sub(r"[^a-z0-9]+", "_", destino["nome"].lower()).strip("_") or f"local{indice}"
    if not destino["numerado"]:
        return base, texto_local(destino, None)
    try:
        numero = int(str(dados.get("numero", "")).strip())
    except (TypeError, ValueError):
        raise ErroChamada(f"Escolha ou digite o número do {destino['nome'].lower()}.")
    if not 1 <= numero <= destino["quantidade"]:
        raise ErroChamada(
            f"{destino['nome']} {numero} não existe (são {destino['quantidade']})."
        )
    return f"{base}_{numero}", texto_local(destino, numero)


def preencher(frase: str, **valores) -> str:
    for chave, valor in valores.items():
        frase = frase.replace("{" + chave + "}", valor)
    return frase


def montar_chamada(dados: dict, config: dict | None = None) -> dict:
    """Valida o pedido e devolve o que anunciar.

    chave      identifica a chamada na fila (evita repetir a mesma)
    texto      o que aparece na tela
    falado     o que a voz lê (a placa sai letra por letra)
    gravacao   prefixo de uma gravação própria em gravacoes/, se houver
    """
    config = config or cfg()
    tipo = dados.get("tipo")
    tipo_cfg = next((c for c in config["chamadas"] if c["id"] == tipo and c["ativo"]), None)
    if not tipo_cfg:
        raise ErroChamada("Escolha o tipo de chamada.")
    frase, rotulo, modelo = tipo_cfg["frase"], tipo_cfg["rotulo"], tipo_cfg["modelo"]

    if modelo == "grupo":
        codigo, local = ler_destino(dados, config)
        texto = preencher(frase, local=local)
        return {"chave": f"{rotulo.lower()} ({local})", "texto": texto,
                "falado": texto, "gravacao": f"{tipo}_{codigo}"}
    if modelo == "pessoa":
        nome = limpar_texto(dados.get("nome"), "o nome")
        _, local = ler_destino(dados, config)
        texto = preencher(frase, nome=nome, local=local)
        return {"chave": f"{rotulo.lower()} {nome} ({local})", "texto": texto,
                "falado": texto, "gravacao": None}
    if modelo == "veiculo":
        modelo_carro = limpar_texto(dados.get("modelo"), "o modelo do veículo")
        cor = limpar_texto(dados.get("cor"), "a cor")
        placa = limpar_placa(dados.get("placa"))
        return {
            "chave": f"{rotulo.lower()} {placa}",
            "texto": preencher(frase, modelo=modelo_carro, cor=cor, placa=placa),
            "falado": preencher(frase, modelo=modelo_carro, cor=cor, placa=placa_falada(placa)),
            "gravacao": None,
        }
    if modelo == "aviso":
        return {"chave": rotulo.lower(), "texto": frase, "falado": frase, "gravacao": tipo}
    raise ErroChamada("Tipo de chamada inválido.")


# --------------------------------------------------------------------------
# Arquivos de áudio
# --------------------------------------------------------------------------
EXTENSOES = (".mp3", ".wav", ".ogg")


def gravacoes(prefixo: str) -> list[Path]:
    """gravacoes/repositores_caixa_3.mp3, ..._b.mp3 (se houver várias, sorteia).
    O começo do nome é o código da chamada (veja em Ajustes)."""
    achados = []
    for ext in EXTENSOES:
        achados += PASTA_GRAVACOES.glob(f"{prefixo}{ext}")
        achados += PASTA_GRAVACOES.glob(f"{prefixo}_*{ext}")
    return sorted(achados)


def arquivo_da_chamada(chamada: dict) -> Path:
    if chamada["gravacao"]:
        proprias = gravacoes(chamada["gravacao"])
        if proprias:
            return random.choice(proprias)
    try:
        return voz.audio(chamada["falado"], cfg())
    except ErroVoz as e:
        raise ErroChamada(str(e))


_preparos = threading.BoundedSemaphore(3)


def preparar_em_segundo_plano(chamada: dict) -> bool:
    """Gera a fala antes do clique em Chamar, para tocar na hora."""
    config = cfg()
    if chamada["gravacao"] and gravacoes(chamada["gravacao"]):
        return False
    if voz.caminho_no_cache(chamada["falado"], config).exists():
        return False
    if not _preparos.acquire(blocking=False):
        return False

    def _trabalho():
        try:
            voz.audio(chamada["falado"], config)
        except ErroVoz:
            pass  # o clique em Chamar tenta de novo e mostra o erro
        finally:
            _preparos.release()

    threading.Thread(target=_trabalho, daemon=True).start()
    return True


_rodada_pre_geracao = 0


def pre_gerar() -> None:
    """Prepara com antecedência as chamadas que não dependem do que o operador digita
    (grupos e avisos). Depois de prontas, funcionam sem internet."""
    global _rodada_pre_geracao
    _rodada_pre_geracao += 1
    rodada = _rodada_pre_geracao
    config = cfg()
    pedidos = []
    for c in config["chamadas"]:
        if not c["ativo"]:
            continue
        if c["modelo"] == "aviso":
            pedidos.append({"tipo": c["id"]})
        elif c["modelo"] == "grupo":
            for i, d in enumerate(config["destinos"]):
                numeros = range(1, min(d["quantidade"], MAX_PRE_GERADOS) + 1) if d["numerado"] else [None]
                pedidos += [{"tipo": c["id"], "destino": i, "numero": n} for n in numeros]

    def _trabalho():
        time.sleep(2)
        for pedido in pedidos:
            if rodada != _rodada_pre_geracao:
                return  # os ajustes mudaram; começa de novo com os novos
            try:
                chamada = montar_chamada(pedido, config)
                if not gravacoes(chamada["gravacao"]):
                    voz.audio(chamada["falado"], config)
            except (ErroChamada, ErroVoz) as e:
                print(f"[aviso] Pré-geração interrompida: {e}")
                return

    threading.Thread(target=_trabalho, daemon=True).start()


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
        self.reiniciar_saida = threading.Event()
        threading.Thread(target=self._loop, daemon=True).start()

    def ja_pendente(self, chave: str) -> bool:
        with self.lock:
            return chave in self.chaves_pendentes

    def adicionar(self, chave: str, arquivo: Path) -> bool:
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

    def _iniciar_mixer(self, pygame=None):
        import pygame as pg

        if pygame is not None:
            pg.mixer.quit()
        config = cfg()
        dispositivo = achar_dispositivo(config["dispositivo_audio"])
        if dispositivo:
            pg.mixer.init(devicename=dispositivo)
        else:
            pg.mixer.init()
        return pg

    def _loop(self) -> None:
        pygame = None
        try:
            pygame = self._iniciar_mixer()
        except Exception as e:
            print(f"[aviso] Saída de áudio ainda não disponível: {type(e).__name__}: {e}")
        while True:
            chave, arquivo = self.fila.get()
            try:
                if pygame is None or self.reiniciar_saida.is_set():
                    self.reiniciar_saida.clear()
                    pygame = self._iniciar_mixer(pygame)
                with self.lock:
                    self.tocando = chave
                    self.erro = None
                self.parar_agora.clear()
                pygame.mixer.music.set_volume(float(cfg()["volume"]))
                pygame.mixer.music.load(str(arquivo))
                pygame.mixer.music.play()
                while pygame.mixer.music.get_busy():
                    if self.parar_agora.is_set():
                        pygame.mixer.music.stop()
                        break
                    time.sleep(0.05)
                pygame.mixer.music.unload()
                time.sleep(0.4)
            except Exception as e:
                with self.lock:
                    self.erro = f"{type(e).__name__}: {e}"
                print(f"[erro] {self.erro}")
                pygame = None
            finally:
                with self.lock:
                    self.chaves_pendentes.discard(chave)
                    self.tocando = None


# --------------------------------------------------------------------------
# Rede
# --------------------------------------------------------------------------
def enderecos_ip() -> list[str]:
    ips = []
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))  # não envia nada; só descobre a placa de rede
            ips.append(s.getsockname()[0])
    except OSError:
        pass
    try:
        for ip in socket.gethostbyname_ex(socket.gethostname())[2]:
            if ip not in ips and not ip.startswith("127."):
                ips.append(ip)
    except OSError:
        pass
    return ips


# --------------------------------------------------------------------------
# Servidor web
# --------------------------------------------------------------------------
app = Flask(__name__, static_folder=str(PASTA_PROGRAMA / "static"), static_url_path="/static")
app.json.ensure_ascii = False
app.json.sort_keys = False  # mantém a ordem das chamadas e dos locais
tocador = Tocador()


def eh_este_computador() -> bool:
    return request.remote_addr in ("127.0.0.1", "::1", "::ffff:127.0.0.1")


def _negar(codigo: int, mensagem: str, **extra) -> None:
    resposta = jsonify({"ok": False, "mensagem": mensagem, **extra})
    resposta.status_code = codigo
    abort(resposta)


def exigir_admin() -> None:
    if eh_este_computador():
        return
    pin = cfg()["pin"]
    if not pin:
        _negar(403, "Os Ajustes só abrem no computador da mesa de som. "
                    "Para abrir de outro computador, crie uma senha nos Ajustes.")
    if request.headers.get("X-Pin", "") != pin:
        _negar(401, "Senha incorreta.", senha=True)


@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.get("/ajustes")
def pagina_ajustes():
    return send_from_directory(app.static_folder, "ajustes.html")


@app.get("/favicon.ico")
def favicon():
    return send_from_directory(app.static_folder, "icone.png")


@app.get("/api/ping")
def api_ping():
    return jsonify({"produto": NOME_PRODUTO, "versao": VERSAO})


@app.get("/api/config")
def api_config():
    config = cfg()
    return jsonify({
        "nome_local": config["nome_local"],
        "chamadas": [{"tipo": c["id"], "rotulo": c["rotulo"], "modelo": c["modelo"]}
                     for c in config["chamadas"] if c["ativo"]],
        "destinos": [{"nome": d["nome"], "numerado": d["numerado"], "quantidade": d["quantidade"]}
                     for d in config["destinos"]],
        "limite_texto": LIMITE_TEXTO,
        "configurado": config["configurado"],
        "este_computador": eh_este_computador(),
    })


@app.post("/api/previa")
def api_previa():
    try:
        chamada = montar_chamada(request.get_json(silent=True) or {})
    except ErroChamada as e:
        return jsonify({"ok": False, "mensagem": str(e)})
    return jsonify({"ok": True, "texto": chamada["texto"]})


@app.post("/api/preparar")
def api_preparar():
    try:
        chamada = montar_chamada(request.get_json(silent=True) or {})
    except ErroChamada:
        return jsonify({"ok": False})
    return jsonify({"ok": True, "iniciado": preparar_em_segundo_plano(chamada)})


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


# ---------------------------------------------------------------- Ajustes
@app.get("/api/ajustes")
def api_ajustes_ler():
    exigir_admin()
    porta = cfg()["porta"]
    return jsonify({
        "ok": True,
        "ajustes": ajustes.publico(cfg()),
        "enderecos": [f"http://{ip}:{porta}" for ip in enderecos_ip()],
        "pasta_dados": str(PASTA_DADOS),
        "versao": VERSAO,
        "instalado": EMPACOTADO,
        "preposicoes": ajustes.PREPOSICOES,
        "modelos": ajustes.MODELOS,
        "frases_exemplo": ajustes.FRASES_EXEMPLO,
        "limite_chamadas": ajustes.LIMITE_CHAMADAS,
    })


@app.post("/api/ajustes")
def api_ajustes_salvar():
    exigir_admin()
    antes = cfg()
    try:
        novo = ajustes.validar(request.get_json(silent=True) or {}, antes)
    except (AjusteInvalido, ValueError, TypeError) as e:
        return jsonify({"ok": False, "mensagem": str(e) or "Valor inválido."}), 400
    trocar_config(novo)
    if novo["dispositivo_audio"] != antes["dispositivo_audio"]:
        tocador.reiniciar_saida.set()
    pre_gerar()
    aviso = ""
    if novo["porta"] != antes["porta"]:
        aviso = " Reinicie o Soundpad para usar a nova porta."
    return jsonify({"ok": True, "mensagem": "Ajustes salvos." + aviso})


@app.get("/api/dispositivos")
def api_dispositivos():
    exigir_admin()
    try:
        return jsonify({"ok": True, "dispositivos": listar_dispositivos()})
    except Exception as e:
        return jsonify({"ok": False, "dispositivos": [], "mensagem": str(e)})


@app.get("/api/vozes")
def api_vozes():
    exigir_admin()
    config = dict(cfg())
    if request.args.get("motor") in ("edge", "azure"):
        config["motor_voz"] = request.args["motor"]
    return jsonify({"ok": True, "vozes": voz.listar_vozes(config)})


def _config_de_teste() -> dict:
    """Config atual com a voz/velocidade que estão na tela (ainda não salvas)."""
    config = dict(cfg())
    dados = request.get_json(silent=True) or {}
    for campo in ("voz", "motor_voz", "azure_regiao"):
        if dados.get(campo):
            config[campo] = str(dados[campo])
    if dados.get("azure_chave"):
        config["azure_chave"] = str(dados["azure_chave"])
    if "velocidade" in dados:
        config["velocidade"] = int(dados["velocidade"])
    return config


def _frase_de_teste(config: dict) -> str:
    destino = config["destinos"][0]
    local = texto_local(destino, 1 if destino["numerado"] else None)
    pessoa = next((c for c in config["chamadas"] if c["modelo"] == "pessoa"), None)
    frase = pessoa["frase"] if pessoa else ajustes.FRASES_EXEMPLO["pessoa"]
    return preencher(frase, nome="Carlos", local=local)


@app.post("/api/amostra")
def api_amostra():
    """Gera uma amostra e devolve o mp3 para ouvir no navegador."""
    exigir_admin()
    config = _config_de_teste()
    try:
        arquivo = voz.audio(_frase_de_teste(config), config, config["voz"])
    except ErroVoz as e:
        return jsonify({"ok": False, "mensagem": str(e)}), 400
    return send_file(arquivo, mimetype="audio/mpeg")


@app.post("/api/testar-som")
def api_testar_som():
    """Toca uma amostra nas caixas de som da loja."""
    exigir_admin()
    config = _config_de_teste()
    try:
        arquivo = voz.audio(_frase_de_teste(config), config, config["voz"])
    except ErroVoz as e:
        return jsonify({"ok": False, "mensagem": str(e)}), 400
    tocador.adicionar("teste de som", arquivo)
    return jsonify({"ok": True, "mensagem": "Tocando o teste nas caixas de som…"})


@app.post("/api/encerrar")
def api_encerrar():
    exigir_admin()
    threading.Timer(0.5, lambda: os._exit(0)).start()
    return jsonify({"ok": True, "mensagem": "Soundpad encerrado."})


# --------------------------------------------------------------------------
# Inicialização
# --------------------------------------------------------------------------
def ja_rodando(porta: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{porta}/api/ping", timeout=1.5) as r:
            return NOME_PRODUTO.encode() in r.read()
    except Exception:
        return False


def porta_livre(porta: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("0.0.0.0", porta))
            return True
        except OSError:
            return False


def avisar(mensagem: str) -> None:
    print(f"[erro] {mensagem}")
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(None, mensagem, NOME_PRODUTO, 0x10)
        except Exception:
            pass


def main() -> None:
    if "--dispositivos" in sys.argv:
        print("Saídas de áudio disponíveis:")
        for nome in listar_dispositivos():
            print(f"  - {nome}")
        return

    config = cfg()
    porta = int(os.environ.get("PORT", config["porta"]))
    abrir_navegador = "--segundo-plano" not in sys.argv
    pagina = f"http://localhost:{porta}/" + ("" if config["configurado"] else "ajustes")

    if ja_rodando(porta):
        # Clicou no atalho com o Soundpad já aberto: só abre a página.
        if abrir_navegador:
            webbrowser.open(pagina)
        return
    if not porta_livre(porta):
        avisar(f"A porta {porta} já está sendo usada por outro programa.\n"
               f"Mude \"porta\" em {ajustes.ARQUIVO_CONFIG} e abra o Soundpad de novo.")
        sys.exit(1)

    PASTA_DADOS.mkdir(parents=True, exist_ok=True)
    PASTA_GRAVACOES.mkdir(exist_ok=True)
    print(f"{NOME_PRODUTO} {VERSAO} rodando na porta {porta}. Dados em: {PASTA_DADOS}")
    for ip in enderecos_ip():
        print(f"  Nos outros computadores, abra: http://{ip}:{porta}")
    if abrir_navegador:
        threading.Timer(1.2, lambda: webbrowser.open(pagina)).start()
    pre_gerar()

    from werkzeug.serving import run_simple

    run_simple("0.0.0.0", porta, app, threaded=True, use_reloader=False)


if __name__ == "__main__":
    main()
