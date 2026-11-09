# Dígito ao vivo na NPU: predição coerente com respostas fora de ordem

Prova de conceito da disciplina **ECM963 — Desenvolvimento de Aplicativos Híbridos** (Pesquisa aplicada com IA): um app em React Native + Expo em que o usuário desenha um dígito no celular e vê a predição da rede neural mudar enquanto desenha.

O TCC é uma plataforma didática com um processador RISC-V em FPGA e uma NPU, um circuito que acelera redes neurais. Nesta PoC, a NPU é **emulada** por um servidor Python no computador, com os pesos int8 da rede de dígitos do TCC. Nenhum resultado aqui foi medido na placa.

## Pergunta de pesquisa e resultado

> O `@tanstack/react-query` é necessário para manter a predição ao vivo coerente com o desenho atual, na condição de as inferências irem pela rede a cada 0,2 s e voltarem atrasadas, fora de ordem ou com erro, ou `fetch` com `AbortController` e um número de revisão bastam?

**Nessa condição, `fetch` com `AbortController` e um número de revisão bastaram.** O `react-query` não foi necessário. Como ele não foi testado, isso não significa que seja pior.

O teste usou um iPhone, 10 desenhos e um servidor que atrasa cada resposta entre 0 e 0,5 s:

| Versão | Resposta antiga sobrescreveu a mais nova | Resposta atrasada depois de limpar (atraso fixo de 2 s) |
|---|---|---|
| Sem proteção | Até 8 vezes em um desenho | Reapareceu na tela limpa |
| Com proteção | 0 vezes | Nada apareceu |

Os detalhes estão em [`PESQUISA.md`](PESQUISA.md), e os critérios de aceitação, em [`CRITERIOS.md`](CRITERIOS.md).

## O que o app faz

- **Lousa:** desenho com o dedo, com um ou mais traços, e botão Limpar.
- **Predição ao vivo:** envia no máximo uma inferência a cada 0,2 s, e mais uma ao levantar o dedo.
- **Proteção:** cancela a requisição anterior e ignora respostas de desenhos ou revisões antigas.
- **Contadores:** Enviadas, Canceladas, Descartadas, Erros e Voltou atrás.
- **LED do servidor:** verde quando ligado e vermelho até 4 s depois de cair. Com o servidor desligado, a lousa bloqueia e aparece o botão Reconectar.
- **Mensagens de erro:** erro na inferência, falha de comunicação e time-out de 5 s.

## Como rodar

Precisa de Python 3, Node.js e do app **Expo Go** no celular. O celular e o computador ficam na mesma rede. O computador pode estar no cabo, desde que seja o mesmo roteador. Os comandos abaixo são para o PowerShell, no Windows.

> Em iPhone físico, o Expo CLI e o Expo Go precisam estar na mesma conta do Expo. Se `npx expo login` falhar ao abrir o navegador, use `npx expo login --no-browser -u SEU-USUARIO`.

**1. Servidor**, no primeiro terminal:

```powershell
cd servidor
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe servidor.py
```

O servidor mostra o endereço a usar no celular. Se o celular não o alcançar, confira no Safari ou no Chrome se `http://SEU-IP:5000/status` abre, e libere a porta 5000 no firewall.

**2. App**, no segundo terminal, a partir da raiz do projeto:

```powershell
npm install
$env:EXPO_PUBLIC_SERVIDOR = "http://SEU-IP:5000"
npx expo start --clear
```

Use o IP do computador na rede, nunca `localhost`: no celular, `localhost` é o próprio celular.

## Como reproduzir os testes

| Comando do servidor | O que testa |
|---|---|
| `servidor.py --atraso-max 500` | Respostas fora de ordem, com atraso aleatório de até 0,5 s |
| `servidor.py --atraso 2000` | Resposta atrasada depois de limpar |
| `servidor.py --atraso 7000` | Time-out |
| `servidor.py --falha 0.3` | 30% das inferências respondem com erro |
| Parar o servidor com `Ctrl+C` | LED, bloqueio da lousa e Reconectar |

Para ver o problema acontecer, rode a versão sem proteção, no commit `b35245b`, com `--atraso-max 500`.

## Estrutura

```text
App.tsx                         tela, envio das inferências, proteção e erros
components/LousaDesenho.tsx     lousa de desenho
servidor/servidor.py            API: GET /status e POST /inferir/digito
servidor/npu_emulada.py         emulação em inteiros e driver da placa
servidor/preprocessamento.py    conversão dos traços para a imagem 28×28
servidor/modelos/               pesos int8 da rede de dígitos
PESQUISA.md                     diário: pergunta, alternativas, fontes e erros da IA
CRITERIOS.md                    critérios de aceitação
AGENTS.md                       contexto e regras para o agente
.github/copilot-instructions.md como o Copilot deve responder
.vscode/mcp.json                servidor MCP do Expo
```

## Como foi construído

O app foi feito com o **GitHub Copilot em modo Agent**, conectado ao servidor MCP do Expo, em etapas pequenas: critério escrito antes, diff lido antes de aceitar, teste no iPhone e um commit por etapa.

| Etapa | O que entrou |
|---|---|
| 1 | Lousa e botão Limpar |
| 2 | Predição ao vivo sem proteção, para registrar o problema |
| 3 | Cancelamento e número de revisão |
| 4 | LED, mensagens de erro, time-out e Reconectar |
| 5 | Organização visual e correção de dois bugs encontrados nos testes |

**Uso de IA fora do agente:** o Claude Code ajudou a planejar as etapas, redigir prompts e documentos e revisar diffs. ChatGPT e Gemini fizeram o mapa do tema. Os erros das ferramentas, e como foram percebidos, estão em "Onde a IA errou", no `PESQUISA.md`.

## Limites

- A inferência roda em uma emulação. O modo `--placa` existe no servidor, mas não foi executado nesta PoC, e os tempos não incluem a FPGA real.
- A emulação usa o arredondamento da PPU, mas não foi comparada bit a bit com a placa.
- O teste usou um único iPhone, 10 desenhos e atrasos de até 0,5 s. Outras condições podem dar outro resultado.
- A documentação do Expo diz que o Expo Go da App Store para no SDK 54, mas este projeto, no SDK 58, abriu no iPhone. Não foi encontrada a explicação. Em outro aparelho, pode ser preciso outro caminho.
