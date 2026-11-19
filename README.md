# Soundpad 2.0

Chamadas por voz nas caixas de som: repositores, vendedor pelo nome e dono de
veículo mal estacionado. O Soundpad roda em um computador ligado à mesa de som
(ou às caixas). Os outros computadores da rede só abrem um endereço no navegador,
sem instalar nada.

---

## Instalação

1. No computador ligado ao som, dê dois cliques em **SoundpadSetup-2.0.exe** e avance.
   - Se aparecer "O Windows protegeu o computador", clique em **Mais informações → Executar assim mesmo**.
2. No fim, o Soundpad abre sozinho na página de **Ajustes**. Escolha:
   - a **saída de som** e clique em **Tocar nas caixas de som** para testar;
   - a **voz** e a **velocidade** (botão **Ouvir aqui**);
   - os **locais** (Caixa, Pacote, Balcão…) e quantos caixas existem;
   - as **chamadas** (dá para criar novas, como Segurança, Açougue ou um aviso de fechamento).
3. Clique em **Salvar**.
4. Nos outros computadores, abra o endereço que aparece em **Acesso pelos outros
   computadores** (ex.: `http://192.168.0.20:5000`) e salve nos favoritos.

O instalador já cria o atalho, liga o Soundpad junto com o Windows e libera o
firewall. Para o endereço não mudar, reserve o IP do computador no roteador.

Os Ajustes abrem sem senha só no próprio computador do som. Para abrir de outro
computador, crie uma senha em Ajustes → Acesso.

---

## Como funciona

- Cada chamada cadastrada nos Ajustes vira um botão no painel. Ao criar uma, o cliente
  escolhe o tipo:
  - **Grupo para um local** (como Repositores): o operador escolhe o local. Frase com `{local}`.
  - **Pessoa pelo nome** (como Vendedor): digita o nome e escolhe o local. Frase com `{nome}` e `{local}`.
  - **Veículo**: digita modelo, cor e placa. Frase com `{modelo}`, `{cor}` e `{placa}`.
  - **Aviso fixo**: não precisa preencher nada; toca sempre a mesma frase (ex.: "a loja fechará em 15 minutos").
- O operador escolhe a chamada, preenche e confirma em **Chamar**.
  A frase aparece na tela antes de tocar.
- Locais numerados mostram botões de 1 a 5. Se houver mais de 5, aparece também
  um campo para digitar o número.
- Enquanto o operador digita, a fala já vai sendo gerada. Ao clicar, ela costuma
  tocar na hora.
- As chamadas de grupo e os avisos fixos são preparados com antecedência e funcionam sem internet
  depois da primeira vez. As que têm nome ou placa são geradas na hora e precisam de internet.
- Chamadas simultâneas entram em fila. **Parar áudio** interrompe e limpa a fila.
- Gravações próprias (opcional): coloque arquivos na pasta `gravacoes` dos dados,
  com o código da chamada no começo do nome: `repositores_caixa_3.mp3`,
  `repositores_pacote.mp3` ou, para um aviso, `fechamento.mp3`. O código é o nome
  da chamada sem acentos e espaços, como ela foi criada. Os arquivos substituem a voz gerada.

Onde ficam os dados: `%APPDATA%\Soundpad` no programa instalado (config.json,
cache das falas e soundpad.log), ou a própria pasta do projeto ao rodar pelo código.

---

## Rodar pelo código (desenvolvimento)

```
iniciar.bat          # Windows: cria o ambiente e inicia
python app.py        # com o ambiente (.venv) ativo
```

O app abre o navegador sozinho. Use `python app.py --segundo-plano` para não abrir.
