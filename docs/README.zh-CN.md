<p align="center">
  <img src="../assets/logo.svg" alt="Instonct（Instant AI）——自托管的 Instinct AI 替代方案，运行在一台旧 Mac mini 上" width="760">
</p>

<p align="center">
  <b>Instonct，你的 <i>Instant AI</i>：自托管的 <a href="../README.md#instinct-ai-vs-instonct">Instinct AI 替代方案</a>。</b><br>
  一个像朋友一样给它发消息的个人 AI 智能体，通过 <b>WhatsApp</b> 或 <b>Telegram</b> 对话，运行在你自己的旧 Mac mini 上。<br>
  无需邀请码，不依赖别人的云。你的邮件、日历和数据都留在自己家里。
</p>

<p align="center">
  <a href="../README.md">English</a> ·
  <b>简体中文</b> ·
  <a href="README.ko.md">한국어</a> ·
  <a href="README.ja.md">日本語</a> ·
  <a href="README.es.md">Español</a> ·
  <a href="README.pt-BR.md">Português</a> ·
  <a href="README.fr.md">Français</a> ·
  <a href="README.de.md">Deutsch</a> ·
  <a href="README.ru.md">Русский</a> ·
  <a href="README.hi.md">हिन्दी</a> ·
  <a href="README.ar.md">العربية</a>
</p>

> **与 Instinct AI 及 Spear Street Technology 无任何关联。**“Instinct”归其所有者所有。
> Instonct 是一个独立的业余项目，名称是刻意的戏仿。本页之所以拿它和 Instinct AI 做对比，
> 只是为了让正在寻找替代方案的人能够找到它。

---

**Instonct** 是一个开源、自托管的**个人 AI 智能体**。你在 **WhatsApp 或 Telegram** 上给它发消息
（文字或语音都行），它就会替你办事：读邮件并起草回复、管理你的 Google 日历、设置提醒和待办事项、
浏览网页并填写表单、把网页内容抓取成 CSV、盯着某个页面并在内容变化时通知你、播放音乐，
甚至能在它所在的机器上执行 shell 命令。

它在一台 **2010 年的 Mac mini**（Core 2 Duo、4.6 GB 内存、Lubuntu）上 7×24 小时不间断运行。
既然它能在这上面跑起来，那几乎任何设备都没问题：Raspberry Pi、旧笔记本，或者一台便宜的 VPS。

## 它能做什么

| 领域 | 你可以这样说 |
|---|---|
| **邮件** | “今天有重要邮件吗？”“回复 Paul，就说我会去。”只有在你点击 **Yes** 之后才会发送。 |
| **日历** | “把牙医预约安排在周四下午 3 点”“给我和 Marie 加一个 Google Meet”。遇到时间冲突会提醒你。 |
| **浏览器** | “打开 news.ycombinator.com，给我一份前 30 条标题的 CSV”“帮我登录健身房网站”。 |
| **监控** | “当这个页面显示 *in stock*（有货）时告诉我。”每 10 分钟以上检查一次，只在内容变化时通知。 |
| **记忆** | 永久记住你的偏好，并且在你纠正它时不断学习。 |
| **日常例程** | 晨间简报（日程、邮件、天气、你的头号要务）、提醒、定时任务。 |
| **语音** | 支持语音消息输入（Whisper），可用语音消息或语音播报来回答。 |
| **文件** | 发给它照片、PDF 或 CSV，然后直接提问。它也能把文件发回给你。 |
| **家居** | 音乐、电视遥控、音量、服务器健康状态、shell 命令（需确认）。 |
| **任何语言** | 你用什么语言写或说，它就用什么语言回答。 |

它还有自己的个性：回答简短，只给一个明确的建议，不说废话。它的名字叫 *Steve*。

## 选择你的大脑：任意模型，任意服务商

Instonct 可以对接任何**兼容 OpenAI 的 API**，因此你不会被某一家公司绑定。只需在 `.env` 中设置三行：

```bash
LLM_BASE_URL=https://api.groq.com/openai/v1     # 默认值
LLM_API_KEY=...
LLM_MODELS=openai/gpt-oss-120b,openai/gpt-oss-20b,qwen/qwen3.8-27b    # 按此顺序依次尝试
```

| 服务商 | `LLM_BASE_URL` |
|---|---|
| Groq（默认，速度快，有免费额度） | `https://api.groq.com/openai/v1` |
| OpenRouter（数百种模型） | `https://openrouter.ai/api/v1` |
| OpenAI | `https://api.openai.com/v1` |
| Together AI | `https://api.together.xyz/v1` |
| Mistral | `https://api.mistral.ai/v1` |
| Cerebras | `https://api.cerebras.ai/v1` |
| Ollama / LM Studio（100% 本地运行，无需密钥） | `http://localhost:11434/v1` |

