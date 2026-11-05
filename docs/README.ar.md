<div dir="rtl">

<p align="center">
  <img src="../assets/logo.svg" alt="Instonct (Instant AI) - بديل Instinct AI ذاتي الاستضافة، يعمل على جهاز Mac mini قديم" width="760">
</p>

<p align="center">
  <b>Instonct، مساعدك <i>Instant AI</i>: بديل <a href="../README.md#instinct-ai-vs-instonct">Instinct AI</a> ذاتي الاستضافة.</b><br>
  وكيل ذكاء اصطناعي شخصي تراسله كما تراسل صديقًا، عبر <b>WhatsApp</b> أو <b>Telegram</b>، ويعمل على جهاز Mac mini القديم الخاص بك.<br>
  بلا قائمة دعوات. بلا سحابة تخص غيرك. بريدك وتقويمك وبياناتك تبقى في بيتك.
</p>

<p align="center">
  <a href="../README.md">English</a> ·
  <a href="README.zh-CN.md">简体中文</a> ·
  <a href="README.ko.md">한국어</a> ·
  <a href="README.ja.md">日本語</a> ·
  <a href="README.es.md">Español</a> ·
  <a href="README.pt-BR.md">Português</a> ·
  <a href="README.fr.md">Français</a> ·
  <a href="README.de.md">Deutsch</a> ·
  <a href="README.ru.md">Русский</a> ·
  <a href="README.hi.md">हिन्दी</a> ·
  <b>العربية</b>
</p>

> **لا صلة لهذا المشروع بشركة Instinct AI ولا بشركة Spear Street Technology.** اسم "Instinct" ملك لصاحبه.
> Instonct مشروع هواية مستقل. الاسم محاكاة ساخرة مقصودة، وهذه الصفحة
> لا تقارنه بـ Instinct AI إلا ليجده من يبحث عن بديل.

---

**Instonct** وكيل **ذكاء اصطناعي شخصي** مفتوح المصدر وذاتي الاستضافة. تراسله عبر **WhatsApp أو Telegram**
(نصًا أو رسالة صوتية) فينجز لك المهام: يقرأ بريدك ويصوغ ردودك، ويدير تقويم Google الخاص بك، ويضبط التذكيرات
وقوائم المهام، ويتصفح الويب ويملأ نماذجه، ويستخرج بيانات صفحة إلى ملف CSV، ويراقب صفحة وينبّهك عندما
تتغير، ويشغّل الموسيقى، بل وينفّذ أوامر الشل على الجهاز الذي يعمل عليه.

يعمل على مدار الساعة على جهاز **Mac mini من عام 2010** (معالج Core 2 Duo، ذاكرة 4.6 GB، نظام Lubuntu). وما دام يعمل هناك، فهو يعمل على
أي جهاز تقريبًا: Raspberry Pi، أو حاسوب محمول قديم، أو خادم VPS رخيص.

## ماذا يستطيع أن يفعل

| المجال | ماذا يمكنك أن تقول |
|---|---|
| **البريد** | "هل وصلني بريد مهم اليوم؟"، "رد على بول وقل له إنني سأحضر." لا يرسل شيئًا إلا بعد أن تضغط **نعم**. |
| **التقويم** | "ضع موعد طبيب الأسنان يوم الخميس الساعة 3 مساءً"، "أضف اجتماع Google Meet مع ماري". ينبّهك إلى التعارضات. |
| **المتصفح** | "افتح news.ycombinator.com وأعطني ملف CSV بأعلى 30 عنوانًا"، "سجّل دخولي إلى موقع النادي الرياضي". |
| **المراقبة** | "نبّهني عندما تظهر في هذه الصفحة عبارة *متوفر في المخزون*." يفحصها كل 10 دقائق أو أكثر، ولا يرسل تنبيهًا إلا عند حدوث تغيير. |
| **الذاكرة** | يتذكر تفضيلاتك بشكل دائم، ويتعلم عندما تصحح له. |
| **الروتين اليومي** | ملخص صباحي (جدول اليوم، البريد، الطقس، أهم أولوياتك)، وتذكيرات، ومهام مجدولة. |
| **الصوت** | يستقبل رسائل صوتية (Whisper)، ويرد برسائل صوتية أو بإجابات منطوقة. |
| **الملفات** | أرسل إليه صورة أو ملف PDF أو CSV واسأله عنه. ويستطيع أن يرسل لك ملفات أيضًا. |
| **المنزل** | الموسيقى، وريموت التلفزيون، والصوت، وحالة الخادم، وأوامر الشل (بعد تأكيدك). |
| **أي لغة** | يرد بلغة كتابتك أو كلامك. |

