"""Configuração do Soundpad.

Tudo o que o cliente pode mudar fica em config.json, editado pela página
de Ajustes (http://localhost:5000/ajustes). Ninguém precisa abrir arquivos.

Onde ficam os dados:
- Programa instalado (Setup.exe): %APPDATA%\\Soundpad
- Rodando pelo código (python app.py): a própria pasta do projeto
"""
import copy
import json
import os
import re
import unicodedata
import sys
import threading
from pathlib import Path

NOME_PRODUTO = "Soundpad"
VERSAO = "2.0"

EMPACOTADO = getattr(sys, "frozen", False)
# Arquivos do programa (página, ícone). No .exe ficam dentro do pacote.
PASTA_PROGRAMA = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))


def _pasta_dados() -> Path:
    if os.environ.get("SOUNDPAD_DADOS"):
        return Path(os.environ["SOUNDPAD_DADOS"])
    if EMPACOTADO:
        base = os.environ.get("APPDATA") or str(Path.home())
        return Path(base) / NOME_PRODUTO
    return Path(__file__).resolve().parent


PASTA_DADOS = _pasta_dados()
ARQUIVO_CONFIG = PASTA_DADOS / "config.json"
PASTA_CACHE = PASTA_DADOS / "audios" / "cache"
# Gravações próprias (opcional). Ex.: gravacoes/repositores_caixa_3.mp3
PASTA_GRAVACOES = PASTA_DADOS / "gravacoes"

PREPOSICOES = ["ao", "à", "no", "na"]
LIMITE_QUANTIDADE = 999

FRASES_EXEMPLO = {
    "grupo": "Atenção repositores, favor comparecerem {local}. "
    "Repositores favor comparecerem {local}.",
    "pessoa": "Atenção vendedor {nome}, favor comparecer {local}. "
    "Vendedor {nome}, favor comparecer {local}.",
    "veiculo": "Atenção proprietário do veículo {modelo}, de cor {cor}, placa {placa}, "
    "favor comparecer ao estacionamento. Atenção proprietário do veículo {modelo}, "
    "de cor {cor}, placa {placa}, favor comparecer ao estacionamento.",
    "aviso": "Atenção, senhores clientes. Nossa loja fechará em quinze minutos.",
}

MODELOS = {
    "grupo": {"nome": "Grupo para um local", "campos": ["{local}"]},
    "pessoa": {"nome": "Pessoa pelo nome", "campos": ["{nome}", "{local}"]},
    "veiculo": {"nome": "Veículo", "campos": ["{modelo}", "{cor}", "{placa}"]},
    "aviso": {"nome": "Aviso fixo", "campos": []},
}
LIMITE_CHAMADAS = 12

PADRAO = {
    "nome_local": "Soundpad",
    "porta": 5000,
    # Locais para onde as pessoas são chamadas.
    # numerado=True mostra os números (Caixa 1, 2, 3...).
    "destinos": [
        {"nome": "Caixa", "preposicao": "ao", "numerado": True, "quantidade": 5},
        {"nome": "Pacote", "preposicao": "ao", "numerado": False, "quantidade": 0},
    ],
    # Tipos de chamada. "modelo" define os campos que o operador preenche:
    #   grupo   -> escolhe o local                 frase com {local}
    #   pessoa  -> digita o nome e escolhe o local frase com {nome} e {local}
    #   veiculo -> digita modelo, cor e placa      frase com {modelo}, {cor} e {placa}
    #   aviso   -> nada a preencher                frase fixa
    "chamadas": [
        {"id": "repositores", "rotulo": "Repositores", "modelo": "grupo", "ativo": True,
         "frase": FRASES_EXEMPLO["grupo"]},
        {"id": "vendedor", "rotulo": "Vendedor", "modelo": "pessoa", "ativo": True,
         "frase": FRASES_EXEMPLO["pessoa"]},
        {"id": "veiculo", "rotulo": "Veículo", "modelo": "veiculo", "ativo": True,
         "frase": FRASES_EXEMPLO["veiculo"]},
    ],
    "dispositivo_audio": "",
    "volume": 1.0,
    # edge  = vozes neurais gratuitas da Microsoft (serviço não oficial)
    # azure = Azure Speech, oficial e pago por uso (precisa de chave)
    "motor_voz": "edge",
    "voz": "pt-BR-ThalitaMultilingualNeural",
    "voz_reserva": "pt-BR-FranciscaNeural",
    "velocidade": -10,  # em %: -10 = 10% mais devagar
    "azure_chave": "",
    "azure_regiao": "brazilsouth",
    "limite_cache": 400,
    # Senha para abrir os Ajustes a partir de outro computador.
    # No próprio computador da mesa de som os Ajustes abrem sem senha.
    "pin": "",
    "configurado": False,
}

