<p align="center">
  <img src="../assets/logo.svg" alt="Instonct (Instant AI) - 오래된 Mac mini에서 돌아가는 셀프 호스팅 Instinct AI 대안" width="760">
</p>

<p align="center">
  <b>Instonct, 당신의 <i>Instant AI</i>: 셀프 호스팅 방식의 <a href="../README.md#instinct-ai-vs-instonct">Instinct AI 대안</a>.</b><br>
  친구에게 문자하듯 <b>WhatsApp</b>이나 <b>Telegram</b>으로 말을 거는 개인 AI 에이전트, 당신의 낡은 Mac mini에서 돌아갑니다.<br>
  초대 대기자 명단도, 남의 클라우드도 없습니다. 메일, 일정, 데이터는 모두 집에 그대로 있습니다.
</p>

<p align="center">
  <a href="../README.md">English</a> ·
  <a href="README.zh-CN.md">简体中文</a> ·
  <b>한국어</b> ·
  <a href="README.ja.md">日本語</a> ·
  <a href="README.es.md">Español</a> ·
  <a href="README.pt-BR.md">Português</a> ·
  <a href="README.fr.md">Français</a> ·
  <a href="README.de.md">Deutsch</a> ·
  <a href="README.ru.md">Русский</a> ·
  <a href="README.hi.md">हिन्दी</a> ·
  <a href="README.ar.md">العربية</a>
</p>

> **Instinct AI 및 Spear Street Technology와 무관합니다.** "Instinct"의 권리는 그 소유자에게 있습니다.
> Instonct는 독립적인 취미 프로젝트입니다. 이름은 의도적인 패러디이며, 이 페이지가 Instinct AI와
> 비교하는 것은 대안을 찾는 사람들이 이 프로젝트를 발견할 수 있도록 하기 위해서일 뿐입니다.

---

**Instonct**는 오픈 소스 셀프 호스팅 **개인 AI 에이전트**입니다. **WhatsApp이나 Telegram**으로
(텍스트 또는 음성 메시지) 말을 걸면 알아서 처리해 줍니다. 메일을 읽고 초안을 쓰고, Google Calendar를 관리하고,
알림과 할 일을 설정하고, 웹 양식을 탐색해 채워 넣고, 웹 페이지를 CSV로 긁어오고, 페이지를 지켜보다가
바뀌면 알려 주고, 음악을 틀고, 심지어 자신이 돌아가는 머신에서 셸 명령까지 실행합니다.

**2010년형 Mac mini**(Core 2 Duo, RAM 4.6 GB, Lubuntu)에서 24시간 365일 돌아갑니다. 거기서 돌아간다면
Raspberry Pi, 오래된 노트북, 저렴한 VPS 등 거의 어디서든 돌아갑니다.

## 할 수 있는 일

| 영역 | 이렇게 말해 보세요 |
|---|---|
| **메일** | "오늘 중요한 메일 있어?", "Paul에게 답장해 줘, 참석한다고." **예**를 누른 뒤에만 발송합니다. |
| **캘린더** | "목요일 오후 3시에 치과 넣어 줘", "Marie와 Google Meet 추가해 줘". 일정이 겹치면 알려 줍니다. |
| **브라우저** | "news.ycombinator.com에 들어가서 상위 30개 제목을 CSV로 줘", "내 헬스장 사이트에 로그인해 줘". |
| **감시** | "이 페이지에 *재고 있음*이라고 뜨면 알려 줘." 10분 이상 간격으로 확인하고, 변할 때만 알립니다. |
| **기억** | 당신의 취향을 계속 기억하고, 바로잡아 주면 배웁니다. |
| **루틴** | 아침 브리핑(일정, 메일, 날씨, 오늘의 최우선 과제), 알림, 예약 작업. |
| **음성** | 음성 메시지 입력(Whisper), 음성 메시지 또는 음성 답변 출력. |
| **파일** | 사진, PDF, CSV를 보내고 물어보세요. 파일을 다시 보내 줄 수도 있습니다. |
| **집** | 음악, TV 리모컨, 볼륨, 서버 상태, 셸 명령(확인 후 실행). |
| **모든 언어** | 당신이 쓰거나 말하는 언어로 답합니다. |