وله شخصية كذلك: إجابات قصيرة، وتوصية واحدة واضحة، بلا حشو. اسمه *Steve*.

## اختر عقلك: أي نموذج، أي مزوّد

يتحدث Instonct مع أي **واجهة برمجية متوافقة مع OpenAI**، فلست مقيّدًا بشركة واحدة. اضبط ثلاثة أسطر في ملف `.env`:

```bash
LLM_BASE_URL=https://api.groq.com/openai/v1     # القيمة الافتراضية
LLM_API_KEY=...
LLM_MODELS=openai/gpt-oss-120b,openai/gpt-oss-20b,qwen/qwen3.8-27b    # تُجرَّب بهذا الترتيب
```

| المزوّد | `LLM_BASE_URL` |
|---|---|
| Groq (الافتراضي، سريع، وله باقة مجانية) | `https://api.groq.com/openai/v1` |
| OpenRouter (مئات النماذج) | `https://openrouter.ai/api/v1` |
| OpenAI | `https://api.openai.com/v1` |
| Together AI | `https://api.together.xyz/v1` |
| Mistral | `https://api.mistral.ai/v1` |
| Cerebras | `https://api.cerebras.ai/v1` |
| Ollama / LM Studio (محلي 100%، بلا مفتاح) | `http://localhost:11434/v1` |

استخدم أسماء النماذج تمامًا كما يكتبها مزوّدك، واختر نماذج تدعم استدعاء الأدوات.

- **التبديل الفوري**: أرسل `/model` لعرض القائمة، و`/model 2` لاستخدام النموذج رقم 2 أولًا، و`/model auto` للعودة إلى الوضع التلقائي.
- **التحويل التلقائي عند التعطل**: إذا بلغ نموذج حد الاستخدام أو توقف عن العمل، يتولى النموذج التالي المهمة من تلقاء نفسه.
- **شبكة أمان اختيارية**: أضف `GEMINI_API_KEY` فيجيب Google Gemini عندما يتعطل مزوّدك الرئيسي (ويقرأ الصور أيضًا).
  وبدونه يعمل Instonct بكفاءة على مزوّد واحد.
- **الرسائل الصوتية**: تُفرَّغ نصيًا عبر واجهة Whisper (`STT_MODEL` و`STT_BASE_URL` و`STT_LANGUAGE`، ومن المزوّد نفسه افتراضيًا).

## WhatsApp أم Telegram؟

كلاهما يعمل في الوقت نفسه، بالعقل والذاكرة وقواعد الأمان ذاتها.

| | Telegram | WhatsApp |
|---|---|---|
| الإعداد | دقيقتان عبر @BotFather | حساب مطوّر لدى Meta، ورقم هاتف، ورمز وصول (نحو 30 دقيقة) |
| يحتاج إلى عنوان عام | لا (البوت هو من يتصل) | نعم (Meta هي من تتصل بخادمك: ويصلح Tailscale Funnel لذلك) |
| أزرار نعم / لا، والصوت، والملفات | نعم | نعم |
| لوحة ريموت التلفزيون، وحفظ كلمات المرور عبر `/site` | نعم | على Telegram فقط (عن قصد، انظر قسم الأمان) |
| الرسائل التي يرسلها البوت من تلقاء نفسه (التذكيرات) | دائمًا | فقط خلال 24 ساعة من آخر رسالة منك |
| مثبّت أصلًا على هاتفك | ربما | شبه مؤكد |

**نصيحة صريحة**: ابدأ بـ Telegram، فهو أبسط وأكثر أمانًا. وأضف WhatsApp عندما تريد أن تحادثه من التطبيق
الذي تستخدمه كل يوم. يعتمد Instonct على **واجهة WhatsApp Cloud API الرسمية** من Meta، ولا يستخدم أبدًا مكتبة غير رسمية، فلا
خطر على رقمك من الحظر.

### إضافة WhatsApp (اختياري)

