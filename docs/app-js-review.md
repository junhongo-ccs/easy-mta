# `frontend/js/app.js` レビュー

## 対象

- ファイル: `C:\github\easy-mta\frontend\js\app.js`
- 観点: 構文健全性、実行時の安定性、改善余地

## 結論

`app.js` は **JavaScript 構文としては正常** で、ファイル単体で明確に壊れている状態ではありません。  
一方で、DOM 要素や依存モジュールの状態によっては **実行時エラーで停止しうる箇所** があります。

## 確認できた内容

このファイルは `DOMContentLoaded` 後に以下を担当しています。

- `MapManager.init()` の初期化
- `ChatManager.init()` の初期化
- チャット送信イベントの設定
- テキストエリアの自動伸縮
- リアルタイム更新ボタンの制御
- 凡例表示の開閉
- 車両フィルタ解除ボタンの制御

## レビュー所見

### 1. `chat-input` / `send-btn` の null チェックがない

以下の要素取得後、そのまま `addEventListener` を呼んでいます。

- `chat-input`
- `send-btn`

HTML 側の変更や読み込み条件次第でこれらが存在しない場合、`addEventListener` 呼び出し時に実行時エラーになります。

**影響**

- 画面初期化の途中でスクリプトが停止する可能性がある
- 一部 UI のみ壊れるのではなく、後続処理まで巻き込んで止まりうる

### 2. `ChatManager.init()` が例外保護されていない

`MapManager.init()` は `try/catch` で保護されていますが、`ChatManager.init()` はそのまま呼ばれています。  
`ChatManager` 側の初期化で例外が発生すると、以降のイベント登録処理を含めて停止する可能性があります。

**影響**

- チャット関連だけでなく、後続の UI 設定全体が実行されない可能性がある

### 3. リアルタイム更新ボタンの後片付けは `finally` 化するとより安全

`refresh-btn` 押下時は以下の順で処理しています。

1. `spinning` を付与
2. `disabled = true`
3. `await MapManager.refreshRealtime()`
4. `spinning` を外す
5. `disabled = false`

現状の `MapManager.refreshRealtime()` は内部で失敗を吸収するため、通常はこの処理で即座にボタンが戻らなくなる可能性は高くありません。  
ただし、将来 `refreshRealtime()` の実装が変わった場合や同期例外が混ざった場合に備え、後片付けは `finally` で固定した方が安全です。

**影響**

- 将来の実装変更に対して脆い
- 失敗時の UI 復旧保証がコード上で読み取りにくい

## 改善内容

### 優先度高

1. `chat-input` と `send-btn` の存在確認を追加する
2. `ChatManager.init()` にも例外時のハンドリングを入れる
3. `refreshRealtime()` 実行後の後片付けを、失敗時でも必ず戻る形にする

### 優先度中

1. 初期化失敗時のユーザー向けメッセージを統一する
2. DOM 要素が不足している場合、開発者向けに `console.error` で不足要素を明示する
3. `submitChat()` 内でも `input` の存在前提を減らし、ガードを明示する

## 改善例

### DOM 要素の存在チェック

```js
const input = document.getElementById('chat-input');
const sendBtn = document.getElementById('send-btn');

if (!input || !sendBtn) {
  console.error('[都バスPoC] チャットUI要素が見つかりません');
  return;
}
```

### `ChatManager.init()` の保護

```js
try {
  ChatManager.init();
} catch (e) {
  console.error('[都バスPoC] チャットの初期化に失敗しました:', e);
}
```

### 更新ボタンの復旧保証

```js
refreshBtn.addEventListener('click', async () => {
  refreshBtn.classList.add('spinning');
  refreshBtn.disabled = true;

  try {
    await MapManager.refreshRealtime();
  } finally {
    refreshBtn.classList.remove('spinning');
    refreshBtn.disabled = false;
  }
});
```

## 総評

このファイルは責務が明確で読みやすく、イベント配線の役割も整理されています。  
ただし、**「必要な DOM が必ず存在する」「依存モジュールの初期化は失敗しない」ことを前提にしすぎている** ため、運用や改修時の耐障害性には改善余地があります。

現状は **致命的に壊れているわけではないが、実行環境次第で壊れやすい実装** です。

---

# `frontend/js` 配下の追加レビュー