_lock = threading.Lock()


def _mesclar(base: dict, extra: dict) -> dict:
    saida = copy.deepcopy(base)
    for chave, valor in extra.items():
        if isinstance(valor, dict) and isinstance(saida.get(chave), dict):
            saida[chave] = _mesclar(saida[chave], valor)
        else:
            saida[chave] = valor
    return saida


def _migrar(dados: dict) -> dict:
    """Aceita o config.json da versão anterior."""
    if isinstance(dados.get("velocidade"), str):
        try:
            dados["velocidade"] = int(dados["velocidade"].strip().rstrip("%"))
        except ValueError:
            dados.pop("velocidade")
    if "numero_de_caixas" in dados and "destinos" not in dados:
        destinos = copy.deepcopy(PADRAO["destinos"])
        destinos[0]["quantidade"] = int(dados["numero_de_caixas"])
        dados["destinos"] = destinos
        dados["configurado"] = True  # já estava em uso
    if "chamadas" not in dados and ("abas" in dados or "frases" in dados):
        abas, frases = dados.get("abas", {}), dados.get("frases", {})
        chamadas = copy.deepcopy(PADRAO["chamadas"])
        for c in chamadas:
            c.update({k: v for k, v in abas.get(c["id"], {}).items() if k in ("ativo", "rotulo")})
            if frases.get(c["id"]):
                c["frase"] = frases[c["id"]]
        dados["chamadas"] = chamadas
    for antiga in ("numero_de_caixas", "pasta_audios", "abas", "frases"):
        dados.pop(antiga, None)
    return dados


def carregar() -> dict:
    with _lock:
        if ARQUIVO_CONFIG.exists():
            try:
                dados = json.loads(ARQUIVO_CONFIG.read_text(encoding="utf-8"))
            except (ValueError, OSError) as e:
                print(f"[aviso] config.json ilegível ({e}); usando o padrão.")
                dados = {}
        else:
            dados = {}
        return _mesclar(PADRAO, _migrar(dados))


def salvar(config: dict) -> None:
    with _lock:
        PASTA_DADOS.mkdir(parents=True, exist_ok=True)
        temporario = ARQUIVO_CONFIG.with_suffix(".tmp")
        temporario.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(temporario, ARQUIVO_CONFIG)


