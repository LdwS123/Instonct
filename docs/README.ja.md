<p align="center">
  <img src="../assets/logo.svg" alt="Instonct (Instant AI) - 古い Mac mini で動く、セルフホスト型の Instinct AI 代替" width="760">
</p>

<p align="center">
  <b>Instonct は、あなたの <i>Instant AI</i>。セルフホスト型の <a href="../README.md#instinct-ai-vs-instonct">Instinct AI 代替</a> です。</b><br>
  友だちにメッセージを送る感覚で話しかけられるパーソナル AI エージェント。<b>WhatsApp</b> でも <b>Telegram</b> でも使えて、あなた自身の古い Mac mini 上で動きます。<br>
  招待リストは不要。他人のクラウドも使いません。メールもカレンダーもデータも、すべて手元に残ります。
</p>

<p align="center">
  <a href="../README.md">English</a> ·
  <a href="README.zh-CN.md">简体中文</a> ·
  <a href="README.ko.md">한국어</a> ·
  <b>日本語</b> ·
  <a href="README.es.md">Español</a> ·
  <a href="README.pt-BR.md">Português</a> ·
  <a href="README.fr.md">Français</a> ·
  <a href="README.de.md">Deutsch</a> ·
  <a href="README.ru.md">Русский</a> ·
  <a href="README.hi.md">हिन्दी</a> ·
  <a href="README.ar.md">العربية</a>
</p>

> **Instinct AI および Spear Street Technology とは一切関係ありません。** 「Instinct」はその所有者に帰属します。
> Instonct は独立した趣味のプロジェクトです。名前は意図的なパロディであり、このページで Instinct AI と
> 比較しているのは、代替手段を探している人が見つけられるようにするためだけです。

---

**Instonct** は、オープンソースでセルフホスト型の**パーソナル AI エージェント**です。**WhatsApp または Telegram** で
(テキストでもボイスメッセージでも)話しかけると、メールの確認や下書き、Google カレンダーの管理、リマインダーや
ToDo の設定、ウェブの閲覧とフォーム入力、ページのスクレイピングによる CSV 化、ページの監視と変更時の通知、
音楽の再生まで、さらには動いているマシン上でシェルコマンドの実行までこなします。

2010 年製の **Mac mini**(Core 2 Duo、RAM 4.6 GB、Lubuntu)で 24 時間 365 日稼働しています。ここで動くなら、
ほとんどどんな環境でも動きます。Raspberry Pi、古いノートパソコン、安価な VPS などです。

## できること

| 分野 | 話しかけ方の例 |
|---|---|
| **メール** | 「今日の重要なメールはある?」「Paul に返信して、参加すると伝えて」。送信は **Yes** をタップした後だけです。 |
| **カレンダー** | 「木曜の午後 3 時に歯医者を入れて」「Marie との Google Meet を追加して」。予定の重複があれば警告します。 |
| **ブラウザ** | 「news.ycombinator.com を開いて、上位 30 件のタイトルを CSV にして」「ジムのサイトにログインして」。 |
| **監視** | 「このページに *in stock*(在庫あり)と表示されたら教えて」。10 分以上の間隔でチェックし、変化があったときだけ通知します。 |
| **メモリ** | あなたの好みをずっと覚えていて、訂正されると学習します。 |
| **ルーティン** | 朝のブリーフィング(予定、メール、天気、最優先事項)、リマインダー、定期タスク。 |
| **音声** | ボイスメッセージの入力(Whisper)、ボイスメッセージや音声での返答。 |
| **ファイル** | 写真、PDF、CSV を送って質問できます。ファイルを送り返すこともできます。 |
| **ホーム** | 音楽、テレビのリモコン、音量、サーバーの状態、シェルコマンド(確認つき)。 |
| **あらゆる言語** | 書いた言語、話した言語で答えてくれます。 |

性格もあります。答えは短く、おすすめは明確に一つ、無駄話はなし。名前は *Steve* です。

## 頭脳を選ぶ:どのモデルでも、どのプロバイダーでも

Instonct は **OpenAI 互換 API** ならどれとでも通信できるので、特定の一社に縛られません。`.env` に 3 行設定するだけです。

```bash
LLM_BASE_URL=https://api.groq.com/openai/v1     # デフォルト
LLM_API_KEY=...
LLM_MODELS=openai/gpt-oss-120b,openai/gpt-oss-20b,qwen/qwen3.8-27b    # この順に試行
```

| プロバイダー | `LLM_BASE_URL` |
|---|---|
| Groq(デフォルト、高速、無料枠あり) | `https://api.groq.com/openai/v1` |
| OpenRouter(数百のモデル) | `https://openrouter.ai/api/v1` |
| OpenAI | `https://api.openai.com/v1` |
| Together AI | `https://api.together.xyz/v1` |
| Mistral | `https://api.mistral.ai/v1` |
| Cerebras | `https://api.cerebras.ai/v1` |
| Ollama / LM Studio(100% ローカル、キー不要) | `http://localhost:11434/v1` |

