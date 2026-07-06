# KoeKichi 仕様書 (v1.3.1)

Whisper によるローカル完結の音声入力ユーティリティ。グローバルホットキーで録音し、文字起こし結果をアクティブなアプリケーションのカーソル位置へ挿入する(AquaVoice 型のワークフロー)。ネットワーク送信は行わない(モデルの初回ダウンロードと、明示的に有効化した場合のローカル Ollama 通信を除く)。

## 1. 目標と非目標

### 目標
1. 日本語中心の音声入力。精度と速度の両立(§15 の性能目標)。
2. ハルシネーション(無音時の「ご視聴ありがとうございました」等)による誤入力の排除(§8)。
3. 出力の軽い整形 — 特に句読点。**発話内容そのものには手を加えない**(§9)。
4. ユーザー辞書による認識精度向上(§10)。
5. Mac (Apple Silicon のみ) / Windows 10・11 x64 (CPU のみで動作可能) の両対応。
6. MIT ライセンスで配布可能な構成(依存もすべて MIT/BSD/Apache 系で統一)。

### 非目標(v1 では実装しない)
- 発話中のリアルタイム逐次挿入(ストリーミング認識)。録音停止後に一括認識する。
- GUI の設定画面(config.json は JSON ファイルを直接編集。トレイメニューから開ける)。**辞書編集は v1.4 で GUI 化した(§11.5)**。
- インストーラ(.dmg / .msi)。ソース配布 + uv によるセットアップ。
- 多言語自動判定。言語は設定で固定(既定 `ja`)。

## 2. 対応環境

| | Mac | Windows |
|---|---|---|
| OS | macOS 13+ / Apple Silicon (arm64) のみ | Windows 10/11 x64 |
| Python | 3.12 (uv で固定管理) | 同左 |
| ASR バックエンド既定 | mlx-whisper (Metal/GPU) | faster-whisper (CPU, int8) |
| 既定モデル | `mlx-community/whisper-large-v3-turbo` | `small` |
| GPU | Apple Silicon GPU (MLX) | 不要(CUDA があれば設定で利用可) |

- Mac で Intel を検出した場合(`platform.machine() != "arm64"`)は起動時にエラーメッセージを出して終了する。
- バックエンドは設定 `engine.backend` = `auto | mlx | faster-whisper` で切替可能。`auto` は Mac(arm64)→mlx、それ以外→faster-whisper。

## 3. アーキテクチャ / ディレクトリ構成

```
koekichi/
  LICENSE                 # MIT
  README.md
  pyproject.toml          # uv/pip 対応。プラットフォーム条件付き依存
  SPEC.md
  koekichi/
    __init__.py           # __version__
    __main__.py           # python -m koekichi
    app.py                # エントリポイント。Qt アプリ、状態機械、各部品の接続
    config.py             # 設定のロード/保存/既定値/検証
    paths.py              # OS別の設定ディレクトリ解決
    audio.py              # 録音 (sounddevice)、レベル計算、WAV化
    vad.py                # webrtcvad による発話ゲート・端点トリム
    engine/
      __init__.py         # get_engine(config) ファクトリ
      base.py             # EngineBase 抽象クラス
      fw.py               # faster-whisper バックエンド
      mlx.py              # mlx-whisper バックエンド (darwin/arm64 のみ import)
    antihallucination.py  # §8 のフィルタ群
    dictionary.py         # ユーザー辞書 (§10)
    prompt.py             # initial_prompt の構築 (§9.1)
    formatter.py          # ルールベース整形 (§9.2)
    llm_format.py         # Ollama 整形 + 内容不変ガード (§9.3)
    inject.py             # テキスト挿入。OS別実装を内包 (§12)
    hotkey.py             # グローバルホットキー。pynput (§13)
    ui/
      overlay.py          # フローティングオーバーレイ (§11.1)
      tray.py             # タスクトレイ/メニューバー (§11.2)
  tests/
    test_formatter.py
    test_antihallucination.py
    test_dictionary.py
    test_prompt.py
    test_config.py
    test_llm_guard.py
    test_engine_integration.py   # @pytest.mark.integration (Mac実機のみ)
    data/                        # テスト用固定データ
```

### スレッドモデル
- **メインスレッド**: Qt イベントループ(オーバーレイ・トレイ)。
- **hotkey スレッド**: pynput listener。イベントは Qt Signal 経由でメインへ。
- **audio コールバック**: sounddevice の内部スレッド。リングバッファへの追記のみ。
- **worker スレッド**: 文字起こし〜整形〜挿入を実行(QThread または threading.Thread 1本)。メインスレッドで ASR を実行してはならない。
- モデルはアプリ起動時に worker スレッドでプリロードし、常駐させる(§15)。

### 状態機械

```
IDLE --(hotkey発火)--> RECORDING --(hotkey再発火/キー解放)--> TRANSCRIBING --> INSERTING --> IDLE
RECORDING --(Esc)--> IDLE (録音破棄)
RECORDING --(最大録音時間到達)--> TRANSCRIBING
任意状態 --(エラー)--> IDLE (オーバーレイに短くエラー表示)
```

- TRANSCRIBING 中のホットキーは無視する(再入禁止)。
- 最大録音時間: `audio.max_duration_s` (既定 120)。

## 4. 依存ライブラリ

| ライブラリ | 用途 | 条件 |
|---|---|---|
| faster-whisper >= 1.0 | ASR (CTranslate2) | 全プラットフォーム |
| mlx-whisper | ASR (Apple GPU) | `sys_platform == 'darwin' and platform_machine == 'arm64'` |
| sounddevice | 録音 | 全 |
| webrtcvad-wheels | VAD | 全 |
| numpy | 音声バッファ | 全 |
| PySide6 | UI | 全 |
| pynput | ホットキー・キー送出 | 全 |
| pyperclip | クリップボード | 全 |
| requests | Ollama 通信 | 全(未使用時は import しない) |
| pytest | テスト | dev |
| nvidia-cublas-cu12 / nvidia-cudnn-cu12 | CUDA ランタイム(pip ホイール) | optional-dependencies `gpu`。`sys_platform == 'win32'` のみ。`uv sync --extra gpu` で導入。システムへの CUDA Toolkit インストール不要(§7.2 の DLL 探索が bin ディレクトリを直接登録) |

pyproject.toml の `requires-python = ">=3.12,<3.13"`。

## 5. 設定ファイル仕様

- 置き場所: Mac `~/Library/Application Support/KoeKichi/config.json`、Windows `%APPDATA%\KoeKichi\config.json`。辞書 `dictionary.json`、ログ `koekichi.log` も同ディレクトリ。
- 初回起動時に既定値で自動生成する。既存ファイルに無いキーは既定値で補完(マージ)し、未知キーは警告ログのみで無視。
- **`load_config()` が返す dict は、既定値スキーマ(`DEFAULT_CONFIG`)とネストされた dict オブジェクトを一切共有しない独立コピーであること(v1.2・必須)**。`DEFAULT_CONFIG.copy()` のような浅いコピーは、`loaded` 側で上書きされなかったセクション(例: ユーザーが `engine` を触っていない場合の `engine` サブ dict)がモジュールレベルの `DEFAULT_CONFIG` と同一オブジェクトのまま返るバグを生む(呼び出し側が設定を in-place で書き換えると `DEFAULT_CONFIG` 自体が汚染される)。`copy.deepcopy` を用いること。
- スキーマ(既定値):

