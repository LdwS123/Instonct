<p align="center">
  <img src="../assets/logo.svg" alt="Instonct (Instant AI) - la alternativa autoalojada a Instinct AI, funcionando en un viejo Mac mini" width="760">
</p>

<p align="center">
  <b>Instonct, tu <i>Instant AI</i>: la <a href="../README.md#instinct-ai-vs-instonct">alternativa autoalojada a Instinct AI</a>.</b><br>
  Un agente de IA personal al que escribes como a un amigo, por <b>WhatsApp</b> o <b>Telegram</b>, funcionando en tu propio Mac mini viejo.<br>
  Sin lista de invitados. Sin la nube de nadie más. Tus correos, tu calendario y tus datos se quedan en casa.
</p>

<p align="center">
  <a href="../README.md">English</a> ·
  <a href="README.zh-CN.md">简体中文</a> ·
  <a href="README.ko.md">한국어</a> ·
  <a href="README.ja.md">日本語</a> ·
  <b>Español</b> ·
  <a href="README.pt-BR.md">Português</a> ·
  <a href="README.fr.md">Français</a> ·
  <a href="README.de.md">Deutsch</a> ·
  <a href="README.ru.md">Русский</a> ·
  <a href="README.hi.md">हिन्दी</a> ·
  <a href="README.ar.md">العربية</a>
</p>

> **Sin afiliación con Instinct AI ni con Spear Street Technology.** "Instinct" pertenece a su propietario.
> Instonct es un proyecto independiente de aficionado. El nombre es una parodia deliberada, y esta página
> lo compara con Instinct AI únicamente para que quienes buscan una alternativa puedan encontrarlo.

---

**Instonct** es un **agente de IA personal** de código abierto y autoalojado. Le escribes por **WhatsApp o Telegram**
(texto o nota de voz) y hace cosas: lee y redacta tu correo, gestiona tu Google Calendar, programa recordatorios
y tareas pendientes, navega y rellena formularios web, extrae una página a un CSV, vigila una página y te avisa cuando
cambia, pone música e incluso ejecuta comandos de shell en la máquina donde vive.

Funciona 24/7 en un **Mac mini de 2010** (Core 2 Duo, 4,6 GB de RAM, Lubuntu). Si funciona ahí, funciona en
casi cualquier cosa: una Raspberry Pi, un portátil viejo, un VPS barato.

## Qué puede hacer

| Área | Qué puedes decirle |
|---|---|
| **Correo** | "¿Algún correo importante hoy?", "Responde a Paul, dile que voy." Solo envía después de que pulses **Sí**. |
| **Calendario** | "Pon dentista el jueves a las 3 de la tarde", "Añade un Google Meet con Marie". Avisa de los conflictos. |
| **Navegador** | "Ve a news.ycombinator.com y dame un CSV con los 30 titulares principales", "Inicia sesión en la web de mi gimnasio". |
| **Vigilancia** | "Avísame cuando esta página diga *en stock*." Comprueba cada 10 minutos o más, y avisa solo si hay cambios. |
| **Memoria** | Recuerda tus preferencias para siempre, y aprende cuando lo corriges. |
| **Rutinas** | Un resumen matutino (agenda, correo, tiempo, tu prioridad n.º 1), recordatorios, tareas programadas. |
| **Voz** | Entiende notas de voz (Whisper) y responde con notas de voz o respuestas habladas. |
| **Archivos** | Envíale una foto, un PDF o un CSV y pregúntale sobre ellos. También puede devolverte archivos. |
| **Hogar** | Música, mando de la TV, volumen, estado del servidor, comandos de shell (con confirmación). |
| **Cualquier idioma** | Responde en el idioma en que le escribes o le hablas. |

También tiene personalidad: respuestas cortas, una recomendación clara, sin rodeos. Se llama *Steve*.

## Elige tu cerebro: cualquier modelo, cualquier proveedor

Instonct habla con cualquier **API compatible con OpenAI**, así que no estás atado a una sola empresa. Configura tres líneas en `.env`:

```bash
LLM_BASE_URL=https://api.groq.com/openai/v1     # el valor por defecto
LLM_API_KEY=...
LLM_MODELS=openai/gpt-oss-120b,openai/gpt-oss-20b,qwen/qwen3.8-27b    # se prueban en este orden
```

| Proveedor | `LLM_BASE_URL` |
|---|---|
| Groq (por defecto, rápido, plan gratuito) | `https://api.groq.com/openai/v1` |
| OpenRouter (cientos de modelos) | `https://openrouter.ai/api/v1` |
| OpenAI | `https://api.openai.com/v1` |
| Together AI | `https://api.together.xyz/v1` |
| Mistral | `https://api.mistral.ai/v1` |
| Cerebras | `https://api.cerebras.ai/v1` |
| Ollama / LM Studio (100 % local, sin clave) | `http://localhost:11434/v1` |

