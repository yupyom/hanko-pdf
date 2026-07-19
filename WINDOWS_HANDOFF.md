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

## Windows ビルド

- macOS専用の `Hanko PDF.spec` とは別に、Windows one-folder 用の `packaging/windows/Hanko PDF.spec` を用意しています。`CoreText` のhidden importやmacOSの `BUNDLE` は含みません。
- `packaging/windows/build.ps1` は `assets/hanko-icon.png` からビルド時に `.ico` を生成し、Windows用の `EXE`/`COLLECT` を作成します。
- 凍結したWindowsアプリの設定・一時PDFは、`%LOCALAPPDATA%/Hanko PDF` に保存します。`HANKO_DATA_DIR` を指定すると保存先を変更できます。
- フォント一覧は `%LOCALAPPDATA%/Hanko PDF/font-catalog-v1.json` にキャッシュします。フォントファイルのパス・更新時刻・サイズが前回と一致する場合、次回起動時はメタデータ解析を省略します。フォントの追加・更新・削除時は自動的に再走査されます。キャッシュ保存は一覧を利用可能にした後でバックグラウンド実行するため、保存失敗や遅延で画面を待たせません。

Python 3.12 x64 の仮想環境で次を実行すると、`dist/Hanko PDF/` に one-folder 配布物が生成されます。

```powershell
python -m pip install -r requirements.txt
.\packaging\windows\build.ps1 -Python .\.hanko-venv-windows\Scripts\python.exe
```

実機では `python launcher.py` または `dist/Hanko PDF/Hanko PDF.exe` を起動し、PDF読込・印影作成・保存ダイアログ・ユーザーが追加したフォントの表示を確認してください。特に pywebview 保存ダイアログが文字列／配列のどちらでパスを返すかを確認します。

## フォント読込に関するクロスプラットフォームの知見

