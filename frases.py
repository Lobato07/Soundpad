"""Frases usadas pelo soundpad.

Para mudar um texto, edite aqui. As falas de repositores ficam salvas na pasta
audios/ (rode gerar_falas.py de novo depois de mudar). As de vendedor e
veículo são geradas na hora, então a mudança vale na próxima chamada.

`destino` é o texto do local, por exemplo "caixa 3" ou "pacote".
"""


def nome_destino(destino: str, numero: int | None = None) -> str:
    return f"caixa {numero}" if destino == "caixa" else "pacote"


def frase_repositores(destino: str) -> str:
    return (
        f"Atenção repositores, favor comparecerem ao {destino}. "
        f"Repositores favor comparecerem ao {destino}."
    )


def frase_vendedor(nome: str, destino: str) -> str:
    return (
        f"Atenção vendedor {nome}, favor comparecer ao {destino}. "
        f"Vendedor {nome}, favor comparecer ao {destino}."
    )


def frase_veiculo(modelo: str, cor: str, placa: str) -> str:
    trecho = f"proprietário do veículo {modelo}, de cor {cor}, placa {placa}, favor comparecer ao estacionamento."
    return f"Atenção {trecho} Atenção {trecho}"


def placa_falada(placa: str) -> str:
    """'ABC1D23' -> 'A, B, C, 1, D, 2, 3', para a voz ler letra por letra."""
    return ", ".join(placa)
