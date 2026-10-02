"""Build offline, printable English/Japanese manuals from maintained HTML sections."""
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
VERSION = '0.3.1-laptop-preview'

EN = [
('start', 'Get started', r'''<p>F1 Telemetry records your driving and helps you compare completed laps. It runs in its own Windows window. You can try your previous laps without launching a game.</p>
<ol><li>Download the release ZIP. Right-click it → <b>Properties → Unblock → Apply</b>, if that option appears. Extract the entire ZIP into a new folder.</li><li>Keep <code>F1 Telemetry.exe</code> and <code>_internal</code> together. Python is not required.</li><li>Open <b>Test previous laps.cmd</b> to explore the included laps. To receive new telemetry, open <b>Open my recordings.cmd</b> or the EXE.</li><li>Choose <b>Language / 言語</b> at the top. The app remembers English or Japanese for the next launch.</li></ol>
<p>The window requires Microsoft Edge WebView2 Runtime. If it is missing, get the x64 Evergreen Standalone Installer from <a href="https://developer.microsoft.com/en-us/microsoft-edge/webview2/">Microsoft</a>.</p>
<aside><b>Release status:</b> This unsigned preview passed the packaged EXE window check on the development PC: 37 laps, charts, notes, eight app pages and both manuals. Laptop/game compatibility still needs testing. Windows can block an unsigned app on other PCs. ZIP Unblock does not fix an App Control signing-policy block; see <a href="https://support.microsoft.com/en-us/windows/security/threat-malware-protection/smart-app-control-frequently-asked-questions">Microsoft guidance</a> and use a trusted signed release where required.</aside>'''),
('record', 'Record while playing', r'''<ol><li>Close the older browser recorder and any other app using UDP port <b>20777</b>.</li><li>Open <b>My recordings</b> mode before driving. Test mode has recording switched off.</li><li>In the game's telemetry settings, enable UDP telemetry. For game and app on the same laptop, use address <code>127.0.0.1</code> and port <code>20777</code>. Start with <b>60 Hz</b>.</li><li>Select the UDP format appropriate to your game. For 2026 Season Pack, its own format gives the most reliable edition detection. Legacy F1 25 format can leave the edition unconfirmed until edition-specific signals arrive.</li><li>Drive a complete lap, then cross the start/finish line into the next lap. The completed lap appears automatically, normally within the next three-second refresh.</li></ol>
<p>Recording continues when you minimize the app or change its page. An unfinished lap is not saved simply by closing the window. On normal exit, completed laps queued for saving are flushed.</p>
<p>If the game runs on another device, send UDP to the laptop's local network IP instead. Both devices must be on the same reachable network. Allow the receiver on a trusted private network if Windows asks. The local app page and game UDP destination are different settings.</p>
<p>The recording-health panel shows whether needed packet groups are arriving. No packets: check UDP enabled, address, port, firewall and the selected game format. Missing groups can limit setup, tyre or energy analysis even when speed data arrives.</p>'''),
('compare', 'Compare laps', r'''<ol><li>On <b>Lap analysis</b>, select a session.</li><li><b>Selected lap</b> is the lap you are inspecting. <b>Comparison lap</b> is the reference for the plots and time differences. Choose comparable valid laps on the same track.</li><li><b>Fastest lap</b> shows the fastest reference available for the selected session. It is a summary; choosing a comparison lap remains your control.</li><li>Move over the speed, acceleration or input charts to follow the same distance on the map. Click a chart or map section to inspect it. Use <b>Reset zoom</b> to return to the full lap.</li><li>Inspect tyre wear, consistency, stints and setup differences where recorded evidence exists. Type a lap note and press <b>Save note</b>; typing alone does not save it.</li></ol>
<p>Comparisons use distance along the track. Positive time loss means the selected lap is slower than its reference at that location. Fuel, tyre compound/age, setup, weather and session type can change the interpretation. Missing conditions reduce confidence. Gaps above 50 m are excluded from coaching evidence.</p>
<p>Comparison insights point to recorded patterns such as earlier braking or later throttle. They describe an association, not a proven cause. Invalid laps, pit laps and missing evidence must be read in context. Enable the pit/invalid-lap option only when you want those laps included in the stint view.</p>'''),
('pages', 'Use the other pages', r'''<table><thead><tr><th>Page</th><th>How to use it</th></tr></thead><tbody>
<tr><td>Session analysis</td><td>Select a session, track and analysis lap, then press Analyze session. If the course is unregistered, this opens corner registration first; review and save the definitions. Otherwise it starts analysis and opens the result. Wait for its status to complete. Saved results can be reopened later. Recompute when the app says the underlying data or rules have changed.</td></tr>
<tr><td>Map &amp; Corners</td><td>In Archive, review/edit existing verified course profiles. Start a new course registration from Session analysis. Inspect the map and corner ranges before saving; a poor definition affects downstream analysis.</td></tr>
<tr><td>Turn analysis result</td><td>Inspect the saved corner-by-corner results and supporting lap evidence. This is a result view, not a live driving overlay.</td></tr>
<tr><td>Operation Library</td><td>Classify braking, acceleration, coasting and other operation sections. A single-lap view describes that lap; a representative view combines eligible laps. Check the selected source and available evidence.</td></tr>
<tr><td>ERS Strategy</td><td>Choose a 26-edition course with at least two valid, non-pit laps. The default pace window is 5% from the fastest; refresh the page after new laps are saved. Data is pooled by course across sessions. Check battery state and assumptions before pressing Analyze; missing ERS evidence limits results.</td></tr>
<tr><td>Qualifying strategy</td><td>Explore energy use for a qualifying lap using recorded evidence and start/finish battery targets. Start analysis manually and review feasibility and confidence.</td></tr>
<tr><td>Race strategy</td><td>Explore the multi-lap prototype using current battery state, minimum state and remaining laps. Results depend on its model and recorded conditions.</td></tr></tbody></table>
<p>Qualifying and race strategy require at least two comparable valid F1 26 laps; the included COTA session provides suitable test data. Strategy features are experimental planning aids. They do not control the game or prove an optimal real-world driving plan. Run heavier session and strategy calculations between stints when frame-time consistency matters.</p>'''),
('test', 'Try the included real laps', r'''<p>Test mode seeds a separate writable copy of <b>37 real recorded laps</b>. Personal lap notes and old analysis caches were removed; sample values, invalid flags and missing evidence were preserved.</p>
<table><tr><th>Session</th><th>Track</th><th>Laps / valid</th></tr><tr><td>2026-08-25 · Practice 1</td><td>Bahrain</td><td>7 / 5</td></tr><tr><td>2026-08-14 · Race</td><td>COTA</td><td>22 / 20</td></tr><tr><td>2026-09-11 · Time Trial</td><td>Unknown Track 42</td><td>8 / 1</td></tr></table>
<p>Track 42 is not identified by the current project. Test edits persist in the test copy and do not alter normal recordings. Test mode never binds the game's UDP port.</p>
<p><b>First-run check:</b> open all three sessions; compare two valid Bahrain laps; inspect COTA stints; run session analysis; save a test note; switch languages; close and reopen to confirm the note and language persist.</p>'''),
('performance', 'Performance while gaming', '__PERFORMANCE_EN__'),
('files', 'Files, backups and updates', r'''<p>Open the dark <b>File</b> menu to switch between test/recording windows, open the current recordings folder, open logs, or exit. The <b>User manual</b> link opens this guide in the selected language. Both manuals also work offline from the extracted release folder.</p>
<table><tr><th>Inside <code>%LOCALAPPDATA%\F1Telemetry</code></th><th>Contents</th></tr><tr><td>sessions</td><td>Your recorded laps, setup snapshots and saved analyses.</td></tr><tr><td>test-laps-v1</td><td>Separate editable test dataset.</td></tr><tr><td>preferences.json</td><td>Selected interface language.</td></tr><tr><td>logs\desktop.log</td><td>Rotating startup/application log.</td></tr><tr><td>webview / webview-test</td><td>Window-engine settings for the two modes.</td></tr></table>
<p><b>Backup:</b> close both windows, then copy the whole <code>F1Telemetry</code> data folder to a backup location. The application ZIP does not contain your new recordings.</p>
<p><b>Update:</b> close the app and extract the new release into a fresh application folder. Data remains in Local AppData. Keep a backup before updating. Copy the entire app folder to another PC, then copy your data separately if wanted.</p>
<p><b>Reset test data:</b> close test mode and rename <code>test-laps-v1</code> to a backup name. The next test launch seeds the original dataset again. Do not rename or delete <code>sessions</code> to reset a demo.</p>
<p>Moving the executable folder preserves recordings. English/Japanese switching changes display text; it preserves lap choices, unsaved notes, stored telemetry and units. Save notes before navigating to another page.</p>'''),
('troubleshooting', 'Troubleshooting', r'''<table><tr><th>Problem</th><th>Action</th></tr>
<tr><td>“Failed to resolve Python.Runtime.Loader.Initialize”</td><td>Close the app. Unblock the original ZIP in Properties before extracting into a new folder. Unblocking the ZIP after extraction does not clear markers already on DLLs. If it persists, inspect the log and WebView2 installation.</td></tr>
<tr><td>“Application Control policy has blocked this file”</td><td>This is a separate signing-policy restriction. ZIP Unblock will not fix it. Ask the distributor for a trusted signed build; keep the Windows protection enabled.</td></tr>
<tr><td>UDP 20777 already in use</td><td>Close the other telemetry receiver, then reopen My recordings. Test mode can coexist because it does not listen for UDP.</td></tr>
<tr><td>This mode is already open</td><td>Use its existing window. One window per mode is supported.</td></tr>
<tr><td>Recording: save error</td><td>Some completed-lap saves failed or the bounded save queue overflowed. Check free space, folder permissions and logs. The warning stays until restart. Previously failed writes are not automatically recovered.</td></tr>
<tr><td>No completed lap appears</td><td>Confirm recording mode and live packet health. Check game UDP settings. Cross the line after a full lap. Incomplete or unusable recordings may be skipped.</td></tr>
<tr><td>Blank window / cannot start</td><td>Keep the entire extracted folder together, check WebView2 Runtime, and inspect <code>logs\desktop.log</code>.</td></tr>
<tr><td>Analysis cannot run / result looks incomplete</td><td>Check selected track/session, valid eligible laps, registered course and required telemetry. Unknown conditions and missing energy/setup fields are not manufactured.</td></tr>
<tr><td>Frame-time spikes while driving</td><td>Minimize the app, keep UDP at 60 Hz, close unused test windows, and defer manual strategy/session analysis until between stints. Compare the game with/without the recorder on your laptop.</td></tr></table>
<p>When reporting an issue, provide app version, Windows version, game/UDP format, session and lap, steps to reproduce, and relevant log lines or a screenshot. Review logs before sharing; they can contain local paths. This app works locally; uploading recordings to Drive or GitHub is a separate sharing action.</p>''')]