Usa los nombres de los modelos exactamente como los escribe tu proveedor, y elige modelos que admitan llamadas a herramientas (tool calling).

- **Cambia al vuelo**: envía `/model` para ver la lista, `/model 2` para usar primero el número 2, `/model auto` para volver atrás.
- **Respaldo automático**: si un modelo tiene el límite de uso alcanzado o está caído, el siguiente toma el relevo por sí solo.
- **Red de seguridad opcional**: añade `GEMINI_API_KEY` y Google Gemini responderá cuando tu proveedor principal esté caído (y además lee imágenes).
  Sin ella, Instonct funciona perfectamente con un solo proveedor.
- **Notas de voz**: se transcriben con una API de Whisper (`STT_MODEL`, `STT_BASE_URL`, `STT_LANGUAGE`, el mismo proveedor por defecto).

## ¿WhatsApp o Telegram?

Ambos funcionan, al mismo tiempo, con el mismo cerebro, la misma memoria y las mismas reglas de seguridad.

| | Telegram | WhatsApp |
|---|---|---|
| Configuración | 2 minutos con @BotFather | Cuenta de desarrollador de Meta, un número, un token (unos 30 minutos) |
| Necesita una dirección pública | No (el bot llama hacia fuera) | Sí (Meta llama a tu servidor: Tailscale Funnel sirve) |
| Botones Sí / No, voz, archivos | Sí | Sí |
| Teclado de mando de TV, guardado de contraseñas con `/site` | Sí | Solo en Telegram (a propósito, ver Seguridad) |
| Mensajes que el bot envía por iniciativa propia (recordatorios) | Siempre | Solo dentro de las 24 h posteriores a tu último mensaje |
| Ya está en tu teléfono | Quizá | Casi seguro |

**Consejo sincero**: empieza con Telegram, es más sencillo y más seguro. Añade WhatsApp cuando quieras hablarle desde la aplicación
que ya usas todos los días. Instonct usa la **API oficial de WhatsApp Cloud** de Meta, nunca una biblioteca no oficial, así que
no hay riesgo de que te bloqueen el número.

### Añadir WhatsApp (opcional)

