# Windows版への引き継ぎ

このリポジトリは、Hanko PDFの共有ソースです。Windows版の作業は、SMB共有フォルダではなく、このリポジトリをWindows PCのローカルディスクへcloneして進めてください。仮想環境・PyInstallerの生成物・署名用ファイルはOSごとにローカルで持ち、Gitへ追加しません。

## 現在の状態

- macOS arm64版はアプリ版 `1.0.0` としてDeveloper ID署名・Apple公証済みです。
- UI、FastAPI、PDF処理、SVG印影生成の大部分はOS共通です。
- macOSのCore Textを使ったAdobe Fonts等の検出は、`stamp_generator.py` 内でmacOS時だけ有効です。Windowsでは通常のフォントフォルダ走査へフォールバックします。
- `dev_docs/` はローカル開発資料です。公開対象は `dev_docs/STAMP_STUDIO_DESIGN.md` のみです。
- `docs/` はLP制作中のため、この初回公開では意図的にgitignore対象です。追加・公開はLP完成後に行います。

## Windows版で最初に行うこと

1. Windows 11 x64環境へPython 3.12 x64、Git、Microsoft Edge WebView2 Runtimeを用意します。
2. Windowsローカルのcloneで仮想環境を作り、`requirements.txt` をインストールします。macOS専用のPyObjC依存関係は環境マーカーで自動的に除外されます。
3. `python -m unittest discover -s tests -q` を実行します。`dev_docs/sample` がない場合、ローカル開発サンプルの検査だけがskipになります。
4. `python launcher.py` で、PDF読込・印影作成・保存ダイアログ・Windowsのフォント検出を手動確認します。

## 実装が必要な差分

現行の `Hanko PDF.spec` はmacOS専用です。Windows向けには別specを作ってください。

- `CoreText` のhidden importをWindows specへ入れない。
- macOSの`BUNDLE`と`.icns`ではなく、Windows用の`EXE`/`COLLECT`と`.ico`を使う。アイコンの元画像は `assets/hanko-icon.png`。
- `app.py` の凍結アプリ用データ保存先を、Windowsでは書込み可能な `%LOCALAPPDATA%/Hanko PDF` 等へ変更する。アプリ本体のフォルダへ設定・一時PDFを書き込まない。
- `launcher.py` のpywebview保存ダイアログはWindowsでも利用できる見込みだが、文字列／配列で返るパスを実機で確認する。
- `stamp_generator.py` のWindowsフォントフォルダ走査と、ユーザーがインストールしたフォントの表示を実機で確認する。

最初の配布物はPyInstallerのone-folder版をInno Setup等のインストーラーへまとめる方法が扱いやすいです。公開配布前には、インストーラーと実行ファイルをAuthenticode署名し、タイムスタンプを付与します。証明書、PFX、トークン、パスワードはリポジトリへ入れません。

## Git運用

- 共有ソースはこのリポジトリの`main`を基準にする。
- OS固有のビルド設定は `packaging/windows/`、`packaging/macos/`、`packaging/linux/` のように分離する。
- `build/`、`dist/`、`.hanko-venv*/`、署名・公証スクリプト、ローカル資料はgitignore対象のままにする。
- リリースをそろえるときは、同じコミットにタグを付け、それぞれのOSでビルドする。PyInstallerはクロスコンパイルではないため、Windows版はWindows上でビルドする。