def _sem_acento(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")


class AjusteInvalido(Exception):
    pass


def _texto(valor, campo: str, maximo: int = 40, vazio_ok: bool = False) -> str:
    texto = " ".join(str(valor or "").split())
    if not texto and not vazio_ok:
        raise AjusteInvalido(f"Preencha {campo}.")
    if len(texto) > maximo:
        raise AjusteInvalido(f"{campo.capitalize()}: máximo de {maximo} letras.")
    return texto


def validar(novo: dict, atual: dict) -> dict:
    """Confere o que veio da página de Ajustes e devolve o config completo."""
    cfg = copy.deepcopy(atual)

    if "nome_local" in novo:
        cfg["nome_local"] = _texto(novo["nome_local"], "o nome do local", 50)

    if "destinos" in novo:
        destinos = []
        for d in novo["destinos"]:
            nome = _texto(d.get("nome"), "o nome do local", 30)
            prep = d.get("preposicao", "ao")
            if prep not in PREPOSICOES:
                raise AjusteInvalido(f"Preposição inválida em {nome}.")
            numerado = bool(d.get("numerado"))
            try:
                quantidade = int(d.get("quantidade") or 0)
            except (TypeError, ValueError):
                raise AjusteInvalido(f"Quantidade inválida em {nome}.")
            if numerado and not 1 <= quantidade <= LIMITE_QUANTIDADE:
                raise AjusteInvalido(f"{nome}: a quantidade deve ser de 1 a {LIMITE_QUANTIDADE}.")
            destinos.append(
                {"nome": nome, "preposicao": prep, "numerado": numerado,
                 "quantidade": quantidade if numerado else 0}
            )
        if not destinos:
            raise AjusteInvalido("Cadastre pelo menos um local (ex.: Caixa).")
        if len({d["nome"].lower() for d in destinos}) != len(destinos):
            raise AjusteInvalido("Há dois locais com o mesmo nome.")
        cfg["destinos"] = destinos

    if "chamadas" in novo:
        chamadas, ids = [], set()
        for c in novo["chamadas"]:
            rotulo = _texto(c.get("rotulo"), "o nome da chamada", 20)
            modelo = c.get("modelo")
            if modelo not in MODELOS:
                raise AjusteInvalido(f"Escolha o tipo da chamada {rotulo}.")
            frase = _texto(c.get("frase"), f"a frase de {rotulo}", 400)
            faltando = [x for x in MODELOS[modelo]["campos"] if x not in frase]
            if faltando:
                raise AjusteInvalido(f"A frase de {rotulo} precisa ter {', '.join(faltando)}.")
            if modelo == "aviso" and re.search(r"\{\w+\}", frase):
                raise AjusteInvalido(f"{rotulo} é um aviso fixo: a frase não pode ter palavras entre chaves.")
            ident = re.sub(r"[^a-z0-9_]", "", str(c.get("id") or "").lower())
            if not ident or ident in ids:
                base = re.sub(r"[^a-z0-9]+", "_", _sem_acento(rotulo).lower()).strip("_") or "chamada"
                ident, n = base, 2
                while ident in ids:
                    ident, n = f"{base}_{n}", n + 1
            ids.add(ident)
            chamadas.append({"id": ident, "rotulo": rotulo, "modelo": modelo,
                             "ativo": bool(c.get("ativo", True)), "frase": frase})
        if not any(c["ativo"] for c in chamadas):
            raise AjusteInvalido("Deixe pelo menos uma chamada ativa.")
        if len(chamadas) > LIMITE_CHAMADAS:
            raise AjusteInvalido(f"Máximo de {LIMITE_CHAMADAS} chamadas.")
        if len({c["rotulo"].lower() for c in chamadas}) != len(chamadas):
            raise AjusteInvalido("Há duas chamadas com o mesmo nome.")
        cfg["chamadas"] = chamadas

    if "dispositivo_audio" in novo:
        cfg["dispositivo_audio"] = str(novo["dispositivo_audio"] or "")
    if "volume" in novo:
        cfg["volume"] = min(1.0, max(0.05, float(novo["volume"])))

    if "motor_voz" in novo:
        if novo["motor_voz"] not in ("edge", "azure"):
            raise AjusteInvalido("Motor de voz inválido.")
        cfg["motor_voz"] = novo["motor_voz"]
    if "voz" in novo:
        cfg["voz"] = _texto(novo["voz"], "a voz", 80)
    if "velocidade" in novo:
        cfg["velocidade"] = min(30, max(-40, int(novo["velocidade"])))
    if "azure_regiao" in novo:
        cfg["azure_regiao"] = _texto(novo["azure_regiao"], "a região", 40, vazio_ok=True)
    if novo.get("azure_chave"):  # vazio = manter a chave atual
        cfg["azure_chave"] = _texto(novo["azure_chave"], "a chave", 200)
    if cfg["motor_voz"] == "azure" and not cfg["azure_chave"]:
        raise AjusteInvalido("Para usar o Azure, informe a chave.")

    if "pin" in novo and novo["pin"] is not None:
        pin = str(novo["pin"]).strip()
        if pin and not (pin.isdigit() and 4 <= len(pin) <= 8):
            raise AjusteInvalido("A senha deve ter de 4 a 8 números.")
        cfg["pin"] = pin

    cfg["configurado"] = True
    return cfg


def publico(config: dict) -> dict:
    """Versão para mandar ao navegador (sem chave nem senha)."""
    saida = copy.deepcopy(config)
    saida["azure_chave_definida"] = bool(saida.pop("azure_chave", ""))
    saida["pin_definido"] = bool(saida.pop("pin", ""))
    return saida
