# F1 25 / F1 26 Lap Analysis

UDPテレメトリーを距離ベースで記録し、ラップ比較・ミス候補・セッション分析を行います。リアルタイム入力オーバーレイは無効化済みです。

これまでの更新内容は[CHANGELOG.md](CHANGELOG.md)を参照してください。

開発への参加・Windowsでのソース環境構築・プルリクエストの手順は [CONTRIBUTING.md](CONTRIBUTING.md) を参照してください (English)。

F1 25と2026 Season Packは受信パケットから自動判別します。Recording healthを開くと判別結果とParticipantsパケットの受信状態を確認できます。判別に必要なデータがまだ届いていない場合は待機表示になります。[パケット監査と判別条件](docs/UDP_PACKET_AUDIT.md)も参照してください。

## 起動

### Windowsアプリ版（配布・ノートPCテスト）

`releases/F1-Telemetry-0.3.3-strategy-preview-windows-x64.zip` を全て展開し、
`F1 Telemetry.exe` をダブルクリックすると専用ウィンドウで開きます。
Pythonのインストールは不要です。WebView2 Runtimeが必要です。
`Test previous laps.cmd` では実際の過去37周を別コピーで確認でき、記録は無効です。
新しい記録は `%LOCALAPPDATA%\F1Telemetry\sessions` に保存されます。
各画面上部の **Language / 言語** で日本語／Englishを切り替えます。設定は次回起動にも引き継ぎます。
日本語の起動・テスト手順は [docs/LAPTOP_TEST_JA.md](docs/LAPTOP_TEST_JA.md)、
英語版は [docs/LAPTOP_TEST.md](docs/LAPTOP_TEST.md)、
完全なマニュアルは [日本語](docs/manual-ja.html) ／ [English](docs/manual-en.html)、測定した負荷は [docs/PERFORMANCE.md](docs/PERFORMANCE.md) です。

友人向けの初回配布ZIPは `F1テレメトリー_初回配布版_v0.3.3_プレビュー_Windows64bit.zip`、説明書だけのZIPは `F1テレメトリー_使い方マニュアル_日本語・英語_v0.3.3.zip` です。展開後は `最初にお読みください.md` と `使い方_日本語.html` を開いてください。[リリース前レビュー](docs/リリース前レビュー_日本語.md) は旧0.3.1の検証結果です。0.3.3は統合した戦略画面とバッテリー制約をソース版・自動テストで検証しています。Windows Application Controlにより新EXEの実ウィンドウ検証は未完了です。
構造のレビューと今後の改善案は [docs/STRUCTURE_REVIEW.md](docs/STRUCTURE_REVIEW.md) を参照してください。

開発環境からビルドする場合は `powershell -ExecutionPolicy Bypass -File scripts/Build-Desktop.ps1` を実行します。
実ラップの元データがない場合、配布ZIPの `_internal/test-laps` を `.build-assets/test-laps` にコピーしてビルドできます。

### ソース版

初めてソースを取得した場合は [CONTRIBUTING.md](CONTRIBUTING.md) の手順でPython環境を準備してください。通常は `START_OVERLAY.cmd` をダブルクリックすると起動します。ローカル環境でショートカットを作成済みの場合は、プロジェクト直下の `F1 Telemetry.lnk` も使用できます。承認済みのT＋オレンジのパルスをアプリアイコンとして使います。二重起動を検知し、起動後に分析画面を自動で開きます。終了するときは `STOP_OVERLAY.cmd` をダブルクリックしてください。

アイコン画像は `frontend/static/icons/` に保存され、全ページのブラウザーアイコンにも適用されます。プロジェクトを移動した場合は `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/Create-AppShortcut.ps1` を実行してショートカットのパスを更新してください。PNGとWindows用の複数サイズのICOは `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/Build-AppIcon.ps1` で元画像から再生成できます。

PowerShellから操作する場合は次のコマンドも使用できます。

```powershell
.\scripts\Start-Telemetry.ps1
.\scripts\Stop-Telemetry.ps1
```

ブラウザーを自動で開かずに起動する場合は、`.\scripts\Start-Telemetry.ps1 -NoBrowser` を使用します。ログとPIDは `.runtime/` に保存されます。

従来どおり直接起動する場合:

```powershell
python backend/app.py
```

分析画面は `http://localhost:5000/analysis` です。ルートURLも分析画面へ転送されます。ゲームなしで確認する場合は `python scripts/generate_sample_lap.py` を先に実行します。新規記録は次の階層へ原子的に保存されます。

```text
data/sessions/
└─ YYYY-MM-DD_HH-MM-SS_session-{uid}/
   ├─ session.json
   └─ track-{trackId}-{course-name}/
      ├─ track.json
      ├─ best_lap.json
      └─ laps/
         ├─ lap_001.json
         └─ lap_002.json
```

`GET /api/sessions` は同じセッション→コース→ラップ階層を返します。旧形式の記録も引き続きAPIと分析画面から参照できます。

## 設定と対応状況

しきい値とサンプル間隔は `backend/analysis_config.py` に集約しています。F1 25 / F1 26 の既存判定を維持し、Lap Data、Motion、Motion Ex、Car Telemetry、Car Status、Car Damage、Sessionをパケット長検査後に読みます。タイヤ配列は公式の `RL, RR, FL, FR` 順です。

