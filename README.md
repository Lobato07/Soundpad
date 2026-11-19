# Soundpad da Loja

Chamadas de áudio para repositores, vendedores e donos de veículos mal
estacionados. O app roda no
computador ligado à mesa de som; os outros computadores da loja apenas abrem
uma página no navegador. Não precisa de Anydesk/RDP nem de instalar nada nos
outros PCs.

## 1. Instalar (no computador da mesa de som)

Requisitos: Python 3.11, 3.12 ou 3.13 (o pygame ainda não funciona no 3.14+).

- **Windows:** dê dois cliques em `iniciar.bat` (cria o ambiente e instala tudo na primeira vez).
- **Linux:** `./iniciar.sh`

## 2. Gerar os áudios

Com o ambiente ativo (`.venv`), rode uma vez:

```
python gerar_falas.py                  # voz neural pt-BR (precisa de internet só nessa hora)
python gerar_falas.py --motor offline  # voz do sistema, sem internet (requer: pip install pyttsx3)
```

Isso cria na pasta `audios/` as chamadas de repositores:
`repositores_caixa_1` … `repositores_caixa_5` e `repositores_pacote`.
Com eles prontos, a chamada de repositores funciona mesmo sem internet.
Os arquivos antigos `caixa_1.mp3` … `pacote.mp3` não são mais usados e podem ser apagados.

Para usar **gravações próprias**, coloque arquivos com esses mesmos nomes
(`.mp3`, `.wav` ou `.ogg`). Se houver mais de uma versão (ex.:
`repositores_caixa_3.mp3` e `repositores_caixa_3_b.mp3`), o app sorteia uma delas.

As chamadas de **vendedor** e de **veículo** mudam a cada vez, por isso o app
gera a fala na hora em que o operador aperta Chamar. **Precisa de internet**
no PC da mesa de som. Cada fala gerada fica guardada em `audios/cache`, e
repetir a mesma chamada não gera de novo.

Para mudar os textos, edite `frases.py` (e rode `gerar_falas.py` de novo para os repositores).
### Voz e velocidade

No `config.json`:

- `"voz"`: a voz usada (padrão `pt-BR-ThalitaMultilingualNeural`). Se ela falhar, o app usa `"voz_reserva"`.
- `"velocidade"`: `"-10%"` fala 10% mais devagar; `"-15%"` mais devagar ainda; `"+0%"` é o normal.

Para escolher a voz de ouvido, rode `python gerar_falas.py --amostras`. Isso cria em
`audios/amostras/` um arquivo com cada voz pt-BR disponível. Coloque o nome do
arquivo escolhido (sem `.mp3`) em `"voz"`, rode `python gerar_falas.py` de novo e
reinicie o app.

## 3. Escolher a saída de áudio (mesa de som)

```
python app.py --dispositivos
```

Copie o nome (ou um trecho) da saída ligada à mesa de som para
`"dispositivo_audio"` no `config.json`. Vazio = saída padrão do sistema.

## 4. Acessar dos outros computadores

1. Descubra o IP do PC da mesa de som (`ipconfig` no Windows, `hostname -I` no Linux), p. ex. `192.168.0.20`.
2. Nos outros PCs, abra no navegador: **`http://192.168.0.20:5000`**
3. Dica: salve nos favoritos ou crie um atalho na área de trabalho.

Para funcionar de forma estável:

- **IP fixo:** reserve o IP do PC da mesa de som no roteador (reserva DHCP), senão o endereço pode mudar.
- **Firewall (Windows)**, em um prompt como administrador:
  `netsh advfirewall firewall add rule name="Soundpad" dir=in action=allow protocol=TCP localport=5000`
- **Firewall (Ubuntu):** `sudo ufw allow 5000/tcp`
- **Iniciar com o Windows:** `Win+R` → `shell:startup` → coloque um atalho para o `iniciar.bat`.
- Mantenha o PC sem suspensão automática.

> Não exponha a porta 5000 na internet (sem redirecionamento de porta no roteador).
> O app não tem login: use apenas dentro da rede da loja.

## Como funciona

- **Repositores:** escolha Caixa (e o número) ou Pacote.
- **Vendedor:** digite o nome e escolha Caixa (e o número) ou Pacote.
- **Veículo:** digite modelo, cor e placa (7 letras e números, com ou sem hífen). A placa é lida letra por letra.
- A mensagem aparece na tela e só toca ao apertar **Chamar** (evita anúncio por clique acidental).
- Chamadas simultâneas entram em **fila** e tocam uma depois da outra, sem se cortarem.
  A mesma chamada repetida enquanto ainda está na fila é ignorada.
- **Parar áudio** interrompe o que está tocando e limpa a fila.