```jsonc
{
  "language": "ja",
  "engine": {
    "backend": "auto",            // auto | mlx | faster-whisper
    "model": "auto",              // auto | モデル名/HFリポジトリ名
    "device": "auto",             // faster-whisper: auto|cpu|cuda。autoはcpu
    "compute_type": "int8",       // faster-whisper 用
    "beam_size": 1,               // 速度優先。精度優先なら 5
    "cpu_threads": 0              // 0 = 自動 (物理コア数)
  },
  "hotkey": {
    "type": "double-tap",         // double-tap | combo
    "double_tap_key": "alt",      // alt | ctrl | shift | cmd (type=double-tap 時)
    "double_tap_window_ms": 400,  // 1回目の release から 2回目の release までの許容時間
    "hold_to_record": true,       // type=double-tap 時のみ有効。長押し(押している間だけ録音)にも対応(v1.3 で既定 true に変更)
    "hold_threshold_ms": 300,     // 長押しと判定するしきい値
    "mode": "toggle",             // type=combo 時のみ有効: toggle | hold
    "combo": "<ctrl>+<shift>+<space>"  // type=combo 時。pynput GlobalHotKeys 形式
  },
  "audio": {
    "device": null,               // null = 既定入力デバイス
    "sample_rate": 16000,
    "max_duration_s": 120,
    "idle_stream": "running",     // running=常駐(開始<5ms, インジケータ常時) | stopped=待機停止(開始~140ms)
    "pre_roll_ms": 200            // 常駐時のみ: 録音開始直前の取り込み(語頭欠け防止)。0で無効
  },
  "vad": {
    "aggressiveness": 2,          // webrtcvad 0-3
    "min_speech_ms": 300,         // これ未満の発話は無視
    "min_speech_ratio": 0.10,     // 3000ms超の録音にのみ適用する発話比率ゲート(§8-H1b)
    "pad_ms": 200                 // トリム時に前後へ残す余白
  },
  "format": {
    "rules_enabled": true,
    "normalize_ja_punct": true,   // ，．→ 、。
    "ensure_final_period": false,
    "llm": {
      "enabled": false,
      "endpoint": "http://127.0.0.1:11434",
      "model": "qwen2.5:3b-instruct",
      "timeout_s": 6
    }
  },
  "insert": {
    "method": "clipboard",        // v1 は clipboard のみ
    "restore_clipboard": true,
    "paste_delay_ms": 30,         // クリップボード設定→ペースト送出までの待ち
    "restore_delay_ms": 500
  },
  "ui": {
    "overlay": true,
    "overlay_position": "bottom-center"   // bottom-center | top-center
  },
  "hallucination": {
    "no_speech_threshold": 0.6,
    "logprob_threshold": -1.0,
    "compression_ratio_threshold": 2.4,
    "blacklist_extra": []         // ユーザー追加の定型ハルシネーション文
  },
  "log_level": "INFO"
}
```

## 6. 音声入力パイプライン

### 6.0 常駐オーディオストリーム(v1.1 改訂・必須)

録音開始のたびに `InputStream` を open すると開始まで 100〜130ms(プロセス初回は CoreAudio 初期化で数秒)かかり、§15 の 50ms 目標を満たせない(実測 2026-07-05)。停止→再開方式も start() 68〜75ms + 最初の音声コールバック到達 ~134ms で語頭が欠けるため不採用。よって:

- **起動時**に `InputStream`(16kHz, mono, float32, blocksize 512)を 1 本 open→start し、**常時走らせる**(`audio.idle_stream: "running"` 既定)。初回 open の重い初期化とマイク権限プロンプトは起動時に済む。
- コールバックは常時、**プリロールリングバッファ**(直近 `audio.pre_roll_ms`、既定 200ms、サンプル数上限で管理)へ追記する。`capturing` フラグが立っている間のみ捕捉リストへも追記する。
- **録音開始** = ロック下で「捕捉リストをプリロール内容で初期化し `capturing=True`」のみ。デバイス呼び出しゼロ、目標 <5ms。
- **録音停止** = `capturing=False` → チャンク結合して ndarray を返す。
- `audio.idle_stream: "stopped"` 設定時は IDLE 中 `stream.stop()` し録音開始時に `start()`(開始 ~70-140ms・プリロール無効。マイク使用インジケータを消したい利用者向けの明示オプション。README に両者のトレードオフを記載)。
- トレイ「有効」オフの間は `stream.stop()`(インジケータ消灯)、再有効化で `start()`。終了時は stop→close。
- デバイス異常(コールバック status・ストリーム死亡)は WARNING ログ。録音開始時にストリームが死んでいたら 1 回だけ再 open を試み、失敗なら既存のエラー経路。

1. **録音開始**(RECORDING 遷移時): §6.0 の通り捕捉フラグを立てるのみ。オーバーレイに録音レベル(RMS を 50ms ごと)と経過秒を表示。
2. **録音停止**: バッファを確定し float32 numpy 配列(16kHz mono)として worker へ渡す。
3. **VAD ゲート**(§8-H1): 発話が無ければここで終了(IDLE へ戻り、オーバーレイに「無音」と 800ms 表示)。端点トリムを実施。
4. **ASR**: エンジンの `transcribe()` を呼ぶ(§7)。initial_prompt は §9.1 で構築。
5. **ハルシネーションフィルタ**(§8-H3〜H6)でセグメントを選別し、テキストを連結(日本語は区切り無しで連結)。
6. **辞書補正**(§10.3)。
7. **ルール整形**(§9.2)。LLM 整形が有効なら §9.3(ガード付き)。
8. **挿入**(§12)。オーバーレイを閉じ IDLE へ。

## 7. ASR エンジン仕様

### 7.1 抽象インターフェース (`engine/base.py`)

```python
@dataclass
class Segment:
    text: str
    avg_logprob: float       # 取得不能なバックエンドでは 0.0
    no_speech_prob: float    # 同上
    compression_ratio: float # 同上

class EngineBase(ABC):
    def load(self) -> None: ...          # モデルのロード(冪等)
    def transcribe(self, audio: np.ndarray, initial_prompt: str,
                   language: str) -> list[Segment]: ...
    @property
    def name(self) -> str: ...
```

### 7.2 faster-whisper バックエンド (`engine/fw.py`)

- `WhisperModel(model, device=..., compute_type=..., cpu_threads=...)`
- **既定モデル(v1.3 改訂)**: `model == "auto"` のとき、`language == "ja"` なら `kotoba-tech/kotoba-whisper-v2.0-faster`(日本語特化の蒸留 large-v3、CTranslate2 版)。それ以外の言語は従来通り `"small"`。
  - 動機: CPU 専用機(例 Intel N100)で `small` は日本語の聞き間違いが多く実測で確認された(「ハルシネーション」→「ハルシネエション」等)。kotoba は large-v3 級の精度を medium 級の計算量で実現し、誤認識が大幅に減る。