モデル名はプロバイダーの表記どおりに指定し、ツール呼び出し(tool calling)に対応したモデルを選んでください。

- **その場で切り替え**:`/model` を送ると一覧が表示され、`/model 2` で 2 番を最優先に、`/model auto` で元に戻ります。
- **自動フォールバック**:モデルがレート制限を受けたりダウンしたりしても、次のモデルが自動で引き継ぎます。
- **オプションのセーフティネット**:`GEMINI_API_KEY` を追加すると、メインのプロバイダーが落ちたときに Google Gemini が応答します(画像の読み取りにも対応)。
  なくても、Instonct は単一のプロバイダーで問題なく動きます。
- **ボイスメッセージ**:Whisper API で文字起こしします(`STT_MODEL`、`STT_BASE_URL`、`STT_LANGUAGE`。デフォルトでは同じプロバイダーを使用)。

## WhatsApp と Telegram、どちらにする?

どちらも同時に使え、頭脳、メモリ、安全ルールも共通です。

| | Telegram | WhatsApp |
|---|---|---|
| セットアップ | @BotFather で 2 分 | Meta 開発者アカウント、電話番号、トークンが必要(約 30 分) |
| 公開アドレスの要否 | 不要(ボット側から接続) | 必要(Meta があなたのサーバーを呼び出す。Tailscale Funnel が使えます) |
| Yes / No ボタン、音声、ファイル | 対応 | 対応 |
| テレビのリモコンキーボード、`/site` のパスワード保存 | 対応 | Telegram のみ(意図的な仕様。「安全性」を参照) |
| ボットが自発的に送るメッセージ(リマインダー) | いつでも | あなたの最後のメッセージから 24 時間以内のみ |
| すでにスマホに入っている | かもしれない | ほぼ確実に |

**正直なアドバイス**:まずは Telegram から始めましょう。そのほうがシンプルで安全です。毎日使っているアプリから
話しかけたくなったら WhatsApp を追加してください。Instonct が使うのは Meta の**公式 WhatsApp Cloud API** で、
非公式ライブラリは一切使わないので、番号が BAN されるリスクはありません。

### WhatsApp を追加する(任意)

