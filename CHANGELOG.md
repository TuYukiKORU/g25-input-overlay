# Change Log

このファイルには、F1テレメトリー分析ツールへ加えた主な変更を記録します。

## 2026-10-02

- Reviewed and packaged 0.3.1-laptop-preview: 131 tests and two actual EXE launches from Japanese paths, with restart persistence, analysis jobs, duplicate-window and UDP conflict checks.
- Made lap-save failures and queue overflow visible; kept the writer alive after save exceptions and warned on failed shutdown flushes.
- Restricted desktop HTTP Host/Origin and cross-site requests, capped request size and added response protections.
- Clarified the F1 26 strategy evidence requirement; added Japanese release/manual filenames, bilingual release reviews and dependency license notices.
- Measured the full desktop/WebView2 process tree during isolated 60/120 Hz replay, minimized reception and session analysis; published measurements and limitations.
- Avoided unchanged lap-control rebuilds, paused hidden-page lap polling, prevented overlapping refreshes and batched hover/resize chart redraws.
- Added offline English/Japanese user manuals, an in-app manual link and additional translated comparison insights.
- Packaged 0.3.0-laptop-preview and validated the actual EXE with 37 real laps, notes, charts, languages, eight pages and both manuals.

- Applied the approved cyan T and enlarged orange telemetry pulse as the app icon, browser favicon and touch/manifest icons.
- Added a Windows app shortcut with the custom icon and scripts to regenerate icon sizes or recreate the shortcut after moving the project.

## 2026-09-30

- Added linked corner zoom and full-lap reset across speed, inputs, acceleration and recorded driving paths.
- Added corner consistency across at least three clean laps with known, similar setup, compound, fuel, wear and ERS conditions.
- Added inferred stint selection, pace/fuel/wear/ERS charts and an explicit pit/invalid-lap filter.
- Added a live packet receipt health indicator with per-group ages and missing/stale states.
- Added persisted analysis source/rule signatures, stale-result notices and cache invalidation when the selected lap, settings or data change.
- Added actual setup snapshot differences and collapsible notes/evidence panels.
- Fixed narrow-screen table/navigation overflow and strategy-map rendering for percentage-based lift recommendations.
- Honored hidden UI states and prevented earlier lap-loading requests from overwriting later selections.
- Replaced the unconditioned tyre-wear regression with tightly matched pair evidence and an explicit insufficient-data state.
- Added three ranked time-loss cards above the lap charts, with linked chart/map highlights and comparison-condition notes.
- Session comparison selection now considers compound, setup, starting fuel, tyre wear and starting ERS; missing conditions receive a penalty.
- Replaced average brake/throttle heuristics in lap loss analysis with measured 20% input crossings.
- Excluded large recording gaps from lap coaching and guarded session interpolation and turn metrics.
- Added a README page guide and documented evidence limitations and reanalysis of saved results.

## 2026-08-12

- Split new recordings when track ID or persistent session link ID changes, even if F1 25 reuses the same session UID.
- Added full hexadecimal session UID plus season, weekend, and session link identifiers to session metadata.
- Added numeric and human-readable game mode/session type metadata, including F1 25 Career and Time Trial modes, and exposed it in the session picker.
- Added player car setup capture (wings, differential, geometry, suspension, brakes, tyre pressures, ballast, and fuel). Identical setups are stored once and laps keep only a short setup reference to limit disk usage.
- Removed the disabled real-time overlay HTML, CSS, JavaScript, API endpoints, and legacy route alias.
- Reduced new lap samples to fields consumed by the overview, event detection, track mapping, and session analysis.
- Stopped parsing and serializing unused gear, RPM, steering, tyre temperature, MGU-K power, Aero availability/distance, and duplicate state fields.
- Existing recorded lap JSON remains readable without migration.

## 2026-07-24

- Fixed UDP mode detection to honor the header `gameYear`; `gameYear=26` now selects the 2026 Season Pack structures and metadata even when the raw packet format field is 2025.
- When comparing laps, the area between the two ERS battery traces is green where the selected lap has more charge and red where it has less, including exact color changes at trace crossings.
- Added ERS battery percentage to the longitudinal acceleration chart with a yellow line, translucent area fill, right-side 0–100% axis, comparison line, and acceleration kept on the upper drawing layer.

## 2026-07-18

- Added double-clickable `START_OVERLAY.cmd` and `STOP_OVERLAY.cmd` launchers.
- Added PowerShell start/stop scripts with PID ownership checks, duplicate-start prevention, port conflict detection, readiness checks, logs, and optional browser launch.

## 2026-07-17

