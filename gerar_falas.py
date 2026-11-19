"""Gera os áudios fixos das chamadas de repositores na pasta audios/.

    python gerar_falas.py                  # voz neural pt-BR (precisa de internet só agora)
    python gerar_falas.py --motor offline  # voz do próprio sistema (sem internet)
    python gerar_falas.py --voz pt-BR-AntonioNeural
    python gerar_falas.py --amostras       # gera uma amostra de cada voz pt-BR para ouvir

Com esses arquivos prontos, as chamadas de repositores funcionam mesmo sem
internet. As chamadas de vendedor e de veículo mudam a cada vez (nome, placa...),
por isso são geradas na hora pelo app e precisam de internet.

Para usar a própria voz, grave arquivos com os nomes
repositores_caixa_1.mp3 ... repositores_caixa_5.mp3 e repositores_pacote.mp3
(também aceita .wav e .ogg).
"""
import argparse
import asyncio
import json
import sys
from pathlib import Path

from frases import frase_repositores, nome_destino

BASE = Path(__file__).resolve().parent


def ler_config() -> dict:
    config = {
        "numero_de_caixas": 5,
        "pasta_audios": "audios",
        "voz": "pt-BR-ThalitaMultilingualNeural",
        "voz_reserva": "pt-BR-FranciscaNeural",
        "velocidade": "-10%",
    }
    arquivo = BASE / "config.json"
    if arquivo.exists():
        config.update(json.loads(arquivo.read_text(encoding="utf-8")))
    return config


CONFIG = ler_config()
PASTA = BASE / CONFIG["pasta_audios"]


def itens():
    for n in range(1, int(CONFIG["numero_de_caixas"]) + 1):
        yield f"repositores_caixa_{n}", frase_repositores(nome_destino("caixa", n))
    yield "repositores_pacote", frase_repositores(nome_destino("pacote"))


FRASE_AMOSTRA = (
    "Atenção vendedor Carlos, favor comparecer ao caixa 3. "
    "Atenção proprietário do veículo Fiat Uno, de cor prata, placa A, B, C, 1, D, 2, 3, "
    "favor comparecer ao estacionamento."
)


def gerar_edge(voz: str, velocidade: str) -> None:
    import edge_tts

    async def _salvar(texto, destino, voz_usada):
        await edge_tts.Communicate(texto, voz_usada, rate=velocidade).save(str(destino))

    async def _tudo():
        reserva = CONFIG.get("voz_reserva")
        for nome, texto in itens():
            destino = PASTA / f"{nome}.mp3"
            try:
                await _salvar(texto, destino, voz)
            except Exception as e:
                if not reserva or reserva == voz:
                    raise
                print(f"  [aviso] voz '{voz}' falhou ({type(e).__name__}); usando {reserva}")
                await _salvar(texto, destino, reserva)
            print(f"  ok  {destino.name}")

    asyncio.run(_tudo())


def gerar_amostras(velocidade: str) -> None:
    import edge_tts

    pasta = PASTA / "amostras"
    pasta.mkdir(parents=True, exist_ok=True)

    async def _tudo():
        vozes = [v for v in await edge_tts.list_voices() if v["Locale"] == "pt-BR"]
        for v in vozes:
            destino = pasta / f"{v['ShortName']}.mp3"
            try:
                await edge_tts.Communicate(FRASE_AMOSTRA, v["ShortName"], rate=velocidade).save(str(destino))
                print(f"  ok  {destino.name}  ({v.get('Gender', '')})")
            except Exception as e:
                print(f"  --  {v['ShortName']} falhou: {type(e).__name__}")

    asyncio.run(_tudo())
    print(f"\nOuça os arquivos em {pasta}")
    print('Escolha uma e coloque o nome (sem .mp3) em "voz" no config.json.')


def gerar_offline(voz: str | None) -> None:
    import pyttsx3

    motor = pyttsx3.init()
    if voz:
        motor.setProperty("voice", voz)
    else:
        for v in motor.getProperty("voices"):
            idiomas = " ".join(str(l) for l in getattr(v, "languages", []))
            if "pt" in v.id.lower() or "portug" in v.name.lower() or "pt" in idiomas.lower():
                motor.setProperty("voice", v.id)
                break
    motor.setProperty("rate", 150)
    for nome, texto in itens():
        destino = PASTA / f"{nome}.wav"
        motor.save_to_file(texto, str(destino))
        print(f"  ok  {destino.name}")
    motor.runAndWait()


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--motor", choices=["edge", "offline"], default="edge")
    p.add_argument("--voz", default=None, help=f"nome da voz (padrão: {CONFIG['voz']})")
    p.add_argument("--velocidade", default=CONFIG["velocidade"], help="ex.: -10%% (mais devagar)")
    p.add_argument("--amostras", action="store_true", help="gera uma amostra de cada voz pt-BR")
    args = p.parse_args()

    PASTA.mkdir(exist_ok=True)
    try:
        if args.amostras:
            print("Gerando amostras das vozes pt-BR ...")
            gerar_amostras(args.velocidade)
            return
        print(f"Gerando áudios em {PASTA} ...")
        if args.motor == "edge":
            gerar_edge(args.voz or CONFIG["voz"], args.velocidade)
        else:
            gerar_offline(args.voz)
    except ImportError as e:
        sys.exit(f"Falta instalar um pacote: {e.name}. Rode: pip install -r requirements.txt")
    print("Pronto.")


if __name__ == "__main__":
    main()
