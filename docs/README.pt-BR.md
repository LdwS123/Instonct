<p align="center">
  <img src="../assets/logo.svg" alt="Instonct (Instant AI) - a alternativa self-hosted ao Instinct AI, rodando em um Mac mini antigo" width="760">
</p>

<p align="center">
  <b>Instonct, o seu <i>Instant AI</i>: a alternativa self-hosted ao <a href="../README.md#instinct-ai-vs-instonct">Instinct AI</a>.</b><br>
  Um agente de IA pessoal para quem você manda mensagem como se fosse um amigo, no <b>WhatsApp</b> ou no <b>Telegram</b>, rodando no seu próprio Mac mini antigo.<br>
  Sem lista de convidados. Sem a nuvem de ninguém. Seus e-mails, sua agenda e seus dados ficam em casa.
</p>

<p align="center">
  <a href="../README.md">English</a> ·
  <a href="README.zh-CN.md">简体中文</a> ·
  <a href="README.ko.md">한국어</a> ·
  <a href="README.ja.md">日本語</a> ·
  <a href="README.es.md">Español</a> ·
  <b>Português</b> ·
  <a href="README.fr.md">Français</a> ·
  <a href="README.de.md">Deutsch</a> ·
  <a href="README.ru.md">Русский</a> ·
  <a href="README.hi.md">हिन्दी</a> ·
  <a href="README.ar.md">العربية</a>
</p>

> **Sem qualquer vínculo com a Instinct AI ou a Spear Street Technology.** "Instinct" pertence ao seu dono.
> O Instonct é um projeto independente, feito por hobby. O nome é uma paródia deliberada, e esta página
> o compara com a Instinct AI apenas para que quem procura uma alternativa possa encontrá-lo.

---

O **Instonct** é um **agente de IA pessoal** de código aberto e self-hosted. Você manda mensagem para ele no **WhatsApp ou no Telegram**
(texto ou áudio) e ele faz as coisas: lê e redige seus e-mails, gerencia seu Google Agenda, cria lembretes
e tarefas, navega e preenche formulários na web, transforma uma página em CSV, vigia uma página e avisa você quando
ela muda, toca música e até executa comandos de shell na máquina em que está instalado.

Ele roda 24 horas por dia, 7 dias por semana, em um **Mac mini de 2010** (Core 2 Duo, 4,6 GB de RAM, Lubuntu). Se roda ali, roda em
quase qualquer coisa: um Raspberry Pi, um notebook velho, um VPS barato.

## O que ele sabe fazer

| Área | O que você pode dizer |
|---|---|
| **E-mail** | "Tem algum e-mail importante hoje?", "Responde ao Paul que eu vou." Só envia depois que você toca em **Sim**. |
| **Agenda** | "Marca dentista na quinta às 15h", "Adiciona um Google Meet com a Marie". Avisa sobre conflitos de horário. |
| **Navegador** | "Entra no news.ycombinator.com e me dá um CSV com os 30 primeiros títulos", "Faz meu login no site da academia". |
| **Monitoramento** | "Me avisa quando esta página disser *em estoque*." Verifica a cada 10 minutos ou mais e só avisa quando houver mudança. |
| **Memória** | Lembra das suas preferências para sempre e aprende quando você o corrige. |
| **Rotinas** | Um resumo matinal (agenda, e-mails, previsão do tempo, sua prioridade nº 1), lembretes, tarefas agendadas. |
| **Voz** | Recebe áudios (Whisper) e responde com áudios ou respostas faladas. |
| **Arquivos** | Mande uma foto, um PDF ou um CSV e pergunte sobre ele. Também consegue enviar arquivos de volta. |
| **Casa** | Música, controle remoto da TV, volume, saúde do servidor, comandos de shell (com confirmação). |
| **Qualquer idioma** | Responde no idioma em que você escreve ou fala. |

Ele também tem personalidade: respostas curtas, uma recomendação clara, sem enrolação. Chama-se *Steve*.

## Escolha o seu cérebro: qualquer modelo, qualquer provedor

O Instonct conversa com qualquer **API compatível com OpenAI**, então você não fica preso a uma única empresa. Configure três linhas no `.env`:

```bash
LLM_BASE_URL=https://api.groq.com/openai/v1     # o padrão
LLM_API_KEY=...
LLM_MODELS=openai/gpt-oss-120b,openai/gpt-oss-20b,qwen/qwen3.8-27b    # testados nesta ordem
```

| Provedor | `LLM_BASE_URL` |
|---|---|
| Groq (padrão, rápido, plano gratuito) | `https://api.groq.com/openai/v1` |
| OpenRouter (centenas de modelos) | `https://openrouter.ai/api/v1` |
| OpenAI | `https://api.openai.com/v1` |
| Together AI | `https://api.together.xyz/v1` |
| Mistral | `https://api.mistral.ai/v1` |
| Cerebras | `https://api.cerebras.ai/v1` |
| Ollama / LM Studio (100% local, sem chave) | `http://localhost:11434/v1` |

