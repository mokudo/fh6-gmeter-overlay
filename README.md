# FH6 G-Meter Overlay

## 特記事項

このプロジェクトのコードはAIによるコーディングで作成されています。

Forza Horizon 6 / Forza Motorsport系の **Data Out** UDPパケットを読み取り、GメーターをWindows 11上に常時最前面のオーバーレイとして表示するPythonアプリです。

## 起動

```powershell
py -3 fh6_gmeter_overlay.py
```

または `run_overlay.bat` をダブルクリックしてください。

円描画モードで起動する場合は、以下を実行してください。円描画モードではマーカーの可動領域も円形になります。

```powershell
py -3 fh6_gmeter_overlay.py --round
```

または `run_overlay_round.bat` をダブルクリックしてください。

追加ライブラリは不要です。Python標準ライブラリの `tkinter` を使います。

## ゲーム側設定

ゲームの設定で Data Out を有効にし、以下のように送信先を設定してください。

- IP Address: `127.0.0.1`
- Port: `1024`
- Packet Format: `Dash` 推奨

別PCから受信する場合は、ゲーム側の送信先IPをこのPCのLAN内IPに変更してください。

## 操作

- 左ドラッグ: オーバーレイ位置を移動
- 右クリック: メニューを表示
- 位置を固定/解除: 誤操作防止のロック切替
- 設定: UDP受信、Data Out転送、サイズ、透明度、最大G、スムージングを変更
- Esc: 終了

設定と位置は `config.json` に保存されます。このリポジトリには初期設定用の `config.json` も含まれています。

## Data Out転送

このアプリで受信したData Outパケットを、別のアプリや別PCへそのままUDP転送できます。

右クリックメニューの「設定」で以下を指定してください。

- Data Outを転送: 有効化
- 転送先IP: 転送したい相手のIPアドレス
- 転送先ポート: 転送したい相手のUDPポート

受信直後のUDPスレッド内で生パケットをそのまま `sendto()` するため、Gメーター描画やパース処理の待ち時間は転送経路に乗りません。転送先を受信IP/受信ポートと同じにするとループするため、その組み合わせは送信しないようにしています。

## 表示テスト

ゲームなしで動作確認する場合は、別のPowerShellで以下を実行してください。

```powershell
py -3 send_test_packet.py
```

Gメーターの点が動けば、アプリ側のUDP受信と描画は動作しています。

## 注意

フルスクリーン排他モードのゲーム画面上には、Windowsの通常ウィンドウが重ならないことがあります。その場合はゲームを「ボーダーレス」または「ウィンドウ」表示にしてください。

Data Outの加速度値は、FH6公式Data Outドキュメントの324 byte固定パケットに合わせ、`AccelerationX` を20 byte、`AccelerationY` を24 byte、`AccelerationZ` を28 byteから読み取っています。FH6のData OutにはG-Force専用フィールドがないため、受信した車体加速度を標準重力加速度 `9.80665 m/s^2` で割り、重力加速度単位のG値として参照・表示します。