JA = [
('start', 'はじめに', r'''<p>F1 Telemetryは走行データを記録し、完了したラップを比較するWindowsアプリです。専用ウィンドウで動作し、ゲームを起動せずに過去のラップで試すこともできます。</p>
<ol><li>リリースZIPをダウンロードします。右クリック → <b>プロパティ → 許可する（表示される場合）→ 適用</b>の順に操作してから、新しいフォルダーへZIP全体を展開します。</li><li><code>F1 Telemetry.exe</code>と<code>_internal</code>は同じフォルダーに置いてください。Pythonのインストールは不要です。</li><li><b>過去ラップで試す.cmd</b>でテストデータを開きます。新しい走行を記録する場合は<b>自分の走行を記録.cmd</b>またはEXEを開きます。</li><li>画面上部の<b>Language / 言語</b>で日本語・Englishを選びます。次回起動時も設定が保持されます。</li></ol>
<p>ウィンドウ表示にはMicrosoft Edge WebView2 Runtimeが必要です。不足している場合は<a href="https://developer.microsoft.com/en-us/microsoft-edge/webview2/">Microsoft公式サイト</a>からx64版Evergreen Standalone Installerを入手してください。</p>
<aside><b>配布版の検証状況：</b>本版は未署名のプレビューです。開発PCで配布EXEの実ウィンドウを検証し、37周・グラフ・メモ・8ページ・両言語のマニュアルが動作しました。ノートPCとゲーム併用の検証は必要です。別のPCでは未署名アプリがブロックされる場合があります。ZIPの「許可する」はApp Controlの署名ポリシーには効きません。<a href="https://support.microsoft.com/en-us/windows/security/threat-malware-protection/smart-app-control-frequently-asked-questions">Microsoftの説明</a>を参照し、必要なPCには信頼できる署名済み版を使用してください。</aside>'''),
('record', 'ゲーム中に記録する', r'''<ol><li>以前のブラウザー版レコーダーなど、UDPポート<b>20777</b>を使用する他の受信アプリを終了します。</li><li>走行前に<b>自分の走行記録</b>モードを起動します。テストモードでは記録しません。</li><li>ゲームのテレメトリー設定でUDP送信を有効にします。同じノートPCでゲームとアプリを動かす場合は、送信先<code>127.0.0.1</code>、ポート<code>20777</code>を指定します。まずは<b>60 Hz</b>で使用してください。</li><li>ゲームに合うUDP形式を選びます。2026 Season Packでは専用形式が最も確実です。従来のF1 25形式では、専用の信号が到着するまでエディションが未確定になる場合があります。</li><li>1周を完走し、スタート／フィニッシュラインを越えて次の周へ進みます。完了ラップは自動で追加され、通常は次の3秒間隔の更新で表示されます。</li></ol>
<p>最小化中や別ページを表示中でも記録は続きます。走行途中のラップは、ウィンドウを閉じるだけでは保存されません。通常終了時には、保存待ちの完了ラップを書き込みます。</p>
<p>ゲームが別の機器で動いている場合は、送信先にノートPCのLAN内IPアドレスを指定します。両機器が通信可能な同じネットワークに接続されていることを確認してください。Windowsに聞かれた場合は、信頼するプライベートネットワークで受信を許可します。アプリ画面のURLとゲームのUDP送信先は別の設定です。</p>
<p>記録状態パネルで必要なパケットが届いているか確認できます。何も届かない場合はUDP有効化・アドレス・ポート・ファイアウォール・形式を確認してください。速度が届いていても、一部のパケットが不足するとセットアップ・タイヤ・エネルギー分析が制限されます。</p>'''),
('compare', 'ラップを比較する', r'''<ol><li><b>ラップ分析</b>でセッションを選びます。</li><li><b>選択ラップ</b>は確認するラップ、<b>比較ラップ</b>はグラフとタイム差の基準です。同じコースで条件の近い有効ラップを選んでください。</li><li><b>最速ラップ</b>は選択セッションの利用可能な最速基準を表示します。比較ラップは引き続き自分で選択できます。</li><li>速度・加速度・操作グラフ上でマウスを動かすと、同じ走行距離をマップ上で確認できます。グラフまたはマップの区間をクリックして詳しく見ます。全周表示へ戻すには<b>ズームをリセット</b>を使います。</li><li>記録されている範囲でタイヤ摩耗・安定性・スティント・セットアップ差を確認します。メモを入力したら<b>メモを保存</b>を押してください。入力だけでは保存されません。</li></ol>
<p>比較はコース上の走行距離を基準にします。タイムロスが正の場合、選択ラップはその地点で比較ラップより遅れています。燃料・タイヤ種類と使用周数・セットアップ・天候・セッション種類が解釈に影響します。条件が不明だと信頼度は下がり、50 mを超えるデータ欠落はコーチングの根拠から除外されます。</p>
<p>比較分析はブレーキ開始の早さやアクセル開始の遅さなど、記録上の関連を示します。原因を確定するものではありません。無効ラップ・ピット周回・不足データは状況と合わせて判断してください。スティントにそれらを含めたい場合だけ、ピット／無効ラップを含める設定を有効にします。</p>'''),
('pages', '各ページの使い方', r'''<table><thead><tr><th>ページ</th><th>操作と確認点</th></tr></thead><tbody>
<tr><td>セッション分析</td><td>セッション・コース・分析ラップを選び、分析を開始します。未登録コースでは先にコーナー登録画面が開くので定義を確認して保存します。登録済みなら分析が始まり結果画面へ移動します。完了するまで状態を確認してください。保存結果は後で開けます。データや分析ルールの変更が表示された場合は再計算します。</td></tr>
<tr><td>マップ・コーナー</td><td>アーカイブから既存の検証済みコース設定を確認・編集します。新規登録はセッション分析から開始します。保存前にマップと区間を確認してください。定義のずれは後の分析に影響します。</td></tr>
<tr><td>コーナー分析結果</td><td>保存済みのコーナー別結果と根拠となるラップを確認します。リアルタイムの走行オーバーレイではありません。</td></tr>
<tr><td>操作ライブラリ</td><td>ブレーキ・加速・惰性走行などの操作区間を分類します。単一ラップ表示はその周を、代表表示は条件を満たす複数周をまとめます。対象ラップと根拠の有無を確認してください。</td></tr>
<tr><td>ERS戦略</td><td>26エディションの有効・ピットなしラップが2周以上あるコースを選びます。標準では最速の5%以内を採用し、複数セッションをコース単位で集約します。新規保存後はページを再読み込みしてください。バッテリーと条件を確認してAnalyzeを押します。ERSの根拠不足で結果が制限されます。</td></tr>
<tr><td>予選戦略</td><td>走行記録とスタート／フィニッシュのバッテリー目標から予選1周の使い方を検討します。手動で分析を開始し、実現可能性と信頼度を確認します。</td></tr>
<tr><td>レース戦略</td><td>現在のバッテリー状態・最低状態・残り周回数を使い、複数周の試作機能を試します。結果はモデルと記録条件に依存します。</td></tr></tbody></table>
<p>予選・レース戦略には、比較可能な有効なF1 26のラップが2周以上必要です。同梱のCOTAセッションで試せます。戦略機能は実験的な検討支援です。ゲームを操作せず、実際の最適走行を保証しません。ゲームのフレーム時間を安定させたい場合は、重いセッション／戦略計算をスティント間に実行してください。</p>'''),
('test', '同梱の実走行データで試す', r'''<p>テストモードには、編集可能な別コピーとして<b>実際に記録された37周</b>が入っています。個人メモと古い分析キャッシュは除去し、計測値・無効フラグ・不足データはそのまま残しています。</p>
<table><tr><th>セッション</th><th>コース</th><th>周数／有効</th></tr><tr><td>2026-08-25・練習1</td><td>バーレーン</td><td>7／5</td></tr><tr><td>2026-08-14・レース</td><td>COTA</td><td>22／20</td></tr><tr><td>2026-09-11・タイムトライアル</td><td>不明コース42</td><td>8／1</td></tr></table>
<p>現在のプロジェクトはコース42を識別していません。編集はテスト用コピーに保存され、通常の記録に影響しません。テストモードはゲームのUDPポートを使用しません。</p>
<p><b>初回確認：</b>3セッションを開く → バーレーンの有効ラップ2周を比較 → COTAのスティントを見る → セッション分析を実行 → テストメモを保存 → 言語を切り替え → 再起動してメモと言語が保持されるか確認します。</p>'''),
('performance', 'ゲーム中の負荷', '__PERFORMANCE_JA__'),
('files', '保存先・バックアップ・更新', r'''<p>暗色の<b>ファイル</b>メニューでテスト／記録モードの別ウィンドウを開く、現在の記録フォルダーやログフォルダーを開く、終了する操作ができます。<b>ユーザーマニュアル</b>リンクは選択中の言語でこの説明を開きます。展開フォルダー内の英語・日本語HTMLもオフラインで読めます。</p>
<table><tr><th><code>%LOCALAPPDATA%\F1Telemetry</code>の中</th><th>内容</th></tr><tr><td>sessions</td><td>新しい走行記録・セットアップ・保存分析。</td></tr><tr><td>test-laps-v1</td><td>編集可能なテストデータ。</td></tr><tr><td>preferences.json</td><td>画面の言語設定。</td></tr><tr><td>logs\desktop.log</td><td>自動ローテーションする起動・動作ログ。</td></tr><tr><td>webview / webview-test</td><td>各モードのウィンドウエンジン設定。</td></tr></table>
<p><b>バックアップ：</b>両ウィンドウを閉じ、データ用の<code>F1Telemetry</code>フォルダー全体を別の場所へコピーします。配布ZIPには新たに記録したラップは含まれません。</p>
<p><b>更新：</b>アプリを閉じ、新しい版を新しいアプリ用フォルダーへ展開します。データはLocal AppDataに残ります。更新前にバックアップしてください。別PCへ移す場合はアプリ全体をコピーし、必要ならデータも別途コピーします。</p>
<p><b>テストデータのリセット：</b>テストモードを閉じ、<code>test-laps-v1</code>をバックアップ名に変更します。次回起動で元のデータが再コピーされます。デモを初期化するために<code>sessions</code>を変更・削除しないでください。</p>
<p>アプリの展開先を移動しても記録は残ります。言語切替は表示だけを変更し、ラップ選択・未保存メモ・記録値・単位を維持します。別ページへ移動する前にはメモを保存してください。</p>'''),
('troubleshooting', '困ったとき', r'''<table><tr><th>症状</th><th>対処</th></tr>
<tr><td>Failed to resolve Python.Runtime.Loader.Initialize</td><td>アプリを閉じ、元のZIPをプロパティで「許可する」にしてから新しいフォルダーへ展開します。展開後にZIPを許可してもDLLのマークは消えません。直らない場合はログとWebView2を確認します。</td></tr>
<tr><td>Application Control policy has blocked this file</td><td>別の署名ポリシーによる制限です。ZIPの許可では解消しません。配布者に信頼できる署名済み版を依頼し、Windowsの保護は有効のままにしてください。</td></tr>
<tr><td>UDP 20777が使用中</td><td>別のテレメトリー受信アプリを閉じて記録モードを開き直します。UDPを受信しないテストモードは同時起動できます。</td></tr>
<tr><td>同じモードがすでに起動中</td><td>既存のウィンドウへ切り替えます。各モードは1ウィンドウずつ対応します。</td></tr>
<tr><td>記録：保存エラー</td><td>完了ラップの保存失敗、または保存キューの上限超過です。空き容量・アクセス権・ログを確認します。警告は再起動まで残り、過去の保存失敗は自動復旧されません。</td></tr>
<tr><td>完了ラップが増えない</td><td>記録モードとパケット受信状態を確認し、ゲームのUDP設定を確認します。1周完走後にラインを越えてください。不完全・利用不能な記録は保存されない場合があります。</td></tr>
<tr><td>空白ウィンドウ・起動失敗</td><td>展開フォルダー全体を揃え、WebView2 Runtimeと<code>logs\desktop.log</code>を確認します。</td></tr>
<tr><td>分析できない・結果が不足する</td><td>セッション／コース選択・有効な対象周・コース登録・必要な計測値を確認します。不明条件や欠けたエネルギー／セットアップ値は補われません。</td></tr>
<tr><td>走行中にカクつく</td><td>アプリを最小化し、UDPを60 Hzにし、不要なテストウィンドウを閉じます。手動の戦略／セッション分析はスティント間に行い、ノートPCで記録あり／なしのゲームを比較してください。</td></tr></table>
<p>不具合を報告するときは、アプリ版・Windows版・ゲームとUDP形式・セッションとラップ・再現手順・関係するログやスクリーンショットを添えてください。ログにはローカルパスが入る場合があるため共有前に確認してください。通常動作はローカルです。DriveやGitHubへのアップロードは別の共有操作になります。</p>''')]

