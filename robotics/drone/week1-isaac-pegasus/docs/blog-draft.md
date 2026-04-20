# AWS g6でNVIDIA Isaac Sim + Pegasus Simulatorドローン環境を構築する

## はじめに

CES 2026でNVIDIAが発表したCosmos World Foundation Modelsを活用したドローン自律飛行プロジェクトの第1週目の成果をまとめます。

本記事では、実機ドローンを購入せずにシミュレーション環境を構築し、基本的な飛行デモを実装する方法を解説します。Week 2では、このデータを使ってNVIDIA Cosmos Transferで合成データを生成する予定です。

### 記事の対象読者

- ドローン開発に興味がある方
- Isaac SimやOmniverseに興味がある方
- AI/MLを使ったロボティクス開発をしたい方
- シミュレーションファーストの開発手法を学びたい方

### 得られる成果

- AWS上で動作するIsaac Sim + Pegasus環境
- Irisドローンの基本飛行デモ
- ROS2経由のセンサーデータ収集パイプライン
- Week 2（Cosmos Transfer）へ繋がるデータセット

---

## プロジェクト概要

### なぜシミュレーションから始めるのか

実機ドローンでの開発には以下の課題があります：

1. **高コスト**: ドローン本体 + センサー + コンピュータで数万円〜数十万円
2. **リスク**: クラッシュによる機体損傷
3. **場所の制約**: 屋外飛行には許可が必要、屋内は広い空間が必要
4. **データ収集の困難さ**: 様々な環境条件でのデータ取得に時間がかかる

シミュレーションなら：
- ✅ クラウドGPUで数百円〜数千円/週
- ✅ クラッシュしても問題なし
- ✅ 場所不問、24時間稼働可能
- ✅ 無限にデータ生成可能

### 技術スタック

```yaml
インフラ:
  - AWS EC2: g6.xlarge (NVIDIA L4 GPU)
  - OS: Ubuntu 22.04 LTS
  - Container: Docker + NVIDIA Container Toolkit

シミュレーション:
  - Isaac Sim: 4.5.0 (NGC Container)
  - Pegasus Simulator: v4.5.1
  - Physics: PhysX 5
  - Rendering: RTX Ray Tracing

ミドルウェア:
  - ROS2: Humble
  - Communication: MAVLink
  - Python: 3.10

ドローンモデル:
  - 機体: 3DR Iris Quadcopter
  - センサー: RGB/Depth Camera, IMU, GPS
```

---

## 環境構築

### Step 1: AWS EC2インスタンス準備

#### インスタンスタイプの選択

今回はg6.xlargeを選択：

```
g6.xlarge スペック:
- GPU: 1x NVIDIA L4 (24GB VRAM)
- vCPU: 4コア
- メモリ: 16GB
- コスト: $0.70/時間 (On-Demand)
         $0.21/時間 (Spot Instance)
```

**選定理由**:
- Isaac Sim 4.5.0の最小要件を満たす
- L4 GPUはRTXレイトレーシング対応
- コストパフォーマンスが良好

#### AMIの選択

```bash
Deep Learning Base OSS Nvidia Driver GPU AMI (Ubuntu 22.04)
```

このAMIには以下がプリインストール済み：
- NVIDIA Driver 550.x
- CUDA Toolkit 12.4
- Docker 26.0+

### Step 2: Docker + NVIDIA環境構築

セットアップスクリプトを実行：

```bash
cd week1-isaac-pegasus
bash scripts/01-aws-setup.sh
```

このスクリプトが実行する内容：

1. システムアップデート
2. 必要なツール (git, vim, htop等) のインストール
3. NVIDIA Driverの確認
4. Dockerのインストール
5. NVIDIA Container Toolkitのインストール
6. 動作確認テスト

**実行時間**: 約10-15分

#### 重要な注意点

スクリプト完了後は**必ずログアウト→再ログイン**：

```bash
exit
ssh -i your-key.pem ubuntu@<EC2_PUBLIC_IP>
```

これによりDockerグループの変更が反映されます。

### Step 3: Isaac Sim 4.5.0セットアップ

#### NGC APIキーの取得

