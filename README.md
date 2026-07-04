# KoeKichi

Whisper によるローカル完結の音声入力ユーティリティです。グローバルホットキーで録音し、文字起こし結果をアクティブなアプリケーションのカーソル位置へ挿入します。

音声・テキストが外部に送信されることはありません。ネットワーク通信が発生するのは次の 2 つの場合のみです。

- 初回起動時の Whisper モデルの自動ダウンロード(HuggingFace Hub)
- 明示的に有効化した場合のローカル Ollama との通信(既定は無効。§Ollama 連携)

## 特徴

- **バックエンド自動選択**: Mac (Apple Silicon) では mlx-whisper(GPU/Metal)、それ以外では faster-whisper(CPU, int8)を自動選択
- **ハルシネーション対策**: VAD ゲート、確信度/圧縮率によるセグメント棄却、定型文ブラックリスト、プロンプトエコー棄却を多段適用。無音時に「ご視聴ありがとうございました」等が入力される事故を防ぎます
- **句読点整形**: 発話内容そのものには手を加えず、句読点・空白のみをルールベースで整える
- **ユーザー辞書**: 固有名詞などの認識精度向上(プロンプト注入)と誤認識の強制置換
- **LLM 整形(オプション)**: ローカル Ollama による句読点校正。「内容不変ガード」付き

## 動作環境

| | Mac | Windows |
|---|---|---|
| OS | macOS 13+ / **Apple Silicon (arm64) のみ** | Windows 10 / 11 x64 |
| Python | 3.12(uv が自動取得) | 同左 |
| GPU | Apple Silicon GPU (MLX) | 不要(CPU のみで動作可) |
| 既定モデル | mlx-community/whisper-large-v3-turbo | small (int8) |

Intel Mac は非対応です(起動時にエラー終了します)。

## インストール