- **デバイス自動検出・解決(v1.3・必須)**: `device == "auto"` または `"cuda"` の場合、まず `_register_nvidia_dll_dirs()` を呼び NVIDIA ランタイム DLL の探索ディレクトリを登録する(下記参照)。その上で `device == "auto"` なら `ctranslate2.get_cuda_device_count() > 0` を `_cuda_available()` として判定し、真なら `cuda`、偽なら `cpu` に解決する。
- **compute_type 解決(v1.3・必須)**: `device == "cuda"` かつ `compute_type` が `"auto"` または `"int8"`(config.json の長年の既定値)なら `"float16"` に格上げする。`compute_type == "auto"` かつ CPU なら `"int8"`。それ以外の明示値(例 `int8_float16`)はそのまま尊重する。
- **ロード失敗時の自動フォールバック(v1.3・必須)**: `device` が `cuda` に解決された状態でモデルロード or ウォームアップが失敗した場合(cuDNN/cuBLAS 不在等)、WARNING をログしてから **device=cpu, compute_type=int8 で再ロードを試みる**。CPU での再ロードも失敗したら例外を送出する(§14 のエラー経路)。`device` が最初から `cpu` の場合は従来通り即座に例外送出。
- **NVIDIA ランタイム DLL の探索(v1.3・Windows のみ有効、他 OS は no-op)**: `_register_nvidia_dll_dirs()` は以下を優先順に `os.add_dll_directory()` および `PATH` へ登録する(存在するディレクトリのみ):
  1. `%LOCALAPPDATA%\KoeKichi\cuda\bin`(インストーラーの GPU オプションタスクが配置。§18.5)
  2. `nvidia-cublas-cu12` / `nvidia-cudnn-cu12` / `nvidia-cuda-nvrtc-cu12` の pip ホイール(`pyproject.toml` の `gpu` extra)の bin ディレクトリ(importlib で存在確認)
- transcribe パラメータ(固定):
  - `language=config.language`, `beam_size=config.engine.beam_size`
  - `condition_on_previous_text=False`(ハルシネーション対策 §8-H2)
  - `vad_filter=True`(Silero VAD 内蔵)
  - `no_speech_threshold`, `log_prob_threshold`, `compression_ratio_threshold` は §5 の hallucination 設定値を渡す
  - `initial_prompt=<§9.1>`。**ただし蒸留系モデル(モデル名に `kotoba` または `distil` を含む)には常に `None` を渡す**(下記の重要な既知の非互換のため)。
- **【重要な既知の非互換】蒸留系モデルは initial_prompt と組み合わせるとハルシネーションする(v1.3・実測確認済み)**: `kotoba-whisper` 等の蒸留(distilled)モデルはプロンプト条件付けを学習していないため、initial_prompt を渡すと(**空文字列 `""` でも発生**)誤変換(例:「辞書」→「事書」)と後続文の欠落が起きる。`None` を渡した場合のみ正常動作する。そのため辞書語のプロンプト注入(§9.1/§10.2)は蒸留系モデル使用時は事実上無効になる(**辞書の置換補正(§10.3, corrections)は影響を受けず引き続き有効**)。この制約は README の辞書節に明記すること。mlx-whisper 側で将来 distil 系モデルを採用する場合も同じ罠に注意。
- 各セグメントの `avg_logprob` / `no_speech_prob` / `compression_ratio` を `Segment` に写す。
- **`load()` 内でウォームアップを行う(v1.2・必須)**: `mlx.py` は起動時に無音 0.5 秒でダミー transcribe を行いモデルを常駐させているが、本バックエンドにはこれが無く、初回の実録音で CTranslate2 のスレッドプール初期化コストを負っていた(§15 のプリロード要件違反)。`load()` の最後に `np.zeros(8000, dtype=np.float32)` で同様のウォームアップ transcribe を行うこと。**ウォームアップは transcribe の戻り値(セグメント generator)を明示的に反復消費すること**(faster-whisper の `transcribe()` は遅延評価で、generator を消費しない限り実際の推論は実行されない)。CUDA 経路ではこのウォームアップが cuDNN/cuBLAS DLL の実動確認を兼ねる(失敗時は上記フォールバックへ)。
- `name` プロパティ: モデルロード後は `f"faster-whisper/{resolved_device}"`(例 `faster-whisper/cuda`)を返す(トレイのツールチップで実行デバイスが分かるようにするため)。ロード前は `"faster-whisper"`。

### 7.3 mlx-whisper バックエンド (`engine/mlx.py`)

- `mlx_whisper.transcribe(audio, path_or_hf_repo=model, language=..., initial_prompt=..., condition_on_previous_text=False, no_speech_threshold=..., logprob_threshold=..., compression_ratio_threshold=..., word_timestamps=False)`
- `model == "auto"` → `"mlx-community/whisper-large-v3-turbo"`。
- 戻り値 `result["segments"]` から `Segment` に写す(`avg_logprob`, `no_speech_prob`, `compression_ratio` キー)。
- このモジュールは darwin/arm64 以外で import されないこと(engine/__init__.py のファクトリで分岐)。

### 7.4 モデルダウンロード

- 初回はモデルを自動ダウンロードする(HuggingFace Hub / faster-whisper のキャッシュ機構)。ダウンロード中はトレイのツールチップとオーバーレイに「モデルをダウンロード中…」を表示。失敗時はエラーを表示して IDLE。

## 8. ハルシネーション対策(必須要件)

