# ArcGIS Online 個人版（3）アップロード用ファイル

## 生成済みファイル

- `routes-shapes-exact.geojson`
- `stops-terminals.geojson`

## 取り込み順（ArcGIS Online 個人版）

1. `routes-shapes-exact.geojson` をアップロード（線レイヤー）
2. `stops-terminals.geojson` をアップロード（始点/終点ポイント）
3. 既存の `都バス車両位置CSV` レイヤーを重ねる（点レイヤー）

## 推奨レイヤー順（下から）

1. `routes-shapes-exact`
2. `stops-terminals`
3. `都バス車両位置CSV`

## 表示項目ルール

- 識別キー: `route_id`
- 表示名: `route_short_name`（空なら `route_id`）