1. [uv](https://docs.astral.sh/uv/) をインストール

   ```bash
   # Mac
   curl -LsSf https://astral.sh/uv/install.sh | sh
   # Windows (PowerShell)
   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
   ```

2. リポジトリを取得(git clone または zip を展開)

   ```bash
   git clone <このリポジトリのURL> koekichi
   cd koekichi
   ```

3. 依存関係をインストールして起動

   ```bash
   uv sync
   uv run koekichi
   ```

Windows も同一手順です(uv が Python 3.12 と依存関係をすべて自動で用意します)。初回起動時は Whisper モデルのダウンロードが行われます(Mac 既定モデルは約 1.6GB)。

## スタンドアロン版(Python 環境不要)

Python / uv のセットアップなしでダブルクリックで使えるビルド済みアプリも配布しています(ビルド手順は [`packaging/BUILD.md`](packaging/BUILD.md) 参照)。

### macOS: DMG からのインストール

1. `KoeKichi-<ver>-mac-arm64.dmg` をダブルクリックしてマウント
2. `KoeKichi.app` を `Applications`(同梱されているシンボリックリンク)へドラッグ&ドロップ
3. `/Applications/KoeKichi.app` を起動

**Gatekeeper に「開発元を確認できません」と表示される場合**(ad-hoc 署名のみで Apple の公証は行っていないため、初回起動時に表示されることがあります):

- **方法A**: Finder で `KoeKichi.app` を **右クリック(または Control+クリック)→「開く」** を選択し、表示されるダイアログで「開く」を選択(2回目以降は通常どおりダブルクリックで起動できます)
- **方法B**: ターミナルで隔離属性を削除

  ```bash
  xattr -dr com.apple.quarantine /Applications/KoeKichi.app
  ```

初回起動時は §11.4 の初回セットアップウィザードが表示され、モデルダウンロードと権限設定(マイク・アクセシビリティ・入力監視)を案内します。Apple Silicon (arm64) 専用です。

### Windows: Setup.exe からのインストール

1. `KoeKichi-Setup-<ver>.exe` を実行し、インストーラの指示に従う(スタートメニュー登録・「スタートアップに登録」を任意で選択可能)
2. インストール完了後、スタートメニューから `KoeKichi` を起動

**SmartScreen に「Windows によって PC が保護されました」と表示される場合**(コード署名を行っていないため表示されることがあります): 「詳細情報」をクリックし、「実行」を選択してください。

初回起動時は初回セットアップウィザードが表示されます。

## macOS の権限設定(必須)

KoeKichi のホットキーとペースト機能には、システムの権限が必要です。

### 必要な権限

「システム設定 → プライバシーとセキュリティ」で、**ターミナル(または koekichi を起動するアプリ)**に以下の 3 つの権限を付与してください。

1. **マイク** — 録音に必要
2. **アクセシビリティ** — ペーストキー(Cmd+V)の送出に必要
3. **入力監視** — グローバルホットキーの検出に必要

権限を付与した後、ターミナル(および koekichi)の再起動が必要な場合があります。初回起動時は初回セットアップウィザードで権限の確認を案内します。

### スタンドアロン版で再ビルド後に権限が消える場合

Python パッケージ版を `uv run koekichi` で実行している場合は無視してください。

**PyInstaller でビルドした `.app`** を再ビルドすると、macOS の仕様により「入力監視」「アクセシビリティ」の権限が自動的に消去されます。これは `.app` の code identity が毎回変わるため(ad-hoc 署名)です。

**1回限りの初期セットアップで以後の権限を維持できます:**

```bash
bash packaging/make_signing_cert.sh
```

このコマンドで、ログインキーチェーンに安定した自己署名証明書を作成します(初回実行時のみキーチェーンパスワード入力が必要)。その後 `bash packaging/build_mac.sh` でビルドすると、同一の証明書で署名され、付与した権限は再ビルド後も維持されます。

もし権限が消えてしまった場合は、システム設定の該当する欄で KoeKichi を一度「−」で削除してから「+」で再追加してください。

## 使い方

1. `uv run koekichi` で起動すると、メニューバー(タスクトレイ)にマイクアイコンが表示されます
2. **Option(Alt)キーを素早く2回押す**と録音開始(画面下部にオーバーレイが表示されます)
3. 話し終えたら再度 **Option(Alt)2回押し**で停止 → 認識結果がカーソル位置に挿入されます
4. 録音中に **Esc** を押すと録音を破棄(何も挿入されません)

### ホットキーの変更

トレイメニューの「**ホットキー設定…**」から変更できます(アプリ再起動不要)。

- **修飾キー2回押し**(既定): Option / Ctrl / Shift / Cmd(Windows は Alt / Ctrl / Shift / Win)から選択。単独の2回押しのみが対象で、Option+C のような組み合わせ入力の一部では発火しません
- **キーコンビネーション**: pynput 形式(例 `<ctrl>+<shift>+<space>`)を直接入力。「トグル」(押すたび開始⇄停止)または「押している間だけ」(push-to-talk)を選べます

### トレイメニュー

| 項目 | 説明 |
|---|---|
| 録音開始/停止 | ホットキーと同じ操作 |
| 有効 | チェックを外すとホットキーを無視(素通し) |
| ホットキー設定… | ホットキー設定ダイアログを開く |
| 設定ファイルを開く | config.json を既定アプリで開く |
| 辞書を開く | dictionary.json を開く |
| 辞書を再読み込み | 辞書を即時リロード |
| ログを開く | koekichi.log を開く |
| 終了 | アプリを終了 |

## 設定 (config.json)

場所: Mac `~/Library/Application Support/KoeKichi/config.json`、Windows `%APPDATA%\KoeKichi\config.json`(初回起動時に既定値で自動生成)。

主要項目:

| キー | 既定値 | 説明 |
|---|---|---|
| `language` | `"ja"` | 認識言語(固定。自動判定なし) |
| `hotkey.type` | `"double-tap"` | `double-tap`(修飾キー2回押し)/ `combo`(キーコンビネーション) |
| `hotkey.double_tap_key` | `"alt"` | 2回押し対象: `alt` / `ctrl` / `shift` / `cmd` |
| `hotkey.double_tap_window_ms` | `400` | 1回目→2回目の release 間の許容時間 |
| `hotkey.combo` | `"<ctrl>+<shift>+<space>"` | type=combo 時のキー(pynput 形式) |
| `hotkey.mode` | `"toggle"` | type=combo 時: `toggle` / `hold`(押している間のみ録音) |
| `engine.backend` | `"auto"` | `auto` / `mlx` / `faster-whisper` |
| `engine.model` | `"auto"` | モデル名または HF リポジトリ名 |
| `engine.beam_size` | `1` | 速度優先。精度優先なら `5` |
| `audio.max_duration_s` | `120` | 最大録音秒数(到達で自動停止) |
| `format.ensure_final_period` | `false` | 末尾に句点が無ければ付加 |
| `format.llm.enabled` | `false` | Ollama 整形の有効化(§Ollama 連携) |
| `hallucination.blacklist_extra` | `[]` | 追加のハルシネーション定型文 |
| `log_level` | `"INFO"` | ログレベル |

設定ファイルに無いキーは既定値で補完されます。変更後はアプリを再起動してください。

## ユーザー辞書 (dictionary.json)

設定と同じディレクトリの `dictionary.json` を編集します。

```json
{
  "entries": [
    {
      "word": "Anthropic",
      "reading": "アンソロピック",
      "corrections": ["アンスロピック", "アンソロピク"]
    }
  ]
}
```

- `word`(必須): 正しい表記。認識プロンプトに注入され、認識精度が向上します
- `reading`(任意): 読み仮名(将来用。v1 では未使用)
- `corrections`(任意): 誤認識された文字列を `word` へ強制置換します

**反映タイミング**: 録音開始時にファイルの更新を自動検出してリロードします(トレイメニューから即時リロードも可能)。

**重要な制限(蒸留系モデル使用時)**: `kotoba-whisper` や `distil-whisper` 等の蒸留(distilled)モデルを使っている場合、`word` によるプロンプト注入は**自動的に無効化されます**(空文字列を含むプロンプトを渡すと誤変換・文章の欠落が起きることが実測で確認されているため)。この場合も `corrections` による強制置換は引き続き有効に機能します。標準の `large-v3` 系モデル(Mac の既定)ではこの制限はありません。

## Ollama 連携(オプション)

ローカル LLM で句読点をより自然に整えたい場合に使用します。

1. [Ollama](https://ollama.com/) をインストールし、モデルを取得

   ```bash
   ollama pull qwen2.5:3b-instruct
   ```

2. config.json で有効化

   ```jsonc
   "format": {
     "llm": {
       "enabled": true,
       "endpoint": "http://127.0.0.1:11434",
       "model": "qwen2.5:3b-instruct",
       "timeout_s": 6
     }
   }
   ```

**内容不変ガード**: LLM の出力は句読点・空白・記号を除いた本文が入力と完全一致するか検査され、一致しない場合(単語の追加・削除・言い換えがあった場合)は LLM の結果を破棄してルール整形のみの結果を採用します。タイムアウトや接続失敗時も同様にフォールバックし、入力が止まることはありません。

## トラブルシュート

- **診断モード**: `uv run koekichi --check` — 設定ロード・エンジン選択・UI 構築を検査し、正常なら「OK」を表示します
- **ログ**: Mac `~/Library/Application Support/KoeKichi/koekichi.log`、Windows `%APPDATA%\KoeKichi\koekichi.log`
- **ホットキーが効かない**(Mac): 「入力監視」権限がターミナルに付与されているか確認し、付与後にターミナルを再起動してください
- **貼り付けされない**(Mac): 「アクセシビリティ」権限を確認してください
- **録音されない / 無音になる**: 「マイク」権限と、config.json の `audio.device`(`null` = 既定入力デバイス)を確認してください

## Windows 手動テストチェックリスト

- [ ] ホットキーで録音開始/停止、オーバーレイ表示
- [ ] メモ帳へ日本語が挿入される。クリップボードが復元される
- [ ] 無音で停止 → 何も挿入されない
- [ ] 辞書登録語が正しく変換される
- [ ] 一時無効化(トレイ)でホットキーが素通しになる
- [ ] Esc で録音破棄
- [ ] CPU のみ(GPU なし)で性能目標(5秒発話の停止→挿入完了 < 3.0s)を満たす

## 既知の制限

- リアルタイム逐次挿入(ストリーミング認識)は非対応。録音停止後に一括認識します
- Intel Mac は非対応(Apple Silicon のみ)
- 言語の自動判定は非対応(設定で固定、既定 `ja`)
- 設定・辞書の GUI 編集画面はありません(JSON を直接編集)
- 管理者権限で動作しているウィンドウ(Windows の昇格プロセス等)へは OS の制約により挿入できない場合があります
- クリップボード経由で挿入するため、クリップボード履歴ツールに認識結果が残ることがあります
- (macOS)起動中のキーボードレイアウト切替は貼り付けに反映されません(再起動で反映)

## ライセンス

MIT License — 詳細は [LICENSE](LICENSE) を参照してください。
