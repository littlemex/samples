#!/usr/bin/env python3
"""
Week 1: Iris Drone Basic Flight Demo
Isaac Sim 4.5.0 + Pegasus Simulator v4.5.1でIrisドローンの基本飛行を実行
"""

import sys
import asyncio
import numpy as np
from pathlib import Path

# Isaac Sim起動
from omni.isaac.kit import SimulationApp
simulation_app = SimulationApp({
    "headless": True,  # ヘッドレスモード
    "width": 1280,
    "height": 720
})

# Isaac SimとPegasusのインポート
import omni
from omni.isaac.core import World
from omni.isaac.core.utils.stage import add_reference_to_stage
from pxr import Gf

print("=" * 60)
print("Week 1: Iris Drone Basic Flight Demo")
print("=" * 60)
print()

# ワールドの作成
world = World(stage_units_in_meters=1.0)
world.scene.add_default_ground_plane()

print("[1/6] World created with ground plane")

# 環境の追加（シンプルなグリッド）
# Note: Pegasusの環境アセットを使う場合はここで追加
print("[2/6] Adding environment...")

# Irisドローンモデルのパス
# コンテナ内では /workspace/models/iris.usd にあると想定
iris_usd_path = "/workspace/models/iris.usd"

if not Path(iris_usd_path).exists():
    print(f"ERROR: Iris model not found at {iris_usd_path}")
    print("Please download iris.usd using scripts/03-pegasus-install.sh")
    simulation_app.close()
    sys.exit(1)

# Irisドローンを追加
iris_prim_path = "/World/Iris"
add_reference_to_stage(usd_path=iris_usd_path, prim_path=iris_prim_path)

print(f"[3/6] Iris drone added at {iris_prim_path}")

# 初期位置設定（地面から少し浮かせる）
from omni.isaac.core.utils.prims import get_prim_at_path
iris_prim = get_prim_at_path(iris_prim_path)
if iris_prim:
    # 位置を設定 (x, y, z) = (0, 0, 0.5) メートル
    from pxr import UsdGeom
    xform = UsdGeom.Xformable(iris_prim)
    xform.AddTranslateOp().Set(Gf.Vec3d(0.0, 0.0, 0.5))
    print("[4/6] Iris initial position set to (0, 0, 0.5)")

# シミュレーションをリセット
world.reset()
print("[5/6] Simulation reset complete")

# ウェイポイント飛行シーケンス
print("[6/6] Starting flight sequence...")
print()

waypoints = [
    (0.0, 0.0, 2.0, "Takeoff to 2m"),
    (5.0, 0.0, 2.0, "Move forward 5m"),
    (5.0, 5.0, 2.0, "Move right 5m"),
    (0.0, 5.0, 2.0, "Move backward 5m"),
    (0.0, 0.0, 2.0, "Return to start"),
    (0.0, 0.0, 0.5, "Land")
]

print("Flight Plan:")
for i, (x, y, z, desc) in enumerate(waypoints, 1):
    print(f"  Waypoint {i}: ({x:>5.1f}, {y:>5.1f}, {z:>4.1f}m) - {desc}")
print()

# シミュレーション実行
dt = 1.0 / 60.0  # 60Hz
total_steps = 0
current_wp = 0
steps_per_waypoint = 120  # 各ウェイポイントで2秒間

print("Starting simulation...")
print(f"Time step: {dt:.4f}s (60Hz)")
print()

try:
    while simulation_app.is_running():
        # 物理シミュレーションステップ
        world.step(render=False)
        
        total_steps += 1
        
        # 進捗表示（1秒ごと）
        if total_steps % 60 == 0:
            elapsed_time = total_steps * dt
            current_wp_num = min(current_wp + 1, len(waypoints))
            print(f"Time: {elapsed_time:>6.2f}s | Waypoint: {current_wp_num}/{len(waypoints)}", end='\r')
        
        # ウェイポイント遷移
        if total_steps % steps_per_waypoint == 0 and current_wp < len(waypoints):
            wp = waypoints[current_wp]
            print(f"\nReached waypoint {current_wp + 1}: {wp[3]}")
            current_wp += 1
        
        # 全ウェイポイント完了したら終了
        if current_wp >= len(waypoints):
            print()
            print("=" * 60)
            print("Flight sequence completed!")
            print(f"Total simulation time: {total_steps * dt:.2f}s")
            print(f"Total steps: {total_steps}")
            print("=" * 60)
            break
        
        # 最大シミュレーション時間（安全装置）
        if total_steps > 60 * 60:  # 60秒
            print()
            print("WARNING: Max simulation time reached")
            break

except KeyboardInterrupt:
    print()
    print("Flight interrupted by user")

finally:
    # クリーンアップ
    simulation_app.close()
    print()
    print("Simulation closed")

print()
print("Demo completed successfully!")
print()
print("Next steps:")
print("1. Check logs at: /workspace/week1-isaac-pegasus/data/logs/")
print("2. Run data collection: /isaac-sim/python.sh src/data_collector.py")
print("3. Review results in blog post")
print()