CSS = '''*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:#f2f5f6;color:#17292e;font:16px/1.75 system-ui,"Yu Gothic",sans-serif}header{background:#11232a;color:#fff;padding:42px max(24px,calc((100vw - 1060px)/2))}header p{color:#acc6cb}h1{font-size:36px;line-height:1.3;margin:8px 0}h2{font-size:24px;border-bottom:2px solid #cee1df;padding-bottom:10px}a{color:#087165}header a{color:#8cebd3}nav{display:flex;flex-wrap:wrap;gap:8px 18px;padding:20px 0;border-bottom:1px solid #c8d8da}main{max-width:1060px;margin:0 auto;padding:0 24px 48px}section{background:#fff;padding:24px 30px;margin:22px 0;border-radius:12px;border:1px solid #d5e2e4}section:target{border-color:#098875}table{border-collapse:collapse;width:100%;margin:18px 0;font-size:14px}th,td{text-align:left;vertical-align:top;border-bottom:1px solid #d5e2e4;padding:12px}th{background:#e9f3f1}code{overflow-wrap:anywhere;font-size:.9em;background:#edf2f3;padding:2px 4px;border-radius:3px}li{padding-left:4px;margin:8px 0}aside{border-left:4px solid #b78416;background:#fff7df;padding:16px;margin:20px 0;font-size:14px}.muted{color:#546d75;font-size:14px}.toolbar{display:flex;gap:24px;flex-wrap:wrap}button{font:inherit;background:transparent;color:inherit;border:1px solid #66858c;padding:5px 12px;border-radius:6px;cursor:pointer}@media(max-width:650px){h1{font-size:28px}main{padding:0 14px 30px}section{padding:18px 16px}th,td{padding:8px;font-size:13px}}@media print{body{background:#fff;font-size:11pt}header{background:#fff;color:#000;padding:0}header p,header a{color:#000}.toolbar,nav{display:none}main{padding:0;max-width:none}section{border:0;padding:0;margin:24px 0;break-inside:auto}h2{break-after:avoid}tr,aside{break-inside:avoid}a{color:#000;text-decoration:none}}'''


