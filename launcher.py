"""macOSアプリ用ランチャー: 安全に空きポートを確保し、専用ウィンドウを開く。"""

from __future__ import annotations

import multiprocessing
import os
import socket
import shutil
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any

import uvicorn

from app import DATA_DIR, app, batch_export_files, export_path, stamp_path


HOST = "127.0.0.1"


def webview_start_options() -> dict[str, Any]:
    """凍結Windows版だけに、プロセス専用のWebView2プロファイルを指定する。"""
    if sys.platform == "win32" and getattr(sys, "frozen", False):
        # このアプリの永続データはDATA_DIR直下へ独自保存しており、WebView2のCookieや
        # LocalStorageへ依存しない。MSIX実機では固定UDF + private_mode=Falseが不定期に
        # EnsureCoreWebView2Asyncで停止したため、終了時に破棄されるプロセス専用UDFを使う。
        # PIDにUUIDを加え、異常終了したフォルダが残った後にPIDが再利用されても
        # 過去のUDFを絶対に再利用しない。
        session_name = f"{os.getpid()}-{uuid.uuid4()}"
        return {
            "storage_path": str(DATA_DIR / "webview-sessions" / session_name),
            "private_mode": True,
        }
    return {}


class NativeFileApi:
    """WebViewから呼び出す、macOSのネイティブ保存ダイアログ。"""

    def __init__(self) -> None:
        # pywebviewはjs_apiの公開属性を再帰的に走査する。Window本体を公開属性へ
        # 入れると循環的なオブジェクトグラフを解析して起動を止めるため、必ず非公開にする。
        self._window: Any | None = None

    def save_export(self, export_id: str, suggested_filename: str = "hanko-stamped.pdf") -> dict[str, bool]:
        import webview

        if self._window is None:
            raise RuntimeError("保存ダイアログを初期化できませんでした。")

        source = export_path(export_id)
        selected = self._window.create_file_dialog(
            webview.FileDialog.SAVE,
            directory=str(Path.home() / "Downloads"),
            save_filename=suggested_filename,
            file_types=("PDFファイル (*.pdf)",),
        )
        if not selected:
            return {"saved": False}

        # Cocoa版pywebviewは保存ダイアログの結果を文字列で返す。
        # （開くダイアログは複数選択に対応するためタプル。）
        destination = Path(selected if isinstance(selected, str) else selected[0])
        if destination.suffix.lower() != ".pdf":
            destination = destination.with_suffix(".pdf")
        shutil.copyfile(source, destination)
        return {"saved": True}

    def save_batch(self, batch_id: str, collision: str) -> dict[str, Any]:
        """一括生成したPDFをフォルダへ保存する。既存ファイルは絶対に上書きしない。"""
        import webview

        if self._window is None:
            raise RuntimeError("保存ダイアログを初期化できませんでした。")
        if collision not in {"rename", "cancel"}:
            raise RuntimeError("重複時の扱いが正しくありません。")

        selected = self._window.create_file_dialog(
            webview.FileDialog.FOLDER,
            directory=str(Path.home() / "Downloads"),
        )
        if not selected:
            return {"saved": False, "count": 0}
        destination_directory = Path(selected if isinstance(selected, str) else selected[0])
        sources = batch_export_files(batch_id)

        destinations: list[tuple[Path, Path]] = []
        planned_names: set[str] = set()
        for source, filename in sources:
            destination = destination_directory / filename
            if destination.exists() or destination.name.casefold() in planned_names:
                if collision == "cancel":
                    return {"saved": False, "count": 0, "reason": "conflict"}
                index = 2
                while destination.exists() or destination.name.casefold() in planned_names:
                    destination = destination_directory / f"{Path(filename).stem} ({index}).pdf"
                    index += 1
            planned_names.add(destination.name.casefold())
            destinations.append((source, destination))

        created: list[Path] = []
        try:
            # x モードで作ることで、確認後に別プロセスが同名ファイルを作っても上書きしない。
            for source, destination in destinations:
                with source.open("rb") as input_file, destination.open("xb") as output_file:
                    created.append(destination)
                    shutil.copyfileobj(input_file, output_file)
        except Exception:
            for path in created:
                path.unlink(missing_ok=True)
            raise
        return {"saved": True, "count": len(created)}

    def save_stamp_source(self, stamp_id: str, suggested_filename: str = "hanko-stamp.svg") -> dict[str, bool]:
        """作成済みSVG印影を、ユーザーが選んだ場所へコピーする。"""
        import webview

        if self._window is None:
            raise RuntimeError("保存ダイアログを初期化できませんでした。")
        source = stamp_path(stamp_id)
        if source.suffix.lower() != ".svg":
            raise RuntimeError("SVGとして保存できるのは、このアプリで作成した印影だけです。")
        filename = Path(suggested_filename).name or "hanko-stamp.svg"
        if Path(filename).suffix.lower() != ".svg":
            filename = f"{filename}.svg"
        selected = self._window.create_file_dialog(
            webview.FileDialog.SAVE,
            directory=str(Path.home() / "Downloads"),
            save_filename=filename,
            file_types=("SVGファイル (*.svg)",),
        )
        if not selected:
            return {"saved": False}
        destination = Path(selected if isinstance(selected, str) else selected[0])
        if destination.suffix.lower() != ".svg":
            destination = destination.with_suffix(".svg")
        shutil.copyfile(source, destination)
        return {"saved": True}


def reserve_local_port() -> socket.socket:
    """ポート番号を探すだけでなく、サーバーへソケットを渡して競合を防ぐ。"""
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind((HOST, 0))
    listener.listen(128)
    return listener


def wait_until_started(server: uvicorn.Server) -> None:
    deadline = time.monotonic() + 10
    while not server.started:
        if time.monotonic() >= deadline:
            raise RuntimeError("ローカルサーバーを起動できませんでした。")
        time.sleep(0.03)


def main() -> None:
    try:
        import webview
    except ImportError as error:
        raise SystemExit("pywebview が必要です。requirements.txt をインストールしてください。") from error

    listener = reserve_local_port()
    port = listener.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host=HOST, port=port, log_level="warning", access_log=False))
    server_thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
    server_thread.start()

    try:
        wait_until_started(server)
        native_api = NativeFileApi()
        window = webview.create_window(
            "Hanko PDF",
            f"http://{HOST}:{port}/",
            width=1280,
            height=900,
            min_size=(960, 650),
            js_api=native_api,
        )
        native_api._window = window
        # MSIXでは pywebview の既定プロファイル（Roaming AppData）がWebView2から
        # 書込み不能・初期化待ちになることがある。Windowsの凍結版だけ、アプリが
        # 管理する書込み可能な場所を指定し、macOSと開発起動の既定動作は変えない。
        webview.start(**webview_start_options())
    finally:
        server.should_exit = True
        listener.close()
        server_thread.join(timeout=3)


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
