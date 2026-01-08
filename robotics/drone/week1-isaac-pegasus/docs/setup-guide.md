# Week 1: 詳細セットアップガイド

AWS EC2上でNVIDIA Isaac Sim 4.5.0 + Pegasus Simulator v4.5.1を使ったドローンシミュレーション環境の構築手順

## 📋 目次

1. [前提条件](#前提条件)
2. [AWS EC2インスタンス準備](#aws-ec2インスタンス準備)
3. [Docker + NVIDIA環境構築](#docker--nvidia環境構築)
4. [Isaac Sim 4.5.0セットアップ](#isaac-sim-450セットアップ)
5. [Pegasus Simulator統合](#pegasus-simulator統合)
6. [飛行デモ実行](#飛行デモ実行)
7. [トラブルシューティング](#トラブルシューティング)

---

## 前提条件

### 必要なアカウント・認証情報

- **AWSアカウント**
  - EC2インスタンス起動権限
  - g6.xlarge以上のインスタンスタイプにアクセス可能
  
- **NVIDIA GPU Cloud (NGC) アカウント**
  - NGC APIキー（[取得方法](https://ngc.nvidia.com/setup/api-key)）
  - Isaac Simコンテナへのアクセス権限

### 推奨スキル

- 基本的なLinuxコマンドライン操作
- Dockerの基礎知識
- ROS2の基本的な理解（オプション）

### 推奨開発環境

- ローカルPC: SSH接続可能な環境
- エディタ: VS Code + Remote SSH拡張機能（推奨）

---

## AWS EC2インスタンス準備

### Step 1: EC2インスタンス起動

1. **AWSコンソールにログイン**
   - EC2ダッシュボードを開く

2. **インスタンスタイプ選択**
   ```
   推奨: g6.xlarge
   - GPU: 1x NVIDIA L4 (24GB)
   - vCPU: 4
   - メモリ: 16GB
   - コスト: ~$0.70/時間
   ```

3. **AMI選択**
   ```
   推奨: Deep Learning Base OSS Nvidia Driver GPU AMI (Ubuntu 22.04)
   - NVIDIA Driver 550.x以上がプリインストール済み
   - CUDA Toolkitも含まれる
   ```
   
   または、Ubuntu 22.04 LTSを選択してNVIDIA Driverを手動インストール

4. **ストレージ設定**
   ```
   - ルートボリューム: 100GB以上（推奨150GB）
   - タイプ: gp3 (高速・コスト効率)
   ```

5. **セキュリティグループ設定**
   ```
   インバウンドルール:
   - SSH (22): 自分のIPアドレスのみ
   - HTTP (8211): WebRTC Streaming用（オプション）
   ```

6. **キーペア**
   - 既存のキーペアを選択、または新規作成

7. **インスタンス起動**

### Step 2: インスタンスへ接続

```bash
# SSH接続
ssh -i your-key.pem ubuntu@<EC2_PUBLIC_IP>

# または、Session Managerを使用（セキュリティ向上）
aws ssm start-session --target <INSTANCE_ID>
```

### Step 3: 初期確認

```bash
# NVIDIA Driver確認
nvidia-smi

# 出力例:
# +-----------------------------------------------------------------------------+
# | NVIDIA-SMI 550.90.07    Driver Version: 550.90.07    CUDA Version: 12.4   |
# |-------------------------------+----------------------+----------------------+
# | GPU  Name        Persistence-M| Bus-Id        Disp.A | Volatile Uncorr. ECC |
# | Fan  Temp  Perf  Pwr:Usage/Cap|         Memory-Usage | GPU-Util  Compute M. |
# |===============================+======================+======================|
# |   0  NVIDIA L4           Off  | 00000000:00:1E.0 Off |                    0 |
# | N/A   30C    P8    10W /  72W |      0MiB / 23034MiB |      0%      Default |
# +-------------------------------+----------------------+----------------------+
```

---

## Docker + NVIDIA環境構築

### Step 4: 自動セットアップスクリプト実行

Week 1プロジェクトのスクリプトを使用します。

```bash
# プロジェクトをクローン（GitHubにプッシュ済みの場合）
git clone https://github.com/your-repo/week1-isaac-pegasus.git
cd week1-isaac-pegasus

# または、ローカルから転送
scp -i your-key.pem -r week1-isaac-pegasus ubuntu@<EC2_PUBLIC_IP>:~/
```

### Step 5: AWSセットアップスクリプト実行

```bash
cd week1-isaac-pegasus
bash scripts/01-aws-setup.sh
```

このスクリプトは以下を実行します：
- システムアップデート
- 必要なツールのインストール
- NVIDIA Driverの確認
- Dockerのインストール
- NVIDIA Container Toolkitのインストール

**実行時間**: 約10-15分

### 注意事項

スクリプト完了後、**必ずログアウト→再ログイン**してください：

```bash
exit  # SSH切断
ssh -i your-key.pem ubuntu@<EC2_PUBLIC_IP>  # 再接続
```

これによりDockerグループの変更が反映されます。

---

## Isaac Sim 4.5.0セットアップ

### Step 6: NGC APIキー設定

```bash
# NGC APIキーを環境変数に設定
export NGC_API_KEY='your_ngc_api_key_here'

# 確認
echo $NGC_API_KEY
```

### Step 7: Isaac Simセットアップスクリプト実行

```bash
cd ~/week1-isaac-pegasus
bash scripts/02-docker-isaac-setup.sh
```

このスクリプトは以下を実行します：
1. NGC loginの実行
2. キャッシュディレクトリ作成
3. Isaac Sim 4.5.0 containerのpull（**約20-30分**）
4. workspaceディレクトリ作成
5. 環境変数の保存
6. 互換性テスト

**実行時間**: 約30-40分（ネットワーク速度に依存）

### Step 8: 環境変数の永続化

```bash
# .bashrcに追加
echo "source ~/.isaac_sim_env" >> ~/.bashrc

# 即座に反映
source ~/.isaac_sim_env
```

---

## Pegasus Simulator統合

### Step 9: Pegasusインストールスクリプト実行

```bash
cd ~/week1-isaac-pegasus
bash scripts/03-pegasus-install.sh
```

このスクリプトは以下を実行します：
1. Pegasus Simulator v4.5.1のクローン
2. Iris droneモデルのダウンロード
3. Week 1プロジェクトのworkspaceへのコピー

**実行時間**: 約5-10分

### Step 10: コンテナ起動

```bash
bash scripts/04-run-container.sh
```

モード選択画面が表示されます：
```
Select container mode:
1) Interactive mode (bash shell)
2) Headless mode with livestream
3) Background mode (detached)

Enter choice [1-3]:
```

**初回は「1」を選択**（インタラクティブモード）

### Step 11: コンテナ内でPegasusインストール

コンテナ内で以下を実行：

```bash
# Pegasus Simulatorディレクトリへ移動
cd /workspace/PegasusSimulator

# Pegasusをインストール
/isaac-sim/python.sh -m pip install -e .

# インストール確認
/isaac-sim/python.sh -c "import pegasus; print('Pegasus installed successfully!')"
```

**実行時間**: 約5分

---

## 飛行デモ実行

### Step 12: 基本飛行デモ

```bash
cd /workspace/week1-isaac-pegasus

# デモ実行
/isaac-sim/python.sh src/demo_iris_flight.py
```

**期待される出力**:
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
  Waypoint 3: (  5.0,   5.0,  2.0m) - Move right 5m
  Waypoint 4: (  0.0,   5.0,  2.0m) - Move backward 5m
  Waypoint 5: (  0.0,   0.0,  2.0m) - Return to start
  Waypoint 6: (  0.0,   0.0,  0.5m) - Land

Starting simulation...
Time step: 0.0167s (60Hz)

Reached waypoint 1: Takeoff to 2m
...
```

**実行時間**: 約60秒

### Step 13: データ収集（オプション）

別のターミナルでコンテナに入り、ROS2データ収集を実行：

```bash
# 別ターミナルでコンテナに入る
docker exec -it isaac-sim-week1 bash

# ROS2環境設定
export ROS_DISTRO=humble
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp

# データ収集開始
cd /workspace/week1-isaac-pegasus
/isaac-sim/python.sh src/data_collector.py
```

**Ctrl+C**で停止すると、データサマリーが表示されます。

---

## トラブルシューティング

### 問題1: NVIDIA Driver not found

**症状**:
```
ERROR: NVIDIA Driver not found!
```

**解決策**:
```bash
# NVIDIA Driverを手動インストール
sudo apt-get update
sudo apt-get install -y nvidia-driver-550
sudo reboot
```

### 問題2: NGC login failed

**症状**:
```
ERROR: NGC login failed!
```

**解決策**:
1. NGC APIキーを確認: https://ngc.nvidia.com/setup/api-key
2. 環境変数を再設定:
```bash
export NGC_API_KEY='correct_api_key'
```

### 問題3: Docker permission denied

**症状**:
```
Got permission denied while trying to connect to the Docker daemon socket
```

**解決策**:
```bash
# ログアウト→再ログイン
exit
ssh -i your-key.pem ubuntu@<EC2_PUBLIC_IP>

# それでも解決しない場合
sudo usermod -aG docker $USER
newgrp docker
```

### 問題4: Iris model not found

**症状**:
```
ERROR: Iris model not found at /workspace/models/iris.usd
```

**解決策**:
```bash
# 手動でダウンロード
mkdir -p /workspace/models
cd /workspace/models
wget https://github.com/PegasusSimulator/PegasusSimulator/raw/v4.5.1/pegasus_simulator/params/robots/iris.usd
```

### 問題5: Out of memory (OOM)

**症状**:
シミュレーション実行中にプロセスが強制終了

**解決策**:
1. より大きなインスタンスタイプに変更（g6.2xlarge以上）
2. レンダリング解像度を下げる
3. headlessモードで実行

### 問題6: ROS2 topics not visible

**症状**:
`ros2 topic list`で何も表示されない

**解決策**:
```bash
# ROS_DOMAIN_IDを確認
echo $ROS_DOMAIN_ID  # 0であるべき

# Isaac Sim側のROS2ブリッジを確認
# Window → Extensions → search "ros2"
# isaacsim.ros2.bridge が有効か確認
```

---

## パフォーマンスチューニング

### AWS Spot Instanceの活用

コスト削減のため、Spot Instanceを使用：

```bash
# Spot Instance料金例
# g6.xlarge: $0.21/h (On-Demand: $0.70/h)
# 約70%のコスト削減
```

**注意**: Spot Instanceは中断される可能性があるため、重要なデータは定期的に保存

### EBSボリュームの最適化

```bash
# gp3ボリュームのIOPSを増やす（オプション）
# Default: 3000 IOPS
# Max: 16000 IOPS
# AWS Console or CLI で設定変更
```

---

## 次のステップ

Week 1のセットアップが完了したら：

1. **ブログ記事執筆**: `docs/blog-draft.md`を参照
2. **Week 2準備**: Cosmos Transferのセットアップ
3. **データ分析**: 収集したデータの可視化

---

## 参考リンク

- [NVIDIA Isaac Sim Documentation](https://docs.isaacsim.omniverse.nvidia.com/4.5.0/)
- [Pegasus Simulator Documentation](https://pegasussimulator.github.io/PegasusSimulator/)
- [ROS2 Humble Documentation](https://docs.ros.org/en/humble/)
- [AWS EC2 GPU Instances](https://aws.amazon.com/ec2/instance-types/g6/)
- [NVIDIA NGC](https://ngc.nvidia.com/)

---

**作成日**: 2026年1月8日  
**バージョン**: 1.0.0  
**対象**: Week 1 - Isaac Sim + Pegasus Simulator環境構築
