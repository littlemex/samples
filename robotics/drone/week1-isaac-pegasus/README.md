# Week 1: AWS g6でNVIDIA Isaac Sim + Pegasus Simulatorドローン環境構築

CES 2026でNVIDIAが発表したCosmos World Foundation Modelsを活用したドローン自律飛行プロジェクトの第1週目。
本週では、実機ドローンを購入せずにシミュレーション環境を構築し、基本的な飛行デモを実装します。

## 🎯 Week 1の目標

- AWS EC2（g6.xlarge）上でIsaac Sim 4.5.0をDockerコンテナで起動
- Pegasus Simulator v4.5.1を統合し、Irisクアッドコプターをシミュレーション
- ROS2 Humbleブリッジでセンサーデータを取得
- ウェイポイント飛行デモの実装とデータ収集
- ブログ記事の執筆

## 📋 プロジェクト構成

```
week1-isaac-pegasus/
├── README.md                          # このファイル
├── docs/
│   ├── blog-draft.md                 # ブログ記事下書き
│   └── setup-guide.md                # 詳細セットアップガイド
├── scripts/
│   ├── 01-aws-setup.sh               # EC2初期セットアップ
│   ├── 02-docker-isaac-setup.sh      # Docker + Isaac Sim
│   ├── 03-pegasus-install.sh         # Pegasus Simulator
│   └── 04-run-container.sh           # コンテナ起動スクリプト
├── src/
│   ├── demo_iris_flight.py           # 基本飛行デモ
│   ├── data_collector.py             # データ収集スクリプト
│   └── waypoint_controller.py        # ウェイポイント制御
├── config/
│   ├── ros2_config.yaml              # ROS2設定
│   └── simulation_params.yaml        # シミュレーションパラメータ
└── data/                              # 収集データ保存先
    ├── images/
    └── logs/
```

## 🚀 クイックスタート

### 前提条件

- AWS アカウント
- NGC (NVIDIA GPU Cloud) APIキー
- 基本的なDocker、ROS2の知識

### セットアップ手順

1. **AWS EC2インスタンス起動**
```bash
# g6.xlarge instance (Ubuntu 22.04, Deep Learning AMI)
bash scripts/01-aws-setup.sh
```

2. **Isaac Sim 4.5.0 + Docker環境構築**
```bash
bash scripts/02-docker-isaac-setup.sh
```

3. **Pegasus Simulator統合**
```bash
bash scripts/03-pegasus-install.sh
```

4. **コンテナ起動**
```bash
bash scripts/04-run-container.sh
```

5. **飛行デモ実行**
```bash
# コンテナ内で実行
/isaac-sim/python.sh src/demo_iris_flight.py
```

## 📊 技術スタック

### インフラ
- **AWS EC2**: g6.xlarge (1x NVIDIA L4 GPU, 4 vCPU, 16GB RAM)
- **OS**: Ubuntu 22.04 LTS
- **Container**: Docker 26.0+, NVIDIA Container Toolkit

### シミュレーション
- **Isaac Sim**: 4.5.0 (NGC Container)
- **Pegasus Simulator**: v4.5.1
- **Physics Engine**: PhysX 5
- **Rendering**: RTX Ray Tracing

### ミドルウェア
- **ROS2**: Humble (内蔵)
- **Communication**: MAVLink, PX4 SITL
- **Python**: 3.10

### ドローンモデル
- **機体**: 3DR Iris Quadcopter
- **センサー**: RGB Camera, Depth Camera, IMU, GPS

## 💰 コスト見積もり

```
AWS g6.xlarge On-Demand: $0.70/h
週40時間開発: $28.00
Spot Instance (70% off): $8.40
EBS 100GB: $10.00/月
━━━━━━━━━━━━━━━━━━━━━
合計: 約 $18.40 (1週間)
```

## 📈 Week 1成果物

1. ✅ AWS上で動作するIsaac Sim + Pegasus環境
2. ✅ Irisドローンの基本飛行デモ（ウェイポイント飛行）
3. ✅ ROS2経由のセンサーデータ収集パイプライン
4. ✅ 飛行ログ・カメラ画像データセット
5. ✅ 技術ブログ記事（セットアップ手順・コード解説）

## 🔗 Week 2への接続

Week 2では、収集した飛行データを使ってNVIDIA Cosmos Transferで合成データを生成します：
- Isaac Simの3Dシーンから高品質ビデオ生成
- 様々な環境条件（天候、照明）のデータ拡張
- Cosmos Reasonによる自動アノテーション

## 📚 参考リンク

- [NVIDIA Isaac Sim Documentation](https://docs.isaacsim.omniverse.nvidia.com/)
- [Pegasus Simulator GitHub](https://github.com/PegasusSimulator/PegasusSimulator)
- [NVIDIA Cosmos Platform](https://www.nvidia.com/en-us/ai/cosmos/)
- [PX4 Autopilot](https://px4.io/)
- [ROS2 Humble](https://docs.ros.org/en/humble/)

## 🤝 貢献

このプロジェクトはオープンソースです。Issue・PRを歓迎します。

## 📄 ライセンス

MIT License

## 👤 作成者

Week 1実装: 2026年1月

---

**次のステップ**: `docs/setup-guide.md`で詳細な環境構築手順を確認してください。