| # | 対策 | 実装箇所 |
|---|---|---|
| H1 | **VAD ゲート**: webrtcvad (30ms フレーム) で発話フレーム比率を判定。発話合計が `min_speech_ms` 未満なら **Whisper を呼ばずに** 空結果を返す。前後の無音は `pad_ms` を残してトリムする | vad.py |
| H1b | **発話比率ゲート(v1.3)**: 録音全体が **3000ms を超える**場合、発話時間 ÷ 録音全体時間(比率)が `min_speech_ratio`(既定 0.10)未満なら、H1 の絶対時間チェックを通過していても空結果を返す。長時間録音(誤ってホットキーを押しっぱなしにした等)の大半が無音で、ごく短いノイズ区間だけが `min_speech_ms` を満たしてしまうケースを弾くため。3000ms 以下の録音には適用しない(通常発話の誤棄却を避ける) | vad.py |
| H2 | `condition_on_previous_text=False` を常時指定(直前文脈による連鎖ハルシネーション防止) | engine/* |
| H3 | セグメント棄却: `no_speech_prob > no_speech_threshold` かつ `avg_logprob < logprob_threshold` のセグメントを捨てる | antihallucination.py |
| H4 | セグメント棄却: `compression_ratio > compression_ratio_threshold`(繰り返し暴走)を捨てる | 同上 |
| H5 | **ブラックリスト**: 正規化(前後空白・句読点・全半角統一)後のセグメント全文が既知ハルシネーション定型文と一致したら捨てる。内蔵リスト(最低限): 「ご視聴ありがとうございました」「ご清聴ありがとうございました」「チャンネル登録お願いします」「おやすみなさい」「最後までご視聴いただきありがとうございます」「字幕視聴ありがとうございました」 + `blacklist_extra` | 同上 |
| H6 | **プロンプトエコー棄却**: セグメント正規化文が initial_prompt(の正規化文)に完全包含される場合は捨てる | 同上 |
| H7 | initial_prompt は全体で **200 文字以内** に制限(長いプロンプトはエコー・混入リスクを上げる) | prompt.py |

- H5/H6 の正規化関数 `normalize_for_match(s)`: **NFKC 正規化を最初に**適用 → 空白(全半角)除去 → `、。，．！？!?…「」` 除去。(NFKC を先に行うことで半角句読点 `｡｢｣` 等も正しく除去される)
- ブラックリストは「セグメント全文一致」のみ。部分一致で消してはならない(実発話に含まれうるため)。

## 9. 整形仕様(「内容に触れない」の厳密定義)

**不変条件**: 整形の前後で、`normalize_for_match()`(§8)を適用した文字列が変化しないこと。すなわち句読点・空白・記号以外の文字を追加・削除・変更してはならない。formatter.py の全ルールとLLMガードはこの不変条件を満たすよう設計する。

### 9.1 initial_prompt 構築 (prompt.py)

```
prompt = SEED + 辞書語句部
SEED = "こんにちは、今日は音声入力のテストです。よろしくお願いします。"
辞書語句部 = 辞書の word を「、」で連結し末尾「。」(辞書が空なら無し)
```

- 全体が 200 文字を超える場合、辞書語は**先頭から**入るだけ入れて打ち切る(SEED は常に含める)。
- SEED は句読点付きの自然文であること(Whisper に句読点付き出力を誘導するのが目的)。命令文(「〜してください」等)を書いてはならない(initial_prompt は指示ではなく「直前の文字起こし」として扱われるため)。

### 9.2 ルールベース整形 (formatter.py) — 適用順を固定

| 順 | ルール | 例 |
|---|---|---|
| F1 | 各セグメント文字列の前後 ASCII/全角空白を strip し、日本語では区切り文字なしで連結 | |
| F2 | `normalize_ja_punct` 有効時(かつ language=ja): `，`→`、`、`．`→`。` | |
| F3 | 同一句読点の連続を 1 つに圧縮: `。。`→`。`、`、、`→`、` | |
| F4 | `、。` → `。`(読点直後の句点は句点に統合) | |
| F5 | 句読点の直前の空白を除去、`。`や`、`の直後の ASCII 空白を除去(language=ja) | `です 。` → `です。` |
| F6 | `ensure_final_period` 有効時: 末尾が `。！？!?…」)` のいずれでもなければ `。` を付加 | |

- ルールはすべて純関数 `format_text(text: str, cfg) -> str` として実装し、テーブル駆動テストを書く(§17)。

### 9.3 LLM 整形(オプション、既定無効)(llm_format.py)

- Ollama `/api/chat` に POST(stream=false)。system プロンプト(固定文字列):

```
あなたは文字起こしテキストの校正器です。与えられたテキストの句読点(、。)と明らかな表記の乱れのみを修正してください。単語の追加・削除・言い換え・要約は禁止です。修正後の本文のみを出力し、説明や前置きを付けないでください。
```

- user メッセージ = 整形対象テキストそのもの。
- **内容不変ガード(必須)**: LLM 出力に対し `normalize_for_match(入力) == normalize_for_match(出力)` を検査。不一致なら LLM 結果を**破棄**し、ルール整形済みテキストを採用。破棄したことを INFO ログに残す。
- タイムアウト(`timeout_s`)・接続失敗・HTTP エラー時も同様にフォールバック。アプリ全体を止めない。

## 10. ユーザー辞書仕様 (dictionary.py)

### 10.1 ファイル形式 (`dictionary.json`)

```jsonc
{
  "entries": [
    {
      "word": "Anthropic",              // 正しい表記(必須)
      "reading": "アンソロピック",        // 任意。v1ではプロンプト補助に使用しない(将来用)
      "corrections": ["アンスロピック", "アンソロピク"]  // 任意。誤認識→word の強制置換
    }
  ]
}
```

- 初回起動時に空の `{"entries": []}` を生成。JSON 破損時はエラーをログし空辞書として続行(上書きはしない)。

### 10.2 プロンプトへの組み込み

- 全 entries の `word` を §9.1 の辞書語句部に渡す(記載順、200 文字制限)。

### 10.3 補正置換

- ASR 出力(セグメント連結後)に対し、各 entry の `corrections` それぞれについて **単純文字列置換** `text.replace(correction, word)` を適用する。
- 適用順: corrections 文字列の**長い順**(短い置換が長い置換対象を破壊しないため)。
- 置換は §9.2 のルール整形の**前**に行う。
- ※置換は内容変更だがユーザー自身の明示指示によるものなので §9 の不変条件の対象外。

### 10.4 リロード

- 録音開始時にファイル mtime が変わっていれば自動再読込。辞書編集ダイアログ(§11.5)からの保存時も即座に反映。**専用の「辞書を再読み込み」トレイメニュー項目は v1.4 で廃止した**(上記2経路で用途が重複するため)。

## 11. UI 仕様

### 11.1 オーバーレイ (ui/overlay.py)

- PySide6。フレームレス・常時最前面・フォーカスを奪わない:
  `Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.WindowDoesNotAcceptFocus`、Mac では加えて `NSPanel` 相当になるよう `Qt.SubWindow` は使わない(フォーカス奪取があると挿入先アプリのフォーカスが失われ入力できなくなるため、**フォーカスを奪わないことは必須要件**)。
- サイズ約 280×56px、角丸(半径 14px)、半透明ダーク背景(rgba(20,20,24,0.92))、白文字。プライマリスクリーンの `overlay_position`(既定: 下端中央、下端から 80px)に表示。
- 表示内容(状態別):
  - RECORDING: 赤丸●(1s周期で点滅) + レベルメーターバー(縦棒10本、RMS連動) + 経過秒 `0:07`
  - TRANSCRIBING: スピナー + 「認識中…」
  - 無音検出: 「(無音)」を800ms表示して消える
  - エラー: ⚠ + 短いメッセージを 1.5s 表示
- IDLE では非表示。

### 11.2 トレイ / メニューバー (ui/tray.py)

- QSystemTrayIcon。アイコンはコード内で QPainter 描画(マイク型の簡易アイコン。外部画像ファイル不要)。状態で色を変える(待機=白/グレー、録音=赤、認識中=青)。
- メニュー:
  - `録音開始/停止`(状態に応じてラベル切替)
  - `有効`(チェックトグル。無効時はホットキーを無視)
  - 区切り
  - `ホットキー設定…`(§11.3 のダイアログを開く)
  - `設定ファイルを開く`(OS 既定アプリで開く: mac `open`, win `os.startfile`。ホットキー以外の設定項目には GUI が無いため必須)
  - `辞書を編集…`(v1.4・§11.5 のダイアログを開く。**旧来の「辞書を開く」「辞書を再読み込み」は v1.4 で廃止**。GUI 編集で用途が重複するため)
  - `認識モデルを再読み込み`(v1.2・§7 のエンジンロードが失敗した場合の復旧手段。従来はアプリ再起動しか手段が無かった)
  - `ログを開く`
  - 区切り
  - `終了`
- `認識モデルを再読み込み` の動作: エンジンが既に準備完了なら「準備完了しています」と通知するのみ。読み込み中なら「読み込み中です」と通知するのみ。未着手または前回失敗している場合のみ実際にロードを(再)開始する(§11.4 の初回ウィザードが使う冪等ロード開始処理を再利用する)。
- macOS では QSystemTrayIcon への setContextMenu を使用しない(NSStatusItem ネイティブメニュー追跡中の NSEvent clickCount アサーションによるクラッシュ回避)。activated シグナルから QMenu.popup() で自前表示する。Windows は setContextMenu を使用する。

### 11.3 ホットキー設定ダイアログ (ui/settings.py)

- トレイメニュー「ホットキー設定…」から開くモーダルダイアログ(このダイアログはフォーカスを取ってよい)。
- 構成:
  - ラジオ A「修飾キー2回押し」+ キー選択ドロップダウン。表示名は OS で切替: Mac = `Option / Ctrl / Shift / Cmd`、Windows = `Alt / Ctrl / Shift / Win`(内部値は alt/ctrl/shift/cmd)
  - ラジオ B「キーコンビネーション」+ combo テキスト入力欄 + モード選択(トグル / 押している間だけ)
  - 「長押しでも録音(押している間だけ)」チェックボックス(v1.2・ラジオ A 選択時のみ有効化。`hotkey.hold_to_record` に対応)
  - 現在の設定値を初期表示する
- `保存`: combo 選択時は `validate_combo` で検証し、不正ならダイアログ内に赤字エラーを表示して保存しない。正当なら config.json に保存し、HotkeyManager を新設定で即時再起動(アプリ再起動不要)。トレイのツールチップに現在のホットキーを反映。
- `キャンセル`: 変更なしで閉じる。

### 11.4 初回セットアップウィザード (ui/firstrun.py)

- **起動条件**: 設定ディレクトリに `setup_done` マーカーファイルが存在しない場合、トレイ常駐開始後にウィザードを表示する(`--check` では表示しない)。完了時にマーカー(内容 = アプリバージョン文字列)を書き込む。
- QWizard または QDialog + ページ切替で実装。ページ構成:
  1. **ようこそ**: KoeKichi の説明(ローカル完結・音声はネットワーク送信されない)。音声認識モデルのダウンロードが必要なこと、目安サイズ(Mac ≈1.6GB / Windows ≈500MB)を明示。
  2. **モデルのダウンロード**: [ダウンロード開始] ボタン → AppController の `ensure_engine_loading()`(冪等にプリロードスレッドを開始する公開メソッド)を呼び、`sig_engine_ready` を受けて完了表示→次へ。進捗は不確定プログレスバー+状態テキストでよい。失敗時はエラー表示+[再試行]。[スキップ] も可(その場合は従来どおり初回利用時にロード)。
  3. **権限設定(macOS のみ)**: マイク / アクセシビリティ / 入力監視 の3項目について、必要な理由の説明と「システム設定を開く」ボタン(それぞれ `x-apple.systempreference:com.apple.preference.security?Privacy_Microphone` / `?Privacy_Accessibility` / `?Privacy_ListenEvent` を `open` で開く)。付与状態の自動判定は行わない(v1)。Windows ではこのページをスキップ。
  4. **完了**: 現在のホットキー(describe_hotkey)と基本操作の案内。
- ウィザードはモーダルにしない(常駐機能をブロックしない)。閉じられたら(完了・途中終了問わず)マーカーを書き込む。

### 11.5 辞書編集ダイアログ (ui/dictionary_editor.py) — v1.4

- トレイメニュー「辞書を編集…」(既存の「辞書を開く」「辞書を再読み込み」の並び)から開くモーダルダイアログ(フォーカスを取ってよい)。
- 構成: `QTableWidget` で3列 — `単語`(必須) / `読み`(任意) / `誤認識パターン`(複数可、区切り文字は `、` または `,` の両対応。表示・入力ともセル内は1行のテキストとして扱う)。
- 開いた時点で `dictionary.load_dictionary()` の内容(ディスク上の最新)をテーブルへ読み込む(アプリ内メモリの状態ではなくファイルを都度読む。他経路での更新と食い違わないため)。
- ボタン: `行を追加`(空行を末尾に追加)/ `選択行を削除` / `保存` / `キャンセル`。
- `保存`: 各行について
  - `単語` が空の行は**無視**(保存しない。エラーにはしない — 空行を残したまま保存操作しても違和感が出ないようにするため)。
  - `誤認識パターン` は `、` と `,` の両方で分割し、前後空白を trim、空文字列は除外。
  - 上記から `entries` リストを構築し `dictionary.save_dictionary()` で書き込む。
  - 保存後、呼び出し元(`AppController`)は既存の辞書リロード経路(§10.4 相当)を呼び、アプリ内メモリの辞書とプロンプト用語をすぐに更新する(再起動不要)。
- `キャンセル`: 変更を破棄して閉じる(ファイルには一切書き込まない)。
- バリデーションで保存をブロックするケースは無い(空行無視のみ)。将来的に重複語のチェック等を追加する余地はあるが v1.4 では行わない。

## 12. テキスト挿入仕様 (inject.py)

方式はクリップボード経由ペースト(v1 唯一の方式):

1. 現在のクリップボード内容(text のみ)を退避(`restore_clipboard` 有効時)。
2. 結果テキストをクリップボードへ設定(pyperclip)。
3. `paste_delay_ms` 待機(v1.1: 既定 80→**30ms**)。
4. ペーストキーを送出: Mac = Cmd+V、Windows = Ctrl+V(pynput Controller。修飾キー down → v down/up → 修飾 up)。**Controller はモジュールレベルで 1 個を生成・再利用**する(毎回生成しない)。
5. **(v1.1 改訂)ここで `inject_text` は制御を返す**(クリティカルパス終了)。クリップボード復元は `threading.Timer(restore_delay_ms)` のデーモンタイマーに委ね、発火時に退避内容を復元(退避が text 以外/空なら復元しない。例外は WARNING ログのみ)。復元完了を呼び出し側は待たない。アプリ終了と競合して復元が失われるのは許容(README 既知の制限)。

- Mac ではキー送出にアクセシビリティ権限(システム設定 > プライバシーとセキュリティ > アクセシビリティ)が必要。権限が無い場合の検出は行わず、README の手順で案内(v1)。
- 挿入直前にフォーカスを奪っていないこと(§11.1)。

## 13. ホットキー仕様 (hotkey.py)

### 13.1 トリガー方式(`hotkey.type`)

**A. double-tap(既定)** — 修飾キー単独の2回押し。**長押し(push-to-talk)にも対応**(v1.2)。
- 対象キー `double_tap_key`: `alt`(Mac では Option)/ `ctrl` / `shift` / `cmd`(Windows では Win)。左右どちらのキーも同一扱い(pynput の `Key.alt`/`Key.alt_l`/`Key.alt_r` 等をすべて対象キーとみなす)。
- **クリーンタップ**の定義: 対象修飾キーの press→release の間に、他のいかなるキーボードイベントも発生しないこと(例: Option+C のような組み合わせ入力の一部は不成立)。
- **発火条件**: クリーンタップが 2 回連続し、1 回目の release から 2 回目の release までが `double_tap_window_ms` 以内。発火後は内部状態をリセットする(3 連打で 2 回発火しない)。
- double-tap は常に toggle 動作(`mode` は無視)。
- 判定ロジックは pynput 非依存の純粋クラス `DoubleTapDetector(target: str, window_ms: int, now_fn)` として実装し、`on_press(key)/on_release(key) -> bool`(True=発火)、`reset()`(内部状態を明示的にクリア)でユニットテスト可能にする。

**A-1. `DoubleTapDetector` の判定バグ修正(v1.2・必須)**

以下 2 点は実運用(特に他の Alt フック常駐ツールとの共存時)で誤動作が確認されたための修正:

1. **無関係キーによる過剰キャンセル**: 現行実装は対象キー以外のキーイベントが起きるたびに(対象キーを押していない=タップ間の待機中であっても)`_first_release_time` を無条件にリセットしていた。これは仕様が要求する「クリーンタップ」の定義(対象キーの press→release **の間**の割り込みのみが不成立の原因)を超えて過剰にキャンセルしている。修正: 対象キー以外のキーイベントは、**対象キーを現在押している最中(`_pressed=True`)のときのみ** `_clean=False` にする(=進行中のタップを不成立にする)。対象キーを押していない間(タップ待機中)のイベントは無視し、`_first_release_time` は変更しない。
2. **OS オートリピートによる dirty フラグの誤復元**: `on_press` が対象キーの押下を検知するたびに無条件で `_clean=True` にしていたため、対象キーを押しっぱなしの間に OS が発する自動リピート press イベントが、割り込みで一度 `False` になった `_clean` を意図せず `True` に戻してしまう。修正: `_clean=True` は **「押していない→押した」の遷移時のみ**設定する(`_pressed` が既に `True` の場合は素通し)。

**A-2. 長押し(push-to-talk)対応(v1.2・`hotkey.hold_to_record`)**

`hotkey.type="double-tap"` の場合のみ有効なオプション。同じ対象キーを**しきい値(`hold_threshold_ms`、既定 300ms)以上押し続けたら押している間だけ録音**する(離すと停止)。2回押しトグルと共存する(同じキーで両方の起動方式が使える)。

- 実装は `HotkeyManager` 側(pynput スレッドを持つため)。`DoubleTapDetector` はタップ判定のみに専念させ、長押し判定はロジックを分離する。
- 対象キーの press で(**新規の押下**、オートリピートではない)、`hold_to_record` が有効なら `threading.Timer(hold_threshold_ms/1000, ...)` を起動。
- 対象キーが押されている最中に**他のキーが press されたら、そのタイマーを即キャンセル**する(Alt+Tab 等のコンボ操作が誤って長押し起動しないようにするため)。
- タイマーが(キャンセルされずに)発火したら「長押し確定」とし `on_hold_start` を呼ぶ。
- 対象キーの release 時:
  - タイマー未発火(=しきい値未満で離した)なら、タイマーをキャンセルして通常のタップ判定(`DoubleTapDetector.on_release`)に処理を渡す(=従来の2回押し判定が働く)。
  - タイマー発火済み(長押し確定していた)なら、**このリリースをタップとしてカウントしない**(`DoubleTapDetector.on_release` は呼ばず、代わりに `DoubleTapDetector.reset()` を呼んで内部状態をクリアする)。代わりに `on_hold_end` を呼ぶ。
- press/release/タイマー発火の 3 者はスレッドが異なる(pynput リスナースレッド ×2 種 + `threading.Timer` のスレッド)ため、`HotkeyManager` 内に専用ロック(例: `_dt_lock`)を設け、状態(押下中か・タイマー保留中か・長押し確定済みか)の読み書きを直列化すること。
- **アプリ側(`app.py`)の状態管理**: 2回押しトグルで開始した録音と、長押しで開始した録音を区別するフラグ(例 `_hold_recording: bool`)を持つ。
  - `on_hold_start` 受信時、状態が `IDLE` でなければ何もしない(既にトグルで録音中の場合に二重で開始しない)。`IDLE` なら録音開始し `_hold_recording=True`。
  - `on_hold_end` 受信時、`_hold_recording` が `True` の場合のみ録音を停止する。トグルで開始した録音(`_hold_recording=False`)は、録音中に対象キーを長押しする操作(例: ゆっくり Alt+Tab をしようとして Alt を長押し)が発生しても停止させない。
- 設定: `hotkey.hold_to_record`(bool, 既定 **true**・v1.3)、`hotkey.hold_threshold_ms`(int, 既定 300)。`describe_hotkey` は有効時「〈キー名〉 2回押し / 長押し」のように表示する。
- UI: ホットキー設定ダイアログ(§11.3)に「長押しでも録音(押している間だけ)」チェックボックスを追加(2回押しモード選択時のみ有効化)。

**B. combo** — 従来のキーコンビネーション。
- pynput `keyboard.GlobalHotKeys`(toggle モード)/ `keyboard.Listener`(hold モード)。
- `combo` は pynput 形式文字列(例 `<ctrl>+<shift>+<space>`)。パース失敗時は既定値にフォールバックし警告ログ。
- toggle: 発火ごとに 録音開始 ⇄ 停止。hold: combo の主キー押下中のみ録音、解放で停止。

### 13.2 共通

- Esc は RECORDING 中のみグローバルに監視し、録音破棄(それ以外の状態では一切フックしない)。
- 設定変更時は HotkeyManager を stop→新設定で再生成→start できること(アプリ再起動不要)。
- Mac では入力監視権限(Input Monitoring)が必要 → README 記載。

### 13.3 macOS TSM クラッシュ回避(必須)

pynput は macOS でキーボードレイアウト取得に Text Input Source Manager(`TISCopyCurrentKeyboardInputSource` 等)を使う。これらは最近の macOS ではメインスレッド以外から呼ぶと `dispatch_assert_queue` により SIGTRAP で異常終了する。pynput はこの API を **Listener 起動スレッド**(`keycode_context()`)と **Controller 生成時**(`get_unicode_to_keycode_map()`、inject.py がワーカースレッドで生成)から呼ぶため、そのままではホットキー設定変更・貼り付け・録音のたびにクラッシュしうる。

**対策(`koekichi/macos_tsm.py`)**: darwin でのみ、アプリ起動直後の**メインスレッド**で `prime_keyboard_layout()` を1回呼び、キーボードレイアウトを取得・キャッシュしたうえで、`pynput._util.darwin` と `pynput.keyboard._darwin` **両方の名前空間**の `keycode_context` / `get_unicode_to_keycode_map` を、キャッシュ値を返すものへ差し替える(後者はリスナーモジュールが import 時に別名で束縛済みのため両方必須)。以降 pynput は二度と TSM を呼ばない。

- 呼び出し場所: `app.main()` の QApplication 生成前後、かつ HotkeyManager / Controller を一切生成する前(メインスレッド)。`--check` でも呼んでよいが失敗は致命にしない(try/except でログのみ、非 darwin では no-op)。
- 制約: レイアウトは起動時固定。実行中のレイアウト切替は反映しない(v1 の許容制限として README 記載)。貼り付けは 'v' 単一キーのため主要レイアウトで問題ない。

## 14. エラー処理・ログ

- `logging` で `koekichi.log`(RotatingFileHandler, 1MB×3)+ stderr。既定 INFO。
- 例外は worker/hotkey スレッドで捕捉し、オーバーレイ表示(§11.1)と ERROR ログ。アプリは落とさない。
- 音声デバイス無し・モデルロード失敗は起動時にトレイ通知+ログ。

## 14.1 macOS 権限の自己診断(必須)

グローバルホットキーには**入力監視**、クリップボード貼り付け(合成 Cmd+V)には**アクセシビリティ**権限が必要。未付与でも例外は出ず、ホットキーは無反応・貼り付けは静かに失敗する(OS が合成イベントを破棄)。ユーザーに「動かない理由」が伝わらないため、自己診断する。

**`koekichi/macos_perms.py`**(darwin 専用、非 darwin は常に True):
- `accessibility_trusted() -> bool`: ApplicationServices の `AXIsProcessTrusted()`(ctypes、restype c_bool)。
- `input_monitoring_granted() -> bool`: IOKit の `IOHIDCheckAccess(1)`(kIOHIDRequestTypeListenEvent、restype c_int、argtypes [c_uint32])が `0` のとき True。
- 権限設定ペインを開くヘルパー(firstrun のディープリンクを再利用)。

**組み込み**:
- 起動時(`AppController.start`、darwin):いずれか未付与なら `tray.notify` で不足権限を通知し、WARNING ログ。起動自体は継続。
- **貼り付け前**(パイプライン、darwin):`accessibility_trusted()` が False なら inject を行わず、オーバーレイに「アクセシビリティ権限が必要です(テキストはクリップボードにコピー済み)」を表示し notify。**"Inserted N chars" を成功ログとして出さない**(クリップボードへの copy は行い手動貼り付けを可能にする)。
- ホットキー機能は入力監視が無いと無反応になる旨を、起動時通知に含める。

## 14.2 PERF 計測ログ(v1.1・必須)

性能目標(§15)の達成を**実測で検証可能**にするため、以下を INFO で出力する(計測は `time.perf_counter()`)。

1. **録音開始レイテンシ**: HotkeyManager はトリガー発火時(`_fire_toggle` / `_fire_hold_start` のコールバック呼び出し直前)に `self.last_fire_ts` を記録する。AppController は `start_recording()` 完了直後に差分を計算し、`PERF rec_start {X.X}ms (fire→capture)` を出力する(Qt キューイング遅延を含む端到端値)。
2. **停止→挿入レイテンシ**: パイプラインは各段の所要時間を計測し、挿入完了(ペースト送出まで。非同期復元は含まない)時に 1 行で出力する:
   `PERF stop→insert total={T}ms vad={a} asr={b} fmt={c} inject={d}`
   (fmt = 辞書補正+ルール整形+LLM 整形の合計。無音・空結果で挿入しない場合は `PERF stop→drop total=... vad=... asr=...` を出力)

## 15. 性能目標(v1.1 改訂)

| 項目 | 目標 |
|---|---|
| ホットキー発火→音声取り込み開始 (`PERF rec_start`, idle_stream=running) | **< 50ms**(実測期待値 < 5ms) |
| テキスト確定→ペースト送出完了 (`inject` 区間) | **< 150ms**(paste_delay 30ms 含む) |
| 5秒発話の 停止→挿入完了 (Mac M系, mlx large-v3-turbo) | < 2.0s |
| 5秒発話の 停止→挿入完了 (Windows 4C8T CPU, small int8) | < 3.0s |
| 常駐メモリ (Mac 既定構成) | < 3GB |
| 常駐メモリ (Win 既定構成) | < 1.5GB |

- 満たすための実装要件: モデル常駐プリロード / **常駐オーディオストリーム(§6.0)** / beam_size 既定 1 / int8(fw) / VAD による無駄な推論回避 / 録音バッファのファイル経由なし / **クリップボード復元の非同期化(§12)** / Controller 再利用(§12)。
- 「停止→挿入」は ASR 時間が支配的であり 450ms 級には batch 認識では到達しない。それを狙う場合はストリーミング認識(v2 候補・非目標)となる。

## 16. 配布・ライセンス

- LICENSE: MIT(Copyright 2026)。
- README.md(日本語): 機能、インストール(`uv sync` → `uv run koekichi`)、Mac 権限設定手順(アクセシビリティ・入力監視・マイク)、設定・辞書の書き方、Ollama 連携の有効化手順、既知の制限、ライセンス表記。
- pyproject.toml: `[project.scripts] koekichi = "koekichi.app:main"`、license = MIT、条件付き依存(§4)。

## 17. テスト計画

### 自動テスト(pytest、CI 相当は `uv run pytest -m "not integration"`)
- formatter: F1〜F6 のテーブル駆動(最低 15 ケース。全角/半角、連続句読点、空文字、既に整形済み、`ensure_final_period` 両値)
- antihallucination: H3/H4 閾値境界、H5 全文一致のみ棄却(部分一致は残す)、H6 プロンプトエコー
- prompt: 辞書 0/1/多数、200 文字打ち切り、SEED 必須包含
- dictionary: 破損 JSON 耐性、corrections 長い順適用、reading 省略可
- config: 既定生成、部分マージ、未知キー無視
- llm_format: requests をモック。正常整形/内容改変(ガード発動でフォールバック)/タイムアウト/接続失敗
- vad: 無音 ndarray → 空、正弦波+無音 → トリム動作(合成データで決定的に)
- hotkey (DoubleTapDetector, now_fn 注入で決定的に): クリーン2連打で発火 / 押下中に他キーが挟まると不成立 / window_ms 超過で不成立 / 3連打で1回のみ発火(その後2打で再発火) / 左右キー(alt_l→alt_r)混在でも発火

### 統合テスト(Mac のみ、`-m integration`)
- `say -v Kyoko` で日本語音声 wav(16kHz 変換)を生成し、mlx バックエンドで transcribe → 期待語句を含むこと・ブラックリスト文を含まないこと
- 無音 wav → 出力が空であること

### 手動テストチェックリスト(README に記載、Windows 検証用)
- [ ] ホットキーで録音開始/停止、オーバーレイ表示
- [ ] メモ帳へ日本語が挿入される。クリップボードが復元される
- [ ] 無音で停止 → 何も挿入されない
- [ ] 辞書登録語が正しく変換される
- [ ] 一時無効化(トレイ)でホットキーが素通しになる
- [ ] Esc で録音破棄
- [ ] CPU のみ(GPU なし)で性能目標 §15 を満たす

## 18. スタンドアロン配布(パッケージング)

ダブルクリックで起動できる単体アプリを両 OS 向けに生成する。Python 環境の事前準備は不要。モデル等の「初回に必要なファイル」は §11.4 のウィザードが取得する。

### 18.1 方式

| | Mac | Windows |
|---|---|---|
| バンドラ | PyInstaller (onedir + BUNDLE → `KoeKichi.app`) | PyInstaller (onedir → `dist/KoeKichi/KoeKichi.exe`) |
| 配布形式 | `KoeKichi-<ver>-mac-arm64.dmg`(/Applications への symlink 同梱) | `KoeKichi-Setup-<ver>.exe`(Inno Setup 6) |
| 署名 | 安定した自己署名証明書があればそれで署名、無ければ ad-hoc。Developer ID・公証は非対応(README に Gatekeeper 回避手順を記載) | なし(SmartScreen 警告は README に記載) |

**重要(署名と TCC 権限)**: ad-hoc 署名はビルドごとに code identity が変わるため、付与済みの「入力監視」「アクセシビリティ」権限が**再ビルドのたびに無効化**される。これを避けるには**安定した自己署名証明書**で署名する:
- `packaging/make_signing_cert.sh`(新規、一度だけ実行): ログインキーチェーンに `KoeKichi Self-Signed` という名前の code signing 証明書が無ければ作成する。作成済みなら何もしない。
- `build_mac.sh`: ビルド後、`security find-identity -v -p codesigning` に `KoeKichi Self-Signed` があれば `codesign --force --deep --identifier jp.koekichi.app --sign "KoeKichi Self-Signed" dist/KoeKichi.app` で署名。無ければ ad-hoc のまま続行し「再ビルドごとに権限の再付与が必要」と警告を print。
- 同一証明書で署名し続ける限り、一度付与した権限は再ビルド後も維持される。README/BUILD.md に手順を記載。

### 18.2 ディレクトリ構成(追加分)

```
packaging/
  launch.py            # PyInstaller エントリ: from koekichi.app import main; main()
  koekichi-mac.spec     # Mac 用 spec
  koekichi-win.spec     # Windows 用 spec
  make_icons.py        # QPainter のマイクアイコンから icon.png/icon.icns/icon.ico を生成
  build_mac.sh         # uv 環境で pyinstaller 実行 → dist/KoeKichi.app
  make_dmg.sh          # dist/KoeKichi.app → KoeKichi-<ver>-mac-arm64.dmg (hdiutil)
  build_win.bat        # Windows 用ビルド(uv + pyinstaller)
  koekichi.iss          # Inno Setup スクリプト
  BUILD.md             # 両OSのビルド手順・前提・トラブルシュート
```

### 18.3 PyInstaller spec 要件(両 OS 共通)

- エントリ `packaging/launch.py`、`console=False`(windowed)。
- **collect_all を明示**: `mlx`(Metal シェーダ `mlx.metallib` を含む。mac spec のみ)、`mlx_whisper`(assets: mel フィルタ・トークナイザ)、`faster_whisper`(assets: Silero VAD 等)、`ctranslate2`、`onnxruntime`、`webrtcvad`。PySide6 / sounddevice / pynput は標準フックに任せる。
- 除外で肥大化抑制: `PySide6.QtWebEngineCore` ほか未使用 Qt モジュール、`tkinter`、`matplotlib` 等。
- `koekichi` パッケージ自体を含める(hiddenimports または pathex)。
- バージョンは `koekichi.__version__` を spec 内で import して使用。

### 18.4 Mac 固有

- BUNDLE の Info.plist:
  - `CFBundleIdentifier = jp.koekichi.app`、`CFBundleShortVersionString = <ver>`
  - `LSUIElement = True`(Dock 非表示のメニューバー常駐アプリ)
  - `NSMicrophoneUsageDescription = "音声入力のためにマイクを使用します。"`
  - `LSMinimumSystemVersion = 13.0`
- アイコン: `make_icons.py` が生成する `icon.icns`。
- `build_mac.sh`: `uv sync` 済み環境で `uv run pyinstaller packaging/koekichi-mac.spec --noconfirm`。arm64 専用(クロスビルドしない)。
- `make_dmg.sh`: ステージングディレクトリに `KoeKichi.app` と `Applications` symlink を置き、`hdiutil create -format UDZO`。
- 動作検証(ビルド後必須): `dist/KoeKichi.app/Contents/MacOS/KoeKichi` を直接起動し、ログに `Hotkey listener started` と `Engine ready` が出ること(モデルはキャッシュ済み前提)。初回セットアップウィザードは `setup_done` の有無で発火するため、検証時は既存マーカーの有無に注意。

### 18.5 Windows 固有

- `koekichi-win.spec`: mlx を含めない。アイコン `icon.ico`。
- `koekichi.iss`(Inno Setup 6): インストール先 `{autopf}\KoeKichi`、スタートメニューショートカット、任意チェックボックスで「スタートアップに登録」(`{userstartup}` へのショートカット)、アンインストーラ同梱。日本語メッセージ(`Languages: japanese`)。
- ビルドは Windows 実機で `build_win.bat` → Inno Setup Compiler。この Mac 上では実行不可のため、スクリプトと `BUILD.md` の手順書を成果物とする。

**GPU オプションのコマンド操作ゼロ提供(v1.3.1)**: 通常のユーザーがコマンドラインを一切使わずに GPU 高速化を有効化できるようにする。
- `koekichi.iss` の `[Code]` セクションに `HasNvidiaGpu: Boolean` 関数を実装: `{sys}\nvml.dll` または `{sys}\nvapi64.dll`(NVIDIA ドライバが必ずシステムに配置する DLL)の存在確認で判定する。
- `[Tasks]` に GPU 検出時のみ表示される任意タスク「NVIDIA GPU 用の高速化ファイルをダウンロードする(約1.4GB・推奨)」(`Check: HasNvidiaGpu`)を追加。チェックすると `[Run]` で `packaging/install_gpu_dlls.ps1` を `waituntilterminated` で実行する。
- `[Icons]` に GPU 検出時のみ「KoeKichi GPU セットアップ」というスタートメニューショートカットを追加(インストール時に見送っても後から実行できるようにするため)。
- `[UninstallDelete]` で `%LOCALAPPDATA%\KoeKichi\cuda` を削除する(config/dictionary は保持。再ダウンロード可能なため)。
- `packaging/install_gpu_dlls.ps1`(新規): Python/pip 不要で、PyPI から `nvidia-cublas-cu12` / `nvidia-cudnn-cu12` / `nvidia-cuda-nvrtc-cu12` の `win_amd64` ホイールを直接ダウンロード(BITS で進捗表示、失敗時 `Invoke-WebRequest` にフォールバック)し、ホイール内の DLL を `%LOCALAPPDATA%\KoeKichi\cuda\bin` に展開する。**日本語文字列を含むため UTF-8 BOM 付きで保存すること**(Windows PowerShell 5.1 は BOM 無し UTF-8 を ANSI として誤読し構文エラーになる)。
- `engine/fw.py` の DLL 探索(§7.2)はこのディレクトリを最優先で見る。

### 18.6 凍結環境(frozen)での動作要件

- 設定・辞書・ログの場所は §5 と同一(ユーザーディレクトリ。アプリバンドル内には書き込まない)。
- モデルキャッシュは HuggingFace 既定(`~/.cache/huggingface`)のまま。
- `sys.frozen` での分岐が必要な箇所(あれば)は最小限にし、通常実行(`uv run koekichi`)と挙動を変えない。

### 18.7 テスト(§17 に追加)

- 自動: firstrun のマーカー判定(存在時はウィザード起動条件が偽になる)のユニットテスト。ウィザード構築の offscreen スモーク(--check に含めるか単体テスト)。
- 手動(Mac、ビルド後): .app 直接起動 → ログ確認 / DMG をマウントして .app が開けること / `setup_done` を消して起動するとウィザードが出ること。
- 手動(Windows、README/BUILD.md 記載): Setup.exe → インストール → 初回ウィザード → チェックリスト §17。