1. [NGC](https://ngc.nvidia.com/setup/api-key)にアクセス
2. APIキーを生成
3. 環境変数に設定：

```bash
export NGC_API_KEY='your_api_key_here'
```

#### Isaac Simコンテナのpull

```bash
bash scripts/02-docker-isaac-setup.sh
```

このスクリプトが実行する内容：

1. NGC loginの実行
2. キャッシュディレクトリ作成 (~/.docker/isaac-sim)
3. **Isaac Sim 4.5.0 containerのpull (約20GB)**
4. workspaceディレクトリ作成
5. 環境変数の保存
6. 互換性テスト

**実行時間**: 約30-40分（ネットワーク速度に依存）

#### ディレクトリ構造

```
~/docker/isaac-sim/
├── cache/           # キャッシュ (シェーダー等)
├── config/          # 設定ファイル
├── data/            # Omniverseデータ
├── logs/            # ログファイル
└── pkg/             # パッケージ

~/workspace/
├── PegasusSimulator/     # Pegasus v4.5.1
├── models/               # Iris.usd
└── week1-isaac-pegasus/  # 本プロジェクト
```

### Step 4: Pegasus Simulator統合

```bash
bash scripts/03-pegasus-install.sh
```

Pegasus Simulator v4.5.1の特徴：

- **PX4/ArduPilot統合**: SITLシミュレーション
- **MAVLink通信**: 標準プロトコル
- **Multi-vehicle対応**: 複数機同時シミュレーション
- **Python API**: 簡単にスクリプト作成

#### 互換性の注意点

⚠️ **重要**: Pegasus v4.5.1はIsaac Sim 4.5.0専用です。

- ❌ Isaac Sim 5.0では動作しません
- ✅ Isaac Sim 4.5.0を使用してください

---

## 飛行デモ実装

### コンテナの起動

```bash
bash scripts/04-run-container.sh
```

モード選択画面：

```
Select container mode:
1) Interactive mode (bash shell)      ← 開発時
2) Headless mode with livestream     ← リモートアクセス時
3) Background mode (detached)         ← 長時間実行時
```

初回は「1」を選択してインタラクティブモードで起動。

### デモコードの解説

`src/demo_iris_flight.py`の主要部分：

```python
# Isaac Sim起動
from omni.isaac.kit import SimulationApp
simulation_app = SimulationApp({
    "headless": True,
    "width": 1280,
    "height": 720
})

# ワールド作成
from omni.isaac.core import World
world = World(stage_units_in_meters=1.0)
world.scene.add_default_ground_plane()

# Irisドローン追加
iris_usd_path = "/workspace/models/iris.usd"
add_reference_to_stage(usd_path=iris_usd_path, prim_path="/World/Iris")

# ウェイポイント定義
waypoints = [
    (0.0, 0.0, 2.0, "Takeoff to 2m"),
    (5.0, 0.0, 2.0, "Move forward 5m"),
    (5.0, 5.0, 2.0, "Move right 5m"),
    (0.0, 5.0, 2.0, "Move backward 5m"),
    (0.0, 0.0, 2.0, "Return to start"),
    (0.0, 0.0, 0.5, "Land")
]

# シミュレーション実行（60Hz）
while simulation_app.is_running():
    world.step(render=False)
    # ウェイポイント制御ロジック
```

### 実行結果

```bash
cd /workspace/week1-isaac-pegasus
/isaac-sim/python.sh src/demo_iris_flight.py
```

出力例：

```
============================================================
Week 1: Iris Drone Basic Flight Demo
============================================================

[1/6] World created with ground plane
[2/6] Adding environment...
[3/6] Iris drone added at /World/Iris
[4/6] Iris initial position set to (0, 0, 0.5)
[5/6] Simulation reset complete
[6/6] Starting flight sequence...

Flight Plan:
  Waypoint 1: (  0.0,   0.0,  2.0m) - Takeoff to 2m
  Waypoint 2: (  5.0,   0.0,  2.0m) - Move forward 5m
  ...

Reached waypoint 1: Takeoff to 2m
Reached waypoint 2: Move forward 5m
...

============================================================
Flight sequence completed!
Total simulation time: 12.00s
Total steps: 720
============================================================
```

**シミュレーション性能**:
- 物理ステップ: 60Hz (16.67ms/step)
- レンダリング: 30Hz (ヘッドレスモードでは無効化可能)
- リアルタイム係数: 約1.0x (実時間と同期)

---

## データ収集

### ROS2ブリッジの設定

Isaac Sim 4.5.0にはROS2 Humbleが内蔵されています：

```bash
# コンテナ内で環境変数設定
export ROS_DISTRO=humble
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
export ROS_DOMAIN_ID=0
```

### データ収集スクリプト

別ターミナルでコンテナに入り、データ収集を開始：

```bash
docker exec -it isaac-sim-week1 bash
cd /workspace/week1-isaac-pegasus
/isaac-sim/python.sh src/data_collector.py
```

収集されるデータ：

1. **RGB画像**: 640x480, 30fps → 6fps間引き保存
2. **Depth画像**: 640x480, 30fps → 6fps間引き保存
3. **IMUデータ**: 加速度・角速度, 100Hz
4. **Odometry**: 位置・姿勢・速度, 60Hz
5. **GPSデータ**: 緯度・経度・高度, 10Hz

### 収集結果

```
Data Collection Summary
============================================================
Session ID: 20260108_120000
Duration: 60.00 seconds
Images saved: 360
IMU messages: 6000
Odom messages: 3600
============================================================

Image directory: /workspace/week1-isaac-pegasus/data/images/20260108_120000
Log file: /workspace/week1-isaac-pegasus/data/logs/flight_log_20260108_120000.jsonl
```

---

## パフォーマンス評価

### シミュレーション性能

AWS g6.xlargeでの測定結果：

| 指標 | 値 |
|------|-----|
| 物理シミュレーションFPS | 60 fps |
| レンダリングFPS | 30 fps |
| GPU利用率 | 40-60% |
| VRAM使用量 | 8-12 GB |
| CPU利用率 | 60-80% |
| メモリ使用量 | 10-14 GB |

### コスト分析

1週間の開発コスト（40時間稼働）：

```
On-Demand Instance:
  $0.70/h × 40h = $28.00

Spot Instance (70% off):
  $0.21/h × 40h = $8.40

EBS 100GB (gp3):
  $10.00/月

合計: 約 $18.40 (Spot利用時)
```

**実機ドローン開発と比較**:
- Holybro X500 Kit: ~$600
- Jetson Orin Nano: ~$499
- カメラ・センサー: ~$400
- **合計: ~$1,500**

シミュレーションなら**$18/週**で開発可能！

---

## トラブルシューティング

### 問題1: GPU Out of Memory

**症状**: シミュレーション実行中にクラッシュ

**解決策**:
```python
# レンダリング解像度を下げる
simulation_app = SimulationApp({
    "headless": True,
    "width": 640,   # 1280 → 640
    "height": 480   # 720 → 480
})
```

### 問題2: ROS2トピックが見えない

**症状**: `ros2 topic list`で何も表示されない

**解決策**:
```bash
# ROS_DOMAIN_IDを確認
echo $ROS_DOMAIN_ID  # 0であるべき

# Isaac Sim側のROS2ブリッジを確認
# Window → Extensions → "ros2"で検索
# isaacsim.ros2.bridgeが有効か確認
```

### 問題3: Iris modelが見つからない

**症状**: `ERROR: Iris model not found`

**解決策**:
```bash
# 手動ダウンロード
mkdir -p /workspace/models
wget -O /workspace/models/iris.usd \
  https://github.com/PegasusSimulator/PegasusSimulator/raw/v4.5.1/pegasus_simulator/params/robots/iris.usd
```

---

## まとめ

### Week 1で達成したこと

✅ AWS EC2上でIsaac Sim 4.5.0環境を構築  
✅ Pegasus Simulator v4.5.1を統合  
✅ Irisドローンの基本飛行デモを実装  
✅ ROS2経由でセンサーデータを収集  
✅ 60秒の飛行ログ・360枚の画像を取得

### 学んだこと

1. **シミュレーションファースト開発の利点**
   - 低コスト、低リスクで開発可能
   - 無限にデータ生成できる
   - 様々な環境条件を簡単に試せる

2. **Isaac SimとPegasusの強力な組み合わせ**
   - PhysX 5による正確な物理シミュレーション
   - RTXレイトレーシングによる高品質レンダリング
   - PX4/MAVLink統合による実機への移行が容易

3. **AWS g6インスタンスの有効性**
   - L4 GPUはコスパ良好
   - Spot Instanceで70%コスト削減
   - 必要な時だけ起動できる柔軟性

### Week 2への展望

次週では、収集したデータを使ってNVIDIA Cosmos Transferで合成データを生成します：

1. **Cosmos Transfer**
   - Isaac Simの3DシーンからリアルなビデオCES生成
   - 様々な天候・照明条件のデータ拡張
   - 大規模データセットの構築

2. **Cosmos Reason**
   - 自動アノテーション（手動ラベリング不要）
   - 障害物検出モデルの訓練

3. **知識蒸留**
   - 軽量モデル（<100MB）の作成
   - Jetson Nanoでの実行を想定

Stay tuned for Week 2! 🚁

---

## 参考リンク

- [プロジェクトGitHub](https://github.com/your-repo/week1-isaac-pegasus)
- [NVIDIA Isaac Sim Documentation](https://docs.isaacsim.omniverse.nvidia.com/4.5.0/)
- [Pegasus Simulator](https://pegasussimulator.github.io/PegasusSimulator/)
- [NVIDIA Cosmos Platform](https://www.nvidia.com/en-us/ai/cosmos/)
- [AWS EC2 G6 Instances](https://aws.amazon.com/ec2/instance-types/g6/)

---

**執筆者**: [Your Name]  
**執筆日**: 2026年1月8日  
**プロジェクト**: Cosmos駆動型自律ドローンシステム Week 1  
**タグ**: #AI #Robotics #Drone #IsaacSim #NVIDIA #Cosmos #AWS