Use os nomes dos modelos exatamente como o seu provedor os escreve e escolha modelos que suportem chamada de ferramentas (tool calling).

- **Troque na hora**: envie `/model` para ver a lista, `/model 2` para usar o número 2 primeiro, `/model auto` para voltar ao padrão.
- **Fallback automático**: se um modelo atingir o limite de requisições ou estiver fora do ar, o próximo assume sozinho.
- **Rede de segurança opcional**: adicione `GEMINI_API_KEY` e o Google Gemini responde quando o seu provedor principal estiver fora do ar (e também lê imagens).
  Sem isso, o Instonct funciona normalmente com um único provedor.
- **Áudios**: transcritos por uma API Whisper (`STT_MODEL`, `STT_BASE_URL`, `STT_LANGUAGE`, o mesmo provedor por padrão).

## WhatsApp ou Telegram?

Os dois funcionam, ao mesmo tempo, com o mesmo cérebro, a mesma memória e as mesmas regras de segurança.

| | Telegram | WhatsApp |
|---|---|---|
| Configuração | 2 minutos com o @BotFather | Conta de desenvolvedor da Meta, um número, um token (cerca de 30 minutos) |
| Precisa de endereço público | Não (o bot é quem faz a chamada) | Sim (a Meta chama o seu servidor: o Tailscale Funnel resolve) |
| Botões Sim / Não, voz, arquivos | Sim | Sim |
| Teclado de controle remoto da TV, salvar senhas com `/site` | Sim | Só no Telegram (de propósito, veja Segurança) |
| Mensagens enviadas pelo bot por conta própria (lembretes) | Sempre | Só dentro de 24 h após a sua última mensagem |
| Já está no seu celular | Talvez | Quase certamente |

**Conselho sincero**: comece pelo Telegram, que é mais simples e mais seguro. Adicione o WhatsApp quando quiser conversar com ele pelo app
que você já usa todos os dias. O Instonct usa a **WhatsApp Cloud API oficial** da Meta, nunca uma biblioteca não oficial, então
não há risco de o seu número ser banido.

### Adicionar o WhatsApp (opcional)