1. [developers.facebook.com](https://developers.facebook.com) でアプリを作成し、**WhatsApp** プロダクトを追加して、
   **Phone number ID** を控えます。無料のテスト用番号で試せます。のちほど自分の番号を紐づけることもできます。
2. 永続アクセストークン(Meta Business 設定の *System User* トークン)を作成し、**App secret** をコピーします
   (アプリ設定の「ベーシック」)。
3. `~/bots/.env` に追加します(自分の番号:数字のみ、先頭は国番号、`+` なし)。
   ```bash
   WA_TOKEN=...
   WA_PHONE_ID=...
   WA_APP_SECRET=...
   WA_VERIFY_TOKEN=any-secret-string-you-invent
   WA_OWNER=33612345678
   ```
4. ローカルの Webhook(ポート 8088、`127.0.0.1` にバインド)用に、Meta へ公開 HTTPS アドレスを用意します。Tailscale なら
   `sudo tailscale funnel --bg 8088` です。`https://<machine>.<tailnet>.ts.net` というアドレスが表示されます。
5. Meta アプリの WhatsApp 設定で、Webhook の **Callback URL** にそのアドレスを、**Verify token** に
   `WA_VERIFY_TOKEN` を設定し、**messages** フィールドを購読します。
6. ボットを再起動し(`sudo systemctl restart bot-telegram`)、WhatsApp の番号にメッセージを送ります。

受信リクエストは、`X-Hub-Signature-256` がアプリシークレットと一致しない限りすべて拒否され、返信されるのは
`WA_OWNER` に登録された番号だけです。Meta のダッシュボードの表記は時々変わりますが、考え方は同じです。
API バージョンのデフォルトは `v23.0` です。Meta がこれを廃止した場合は `WA_API_VERSION` で上書きしてください。

## Instinct AI と Instonct の比較

| | Instinct AI | Instonct |
|---|---|---|
| アクセス | 招待制(報道による) | リポジトリをクローンして実行 |
| 動作場所 | 企業のクラウド | **あなた自身のマシン** |
| あなたのデータ | スタートアップに預けることになる | 手元のマシンに残る(Redis + ローカルファイル) |
| 話しかけ方 | テキスト、電話、WhatsApp(報道による) | WhatsApp または Telegram、テキストまたは音声 |
| モデル | 用意されたものを使う | **OpenAI 互換のあらゆるプロバイダー**、`/model` で切り替え |
| 費用 | 非公開 | 無料枠で動作(Groq、Gemini)。Ollama なら完全ローカルも可 |
| ソースコード | クローズド | **ここにあります** |

Instinct AI は、資金を得たチームが作った本物のプロダクトです。Instonct は、一人の週末プロジェクトが日常使いに育ったものです。
同じアイデアを、自分の手でハンドルを握って使いたいなら Instonct を選んでください。

## 仕組み

- **頭脳**:OpenAI 互換のモデルならどれでも(デフォルトは Groq の `gpt-oss-120b` / `20b`、推論の強度は適応的に調整)。オプションで Gemini へのフォールバックも可能。
- **ツール**:モデルが約 35 個のツール(メール、カレンダー、ブラウザ、ファイル、音楽、テレビ、シェルなど)を呼び出します。[`catalog.py`](../bots/telegram-search/instonct/catalog.py) の `TOOLS` を参照してください。
- **ブラウザ**:[Lightpanda](https://github.com/lightpanda-io/browser) は小さなヘッドレスブラウザ(RAM 約 25 MB)で、2010 年製の CPU でも動きます。[`webagent.py`](../bots/telegram-search/instonct/webagent.py) を参照してください。
- **チャンネル**:Telegram はロングポーリング(ポートを開けない)、WhatsApp は [`whatsapp.py`](../bots/telegram-search/instonct/whatsapp.py)(`127.0.0.1` 上の小さな Webhook)経由です。
- **状態管理**:Redis(履歴、メモリ、リマインダー、監視)。
- **接続**:SSH + [Tailscale](https://tailscale.com)、`ufw` はデフォルトで全閉。サーバーのセットアップは [`home-server.md`](home-server.md) にあります。

## 安全性:シェルを持つエージェントには必要だから

- **プライベート**:Telegram では最初に `/start` を送った人だけが唯一のオーナーになり、WhatsApp では `WA_OWNER` の番号にだけ
  返信します。それ以外の人は無視されます。
- **危険な操作が黙って実行されることはない**:メールの送信、フォームの送信、予定の削除、コマンドの実行、
  「購入 / 支払い / 削除」ボタンのクリックは、すべて先に **Yes / No** のタップで確認します。
- **パスワードがモデルを通ることはない**:サイトのログイン情報は `0600` のファイルに保存され、ただのコードが入力します。
  保存は Telegram 限定です。ボットがその直後にあなたのメッセージを削除するためです(WhatsApp では残ってしまいます)。
- **ウェブページはデータであり、命令ではない**:ページやメールの中にあるテキストが、エージェントに指示を出すことはできません。
- **ブラウザ経由でローカルネットワークには届かない**:許可されるのは公開された `http(s)` アドレスだけです(SSRF ガード)。
- **シークレットはこのリポジトリに含めない**:キーはサーバー上の `.env` に置きます。

## クイックスタート

必要なものは、Linux マシン、Python 3、Redis、**Telegram ボットトークン**([@BotFather](https://t.me/BotFather) から取得)、そして
上記のいずれかのプロバイダーの **API キー**です(Groq には無料枠があります)。

```bash
git clone https://github.com/LdwS123/Instonct.git && cd Instonct
sudo apt install redis-server python3-venv espeak-ng mpv alsa-utils      # 音声 + 音楽(任意)
python3 -m venv ~/bots/venv && ~/bots/venv/bin/pip install -r bots/telegram-search/requirements.txt
mkdir -p ~/bots/telegram-search && cp -r bots/telegram-search/bot.py bots/telegram-search/instonct ~/bots/telegram-search/

cat > ~/bots/.env <<'EOF'
TELEGRAM_TOKEN=...
LLM_API_KEY=...
# 任意: LLM_BASE_URL, LLM_MODELS, GEMINI_API_KEY, STT_LANGUAGE=en, WA_* (WhatsApp)
EOF
chmod 600 ~/bots/.env

sudo cp systemd/bot-telegram.service /etc/systemd/system/    # 先に User= とパスを編集
sudo systemctl daemon-reload && sudo systemctl enable --now bot-telegram
```

あとは Telegram で自分のボットを開き、`/start` を送ってください。オプションとして、ブラウザ用に `~/lightpanda/lightpanda` へ
Lightpanda を置き、メール用に `MAIL_USER` / `MAIL_PASS` / `MAIL_HOST` を設定し、Google カレンダー用に
`scripts/google-auth.py` を使います。

## こんなものをお探しなら...

Instant AI · Instinct AI alternative(Instinct AI の代替)· オープンソースの Instinct AI · セルフホスト型パーソナル AI エージェント · テキストで話しかけられる AI アシスタント ·
WhatsApp の AI アシスタント · Telegram の AI アシスタント · WhatsApp AI エージェント · OpenClaw alternative(OpenClaw の代替)· メールを読んで
カレンダーを管理してくれる AI エージェント · Raspberry Pi や古い Mac mini で動かす AI エージェント · ホームサーバー AI アシスタント · Groq エージェント · Gemini エージェント ·
Ollama エージェント · OpenRouter エージェント · Lightpanda ブラウザエージェント · CSV にしてくれる AI ウェブスクレイパー · クラウド不要のプライベート AI アシスタント。

---

<sub>Instonct は独立したプロジェクトであり、Instinct AI や Spear Street Technology, Inc. と提携しておらず、
承認も後援も受けていません。すべての商標はそれぞれの所有者に帰属します。MIT ライセンス。</sub>