1. في [developers.facebook.com](https://developers.facebook.com) أنشئ تطبيقًا، وأضف منتج **WhatsApp**، ودوّن
   **Phone number ID**. يكفي الرقم التجريبي المجاني للتجربة؛ ويمكنك لاحقًا ربط رقمك الخاص.
2. أنشئ رمز وصول دائمًا (رمز *System User* من إعدادات Meta Business) وانسخ **App secret**
   (إعدادات التطبيق، Basic).
3. أضف إلى `~/bots/.env` (رقمك الخاص: أرقام فقط، يبدأ برمز الدولة، بلا `+`):
   ```bash
   WA_TOKEN=...
   WA_PHONE_ID=...
   WA_APP_SECRET=...
   WA_VERIFY_TOKEN=any-secret-string-you-invent
   WA_OWNER=33612345678
   ```
4. زوّد Meta بعنوان HTTPS عام يشير إلى الـ webhook المحلي (المنفذ 8088، مربوط بالعنوان `127.0.0.1`). باستخدام Tailscale:
   `sudo tailscale funnel --bg 8088`. وسيطبع عنوانًا بصيغة `https://<machine>.<tailnet>.ts.net`.
5. في إعدادات WhatsApp داخل تطبيق Meta، اضبط **Callback URL** الخاص بالـ webhook على ذلك العنوان، و**Verify token**
   على قيمة `WA_VERIFY_TOKEN` لديك، ثم اشترك في الحقل **messages**.
6. أعد تشغيل البوت (`sudo systemctl restart bot-telegram`) وراسل رقم WhatsApp الخاص بك.

يُرفض كل طلب وارد ما لم يطابق ترويسة `X-Hub-Signature-256` سرَّ تطبيقك، ولا يرد البوت إلا على الأرقام الموجودة في
`WA_OWNER`. تتغير تسميات لوحة التحكم لدى Meta من حين لآخر؛ أما الفكرة فتبقى كما هي.
الإصدار الافتراضي للواجهة البرمجية هو `v23.0`؛ يمكنك تغييره عبر `WA_API_VERSION` إذا أوقفته Meta.

## Instinct AI مقابل Instonct

| | Instinct AI | Instonct |
|---|---|---|
| الوصول | بالدعوة فقط (بحسب التغطية الصحفية) | استنسخ المستودع وشغّله |
| أين يعمل | في سحابة شركة | **على جهازك أنت** |
| بياناتك | تُسلَّم إلى شركة ناشئة | تبقى على جهازك (Redis + ملفات محلية) |
| كيف تتحدث معه | نص، وهاتف، وWhatsApp (بحسب التغطية الصحفية) | WhatsApp أو Telegram، نصًا أو صوتًا |
| النماذج | تُختار لك | **أي مزوّد متوافق مع OpenAI**، وتبدّل بينها عبر `/model` |
| التكلفة | غير معلنة | تكفي الباقات المجانية (Groq وGemini)؛ أو محلي بالكامل مع Ollama |
| الشيفرة المصدرية | مغلقة | **هنا أمامك** |

Instinct AI منتج حقيقي يقف خلفه فريق ممول؛ أما Instonct فمشروع شخص واحد بدأ في عطلة نهاية أسبوع ثم صار أداته اليومية.
اختر Instonct إذا أردت الفكرة نفسها وزمام الأمور بيدك.

## كيف يعمل

- **العقل**: أي نموذج متوافق مع OpenAI (افتراضيًا Groq `gpt-oss-120b` / `20b` مع جهد استدلال تكيّفي)، مع نموذج Gemini احتياطي اختياري.
- **الأدوات**: يستدعي النموذج نحو 35 أداة (البريد، التقويم، المتصفح، الملفات، الموسيقى، التلفزيون، الشل...). راجع `TOOLS` في [`catalog.py`](../bots/telegram-search/instonct/catalog.py).
- **المتصفح**: [Lightpanda](https://github.com/lightpanda-io/browser)، متصفح صغير بلا واجهة (نحو 25 MB من الذاكرة) يعمل حتى على معالج من عام 2010. راجع [`webagent.py`](../bots/telegram-search/instonct/webagent.py).
- **القنوات**: Telegram عبر الاستطلاع الطويل (long polling) بلا منفذ مفتوح، وWhatsApp عبر [`whatsapp.py`](../bots/telegram-search/instonct/whatsapp.py) (webhook صغير على `127.0.0.1`).
- **الحالة**: Redis (السجل، والذاكرة، والتذكيرات، وعمليات المراقبة).
- **الوصول**: SSH + [Tailscale](https://tailscale.com)، مع إغلاق `ufw` افتراضيًا. إعداد الخادم موثّق في [`home-server.md`](home-server.md).

## الأمان، لأن وكيلًا يملك صلاحية الشل يحتاج إليه

- **خاص**: على Telegram يصبح أول شخص يرسل `/start` هو المالك الوحيد؛ وعلى WhatsApp لا يُرَدّ إلا على الأرقام الموجودة في `WA_OWNER`.
  ويُتجاهَل الجميع سواهم.
- **لا شيء خطير يحدث في الخفاء**: إرسال بريد، أو إرسال نموذج، أو حذف موعد، أو تنفيذ أمر،
  أو النقر على زر "شراء / دفع / حذف"، كلها تطلب منك أولًا الضغط على **نعم / لا**.
- **كلمات المرور لا تمر عبر النموذج أبدًا**: تُخزَّن بيانات الدخول إلى المواقع في ملف بصلاحيات `0600` وتُدخَل بشيفرة عادية.
  وحفظها متاح على Telegram فقط لأن البوت يحذف رسالتك فور ذلك (بينما يحتفظ بها WhatsApp).
- **صفحات الويب بيانات، لا أوامر**: لا يمكن لنص يوجد في صفحة أو في بريد أن يعطي تعليمات للوكيل.
- **لا وصول إلى الشبكة المحلية عبر المتصفح**: لا تُسمح إلا بعناوين `http(s)` العامة (حماية من SSRF).
- **لا أسرار في هذا المستودع**: المفاتيح تُحفظ في ملف `.env` على الخادم.

## البدء السريع

تحتاج إلى جهاز Linux، وPython 3، وRedis، و**رمز بوت Telegram** (من [@BotFather](https://t.me/BotFather))، و
**مفتاح API** واحد من أي مزوّد مذكور أعلاه (لدى Groq باقة مجانية).

```bash
git clone https://github.com/LdwS123/Instonct.git && cd Instonct
sudo apt install redis-server python3-venv espeak-ng mpv alsa-utils      # الصوت + الموسيقى (اختياري)
python3 -m venv ~/bots/venv && ~/bots/venv/bin/pip install -r bots/telegram-search/requirements.txt
mkdir -p ~/bots/telegram-search && cp -r bots/telegram-search/bot.py bots/telegram-search/instonct ~/bots/telegram-search/

cat > ~/bots/.env <<'EOF'
TELEGRAM_TOKEN=...
LLM_API_KEY=...
# اختياري: LLM_BASE_URL, LLM_MODELS, GEMINI_API_KEY, STT_LANGUAGE=en, WA_* (WhatsApp)
EOF
chmod 600 ~/bots/.env

sudo cp systemd/bot-telegram.service /etc/systemd/system/    # عدّل User= والمسارات أولًا
sudo systemctl daemon-reload && sudo systemctl enable --now bot-telegram
```

ثم افتح البوت في Telegram وأرسل `/start`. اختياريًا: ضع Lightpanda في `~/lightpanda/lightpanda` ليعمل
المتصفح، و`MAIL_USER` / `MAIL_PASS` / `MAIL_HOST` للبريد، و`scripts/google-auth.py` لتقويم Google.

## هل تبحث عن...

Instant AI · بديل Instinct AI (Instinct AI alternative) · نسخة مفتوحة المصدر من Instinct AI · وكيل ذكاء اصطناعي شخصي ذاتي الاستضافة · راسل مساعدك الذكي بالرسائل ·
مساعد ذكاء اصطناعي على WhatsApp · مساعد ذكاء اصطناعي على Telegram · وكيل ذكاء اصطناعي على WhatsApp · بديل OpenClaw (OpenClaw alternative) · وكيل ذكاء اصطناعي يقرأ بريدك الإلكتروني و
يدير تقويمك · تشغيل وكيل ذكاء اصطناعي على Raspberry Pi أو Mac mini قديم · مساعد ذكاء اصطناعي على خادم منزلي · وكيل Groq · وكيل Gemini ·
وكيل Ollama · وكيل OpenRouter · وكيل متصفح Lightpanda · أداة ذكاء اصطناعي لاستخراج بيانات الويب إلى CSV · مساعد ذكاء اصطناعي خاص، بلا سحابة.

---

<sub>Instonct مشروع مستقل، لا يرتبط بشركة Instinct AI ولا بشركة Spear Street Technology, Inc. ولا تتبناه ولا ترعاه.
جميع العلامات التجارية ملك لأصحابها. ترخيص MIT.</sub>

</div>