1. Em [developers.facebook.com](https://developers.facebook.com), crie um app, adicione o produto **WhatsApp** e anote o
   **Phone number ID**. O número de teste gratuito serve para experimentar; depois você pode vincular o seu próprio número.
2. Crie um token de acesso permanente (um token de *System User* nas configurações do Meta Business) e copie o **App secret**
   (Configurações do app, Básico).
3. Adicione ao `~/bots/.env` (o seu próprio número: só dígitos, código do país primeiro, sem `+`):
   ```bash
   WA_TOKEN=...
   WA_PHONE_ID=...
   WA_APP_SECRET=...
   WA_VERIFY_TOKEN=qualquer-texto-secreto-que-voce-inventar
   WA_OWNER=33612345678
   ```
4. Dê à Meta um endereço HTTPS público para o webhook local (porta 8088, vinculada a `127.0.0.1`). Com o Tailscale:
   `sudo tailscale funnel --bg 8088`. Ele exibe um endereço `https://<machine>.<tailnet>.ts.net`.
5. Nas configurações do WhatsApp do seu app na Meta, defina a **Callback URL** do webhook com esse endereço e o **Verify token**
   com o seu `WA_VERIFY_TOKEN`, e depois assine o campo **messages**.
6. Reinicie o bot (`sudo systemctl restart bot-telegram`) e mande uma mensagem para o seu número de WhatsApp.

Toda chamada recebida é rejeitada, a menos que o `X-Hub-Signature-256` corresponda ao seu app secret, e só os números em
`WA_OWNER` recebem resposta. Os nomes no painel da Meta mudam de vez em quando; a ideia continua a mesma.
A versão da API é `v23.0` por padrão; substitua-a com `WA_API_VERSION` se a Meta a descontinuar.

## Instinct AI vs Instonct

| | Instinct AI | Instonct |
|---|---|---|
| Acesso | Somente por convite (segundo a imprensa) | Clone o repositório e rode |
| Onde roda | Na nuvem de uma empresa | **Na sua própria máquina** |
| Seus dados | Entregues a uma startup | Ficam na sua máquina (Redis + arquivos locais) |
| Como você conversa com ele | Texto, telefone, WhatsApp (segundo a imprensa) | WhatsApp ou Telegram, texto ou voz |
| Modelos | Escolhidos por eles | **Qualquer provedor compatível com OpenAI**, troque com `/model` |
| Custo | Não divulgado | Planos gratuitos funcionam (Groq, Gemini); ou totalmente local com Ollama |
| Código-fonte | Fechado | **Bem aqui** |

A Instinct AI é um produto de verdade, feito por uma equipe com financiamento; o Instonct é o projeto de fim de semana de uma pessoa que virou uso diário.
Escolha o Instonct se quiser a mesma ideia, mas com as rédeas na sua mão.

## Como funciona

- **Cérebro**: qualquer modelo compatível com OpenAI (Groq `gpt-oss-120b` / `20b` por padrão, com esforço de raciocínio adaptativo), com fallback opcional para o Gemini.
- **Ferramentas**: o modelo chama cerca de 35 ferramentas (e-mail, agenda, navegador, arquivos, música, TV, shell...). Veja `TOOLS` em [`bots/telegram-search/bot.py`](../bots/telegram-search/bot.py).
- **Navegador**: [Lightpanda](https://github.com/lightpanda-io/browser), um navegador headless minúsculo (~25 MB de RAM) que roda até em uma CPU de 2010. Veja [`webagent.py`](../bots/telegram-search/webagent.py).
- **Canais**: Telegram por long polling (sem porta aberta), WhatsApp através do [`whatsapp.py`](../bots/telegram-search/whatsapp.py) (um pequeno webhook em `127.0.0.1`).
- **Estado**: Redis (histórico, memória, lembretes, monitoramentos).
- **Acesso**: SSH + [Tailscale](https://tailscale.com), com o `ufw` fechado por padrão. A configuração do servidor está em [`home-server.md`](home-server.md).

## Segurança, porque um agente com acesso ao shell precisa dela

- **Privado**: no Telegram, a primeira pessoa que enviar `/start` se torna a única dona; no WhatsApp, só os números em `WA_OWNER`
  recebem resposta. Todos os outros são ignorados.
- **Nada arriscado acontece em silêncio**: enviar e-mail, enviar um formulário, apagar um evento, executar um comando
  ou clicar em um botão "Comprar / Pagar / Excluir" exigem antes um toque em **Sim / Não**.
- **Senhas nunca passam pelo modelo**: os logins de sites ficam guardados em um arquivo `0600` e são preenchidos por código simples.
  Salvá-los só é possível no Telegram, porque o bot apaga a sua mensagem logo em seguida (o WhatsApp a manteria).
- **Páginas da web são dados, não ordens**: o texto encontrado em uma página ou em um e-mail não pode dar instruções ao agente.
- **Sem acesso à rede local pelo navegador**: só endereços `http(s)` públicos são permitidos (proteção contra SSRF).
- **Segredos nunca neste repositório**: as chaves ficam em um `.env` no servidor.

## Início rápido

Você precisa de uma máquina Linux, Python 3, Redis, um **token de bot do Telegram** (do [@BotFather](https://t.me/BotFather)) e uma
**chave de API** de qualquer provedor acima (a Groq tem plano gratuito).

```bash
git clone https://github.com/LdwS123/Instonct.git && cd Instonct
sudo apt install redis-server python3-venv espeak-ng mpv alsa-utils      # voz + música (opcional)
python3 -m venv ~/bots/venv && ~/bots/venv/bin/pip install -r bots/telegram-search/requirements.txt
mkdir -p ~/bots/telegram-search && cp bots/telegram-search/*.py ~/bots/telegram-search/

cat > ~/bots/.env <<'EOF'
TELEGRAM_TOKEN=...
LLM_API_KEY=...
# opcional: LLM_BASE_URL, LLM_MODELS, GEMINI_API_KEY, STT_LANGUAGE=en, WA_* (WhatsApp)
EOF
chmod 600 ~/bots/.env

sudo cp systemd/bot-telegram.service /etc/systemd/system/    # edite User= e os caminhos antes
sudo systemctl daemon-reload && sudo systemctl enable --now bot-telegram
```

Depois abra o seu bot no Telegram e envie `/start`. Opcional: o Lightpanda em `~/lightpanda/lightpanda` para o
navegador, `MAIL_USER` / `MAIL_PASS` / `MAIL_HOST` para o e-mail e `scripts/google-auth.py` para o Google Agenda.

## Procurando por...

Instant AI · Instinct AI alternative · Instinct AI de código aberto · agente de IA pessoal self-hosted · mande mensagem para o seu assistente de IA ·
assistente de IA no WhatsApp · assistente de IA no Telegram · agente de IA no WhatsApp · OpenClaw alternative · agente de IA que lê o seu e-mail e
gerencia a sua agenda · rodar um agente de IA em um Raspberry Pi ou em um Mac mini antigo · assistente de IA em servidor doméstico · agente Groq · agente Gemini ·
agente Ollama · agente OpenRouter · agente de navegador Lightpanda · web scraper com IA para CSV · assistente de IA privado, sem nuvem.

---

<sub>O Instonct é um projeto independente, sem afiliação, aprovação ou patrocínio da Instinct AI ou da
Spear Street Technology, Inc. Todas as marcas pertencem aos seus respectivos proprietários. Licença MIT.</sub>