Motion Exの `wheelSlipRatio` は符号の意味を断定せず、ホイールスピンでは絶対値を使います。ロックは負のslip ratioまたは車速に対するwheel speed低下を候補条件にします。F1 26の最終仕様でサイズ・オフセット、slip ratioの符号、Damage構造を実機確認してください。パケット欠損時は値を保持し、ラップ開始直後に全種類が揃うまで一部フィールドがnullになり得ます。

## 画面ガイド

- **Lap analysis** (`/analysis`): ラップを選び、`Compare with` で別のラップを選択します。上部の「Where did this lap lose time?」に最大3つのタイムロス区間を表示します。カードやCorner consistencyの行をクリックすると、速度・入力・加速度グラフとマップをその区間へ拡大します。`Show full lap`で戻ります。マップには記録された2本の走行軌跡を表示します。
- **Corner consistency**: 既知の近い条件を持つクリーンラップが3周以上ある場合、コーナーごとの時間・ブレーキ開始位置・アクセル開始位置・最低速度のばらつきを表示します。対象は同じセッションとコースです。
- **Stint dashboard**: コンパウンド変更、タイヤ年齢や摩耗のリセット、ピット周回後を区切りとして、ラップタイム・開始燃料・開始摩耗・ERS残量を表示します。初期表示はクリーンラップのみです。`Include pit and invalid laps`で除外ラップも確認できます。記録だけではタイヤ交換を確認できない区切りは明記します。
- **Setup comparison**: 折りたたみパネルに、選択ラップと比較ラップの保存済みセットアップの実際の差分を表示します。スナップショットがない旧記録には不足を表示します。Lap noteと補足パネルも折りたためます。
- **Recording health**: ヘッダーの状態を開くと、Motion・Lap timing・Controls・Fuel/tyres/ERSなどの受信経過時間を確認できます。受信なし、受信中、古い受信を区別します。ゲームのポーズや終了でも古い受信になり、過去ラップの各サンプルの鮮度を保証する表示ではありません。
- **Strategy** (`/strategy`): レースのエネルギー計画、シナリオ比較、予選のエネルギー計画を同じセッション・コース・基準ラップで切り替えます。開始バッテリーと下限を設定して **Build plan** を押し、次の周の区間別操作と3〜5周のバッテリー予測を確認します。条件を変えたら再計算が必要です。
- **Track reference / Sources and assumptions**: 同じコース・エディションと、記録されたコンパウンド・セットアップ・燃料・摩耗・天候等の近いラップを採用します。条件不明や除外理由を表示します。終了バッテリーが共通目標±0.25ポイント以内のシナリオだけ順位付けします。
- **Tools → Session report** (`/session-analysis`): 走行後のターン比較・改善候補を確認します。旧X/Z記録は平面座標で分析し、実測Y座標を持つ新記録は3D座標を使います。コーナー定義の編集はコース設定ツールです。

バッテリーとマップの可用性は別々に確認します。位置データが欠けても距離ベースのエネルギー計画を利用できます。戦略は2026エディションの記録が2周以上必要です。F1 25のラップ分析は引き続き利用できます。旧戦略URLは `/strategy` へ転送されます。

予測は実走で未検証です。ピット・交通・天候変化・レース全体のタイヤ計画は対象外です。[構成とモデルのレビュー](docs/STRATEGY_WORKSPACE_REVIEW.md) を参照してください。

### 比較の読み方

セッション分析はタイヤコンパウンド、セットアップ、開始時の燃料・タイヤ摩耗・ERS残量が近いラップを優先します。条件不明は一致として扱わず、比較スコアにペナルティを加えます。Lap analysisの手動選択は維持され、条件の違いや不明項目をパネルに表示します。燃料差などを秒数に換算する補正は行いません。

「早いブレーキ」「遅いアクセル」は入力が20%を上回る地点を比較し、5m以上の差を候補として表示します。区間内で開始地点を確認できない場合は推測しません。表示は観測された関連であり、タイムロスの原因を断定するものではありません。

50mを超える記録距離の空白は比較補間せず、該当するタイムロス区間を除外します。空白の距離はパネルで確認できます。セッション分析でも大きな空白の補間と該当ターンの評価を抑制します。既存の生データグラフは従来の描画のままです。この検査は記録距離の空白を対象とし、UDPパケット種別ごとの古い値の検出ではありません。距離の上限は `backend/analysis_config.py` の `maximum_comparison_gap_m` で変更できます。

Corner consistencyでは同じコンパウンドとセットアップ、開始燃料±3kg・摩耗±3%・ERS±10%以内のクリーンラップを使います。条件不明や大きな記録空白がある区間は除外します。Tyre wear and pace evidenceは燃料±1kg・ERS±5%へ絞り、摩耗差2%以上の組が3組かつ3周以上ある場合にペア傾きの中央値を求めます。正の関連と選択周回の摩耗増加が記録されている場合だけ周回内のペース損失を表示します。天候・交通・操作の違いは残るため、因果関係や物理的なタイヤ負荷の計算ではありません。旧記録に必要な項目がない場合は証拠不足を表示します。

## テストの実行

```powershell
python -m pytest
```