## 対象ファイル

- `frontend/js/app.js`
- `frontend/js/chat.js`
- `frontend/js/config.js`
- `frontend/js/map.js`

4ファイルとも **JavaScript 構文としては正常** でした。  
以下は、構文エラーではないものの、実行時の不具合や将来の保守で問題になりやすい点です。

## `chat.js`

### 1. `reset()` が会話表示を初期化していない

`reset()` は会話 ID や内部状態をリセットしたあと `init()` を呼び直していますが、`chat-messages` の中身をクリアしていません。

そのため `reset()` が呼ばれると、過去メッセージが残ったままウェルカムメッセージだけが追記されます。

**影響**

- 「会話をリセットしたのに見た目が初期化されない」状態になる
- ウェルカムメッセージが重複表示される

**改善内容**

1. `reset()` 時に `chat-messages` を空にする
2. 初期メッセージ描画を `init()` と分け、完全初期化と再描画の責務を分離する

### 2. 公開 API の引数ガードが薄い

`sendMapContext(context)` や `executeMapCommand(cmd)` は外部から呼べる形で公開されていますが、引数の妥当性確認が最低限です。

特に `sendMapContext(context)` は `context.type` を前提にしており、`null` や不正なオブジェクトを渡されると例外化する可能性があります。

**影響**

- モジュール間連携時の想定外データでチャット処理が停止しうる
- 将来の呼び出し元追加時に壊れやすい

**改善内容**

1. `context` / `cmd` の存在と必須フィールドを先に検証する
2. 不正データ時は `console.warn` と早期終了で壊れ方を限定する

## `map.js`

### 1. 初回アラート表示が停留所読込順に依存している

`init()` では以下を順に呼んでいます。

1. `_fetchStops()`
2. `_fetchAlerts()`
3. `_startRealtimePolling()`

ただし `_fetchStops()` は非同期で、`_fetchAlerts()` も待たずに走ります。  
`loadAlerts()` は既存の `_stopMarkers` に紐づけてアラートを描画する実装のため、停留所マーカー生成前にアラート取得が終わると、**初回表示でアラートが地図上に出ない** 可能性があります。

**影響**

- 起動直後だけアラートが見えないことがある
- 次回ポーリングまで表示が遅延する

**改善内容**

1. 停留所読込完了後にアラート描画する
2. もしくはアラートデータを保持し、停留所描画後に再適用する

### 2. `init()` が再実行に強くない

`init()` は `L.map('map', ...)` を毎回実行し、ポーリングタイマーも新規に開始します。  
同じページで二重に初期化された場合、Leaflet 側の例外や重複ポーリングにつながる可能性があります。

**影響**

- `Map container is already initialized` 系のエラーになりうる
- 車両・アラート取得が重複し、無駄な通信や状態不整合につながる

**改善内容**

1. `_map` が存在する場合は再初期化を避ける
2. 再初期化を許すなら既存タイマーを明示的に止めてから作り直す

### 3. チャット由来の座標コマンドに値検証がない

`ChatManager.executeMapCommand()` から `MapManager.focusOn()` が呼ばれますが、`lat` / `lng` / `zoom` の妥当性確認がありません。

AI 応答や API 応答が不正な値を返した場合、地図操作時に例外や不正移動を引き起こす可能性があります。

**影響**

- 不正なマップコマンドで地図操作が失敗する
- チャット連携由来の不具合切り分けが難しくなる

**改善内容**

1. `focusOn()` で数値検証を行う
2. 不正値なら移動せず警告ログにとどめる

## `config.js`

`config.js` には、今回の確認範囲では **明確な実装不具合は見当たりませんでした。**  
`API_BASE` を空文字で持つ構成は同一オリジン前提としては自然です。

## 追加総評

`frontend/js` 配下全体としては、役割分担は比較的明確で、`app.js`・`chat.js`・`map.js` の責務も分かれています。  
一方で、**非同期初期化の順序保証、再初期化耐性、公開 API の入力防御** はやや弱く、実行環境や将来改修時に不具合化しやすい構造です。

特に優先度が高いのは、以下の3点です。

1. `app.js` の DOM 要素存在チェック
2. `map.js` の初回アラート描画順の見直し
3. `chat.js` の `reset()` の実態と UI 表示の整合
