# 🗽 Easy MTA — ニューヨーク地下鉄リアルタイムガイド

ニューヨークMTAのオープンデータを活用し、左側にLeaflet.jsのGISマップ、右側にDifyベースのLLMチャットを配置した「シームレスなリアルタイム運行案内Webアプリケーション」のPoC（概念実証）です。

**対象ユーザー:** 英語でのナビゲーションに不慣れな日本人観光客

---

## 🌟 主な機能

### Chat → Map（Dify → マップ）
Difyがユーザーの自然言語を解釈し、マップを操作します：
- 「タイムズスクエア駅を表示して」→ 自動ズームイン
- 「車椅子で乗れる駅は？」→ バリアフリー駅のみハイライト
- 「Aトレインの駅を見せて」→ 路線フィルター

### Map → Chat（マップ → Dify）
マップ上の要素をクリックすると、AIが日本語で解説します：
- 駅クリック → 路線・バリアフリー情報を日本語解説
- 列車アイコンクリック → リアルタイム遅延・混雑情報

### リアルタイムデータ
- MTA GTFS-Realtimeから30秒ごとに車両位置を更新
- 遅延・運休などのサービスアラートを表示
- APIキーなしでもモックデータでデモ動作

---

## 🛠 技術スタック

| 層 | 技術 |
|---|---|
| Backend | Python 3.12 + FastAPI |
| Frontend | HTML/CSS/JavaScript + Leaflet.js 1.9 |
| Map | OpenStreetMap tiles (無料) |
| AI Chat | Dify API (self-hosted or cloud) |
| RT Data | MTA GTFS-Realtime (protobuf) |
| Deploy | Docker + docker-compose |

---

## 🚀 セットアップ

### 前提条件
- Docker + Docker Compose
- （任意）MTA Developer API Key：https://api.mta.info/#/signup
- （任意）Dify API URL と API Key（セルフホストの場合は例: `http://localhost`、クラウドの場合は `https://api.dify.ai`）

### 手順

```bash
# 1. リポジトリをクローン
git clone https://github.com/junhongo-ccs/easy-mta.git
cd easy-mta

# 2. 環境変数ファイルを作成
cp .env.example .env
# .env を編集して MTA_API_KEY / DIFY_API_URL / DIFY_API_KEY を設定（任意）

# 3. 起動
docker-compose up --build

# 4. ブラウザで開く
open http://localhost:8000
```

**APIキーなし（デモモード）**: `.env` を編集しなくてもモックデータで動作します。

---

## 📁 プロジェクト構成

```
easy-mta/
├── docker-compose.yml
├── .env.example
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── main.py                  # FastAPI アプリ
│   ├── routers/
│   │   ├── gtfs.py              # GTFS API エンドポイント
│   │   └── chat.py              # Dify チャットプロキシ
│   └── services/
│       ├── gtfs_static.py       # GTFS 静的データ（駅・路線）
│       └── gtfs_realtime.py     # MTA GTFS-Realtime 解析
└── frontend/
    ├── index.html               # メイン SPA
    ├── css/style.css            # ダークトランジットテーマ
    └── js/
        ├── config.js            # 設定（路線カラーなど）
        ├── map.js               # MapManager（Leaflet）
        ├── chat.js              # ChatManager（Dify）
        └── app.js               # アプリ起動・ワイヤリング
```

---

## 🗺 API エンドポイント

| エンドポイント | 説明 |
|---|---|
| `GET /api/gtfs/stops` | 全駅情報（緯度経度・路線・バリアフリー） |
| `GET /api/gtfs/routes` | 全路線情報（カラーコード含む） |
| `GET /api/gtfs/stops/{stop_id}` | 駅詳細＋リアルタイム到着情報 |
| `GET /api/gtfs/realtime/vehicles` | 車両リアルタイム位置 |
| `GET /api/gtfs/realtime/trip-updates` | 列車遅延・到着予測 |
| `GET /api/gtfs/realtime/alerts` | サービスアラート |
| `POST /api/chat/message` | Dify チャットプロキシ |
| `DELETE /api/chat/conversation/{conversation_id}` | Dify 会話の削除 |

---

## 🎭 Dify マップコマンド

Dify のレスポンスに以下の JSON ブロックを含めることで、マップを操作できます：

```json
{"type": "focusOn", "lat": 40.7559, "lng": -73.9874, "zoom": 15}
{"type": "filterAccessible"}
{"type": "highlightStop", "stop_id": "127"}
{"type": "showRoute", "route_id": "A"}
{"type": "resetFilters"}
```

---

## 📄 ライセンス

MIT License

データ提供: [MTA Open Data](https://api.mta.info/) / [OpenStreetMap](https://www.openstreetmap.org/copyright)