성격도 있습니다. 짧은 답변, 명확한 추천 하나, 군더더기 없음. 이름은 *Steve*입니다.

## 두뇌를 고르세요: 어떤 모델, 어떤 제공업체든

Instonct는 모든 **OpenAI 호환 API**와 통신하므로 특정 회사에 묶이지 않습니다. `.env`에 세 줄만 설정하세요.

```bash
LLM_BASE_URL=https://api.groq.com/openai/v1     # 기본값
LLM_API_KEY=...
LLM_MODELS=openai/gpt-oss-120b,openai/gpt-oss-20b,qwen/qwen3.8-27b    # 이 순서대로 시도
```

| 제공업체 | `LLM_BASE_URL` |
|---|---|
| Groq (기본값, 빠름, 무료 티어) | `https://api.groq.com/openai/v1` |
| OpenRouter (수백 개의 모델) | `https://openrouter.ai/api/v1` |
| OpenAI | `https://api.openai.com/v1` |
| Together AI | `https://api.together.xyz/v1` |
| Mistral | `https://api.mistral.ai/v1` |
| Cerebras | `https://api.cerebras.ai/v1` |
| Ollama / LM Studio (100% 로컬, 키 불필요) | `http://localhost:11434/v1` |

모델 이름은 제공업체가 표기하는 그대로 사용하고, 도구 호출(tool calling)을 지원하는 모델을 고르세요.

- **즉석 전환**: `/model`을 보내면 목록이 나오고, `/model 2`는 2번을 먼저 사용하며, `/model auto`로 원래대로 돌아갑니다.
- **자동 폴백**: 모델이 요청 제한에 걸렸거나 다운되면 다음 모델이 알아서 이어받습니다.
- **선택적 안전망**: `GEMINI_API_KEY`를 추가하면 주 제공업체가 다운되었을 때 Google Gemini가 대신 답합니다(이미지도 읽습니다).
  없어도 Instonct는 제공업체 하나만으로 잘 돌아갑니다.
- **음성 메시지**: Whisper API(`STT_MODEL`, `STT_BASE_URL`, `STT_LANGUAGE`, 기본값은 같은 제공업체)로 받아쓰기합니다.

## WhatsApp일까, Telegram일까?

둘 다 동시에 작동하며, 같은 두뇌, 같은 기억, 같은 안전 규칙을 공유합니다.

| | Telegram | WhatsApp |
|---|---|---|
| 설정 | @BotFather로 2분 | Meta 개발자 계정, 전화번호, 토큰(약 30분) |
| 공개 주소 필요 | 아니요 (봇이 먼저 호출) | 예 (Meta가 서버를 호출: Tailscale Funnel 사용 가능) |
| 예 / 아니요 버튼, 음성, 파일 | 예 | 예 |
| TV 리모컨 키보드, `/site` 비밀번호 저장 | 예 | Telegram 전용 (의도된 것, 안전 섹션 참고) |
| 봇이 먼저 보내는 메시지 (알림) | 항상 | 마지막 메시지로부터 24시간 이내에만 |
| 이미 폰에 설치되어 있나 | 아마도 | 거의 확실히 |

**솔직한 조언**: Telegram으로 시작하세요. 더 간단하고 더 안전합니다. 매일 쓰는 앱에서 말을 걸고 싶어지면
그때 WhatsApp을 추가하세요. Instonct는 Meta의 **공식 WhatsApp Cloud API**를 사용하며 비공식 라이브러리는 절대 쓰지 않으므로,
번호가 차단될 위험이 없습니다.

### WhatsApp 추가하기 (선택 사항)

