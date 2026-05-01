# ArcGIS連携 実行ガイド（第1段階）

このドキュメントは、`easy-mta` を次回起動したときに迷わず ArcGIS 連携作業を再開できるようにするための実行メモです。  
方針は「既存Leaflet版を壊さず、ArcGIS版ページを追加する」です。

## 1. ゴール（第1段階）

- `http://127.0.0.1:8000/arcgis.html` で ArcGIS 地図が表示される
- `/api/gtfs/realtime/vehicles` の車両データを ArcGIS 上に点表示できる
- 30秒ごとに再取得・再描画される
- 既存 `index.html`（Leaflet版）はそのまま動く

## 2. スコープ

### 今回やること

- ArcGISページ追加（`arcgis.html`）
- ArcGIS描画ロジック追加（`arcgis.js`）
- 既存APIレスポンスを使った車両描画
- 最低限のエラーハンドリング（取得失敗時は警告ログのみ）

### 今回やらないこと

- ArcGIS Online への永続保存（Feature Layer化）
- Dashboard連携
- 権限設計
- 時系列蓄積基盤の新設
- 既存 Leaflet 実装の置き換え

## 3. 実装方針（コード側）

## 3.1 追加ファイル

- `frontend/arcgis.html`
- `frontend/js/arcgis.js`

## 3.2 参照する既存データ

- API: `GET /api/gtfs/realtime/vehicles`
- 想定フィールド:
  - `latitude`
  - `longitude`
  - `route_id`
  - `route_short_name`（あれば）
  - `vehicle_id` または `id`
  - `timestamp`

## 3.3 実装メモ

- ArcGIS Maps SDK for JavaScript（4.x）をCDNで読み込む
- 地図中心は既存 `config.js` と近い値（東京駅付近）に合わせる
- 車両更新は `setInterval(..., 30000)` を使用
- 応答形式は以下の両方に対応する
  - 配列そのもの
  - `{ vehicles: [...] }`
- fetch失敗時は `console.warn` を出し、表示中の地物は維持する

## 4. ArcGIS Online 側の操作（非エンジニア向け）

第1段階では ArcGIS Online 側で必須作業はありません。  
ただし、次段階のために以下だけ先に済ませるとスムーズです。

1. ArcGIS Online にログイン
2. 任意のフォルダを作成（例: `easy-mta-poc`）
3. Web Map を1つ作成して保存（空でOK）
4. 組織設定で外部参照が必要な場合のルールを確認

メモ: 第1段階は ArcGIS SDK をブラウザで使うだけなので、Feature Layer の公開作業は不要です。

## 5. タスク分解（チェックリスト）

## 5.1 実装

- [x] `frontend/arcgis.html` を作成
- [x] ArcGIS SDK の CSS/JS を読み込む
- [x] `#viewDiv` を配置し、全画面または地図領域を確保
- [x] `frontend/js/arcgis.js` を作成
- [x] `Map` / `MapView` / `GraphicsLayer` を初期化
- [x] `/api/gtfs/realtime/vehicles` 取得処理を実装
- [x] 車両を `Graphic` として描画
- [x] 30秒ポーリングを実装
- [x] 取得失敗時の `console.warn` を追加

## 5.2 動作確認

- [ ] `http://127.0.0.1:8000/app/index.html` が従来どおり動く
- [x] `http://127.0.0.1:8000/arcgis.html` が表示できる
- [x] 車両が点で表示される
- [x] 車両クリックで系統・行先・車両ID・更新時刻のPopupが表示される
- [x] 上部に表示車両数と更新時刻が表示される
- [x] 30秒後に再描画される
- [x] API失敗時に画面が真っ白にならない

## 5.3 反映

- [ ] 差分確認（`git diff`）
- [ ] コミット
- [ ] `main` へ push

## 6. 次段階（第2段階）の候補

- ArcGIS Online の「URL からレイヤーを追加」で `GET /api/gtfs/realtime/vehicles.geojson` を試す
- ArcGISシンボルを系統色に合わせる
- Popupに行先や更新時刻を整形表示
- 停留所データも ArcGIS 側で重ねる
- ArcGIS Online へデータ保存して Dashboard 化

## 7. 次回の作業開始コマンド

```powershell
cd C:\github\easy-mta
git pull
```

その後、このドキュメントを開いて 5.1 の未チェック項目から再開する。
