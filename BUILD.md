# KoeKichi ビルドガイド

スタンドアロン版の `.app` (macOS) / `Setup.exe` (Windows) をビルドする手順。

## macOS: `.app` と `.dmg` をビルド

### 前提

- Apple Silicon Mac (arm64) が必須です。Intel Mac での cross-build には非対応です
- uv がインストール済みであること([インストール手順](https://docs.astral.sh/uv/))

### 安定署名証明書の作成(初回のみ推奨)

PyInstaller でビルドした `.app` は、再ビルドのたびに macOS から「入力監視」「アクセシビリティ」権限を削除されます。これを避けるため、一度だけ安定した自己署名証明書を作成してください。

```bash
bash packaging/make_signing_cert.sh
```

このコマンドを実行すると:
1. ログインキーチェーンに `KoeKichi Self-Signed` という code-signing 用の自己署名証明書を作成
2. 実行時に一度だけログインキーチェーンのパスワードを入力
3. 作成済みなら何もせず終了(冪等)

### ビルド手順

```bash
bash packaging/build_mac.sh
```

このスクリプトが実行すること:
1. `uv sync` で依存関係を整理
2. `packaging/make_icons.py` でアイコンを生成(初回のみ)
3. PyInstaller で `.app` をビルド
4. 安定署名証明書 (`KoeKichi Self-Signed`) が存在すれば、`.app` に署名
   - 証明書がない場合は ad-hoc 署名のままで、警告を表示
5. `dist/KoeKichi.app` が生成される

**署名について:**
- 安定署名がある → メッセージ: `✓ Signed with stable identity: TCC permissions will persist across rebuilds`
- ad-hoc 署名のまま → 警告メッセージが表示され、再ビルドのたびに権限が消えることを案内

### DMG ファイルの作成

```bash
bash packaging/make_dmg.sh
```

`dist/KoeKichi.app` から DMG イメージを生成します。配布時はこのファイルを使用してください。

### 動作確認

ビルド後、以下のコマンドで簡単な検証ができます:

```bash
# チェックモード: 設定・UI・エンジン選択を検査
QT_QPA_PLATFORM=offscreen uv run koekichi --check

# または .app を直接起動して、ログを確認
./dist/KoeKichi.app/Contents/MacOS/KoeKichi
# ログに "Hotkey listener started" と "Engine ready" が出れば成功
```

---

## Windows: `Setup.exe` をビルド

**注意**: Windows でのビルドは Windows マシンで実施してください。

### 前提

- Windows 10 / 11 (x64)
- [uv](https://docs.astral.sh/uv/) がインストール済み
- [Inno Setup 6](https://jrsoftware.org/isdl.php) がインストール済み

### ビルド手順

1. PowerShell で以下を実行:

   ```powershell
   cd <koekichi-repo>
   .\packaging\build_win.bat
   ```

   これで `dist\KoeKichi\KoeKichi.exe` と `dist\KoeKichi-Setup-<version>.exe` が生成されます。

2. (オプション) Inno Setup Compiler で `.iss` ファイルを直接コンパイル:

   ```
   iscc.exe packaging\koekichi.iss
   ```

### コード署名

Windows 版はコード署名を行っていません。スマートスクリーンの警告が表示される場合があります。README の対処法を参照してください。

---

## トラブルシュート

### macOS: PyInstaller がエラー

```
Error: The dependency scanner found an issue:
  ...missing module...
```

→ `packaging/koekichi-mac.spec` の `hiddenimports` リストを確認し、必要な module を追加してください。

### macOS: 署名に失敗する

```
codesign: error: The specified item could not be found in the keychain.
```

→ 安定署名証明書がない可能性があります。以下を実行してください:

```bash
bash packaging/make_signing_cert.sh
bash packaging/build_mac.sh
```

### Windows: Inno Setup が見つからない

→ Inno Setup 6 を[ここから](https://jrsoftware.org/isdl.php)インストールしてください。

---

## ライセンス上の注意

配布物には PySide6 (Qt) / pynput という **LGPLv3** の依存が動的リンクの形で含まれます。ビルド成果物(`.app` / `Setup.exe`)を再配布する際は、各ライブラリのライセンス表記を同梱してください(詳細は [README.md](README.md#依存ライブラリモデルのライセンスに関する注意) を参照)。音声認識モデルの重みは同梱されず実行時に別途ダウンロードされるため、モデル自体のライセンスは配布物のライセンスに含まれません。

## 詳細仕様

詳細な設計や検証方法については [`SPEC.md`](SPEC.md) の §18 を参照してください。
