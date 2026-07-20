# KoeKichi スタンドアロン版ビルド手順 (SPEC §18)

このディレクトリはダブルクリックで起動できる単体アプリ(Mac: `KoeKichi.app` /
Windows: `KoeKichi-Setup-<ver>.exe`)を生成するための PyInstaller / Inno Setup
一式です。Python 環境の事前準備は不要な配布物を作ることが目的で、開発時の
`uv run koekichi` の挙動は変えません(SPEC §18.6)。

## 前提条件

- [uv](https://docs.astral.sh/uv/) がインストール済みで、プロジェクトルートで
  `uv sync` が通ること
- `pyinstaller` は dev 依存として登録済み(`uv add --dev pyinstaller` 済み、
  `pyproject.toml` の `[dependency-groups] dev` を参照)。追加のインストール
  操作は不要です

## macOS 向けビルド

Apple Silicon (arm64) の Mac 実機で行います。クロスビルド(Intel Mac や
CI 上での arm64 ビルド)は非対応です。

```bash
# 1. アイコン生成(初回のみ。packaging/icon.icns が既にあればスキップされる)
QT_QPA_PLATFORM=offscreen uv run python packaging/make_icons.py

# 2. ビルド本体(uv sync + pyinstaller を実行し dist/KoeKichi.app を生成)
bash packaging/build_mac.sh

# 3. DMG 化(dist/KoeKichi-<ver>-mac-arm64.dmg を生成)
bash packaging/make_dmg.sh
```

### 動作検証(ビルド後必須、SPEC §18.4)

```bash
# setup_done マーカーが無いとウィザードが出る。既存マーカーがあれば
# スモークテストのためだけに一時的にコピーしておいてもよい(検証後に戻す)。
dist/KoeKichi.app/Contents/MacOS/KoeKichi &
sleep 5
tail -40 ~/Library/"Application Support"/KoeKichi/koekichi.log
kill %1
```

ログに `Hotkey listener started` と `Engine ready` が出れば正常です(モデル
はあらかじめ `~/.cache/huggingface` にキャッシュ済みである前提)。

DMG の確認:

```bash
hdiutil attach "dist/KoeKichi-<ver>-mac-arm64.dmg"
open "/Volumes/KoeKichi <ver>/KoeKichi.app"   # Finder から開ける・アイコンが出ることを確認
hdiutil detach "/Volumes/KoeKichi <ver>"
```

`setup_done` を消して起動するとウィザードが出ることも確認してください:

```bash
rm -f ~/Library/"Application Support"/KoeKichi/setup_done
dist/KoeKichi.app/Contents/MacOS/KoeKichi &
```

### macOS トラブルシュート

- **`ModuleNotFoundError` (mlx_whisper / faster_whisper / ctranslate2 / onnxruntime 等)**:
  `koekichi-mac.spec` の `collect_all(...)` 対象パッケージにその名前を追加して
  再ビルドしてください。
- **`unable to load mlx.metallib` (実行時エラー)**:
  `collect_all('mlx')` だけではシェーダーバイナリの配置場所によって取りこぼす
  ことがあります。`koekichi-mac.spec` はこれを検知して
  `<site-packages>/mlx/lib/mlx.metallib` を `datas` に `mlx/lib` として明示
  追加するフォールバックを既に含んでいますが、それでも失敗する場合は
  `python -c "import mlx; print(mlx.__path__)"` で実際のインストール場所を
  確認し、パスを spec に合わせて修正してください。
- **`FileNotFoundError` (mel フィルタ・トークナイザ等のアセット)**:
  同様に該当パッケージを `collect_all` に追加してください。
- **`PyInstaller.exceptions.ImportErrorWhenRunningHook` for `hook-webrtcvad.py` /
  `PackageNotFoundError: webrtcvad`**: `pyinstaller-hooks-contrib` の組み込み
  フックが `copy_metadata('webrtcvad')` を呼びますが、本プロジェクトが依存
  するのは `webrtcvad-wheels`(別ディストリビューション名で同じ `webrtcvad`
  モジュールを提供)のため、メタデータが見つからずビルド全体が失敗します。
  `packaging/hooks/hook-webrtcvad.py` でこの組み込みフックを空実装に上書き
  済み(両 spec の `hookspath` に登録済み)なので、通常は発生しません。もし
  再発した場合は `hookspath` の指定順序を確認してください。
- **Gatekeeper に阻まれて開けない**: ad-hoc 署名のみで Developer ID 公証は
  行っていません。README の「スタンドアロン版」節にある回避手順
  (右クリック→開く、または `xattr -dr com.apple.quarantine`)を案内してください。
- **ログに `unrecognized arguments: -B -S -I -c from multiprocessing.resource_tracker...`
  が出る**: モデルロード時、依存ライブラリ(onnxruntime/numpy 系)の内部が
  `multiprocessing.resource_tracker` をサブプロセスとして起動しようとし、
  凍結バイナリを通常の `python` インタプリタとして呼び出そうとして argparse
  エラーになる、PyInstaller + multiprocessing のよく知られた事象です。
  無害(その後の `Engine ready` ログの通りモデルは正常にロードされる)で、
  アプリの動作に影響しません。気になる場合は `packaging/launch.py` の先頭で
  `multiprocessing.freeze_support()` を呼ぶ対応がありますが、v1 では未対応
  です。

## Windows 向けビルド

**配布用の Windows 版は <https://github.com/k3peta/koekichi-win> を正本として管理しています。** この節と `packaging/koekichi-win.spec` は移行前の参考資料として残しています。仲間内配布や GitHub Release に載せる Windows バイナリは、Windows 専用リポジトリ側でビルド・検証してください。

**この Mac 上の開発環境では実行できません**(PyInstaller はターゲット OS 上での
実行が必要で、クロスビルド非対応)。Windows 実機で以下を行ってください。

```bat
REM 1. アイコン生成(初回のみ。packaging\icon.ico が既にあればスキップされる)
uv run python packaging\make_icons.py

REM 2. ビルド本体(uv sync + pyinstaller を実行し dist\KoeKichi\KoeKichi.exe を生成)
packaging\build_win.bat

REM 3. インストーラ作成(Inno Setup 6 が必要: https://jrsoftware.org/isinfo.php)
iscc packaging\koekichi.iss
```

生成物: `dist\KoeKichi-Setup-<ver>.exe`

### Windows 手動テスト(SPEC §18.7)

- [ ] `Setup.exe` を実行 → インストール完了
- [ ] スタートメニューショートカットから起動できる
- [ ] 「スタートアップに登録」を有効にした場合、次回サインイン時に自動起動する
- [ ] 初回起動時にセットアップウィザードが表示される(§11.4)
- [ ] README の「Windows 手動テストチェックリスト」(§17)を実施する
- [ ] アンインストーラでクリーンに削除できる

### Windows トラブルシュート

- **SmartScreen 警告が出る**: 未署名バイナリのため想定内です。README に
  記載の「詳細情報 → 実行」の手順を案内してください。
- **`icon.ico` が見つからない**: `packaging\make_icons.py` を先に実行して
  ください(Qt の ICO ライタを使うため Pillow は不要です)。
- **`ModuleNotFoundError`**: `koekichi-win.spec` の `collect_all(...)` 対象
  パッケージに追加してください。`mlx` / `mlx_whisper` は Windows では意図的に
  含めていません(Apple Silicon 専用のため)。

## spec の collect / exclude 方針 (SPEC §18.3)

| 項目 | 内容 |
|---|---|
| `collect_all` (Mac) | `mlx`, `mlx_whisper`, `faster_whisper`, `ctranslate2`, `onnxruntime`, `webrtcvad` |
| `collect_all` (Win) | `faster_whisper`, `ctranslate2`, `onnxruntime`, `webrtcvad`(`mlx`系は含めない) |
| 標準フック任せ | `PySide6`, `sounddevice`, `pynput` |
| 除外 | 未使用 Qt モジュール(QtWebEngine 系, QtQml/Quick 系, QtNetwork, QtMultimedia, QtSql, Qt3D 系 等)、`tkinter`, `matplotlib`(Win specではさらに `mlx`, `mlx_whisper`)。**`unittest`/`test` は除外しない**(numpy/scipy が実行時に `numpy.testing` 経由で `unittest` を参照するため、除外すると `mlx_whisper` の import が `ModuleNotFoundError: unittest` で失敗する) |

## 凍結環境での動作要件 (SPEC §18.6)

- 設定・辞書・ログの場所は通常実行と同一(ユーザーディレクトリ、アプリ
  バンドル内には書き込まない)。`koekichi/paths.py` は変更していません。
- モデルキャッシュは HuggingFace 既定 (`~/.cache/huggingface`) のまま。
- `packaging/launch.py` は `koekichi.app.main()` を呼ぶだけで、`sys.frozen`
  分岐は koekichi 本体に追加していません(通常実行と挙動を変えないため)。