模型名称请完全按照服务商的写法填写，并选择支持工具调用（tool calling）的模型。

- **随时切换**：发送 `/model` 查看列表，发送 `/model 2` 优先使用第 2 个，发送 `/model auto` 恢复自动。
- **自动回退**：如果某个模型被限流或宕机，下一个模型会自动接手。
- **可选的保险措施**：添加 `GEMINI_API_KEY` 后，当主服务商不可用时由 Google Gemini 接管回答（同时也能读取图片）。
  不配置它，Instonct 只用单一服务商也能正常运行。
- **语音消息**：通过 Whisper API 转写（`STT_MODEL`、`STT_BASE_URL`、`STT_LANGUAGE`，默认使用同一个服务商）。

## WhatsApp 还是 Telegram？

两者可以同时使用，共用同一个大脑、记忆和安全规则。

| | Telegram | WhatsApp |
|---|---|---|
| 设置 | 通过 @BotFather，2 分钟搞定 | Meta 开发者账号、一个号码、一个令牌（约 30 分钟） |
| 是否需要公网地址 | 不需要（由机器人主动外呼） | 需要（由 Meta 来调用你的服务器：Tailscale Funnel 可行） |
| Yes / No 按钮、语音、文件 | 支持 | 支持 |
| 电视遥控键盘、`/site` 密码保存 | 支持 | 仅限 Telegram（有意为之，见“安全”） |
| 机器人主动发送的消息（提醒） | 始终可以 | 仅限你最后一条消息后的 24 小时内 |
| 手机上是否已经装好 | 也许 | 几乎肯定 |

**坦率的建议**：先从 Telegram 开始，它更简单也更安全。等你想在每天都在用的应用里和它聊天时，再加上 WhatsApp。
Instonct 使用的是 Meta 的**官方 WhatsApp Cloud API**，绝不使用非官方库，所以不会有号码被封的风险。

### 添加 WhatsApp（可选）