1. En [developers.facebook.com](https://developers.facebook.com) crea una app, añade el producto **WhatsApp** y anota el
   **Phone number ID**. El número de prueba gratuito sirve para probarlo; más adelante puedes asociar tu propio número.
2. Crea un token de acceso permanente (un token de *System User* en los ajustes de Meta Business) y copia el **App secret**
   (App settings, Basic).
3. Añade a `~/bots/.env` (tu propio número: solo dígitos, con el prefijo del país primero, sin `+`):
   ```bash
   WA_TOKEN=...
   WA_PHONE_ID=...
   WA_APP_SECRET=...
   WA_VERIFY_TOKEN=any-secret-string-you-invent
   WA_OWNER=33612345678
   ```
4. Dale a Meta una dirección HTTPS pública para el webhook local (puerto 8088, enlazado a `127.0.0.1`). Con Tailscale:
   `sudo tailscale funnel --bg 8088`. Imprime una dirección `https://<machine>.<tailnet>.ts.net`.
5. En los ajustes de WhatsApp de tu app de Meta, configura la **Callback URL** del webhook con esa dirección y el **Verify token**
   con tu `WA_VERIFY_TOKEN`, y después suscríbete al campo **messages**.
6. Reinicia el bot (`sudo systemctl restart bot-telegram`) y escribe a tu número de WhatsApp.

Toda llamada entrante se rechaza a menos que su `X-Hub-Signature-256` coincida con tu app secret, y solo los números de
`WA_OWNER` reciben respuesta. Las etiquetas del panel de Meta cambian de vez en cuando; la idea sigue siendo la misma.
La versión de la API es `v23.0` por defecto; cámbiala con `WA_API_VERSION` si Meta la retira.

## Instinct AI vs Instonct

| | Instinct AI | Instonct |
|---|---|---|
| Acceso | Solo por invitación (según la prensa) | Clona el repositorio y ejecútalo |
| Dónde se ejecuta | En la nube de una empresa | **En tu propia máquina** |
| Tus datos | Entregados a una startup | Se quedan en tu equipo (Redis + archivos locales) |
| Cómo hablas con él | Texto, teléfono, WhatsApp (según la prensa) | WhatsApp o Telegram, texto o voz |
| Modelos | Elegidos por ti | **Cualquier proveedor compatible con OpenAI**, cambia con `/model` |
| Coste | No es público | Los planes gratuitos funcionan (Groq, Gemini); o totalmente local con Ollama |
| Código fuente | Cerrado | **Aquí mismo** |

Instinct AI es un producto real creado por un equipo con financiación; Instonct es el proyecto de fin de semana de una sola persona que acabó siendo su herramienta del día a día.
Elige Instonct si quieres la misma idea con las manos en el volante.

## Cómo funciona

- **Cerebro**: cualquier modelo compatible con OpenAI (Groq `gpt-oss-120b` / `20b` por defecto, con esfuerzo de razonamiento adaptativo), con Gemini como respaldo opcional.
- **Herramientas**: el modelo llama a unas 35 herramientas (correo, calendario, navegador, archivos, música, TV, shell...). Consulta `TOOLS` en [`bots/telegram-search/bot.py`](../bots/telegram-search/bot.py).
- **Navegador**: [Lightpanda](https://github.com/lightpanda-io/browser), un diminuto navegador headless (~25 MB de RAM) que funciona incluso en una CPU de 2010. Consulta [`webagent.py`](../bots/telegram-search/webagent.py).
- **Canales**: Telegram mediante long polling (sin puerto abierto), WhatsApp a través de [`whatsapp.py`](../bots/telegram-search/whatsapp.py) (un pequeño webhook en `127.0.0.1`).
- **Estado**: Redis (historial, memoria, recordatorios, vigilancias).
- **Acceso**: SSH + [Tailscale](https://tailscale.com), con `ufw` cerrado por defecto. La configuración del servidor está en [`docs/home-server.md`](home-server.md).

## Seguridad, porque un agente con acceso a un shell la necesita

- **Privado**: en Telegram, la primera persona que envía `/start` se convierte en el único propietario; en WhatsApp solo se responde a los números de `WA_OWNER`.
  A todos los demás se les ignora.
- **Nada arriesgado ocurre en silencio**: enviar correo, enviar un formulario, borrar un evento, ejecutar un comando
  o pulsar un botón de "Comprar / Pagar / Borrar" piden siempre antes una confirmación con un toque en **Sí / No**.
- **Las contraseñas nunca pasan por el modelo**: los inicios de sesión de los sitios se guardan en un archivo `0600` y los rellena código plano.
  Guardarlas solo es posible en Telegram porque el bot borra tu mensaje justo después (WhatsApp lo conservaría).
- **Las páginas web son datos, no órdenes**: el texto que aparece en una página o en un correo no puede dar instrucciones al agente.
- **Sin red local a través del navegador**: solo se permiten direcciones `http(s)` públicas (protección contra SSRF).
- **Los secretos nunca están en este repositorio**: las claves viven en un `.env` en el servidor.

## Inicio rápido

Necesitas una máquina Linux, Python 3, Redis, un **token de bot de Telegram** (de [@BotFather](https://t.me/BotFather)) y una
**clave de API** de cualquiera de los proveedores anteriores (Groq tiene un plan gratuito).

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

sudo cp systemd/bot-telegram.service /etc/systemd/system/    # edita primero User= y las rutas
sudo systemctl daemon-reload && sudo systemctl enable --now bot-telegram
```

Después abre tu bot en Telegram y envía `/start`. Opcional: Lightpanda en `~/lightpanda/lightpanda` para el
navegador, `MAIL_USER` / `MAIL_PASS` / `MAIL_HOST` para el correo, y `scripts/google-auth.py` para Google Calendar.

## ¿Buscas...?

Instant AI · alternativa a Instinct AI (Instinct AI alternative) · Instinct AI de código abierto · agente de IA personal autoalojado · escribe a tu asistente de IA ·
asistente de IA en WhatsApp · asistente de IA en Telegram · agente de IA para WhatsApp · alternativa a OpenClaw (OpenClaw alternative) · agente de IA que lee tu correo y
gestiona tu calendario · ejecutar un agente de IA en una Raspberry Pi o un Mac mini viejo · asistente de IA para servidor doméstico · agente con Groq · agente con Gemini ·
agente con Ollama · agente con OpenRouter · agente de navegador con Lightpanda · web scraper con IA a CSV · asistente de IA privado, sin nube.

---

<sub>Instonct es un proyecto independiente, sin afiliación, respaldo ni patrocinio de Instinct AI ni de
Spear Street Technology, Inc. Todas las marcas pertenecen a sus respectivos propietarios. Licencia MIT.</sub>