def performance(language, report):
    if not report:
        return '<p>Performance report is not built yet.</p>'
    names = ['Idle window', 'Recording · 60 Hz', 'Minimized · 60 Hz', 'Recording · 120 Hz', 'Session analysis + 60 Hz'] if language == 'en' else ['待機中', '記録・60 Hz', '最小化・60 Hz', '記録・120 Hz', 'セッション分析＋60 Hz']
    headings = ['Test', 'Average CPU', 'CPU p95', 'Brief CPU peak', 'Peak private RAM'] if language == 'en' else ['条件', '平均CPU', 'CPU p95', 'CPU瞬間最大', 'プライベートRAM最大']
    rows = ''.join(f'<tr><td>{names[i]}</td><td>{p["cpu_mean_percent"]:.2f}%</td><td>{p["cpu_p95_percent"]:.2f}%</td><td>{p["cpu_peak_percent"]:.2f}%</td><td>{p["private_peak_mb"]:.0f} MiB</td></tr>' for i,p in enumerate(report['phases']))
    table = '<table><tr>' + ''.join(f'<th>{x}</th>' for x in headings) + '</tr>' + rows + '</table>'
    if language == 'en':
        return '<p>Measured on 2026-10-02 on the development desktop: Ryzen 5 3600, 12 logical CPUs, 32 GB RAM. Each phase lasted 30 seconds after startup warm-up, with half-second sampling. CPU is a percentage of the whole machine; p95 means 95% of sampled values were at or below that value. Shorter spikes may be missed.</p>' + table + '<p>The measurement includes the actual source desktop window, recorder and all child WebView2 processes. The replay generator is excluded. Recorded Bahrain samples were sent in full 22-car packet layouts: five packet types at 60/120 Hz plus three types at 1 Hz. This tests reception, chart display and lap saving; it is a generated replay, not a captured game network stream.</p><p>Private RAM is the sum of process-private memory, expressed in MiB. Summed working sets also include shared pages and can be larger. Game FPS/frame-time impact and GPU usage were not measured. Your laptop and actual game may differ; these figures are not a guarantee of zero FPS loss.</p><p><b>For play:</b> keep a single recording window open, minimize it when viewing is unnecessary, use 60 Hz first, and run manual heavy analyses between stints. Lap-list polling pauses when the page is hidden, unchanged lap lists avoid rebuilding, and chart hover redraws are batched. None of these pauses telemetry recording.</p>'
    return '<p>2026-10-02に開発用デスクトップで計測：Ryzen 5 3600、論理CPU 12、RAM 32 GB。起動後の準備時間を除き、各条件を30秒間、0.5秒間隔で測定しました。CPUはPC全体に対する割合です。p95は計測値の95%がその値以下だったことを示し、さらに短いピークは検出できない場合があります。</p>' + table + '<p>ソース版の実ウィンドウ・記録処理・すべての子WebView2プロセスを含み、再生データの送信処理は除外しています。バーレーンの実計測値を22台分のパケット形式に入れ、5種類を60／120 Hz、3種類を1 Hzで送信しました。受信・グラフ表示・ラップ保存の検証であり、ゲームの通信をそのまま再生したものではありません。</p><p>RAMは各プロセスのプライベートメモリ合計をMiBで表示しています。共有ページを含むワーキングセット合計はより大きくなる場合があります。ゲームのFPS・フレーム時間への影響とGPU負荷は測定していません。ノートPCや実ゲームでは異なるため、FPS低下がゼロになる保証ではありません。</p><p><b>ゲーム中の使い方：</b>記録ウィンドウは1つにし、見ない間は最小化します。まず60 Hzを使い、重い手動分析はスティント間に行います。非表示ページの一覧更新を休止し、変更のない一覧の再構築を省略し、マウス移動時のグラフ描画をまとめています。これらによって走行記録が止まることはありません。</p>'


