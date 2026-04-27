# 都バス運行案内サイト PoC

都バス公式ホームページ提案に向けた、リアルタイム車両位置とAI案内の体験デモです。

左側にLeaflet.jsの地図、右側にDify連携を想定したチャットを配置し、利用者が自然文で停留所・系統・運行状況にアクセスできるイメージを示します。

## 現在できること

- 都バス風の停留所モック表示
- ODPT GTFS-RT VehiclePosition による都バス実車両位置表示
- 30秒ごとの車両位置更新
- 停留所・車両クリックからチャット案内
- 車両案内中に同じ車両を再クリックすると、地図の位置・ズームを保ったまま全バス表示へ戻る
- チャットから地図操作
  - 「都庁前付近を表示して」
  - 「都01を見せて」
  - 「バリアフリー停留所を表示して」

## 今後の接続先

- 公共交通オープンデータセンターの都バス GTFS/GTFS-JP 静的情報
- 公共交通オープンデータセンターの都バス GTFS-RT VehiclePosition
- Dify API
- 公式FAQや問い合わせ導線のRAG

実装計画は [docs/toei-bus-dify-demo-plan.md](docs/toei-bus-dify-demo-plan.md) を参照してください。

Dify Toolとして使うAPIは [docs/dify-tool-api.md](docs/dify-tool-api.md) を参照してください。

DifyへインポートするOpenAPI定義は [docs/dify-tools-openapi.yaml](docs/dify-tools-openapi.yaml)、アプリ用プロンプト案は [docs/dify-app-prompt.md](docs/dify-app-prompt.md) です。

## ローカル起動

Dockerが使える場合:

```bash
cp .env.example .env
docker compose up --build
```

Pythonで直接起動する場合:

```bash
cp .env.example .env
py -m venv .venv
.\.venv\Scripts\python -m pip install -r backend\requirements.txt
cd backend
..\.venv\Scripts\python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

ブラウザで開きます。

```text
http://127.0.0.1:8000
```

## Railwayデプロイ

このリポジトリはRailway向けにルートの `Dockerfile` と `railway.json` を用意しています。

手順:

1. このブランチをGitHubへpush
2. Railwayで `New Project` → `Deploy from GitHub repo`
3. 対象リポジトリとブランチを選択
4. Railwayがルートの `Dockerfile` でビルド
5. Deploy後に生成される公開URLを確認

Railway側の環境変数:

```env
ODPT_API_KEY=
ODPT_PUBLIC_GTFS_RT_URL=https://api-public.odpt.org/api/v4/gtfs/realtime/ToeiBus
ODPT_BUSROUTE_PATTERN_URL=https://api-public.odpt.org/api/v4/odpt:BusroutePattern
ODPT_GTFS_RT_URL=
ODPT_SSL_VERIFY=true
DIFY_API_URL=https://api.dify.ai
DIFY_API_KEY=
```

Railway上では原則 `ODPT_SSL_VERIFY=true` を使います。ローカルPCで証明書検証に失敗する場合のみ `.env` で `false` にしてください。

Dify CloudでToolを登録する場合は、[docs/dify-tools-openapi.yaml](docs/dify-tools-openapi.yaml) の `servers.url` をRailwayの公開URLに変更してからインポートします。

```yaml
servers:
  - url: https://your-app.up.railway.app
```

## 環境変数

```env
ODPT_API_KEY=
DIFY_API_URL=https://api.dify.ai
DIFY_API_KEY=
```

GTFS-RT VehiclePosition は、公開エンドポイント `https://api-public.odpt.org/api/v4/gtfs/realtime/ToeiBus` を利用します。

このローカル環境でPythonの証明書検証に失敗する場合は、検証用に `.env` で `ODPT_SSL_VERIFY=false` を指定できます。本番や共有環境では `true` を使ってください。

## 主なAPI

| Endpoint | 説明 |
|---|---|
| `GET /api/gtfs/stops` | 停留所一覧 |
| `GET /api/gtfs/stops/search?q=都庁` | 停留所検索 |
| `GET /api/gtfs/routes` | 系統一覧 |
| `GET /api/gtfs/stops/{stop_id}` | 停留所詳細 |
| `GET /api/gtfs/realtime/vehicles` | 車両位置 |
| `GET /api/gtfs/realtime/vehicles/search?route=早77` | 系統・行先で車両検索 |
| `GET /api/gtfs/realtime/vehicles/nearby?lat=35.689634&lng=139.692101` | 周辺車両検索 |
| `GET /api/gtfs/realtime/alerts` | 運行アラート |
| `POST /api/chat/message` | Difyチャットプロキシ |

## データについて

現在の停留所データは提案用のモックです。車両位置はODPTのGTFS-RT VehiclePositionから取得します。

都バスの実データ接続では、公共交通オープンデータセンターで提供される東京都交通局データの利用条件、ライセンス、クレジット表記を確認します。

クレジット表示対象:

- 東京都交通局・公共交通オープンデータ協議会