1. [developers.facebook.com](https://developers.facebook.com)에서 앱을 만들고 **WhatsApp** 제품을 추가한 뒤
   **Phone number ID**를 메모해 두세요. 무료 테스트 번호로 시험해 볼 수 있고, 나중에 본인 번호를 연결할 수 있습니다.
2. 영구 액세스 토큰(Meta Business 설정의 *System User* 토큰)을 만들고 **App secret**(앱 설정, 기본 설정)을 복사하세요.
3. `~/bots/.env`에 추가하세요(본인 번호: 숫자만, 국가 코드가 맨 앞, `+` 없이):
   ```bash
   WA_TOKEN=...
   WA_PHONE_ID=...
   WA_APP_SECRET=...
   WA_VERIFY_TOKEN=any-secret-string-you-invent
   WA_OWNER=33612345678
   ```
4. 로컬 웹훅(포트 8088, `127.0.0.1`에 바인딩)에 대한 공개 HTTPS 주소를 Meta에 제공하세요. Tailscale을 사용하면
   `sudo tailscale funnel --bg 8088`을 실행합니다. `https://<machine>.<tailnet>.ts.net` 형태의 주소가 출력됩니다.
5. Meta 앱의 WhatsApp 설정에서 웹훅 **Callback URL**을 그 주소로, **Verify token**을
   `WA_VERIFY_TOKEN` 값으로 설정한 다음 **messages** 필드를 구독하세요.
6. 봇을 재시작(`sudo systemctl restart bot-telegram`)하고 WhatsApp 번호로 문자를 보내 보세요.

들어오는 모든 호출은 `X-Hub-Signature-256`이 앱 시크릿과 일치하지 않으면 거부되며, `WA_OWNER`에 있는 번호에만
응답합니다. Meta 대시보드의 항목 이름은 가끔 바뀌지만 방식은 같습니다.
API 버전의 기본값은 `v23.0`이며, Meta가 이를 폐기하면 `WA_API_VERSION`으로 덮어쓰세요.

## Instinct AI vs Instonct

| | Instinct AI | Instonct |
|---|---|---|
| 접근 | 초대 전용 (언론 보도 기준) | 저장소를 클론해서 실행 |
| 실행 위치 | 회사의 클라우드 | **내 머신** |
| 내 데이터 | 스타트업에 넘어감 | 내 박스에 남음 (Redis + 로컬 파일) |
| 대화 방식 | 문자, 전화, WhatsApp (언론 보도 기준) | WhatsApp 또는 Telegram, 텍스트 또는 음성 |
| 모델 | 정해 줌 | **모든 OpenAI 호환 제공업체**, `/model`로 전환 |
| 비용 | 비공개 | 무료 티어로 충분 (Groq, Gemini). 또는 Ollama로 완전 로컬 |
| 소스 코드 | 비공개 | **바로 여기에** |

Instinct AI는 투자를 받은 팀이 만든 진짜 제품이고, Instonct는 한 사람의 주말 프로젝트가 매일 쓰는 도구가 된 것입니다.
같은 아이디어를 직접 운전대를 잡고 쓰고 싶다면 Instonct를 고르세요.

## 작동 방식

- **두뇌**: OpenAI 호환 모델이면 무엇이든 (기본값은 Groq `gpt-oss-120b` / `20b`, 적응형 추론 강도), 선택적으로 Gemini 폴백.
- **도구**: 모델이 약 35개의 도구(메일, 캘린더, 브라우저, 파일, 음악, TV, 셸...)를 호출합니다. [`catalog.py`](../bots/telegram-search/instonct/catalog.py)의 `TOOLS`를 참고하세요.
- **브라우저**: [Lightpanda](https://github.com/lightpanda-io/browser), 2010년형 CPU에서도 돌아가는 아주 작은 헤드리스 브라우저(RAM 약 25 MB). [`webagent.py`](../bots/telegram-search/instonct/webagent.py)를 참고하세요.
- **채널**: Telegram은 롱 폴링(열린 포트 없음), WhatsApp은 [`whatsapp.py`](../bots/telegram-search/instonct/whatsapp.py)(`127.0.0.1`의 작은 웹훅)를 통해 연결합니다.
- **상태**: Redis (대화 기록, 기억, 알림, 감시).
- **접속**: SSH + [Tailscale](https://tailscale.com), `ufw`는 기본적으로 모두 차단. 서버 설정은 [`home-server.md`](home-server.md)에 있습니다.

## 안전: 셸을 가진 에이전트에는 꼭 필요합니다

- **비공개**: Telegram에서는 `/start`를 처음 보낸 사람이 유일한 소유자가 되고, WhatsApp에서는 `WA_OWNER`에 있는 번호에만
  응답합니다. 그 외 모든 사람은 무시됩니다.
- **위험한 일은 조용히 일어나지 않습니다**: 메일 발송, 양식 제출, 일정 삭제, 명령 실행,
  "구매 / 결제 / 삭제" 버튼 클릭은 모두 먼저 **예 / 아니요** 탭으로 확인을 받습니다.
- **비밀번호는 모델을 거치지 않습니다**: 사이트 로그인 정보는 `0600` 파일에 저장되고 단순한 코드가 입력합니다.
  저장은 Telegram에서만 가능한데, 봇이 곧바로 내 메시지를 삭제하기 때문입니다(WhatsApp은 메시지가 남습니다).
- **웹 페이지는 명령이 아니라 데이터입니다**: 페이지나 메일에서 발견된 텍스트는 에이전트에게 지시를 내릴 수 없습니다.
- **브라우저를 통한 로컬 네트워크 접근 금지**: 공개 `http(s)` 주소만 허용됩니다 (SSRF 방어).
- **비밀 정보는 이 저장소에 절대 없음**: 키는 서버의 `.env`에 보관됩니다.

## 빠른 시작

Linux 머신, Python 3, Redis, **Telegram 봇 토큰**([@BotFather](https://t.me/BotFather)에서 발급), 그리고 위에 나온
제공업체 중 하나의 **API 키**가 필요합니다(Groq는 무료 티어가 있습니다).

```bash
git clone https://github.com/LdwS123/Instonct.git && cd Instonct
sudo apt install redis-server python3-venv espeak-ng mpv alsa-utils      # 음성 + 음악 (선택 사항)
python3 -m venv ~/bots/venv && ~/bots/venv/bin/pip install -r bots/telegram-search/requirements.txt
mkdir -p ~/bots/telegram-search && cp -r bots/telegram-search/bot.py bots/telegram-search/instonct ~/bots/telegram-search/

cat > ~/bots/.env <<'EOF'
TELEGRAM_TOKEN=...
LLM_API_KEY=...
# 선택 사항: LLM_BASE_URL, LLM_MODELS, GEMINI_API_KEY, STT_LANGUAGE=en, WA_* (WhatsApp)
EOF
chmod 600 ~/bots/.env

sudo cp systemd/bot-telegram.service /etc/systemd/system/    # 먼저 User=와 경로를 수정하세요
sudo systemctl daemon-reload && sudo systemctl enable --now bot-telegram
```

그런 다음 Telegram에서 봇을 열고 `/start`를 보내세요. 선택 사항: 브라우저용으로 `~/lightpanda/lightpanda`에 Lightpanda,
메일용으로 `MAIL_USER` / `MAIL_PASS` / `MAIL_HOST`, Google Calendar용으로 `scripts/google-auth.py`.

## 이런 걸 찾고 계셨나요...

Instant AI · Instinct AI alternative · 오픈 소스 Instinct AI · 셀프 호스팅 개인 AI 에이전트 · 문자로 부리는 AI 비서 ·
WhatsApp AI 비서 · Telegram AI 비서 · WhatsApp AI 에이전트 · OpenClaw alternative · 이메일을 읽고
일정을 관리하는 AI 에이전트 · Raspberry Pi나 오래된 Mac mini에서 AI 에이전트 돌리기 · 홈 서버 AI 비서 · Groq 에이전트 · Gemini 에이전트 ·
Ollama 에이전트 · OpenRouter 에이전트 · Lightpanda 브라우저 에이전트 · 웹 페이지를 CSV로 긁어오는 AI 스크레이퍼 · 클라우드 없는 프라이빗 AI 비서.

---

<sub>Instonct는 독립 프로젝트이며, Instinct AI 또는 Spear Street Technology, Inc.와 제휴, 보증, 후원 관계가 없습니다.
모든 상표는 해당 소유자에게 있습니다. MIT 라이선스.</sub>