def build(report_path, version=VERSION):
    report = json.loads(report_path.read_text()) if report_path.exists() else None
    for language, sections in [('en', EN), ('ja', JA)]:
        title = 'F1 Telemetry · User manual' if language == 'en' else 'F1 Telemetry・ユーザーマニュアル'
        toc = ''.join(f'<a href="#{key}">{heading}</a>' for key,heading,_ in sections)
        body = ''.join(f'<section id="{key}"><h2>{heading}</h2>{performance(language, report) if key == "performance" else content}</section>' for key,heading,content in sections)
        html = f'''<!doctype html><html lang="{language}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title><style>{CSS}</style></head><body><header><p>WINDOWS DESKTOP · {VERSION}</p><h1>{title}</h1><p>{'Drive. Record. Compare.' if language == 'en' else '走る・記録する・比較する'}</p><div class="toolbar"><a href="manual-en.html">English</a><a href="manual-ja.html">日本語</a><a id="back" href="/analysis">{'Back to app' if language == 'en' else 'アプリへ戻る'}</a><button onclick="window.print()">{'Print / Save PDF' if language == 'en' else '印刷／PDF保存'}</button></div></header><main><nav aria-label="{'Contents' if language == 'en' else '目次'}">{toc}</nav>{body}<p class="muted">{VERSION} · 2026-10-02</p></main><script>if(location.protocol==='file:')document.getElementById('back').hidden=true;</script></body></html>'''
        html = html.replace("if(location.protocol==='file:')document.getElementById('back').hidden=true;", "if(location.protocol==='file:'){document.getElementById('back').hidden=true;}else if(location.pathname==='/manual'){document.querySelectorAll('header a[href^=\"manual-\"]').forEach(a=>a.href='/manual?lang='+(a.getAttribute('href').includes('-ja')?'ja':'en'));}")
        from html import escape
        html = html.replace(VERSION, escape(version))
        for folder in [ROOT/'docs', ROOT/'frontend/static']:
            (folder/f'manual-{language}.html').write_text(html, encoding='utf-8')
    print('Built English and Japanese offline manuals')


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--report', type=Path, default=ROOT/'docs/performance-results.json')
    parser.add_argument('--version', default=VERSION)
    args = parser.parse_args()
    build(args.report, args.version)