- Changed the base track line to gray and returned spin/lock markers to positions directly on the course.
- Added selected-lap DRS/Active Aero and ERS usage ribbons to opposite sides of the racing line, with distinct circle and diamond shapes for spin and lock.
- Moved the Selected/Compare lap controls to the left of the Fastest lap card.
- Separated F1 25 DRS from 2026 Active Aero in recording, analysis events, track markers, and the track legend; old F1 25 recordings are interpreted as DRS.
- Unified Selected lap and Compare with colors across the selectors, speed, acceleration, and pace comparison: cyan for selected and coral for comparison.
- Pace comparison zone differences now use the same signed `±0:00.000` format as Comparison delta.
- Replaced Session best delta with a signed Comparison delta (`+0:02.003`) between the selected and comparison laps.
- Lap selectors now use purple for the session fastest, otherwise green for the faster lap and yellow for the slower lap; comparison-off remains green.
- Replaced the one-sided loss list with a track-ordered pace summary showing where the selected lap or comparison lap was faster.
- Pace zones use green for the selected lap and purple for the comparison lap, with only differences of at least 50 ms shown.
- Main time-loss candidates now follows the shared comparison-lap dropdown instead of always using the session best.
- Gradual loss is aggregated into 100 m zones, adjacent zones are merged, and up to eight zones above 50 ms are ranked by loss.
- Driving events are no longer mixed into the time-loss list; they remain available on the map and in analysis data.
- Tyre compound now includes the selected tyre age (for example `Hard (C4) · 3 laps`), while the former Tyre age card now shows the compared lap's tyre and stays blank when comparison is off.
- Removed all Show comparison checkboxes; comparison is now controlled only by the shared lap dropdown.
- The comparison dropdown defaults to the selected lap, which produces a single-lap view with no duplicate lines or DRS/ERS rows.
- Highlighted the current lap in green and the session-fastest lap in purple inside both lap dropdowns.
- Removed Faster/Equal/Slower section coloring and its legend from the track map.
- Replaced numeric Tyre wear cards with four donut charts separating wear before the lap from wear added during the lap.
- Added one shared comparison-lap dropdown that updates Speed, Longitudinal acceleration, and Throttle/Brake together.
- Reworked the desktop analysis view into a wide two-column dashboard: Speed beside Map/Tyre wear, then Longitudinal acceleration beside Throttle/Brake.
- Expanded the desktop content width to 1800px while retaining a single-column layout below 1200px.
- Moved Tyre wear to a 2x2 panel beside the track map.
- Added a distance graph for throttle, brake, and longitudinal acceleration, including fastest-lap comparison and map-linked hover.
- New recordings now store longitudinal G from the Motion packet; older laps derive it from speed change.
- Corrected the latest COTA session metadata to the 2026 format so the analysis legend uses Active Aero instead of DRS.
- Tyre age is now shown as `n lap` throughout the analysis screen.
- Previous lap delta now uses the same signed `0:00.000` format as Session best delta.
- Removed the Samples summary card.
- Speed graph legends now switch by detected packet format: F1 25 shows DRS (green) and ERS (yellow); F1 26 shows Active Aero (pink-red), ERS (yellow), and ERS (blue).

### レースセッション分析

- ラップ選択UIを、セッション選択プルダウンと選択セッション内のラップタイム一覧へ分離。
- ラップ一覧にタイム、コース、コンパウンド、タイヤ使用ラップ数、有効性、ピット使用を表示。
- 60HzのUDP受信と約5m間隔の保存サンプリングは維持し、マップの色分けだけを1周24区間へ集約。
- 各区間内のタイム増減を合計し、区間単位で紫・緑・白・黄色に色分け。
- `pit_status`を各ラップサンプルへ保存。
- ピット進入回数とピットレーン使用有無をラップJSONへ保存。
- ピットレーンの開始距離、終了距離、滞在時間を分析イベントとして出力。
- 分析マップへ紫色の`P`マーカー、イベント一覧へ`PIT LANE`区間を表示。
- セッション内の最速有効ラップを紫枠で表示。
- ラップ一覧をコンパクト化し、ラップタイムを右端へ配置。
- Lap timesを一行表示へ変更し、左側に最速ラップとタイム、右側にラップ選択プルダウンを配置。
- 最速ラップへコンパウンドとタイヤ使用ラップ数を追加し、選択プルダウンを同じ紫枠カードデザインへ統一。
- Fastest Lapの内容を一行へ固定し、選択プルダウンを白枠・暗色背景・白文字へ変更。
- Time delta by distanceを廃止し、横軸が距離、縦軸が累積経過時間のLap time by distanceへ変更。
- 選択ラップを緑線、セッション最速ラップを紫線で重ね、最速線の表示チェックボックスを追加。
- グラフの距離カーソルとトラックマップ上の位置表示の連動を維持。
- Lap time by distanceの縦軸を反転し、0秒を下、ラップ終盤を上に表示。
- コース座標の主方向を自動計算してマップを横長方向へ回転し、高さをデスクトップ340px・モバイル300pxへ縮小。
- Lap timeグラフ直下へ、横軸が距離、縦軸が通過速度km/hのSpeed by distanceを追加。
- 速度グラフにも選択ラップの緑線、最速ラップの紫線、独立した表示チェックボックスを追加。
- 時間・速度の両グラフでホバー距離を共有し、トラックマップ上の位置表示と同期。
- Lap time by distanceを画面・描画処理から削除し、Speed by distanceへ集約。
- ERS作動状態、モード、残量、MGU-K出力、オーバーテイク状態を新規ラップの各サンプルへ保存。
- 速度グラフへDRS／Active Aero区間を青、ERS使用区間を黄色の半透明背景帯として表示。
- Session best deltaをミリ秒表記から符号付き`0:00.000`形式へ変更。
- ゲーム形式に応じてDRSを緑、Active Aeroを赤ピンクで表示。
- ERS Boostを黄色、Overtakeを青で表示し、Telemetry2のBoost実作動フィールドを追加取得。
- 使用可能区間ではなく実作動フラグだけを描画し、上段をSelected Lap、下段をFastest Lapの使用リボンとして区別。
- F1 25のERSモードを0=None、1=Medium、2=Hotlap、3=Overtakeとして扱い、Overtakeだけを黄色で表示。
- 2026 Season Packは通常Boostを黄色、Overtake有効中のBoostを青で表示。
- 使用リボン左側へ`SELECTED`／`FASTEST`ラベルを直接描画。
- DRS／Active AeroとERSの併用区間が重ならないよう、SelectedとFastestを各2行、合計4行の使用リボンへ分離。
- Speedグラフ高をPC 360px・モバイル320pxへ拡張。
- 使用リボンの`SELECTED DRS`／`SELECTED ERS`等のラベルを11pxへ拡大。
- 速度グラフのホバー位置へSelected／Fastestの速度をkm/hで表示する情報ボックスを追加。
- F1 25の現行Car Damageレコード幅を46バイトへ修正し、Tyre wearの車両オフセットずれを解消。
- Tyre wearをFL／FR／RL／RR、小数1桁、ラップ内増加量のカード表示へ変更。
- 旧レコード幅で保存された異常な極小値は、取得不可として表示。
- Pythonテスト22件、JavaScript構文、HTTP配信、UDP待受を確認。