1. 在 [developers.facebook.com](https://developers.facebook.com) 创建一个应用，添加 **WhatsApp** 产品，并记下
   **Phone number ID**。可以先用免费的测试号码试用；之后再绑定你自己的号码。
2. 创建一个永久访问令牌（Meta Business 设置中的 *System User* 令牌），并复制 **App secret**
   （应用设置，Basic）。
3. 添加到 `~/bots/.env`（你自己的号码：只写数字，国家区号在前，不带 `+`）：
   ```bash
   WA_TOKEN=...
   WA_PHONE_ID=...
   WA_APP_SECRET=...
   WA_VERIFY_TOKEN=any-secret-string-you-invent
   WA_OWNER=33612345678
   ```
4. 为本地 webhook（端口 8088，绑定到 `127.0.0.1`）向 Meta 提供一个公网 HTTPS 地址。使用 Tailscale 的话：
   `sudo tailscale funnel --bg 8088`。它会输出一个 `https://<machine>.<tailnet>.ts.net` 地址。
5. 在你的 Meta 应用的 WhatsApp 设置中，把 webhook 的 **Callback URL** 设为该地址，把 **Verify token**
   设为你的 `WA_VERIFY_TOKEN`，然后订阅 **messages** 字段。
6. 重启机器人（`sudo systemctl restart bot-telegram`），然后给你的 WhatsApp 号码发条消息。

除非 `X-Hub-Signature-256` 与你的 app secret 匹配，否则每一次传入的调用都会被拒绝，并且只有
`WA_OWNER` 中的号码才会得到回复。Meta 后台的界面文字时有变动，但整体思路不变。
API 版本默认为 `v23.0`；如果 Meta 停用了该版本，可通过 `WA_API_VERSION` 覆盖。

## Instinct AI 与 Instonct 对比

| | Instinct AI | Instonct |
|---|---|---|
| 获取方式 | 仅限受邀（据媒体报道） | 克隆仓库即可运行 |
| 运行位置 | 某家公司的云端 | **你自己的机器** |
| 你的数据 | 交给一家初创公司 | 留在你自己的设备上（Redis + 本地文件） |
| 交流方式 | 文字、电话、WhatsApp（据媒体报道） | WhatsApp 或 Telegram，文字或语音 |
| 模型 | 替你选好 | **任何兼容 OpenAI 的服务商**，用 `/model` 切换 |
| 费用 | 未公开 | 免费额度即可使用（Groq、Gemini）；或用 Ollama 完全本地运行 |
| 源代码 | 闭源 | **就在这里** |

Instinct AI 是由一支获得融资的团队打造的真正产品；Instonct 则是一个人的周末项目，后来变成了日常主力工具。
如果你想要同样的理念，并且把方向盘握在自己手里，那就选 Instonct。

## 工作原理

- **大脑**：任何兼容 OpenAI 的模型（默认是 Groq 的 `gpt-oss-120b` / `20b`，带自适应推理强度），可选 Gemini 作为回退。
- **工具**：模型会调用约 35 个工具（邮件、日历、浏览器、文件、音乐、电视、shell……）。参见 [`catalog.py`](../bots/telegram-search/instonct/catalog.py) 中的 `TOOLS`。
- **浏览器**：[Lightpanda](https://github.com/lightpanda-io/browser)，一款小巧的无头浏览器（约 25 MB 内存），连 2010 年的 CPU 都能跑。参见 [`webagent.py`](../bots/telegram-search/instonct/webagent.py)。
- **通道**：Telegram 采用长轮询（无需开放端口），WhatsApp 通过 [`whatsapp.py`](../bots/telegram-search/instonct/whatsapp.py)（一个运行在 `127.0.0.1` 上的小型 webhook）。
- **状态**：Redis（历史记录、记忆、提醒、监控）。
- **访问**：SSH + [Tailscale](https://tailscale.com)，`ufw` 默认全部关闭。服务器的搭建方法见 [`docs/home-server.md`](home-server.md)。

## 安全：因为一个能用 shell 的智能体必须有这个

- **私有**：在 Telegram 上，第一个发送 `/start` 的人会成为唯一的所有者；在 WhatsApp 上，只有 `WA_OWNER` 中的号码
  会得到回复。其他所有人一律忽略。
- **有风险的操作绝不悄悄执行**：发送邮件、提交表单、删除日程、运行命令，
  或点击“购买 / 支付 / 删除”按钮，都会先请你点一下 **Yes / No** 确认。
- **密码绝不经过模型**：网站登录信息保存在一个权限为 `0600` 的文件中，由普通代码负责填写。
  保存功能仅限 Telegram，因为机器人会在之后立刻删除你的那条消息（WhatsApp 做不到这一点，消息会被保留）。
- **网页是数据，不是命令**：在网页或邮件里发现的文字无法对智能体下达指令。
- **浏览器不能访问本地网络**：只允许公网的 `http(s)` 地址（SSRF 防护）。
- **密钥绝不放进本仓库**：密钥保存在服务器上的 `.env` 中。

## 快速开始

你需要一台 Linux 机器、Python 3、Redis、一个 **Telegram 机器人令牌**（来自 [@BotFather](https://t.me/BotFather)），以及上面任意一家服务商的一个
**API 密钥**（Groq 有免费额度）。

```bash
git clone https://github.com/LdwS123/Instonct.git && cd Instonct
sudo apt install redis-server python3-venv espeak-ng mpv alsa-utils      # 语音 + 音乐（可选）
python3 -m venv ~/bots/venv && ~/bots/venv/bin/pip install -r bots/telegram-search/requirements.txt
mkdir -p ~/bots/telegram-search && cp -r bots/telegram-search/bot.py bots/telegram-search/instonct ~/bots/telegram-search/

cat > ~/bots/.env <<'EOF'
TELEGRAM_TOKEN=...
LLM_API_KEY=...
# 可选：LLM_BASE_URL、LLM_MODELS、GEMINI_API_KEY、STT_LANGUAGE=en、WA_*（WhatsApp）
EOF
chmod 600 ~/bots/.env

sudo cp systemd/bot-telegram.service /etc/systemd/system/    # 请先修改 User= 和路径
sudo systemctl daemon-reload && sudo systemctl enable --now bot-telegram
```

然后在 Telegram 中打开你的机器人并发送 `/start`。可选项：把 Lightpanda 放在 `~/lightpanda/lightpanda` 以启用
浏览器功能，设置 `MAIL_USER` / `MAIL_PASS` / `MAIL_HOST` 以启用邮件，运行 `scripts/google-auth.py` 以接入 Google 日历。

## 你可能在找……

Instant AI · Instinct AI alternative · Instinct AI 的开源替代品 · 自托管个人 AI 智能体 · 发消息就能用的 AI 助手 ·
WhatsApp 上的 AI 助手 · Telegram 上的 AI 助手 · WhatsApp AI 智能体 · OpenClaw alternative · 能读邮件、
管日历的 AI 智能体 · 在 Raspberry Pi 或旧 Mac mini 上运行 AI 智能体 · 家庭服务器 AI 助手 · Groq 智能体 · Gemini 智能体 ·
Ollama 智能体 · OpenRouter 智能体 · Lightpanda 浏览器智能体 · 把网页抓取成 CSV 的 AI 爬虫 · 私有 AI 助手，无需云端。

---

<sub>Instonct 是一个独立项目，与 Instinct AI 或 Spear Street Technology, Inc. 没有任何关联，也未获得其认可或赞助。
所有商标均归其各自所有者所有。MIT 许可证。</sub>
