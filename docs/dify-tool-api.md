# Dify Tool API メモ

都バス運行案内PoCで、Difyから呼ばせる想定のFastAPIエンドポイント。

## 系統で走行中車両を探す

```http
GET /api/gtfs/realtime/vehicles/search?route=早77&limit=5
```

入力例:

- `route=早77`
- `route=147`
- `route=都01`
- `route=新宿駅西口`

返却内容:

- `vehicle_id`
- `route_id`
- `route_short_name`
- `route_display_name`
- `origin`
- `destination`
- `latitude`
- `longitude`
- `timestamp`
- `source`

Difyでの使い方:

- 「早77はどこ？」
- 「新宿駅西口行きのバスは？」
- 「147系統を探して」

## 周辺の走行中車両を探す

```http
GET /api/gtfs/realtime/vehicles/nearby?lat=35.689634&lng=139.692101&radius_m=900&limit=5
```

返却内容:

- 車両情報一式
- `distance_m`

Difyでの使い方:

- 「都庁の近くを走っているバスを教えて」
- 「この地点の周辺車両を探して」
- 「半径1km以内の都バスは？」

## 停留所を探す

```http
GET /api/gtfs/stops/search?q=都庁&limit=5
```

返却内容:

- `stop_id`
- `stop_name`
- `stop_lat`
- `stop_lon`
- `routes`
- `wheelchair_accessible`
- `area`

Difyでの使い方:

- 自然文から停留所名を抽出
- 停留所の緯度経度を取得
- その緯度経度で `/vehicles/nearby` を呼ぶ

## Difyで作るとよい処理

1. ユーザー文から系統名が取れる場合
   - `/vehicles/search` を呼ぶ
   - 車両一覧を要約
   - 最初の車両へ `map_command: focusOn` を返す

2. ユーザー文から場所・停留所名が取れる場合
   - `/stops/search` を呼ぶ
   - 見つかった停留所の緯度経度で `/vehicles/nearby` を呼ぶ
   - 近い順に車両を要約
   - 最寄り車両または停留所へ `map_command: focusOn` を返す

3. Difyが判断できない場合
   - 「系統名または停留所名を指定してください」と聞き返す

## map_command 例

```json
{"type": "focusOn", "lat": 35.710808, "lng": 139.709915, "zoom": 15}
```

```json
{"type": "resetFilters"}
```