## 2026-07-13 – 2026-07-14

### ラップ記録とデータ管理

- 距離ベースのラップ記録を追加。
- `セッション / コース / laps / lap_XXX.json` の階層保存に対応。
- コース名とTrack IDを記録し、Track ID 13を鈴鹿として修正。
- セッション最速ラップと前ラップを比較できるAPIを追加。
- 途中開始、記録距離1,000m未満、20サンプル未満、タイム未確定の不完全ラップを保存対象から除外。
- Track limitsなどで無効になった一周分のラップは、無効ラップとして保存。
- ゲームモードとして`packetFormat`、`gameVersion`、`udpMode`をラップへ保存。
- 分析画面とラップ選択欄に`F1 25`または`F1 25 · 2026 SEASON PACK`を表示。

### ラップ分析画面

- Time delta by distanceグラフを追加。
- ミリ秒単位の縦軸と、1・2・5系列の切りのよい自動目盛りを追加。
- グラフ上のカーソル位置に対応する地点をトラックマップへ表示。
- 累積差ではなく区間ごとのタイム差でレーシングラインを色分け。
  - セッション最速：紫
  - 前ラップより速い：緑
  - 同等：白系
  - 遅い：黄色
- トラックマップを拡大し、コース外形と色付きラインを太く変更。
- Tyre wearをトラックマップの下へ移動。
- スタート地点にチェッカーマーカーを追加。

### ドライビングイベント

- ホイールスピンとタイヤロックの検出を追加し、実走データに合わせて判定を調整。
- Track limits発生位置を記録。
- `Invalid`表記を`Track limits`へ変更。
- Track limitsを左上が黒、右下が白の斜め二色旗で表示。
- 主なタイムロス候補と該当距離を分析画面へ表示。

### Active Aero

- 2026 Season PackのActive Aeroフィールドを取得。
- F1 25形式で届くDRSビットも共通の作動状態として記録。
- 作動回数、開始距離、終了距離、継続時間をラップデータへ保存。
- 分析マップへ青い菱形マーカー、分析一覧へ作動区間を表示。

### タイヤ情報

- Car Statusから実コンパウンド、表示コンパウンド、タイヤ使用ラップ数を取得。
- `Soft (C3)`などの名称でラップデータと分析画面へ表示。
- ラップ開始時と終了時のタイヤ使用ラップ数を保存。
- タイヤ摩耗、温度、ホイール速度、スリップ率をサンプルへ保存。

### ラップメモ

- 各ラップに最大5,000文字のメモを保存するAPIを追加。
- 分析画面からメモを追加・編集可能。
- メモ本文と更新日時を対象ラップJSONへ保存。

### 検証

- Pythonテスト19件、JavaScript構文検査、HTTP画面配信、UDPポート20777の待受を確認。
- 作業終了時にローカルHTTPサーバーとUDP受信プロセスを停止。

## 保存場所

- 実装コード：このリポジトリの`backend/`、`frontend/`、`tests/`。
- ラップデータ：`data/sessions/`。
- 更新履歴：この`CHANGELOG.md`。

> 現在の変更はワークスペースには保存されていますが、まだGitコミットにはまとめられていません。