- macOSなどでは、凍結アプリの起動時からフォントカタログをバックグラウンドで準備します。初回の「印影を作る」はローダーを表示し、キャッシュ生成後は速やかに開きます。
- Windowsの凍結版では、フォント走査を印影作成画面が初めて開かれたときに開始します。ローダーをDOMへ表示してから32msだけ制御を戻し、WebView2へ先に描画機会を与えます。
- 凍結Windows版のWebView2 User Data Folder (UDF) は、`%LOCALAPPDATA%/Hanko PDF/webview-sessions/<PID>` のプロセス専用パスを使い、`private_mode=True` で通常終了時に破棄します。Microsoftは通常、インストール型Win32アプリにユーザーごとの固定UDFを推奨しています（[WebView2 user data folders](https://learn.microsoft.com/en-us/microsoft-edge/webview2/concepts/user-data-folder)）。しかしpywebview 6.1のMSIX実機試験では、書込み可能な固定UDFを `private_mode=False` で使うと、新規UDFでも `EnsureCoreWebView2Async` が完了せずウィンドウ表示前に停止しました。pywebview 6.2.1の公式wheelも比較しましたが、該当するWebView2生成コードに修正はありません。Hanko PDFはCookie・LocalStorageを永続データに使わず、設定・登録印影・フォントカタログをUDF外へ保存するため、Windowsでは再利用を捨てて起動の分離を優先します。PIDを含めることで、強制終了後に前回のWebView2子プロセスが残っても競合しません。
- Windowsの凍結版の重いフォント走査とキャッシュ manifest の照合は、WebView2・FastAPIと同じPythonプロセス内のスレッドではなく子プロセスで実行します。進捗と検証済みのフォントカタログをキューで親プロセスへ返すため、特定フォントの解析・I/O・フォントディレクトリ列挙が遅延しても `/api/font-status`、キャッシュ利用時の `/api/fonts`、UIを止めません。macOSなどは従来どおり起動時バックグラウンドスレッドでプリロードします。
- `/api/fonts` は子プロセスへ `join()` せず、読込中はHTTP 202と進捗を返します。ブラウザは同じAPIを短い間隔で再試行するため、フォント名・件数・現在処理中のファイルを表示でき、別の進捗ポーリングを並行実行しません。一時的な通信失敗は3回まで再試行します。
- 起動時の `/api/font-status` はPromiseを共有して二重取得を防ぎ、続くテンプレート・登録済み印影・設定の取得も直列化します。ただし起動画面を操作禁止にはしません。「アプリを準備しています…」オーバーレイと固定1.5秒待機は、WebView2初期化停止を隠すだけで操作不能に見えるため廃止しました。
- 実機スタックで、フォント処理中の停止とは別に、ページのHTTP要求がFastAPIへ一度も到達しないWebView2初期化段階の停止を確認しました。この停止はUvicornやフォントキャッシュではなくUDFとpywebview初期化の問題です。イベントループ差替え、`Connection: close`、送信タイムアウト、WindowsだけのpywebviewネイティブAPI迂回は根本原因を解消せず、共通コードを複雑にしたため採用しません。
- pywebview 6.1は `js_api` オブジェクトのアンダースコアで始まらない属性を再帰的に走査します。保存ダイアログAPIがWebViewの `Window` 本体を公開属性 `window` に保持すると、起動時のAPI生成が循環的で巨大なオブジェクトグラフへ入り、Windowsではウィンドウのメッセージ処理とページ読込を止めました。Window参照は `_window` に保持し、JavaScriptへは保存用メソッドだけを公開します。この修正は全OS共通です。
- 実機解析用の同期ファイルログは、それ自体がI/O待ちを作るため通常ビルドへ含めません。
- UIのOS判定はブラウザのUser-Agentではなく、バックエンドの `sys.platform` と凍結アプリかどうかをAPIで渡して行います。これにより、Windows用の描画待機と進捗表示を確実に有効にできます。
- プレビュー画像は生成前に非表示にし、ローダーはフォント一覧取得では閉じません。有効なSVGプレビューのBlob URLを設定できた時点、または明確なエラー表示時だけ閉じます。
- フォント一覧は先にメモリ上で利用可能にし、キャッシュの書込みは後続のバックグラウンド処理に分離します。キャッシュI/Oやセキュリティソフトによる遅延が、UIや `/api/fonts` の応答を止めないようにします。
- リリース前には、初回起動、初回の印影作成画面、キャッシュ生成後の二回目の印影作成画面を、各OSで手動確認してください。

## Microsoft Store 向け MSIX

Microsoft Store で配布する Windows 版は、Inno Setup の EXE/MSI ではなく MSIX を提出します。Store 提出後は Microsoft がパッケージを再署名するため、Store 配布に CA 発行のコード署名証明書は必要ありません。Web サイトなどから EXE/MSI/MSIX を直接配布する場合は別途コード署名が必要です。

Partner Center で予約済みの Identity は次のとおりです。将来の更新でも変更せず、`packaging/windows/msix/AppxManifest.xml.template` と一致させます。

- Package/Identity/Name: `yupyom.HankoPDF`
- Package/Identity/Publisher: `CN=7927EB7F-72E2-4822-A979-3ADE223146BE`
- Package/Properties/PublisherDisplayName: `yupyom`
- Package Family Name: `yupyom.HankoPDF_fx9rea1yggdcp`
- Microsoft Store ID: `9P6SK13W5K4F`

`packaging/windows/msix/build-msix.ps1` は、Windows one-folder ビルドを入力に、Store 用アイコン、`AppxManifest.xml`、未署名の `.msix` と `.msixupload` を作成します。pywebview / WebView2 は、凍結版でプロセス専用の書込み可能な一時UDFを使います。アプリの永続データは `%LOCALAPPDATA%/Hanko PDF` のUDF外へ保存します。

```powershell
.\packaging\windows\msix\build-msix.ps1 `
  -Python .\.hanko-venv-windows\Scripts\python.exe `
  -Version 1.0.0.0
```

Store へ提出するのは `dist/msix/HankoPDF_<version>_x64.msixupload` です。リリースごとに 4 桁の MSIX version を増やします。Store提出用は署名せずに作成してください。

ローカル試験だけは、Publisher が manifest と一致し、コード署名用途と基本制約を持つ自己署名証明書を作成します。管理者として起動した PowerShell で、テスト端末の `Cert:\LocalMachine\TrustedPeople` に PFX をインポートしてから、署名済み MSIX を `Add-AppxPackage` でインストールします。自己署名証明書は試験中だけに限り、試験後に削除します。PFX、CER、パスワードはリポジトリに追加しません。

```powershell
$password = Read-Host -AsSecureString "ローカル試験用PFXのパスワード"
.\packaging\windows\msix\New-HankoTestCertificate.ps1 -Password $password
.\packaging\windows\msix\build-msix.ps1 `
  -Python .\.hanko-venv-windows\Scripts\python.exe `
  -Version 1.0.0.0 `
  -CertificatePath .\build\msix-test-certificate\HankoPDF-local-test.pfx `
  -CertificatePassword $password
Import-PfxCertificate `
  -FilePath .\build\msix-test-certificate\HankoPDF-local-test.pfx `
  -CertStoreLocation Cert:\LocalMachine\TrustedPeople `
  -Password $password
Add-AppxPackage .\dist\msix\HankoPDF_1.0.0.0_x64.msix
```

初回のローカル試験では、起動、PDF保存、印影作成画面の初回とキャッシュ後、アンインストール後の再インストールを確認します。試験後はこの自己署名証明書を `LocalMachine\TrustedPeople` から削除します。Store 提出後の版は、パッケージの署名・配布・更新を Store に委ねます。

## Git運用

- 共有ソースはこのリポジトリの`main`を基準にする。
- OS固有のビルド設定は `packaging/windows/`、`packaging/macos/`、`packaging/linux/` のように分離する。
- `build/`、`dist/`、`.hanko-venv*/`、署名・公証スクリプト、ローカル資料はgitignore対象のままにする。
- リリースをそろえるときは、同じコミットにタグを付け、それぞれのOSでビルドする。PyInstallerはクロスコンパイルではないため、Windows版はWindows上でビルドする。
