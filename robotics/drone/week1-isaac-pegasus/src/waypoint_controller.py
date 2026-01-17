#!/usr/bin/env python3
"""
Week 1: Waypoint Controller
簡易的なウェイポイント制御システム
"""

import numpy as np
from dataclasses import dataclass
from typing import List, Tuple
from enum import Enum


class FlightMode(Enum):
    """飛行モード"""
    IDLE = 0
    TAKEOFF = 1
    WAYPOINT = 2
    LAND = 3
    EMERGENCY = 4


@dataclass
class Waypoint:
    """ウェイポイントデータクラス"""
    x: float
    y: float
    z: float
    description: str = ""
    tolerance: float = 0.5  # 到達判定の許容誤差（メートル）
    
    def distance_to(self, position: Tuple[float, float, float]) -> float:
        """現在位置からの距離を計算"""
        dx = self.x - position[0]
        dy = self.y - position[1]
        dz = self.z - position[2]
        return np.sqrt(dx**2 + dy**2 + dz**2)
    
    def is_reached(self, position: Tuple[float, float, float]) -> bool:
        """ウェイポイントに到達したか判定"""
        return self.distance_to(position) < self.tolerance


class WaypointController:
    """ウェイポイント制御クラス"""
    
    def __init__(self, initial_position: Tuple[float, float, float] = (0.0, 0.0, 0.0)):
        """
        初期化
        
        Args:
            initial_position: 初期位置 (x, y, z)
        """
        self.current_position = np.array(initial_position, dtype=float)
        self.current_velocity = np.array([0.0, 0.0, 0.0], dtype=float)
        self.waypoints: List[Waypoint] = []
        self.current_waypoint_idx = 0
        self.flight_mode = FlightMode.IDLE
        
        # 制御パラメータ
        self.max_velocity = 2.0  # m/s
        self.max_acceleration = 1.0  # m/s^2
        self.position_gain = 1.0
        self.velocity_gain = 0.5
        
        print("WaypointController initialized")
        print(f"Initial position: {self.current_position}")
    
    def add_waypoint(self, x: float, y: float, z: float, description: str = ""):
        """ウェイポイントを追加"""
        wp = Waypoint(x, y, z, description)
        self.waypoints.append(wp)
        print(f"Waypoint {len(self.waypoints)} added: ({x}, {y}, {z}) - {description}")
    
    def add_waypoint_sequence(self, waypoints: List[Tuple[float, float, float, str]]):
        """複数のウェイポイントを一括追加"""
        for wp_data in waypoints:
            x, y, z, desc = wp_data
            self.add_waypoint(x, y, z, desc)
    
    def start_mission(self):
        """ミッション開始"""
        if not self.waypoints:
            print("ERROR: No waypoints defined")
            return False
        
        self.current_waypoint_idx = 0
        self.flight_mode = FlightMode.WAYPOINT
        print(f"Mission started with {len(self.waypoints)} waypoints")
        return True
    
    def update_position(self, position: Tuple[float, float, float]):
        """位置を更新"""
        self.current_position = np.array(position, dtype=float)
    
    def update_velocity(self, velocity: Tuple[float, float, float]):
        """速度を更新"""
        self.current_velocity = np.array(velocity, dtype=float)
    
    def get_current_waypoint(self) -> Waypoint:
        """現在のターゲットウェイポイントを取得"""
        if self.current_waypoint_idx < len(self.waypoints):
            return self.waypoints[self.current_waypoint_idx]
        return None
    
    def compute_control(self, dt: float) -> Tuple[float, float, float]:
        """
        制御コマンドを計算（簡易PDコントローラー）
        
        Args:
            dt: タイムステップ（秒）
        
        Returns:
            (vx, vy, vz): 目標速度ベクトル
        """
        if self.flight_mode != FlightMode.WAYPOINT:
            return (0.0, 0.0, 0.0)
        
        current_wp = self.get_current_waypoint()
        if current_wp is None:
            return (0.0, 0.0, 0.0)
        
        # 目標位置までのベクトル
        target_pos = np.array([current_wp.x, current_wp.y, current_wp.z])
        position_error = target_pos - self.current_position
        
        # P制御（位置誤差に比例）
        desired_velocity = self.position_gain * position_error
        
        # D制御（速度誤差に比例）
        velocity_error = desired_velocity - self.current_velocity
        control_command = desired_velocity + self.velocity_gain * velocity_error
        
        # 速度制限
        speed = np.linalg.norm(control_command)
        if speed > self.max_velocity:
            control_command = control_command * (self.max_velocity / speed)
        
        return tuple(control_command)
    
    def check_waypoint_reached(self) -> bool:
        """現在のウェイポイントに到達したかチェック"""
        current_wp = self.get_current_waypoint()
        if current_wp is None:
            return False
        
        if current_wp.is_reached(tuple(self.current_position)):
            print(f"✓ Waypoint {self.current_waypoint_idx + 1} reached: {current_wp.description}")
            self.current_waypoint_idx += 1
            
            # 全ウェイポイント完了チェック
            if self.current_waypoint_idx >= len(self.waypoints):
                print("✓ All waypoints completed!")
                self.flight_mode = FlightMode.IDLE
                return True
            else:
                next_wp = self.waypoints[self.current_waypoint_idx]
                print(f"→ Next waypoint {self.current_waypoint_idx + 1}: {next_wp.description}")
            
            return True
        
        return False
    
    def get_mission_progress(self) -> float:
        """ミッションの進捗率を返す（0.0-1.0）"""
        if not self.waypoints:
            return 0.0
        return self.current_waypoint_idx / len(self.waypoints)
    
    def get_status(self) -> dict:
        """現在のステータスを辞書で返す"""
        current_wp = self.get_current_waypoint()
        
        status = {
            'flight_mode': self.flight_mode.name,
            'current_position': tuple(self.current_position),
            'current_velocity': tuple(self.current_velocity),
            'waypoint_index': self.current_waypoint_idx,
            'total_waypoints': len(self.waypoints),
            'progress': self.get_mission_progress(),
        }
        
        if current_wp:
            status['current_target'] = {
                'position': (current_wp.x, current_wp.y, current_wp.z),
                'description': current_wp.description,
                'distance': current_wp.distance_to(tuple(self.current_position))
            }
        
        return status
    
    def print_status(self):
        """ステータスを表示"""
        status = self.get_status()
        print(f"\n--- Flight Status ---")
        print(f"Mode: {status['flight_mode']}")
        print(f"Position: ({status['current_position'][0]:.2f}, "
              f"{status['current_position'][1]:.2f}, "
              f"{status['current_position'][2]:.2f})")
        print(f"Progress: {status['waypoint_index']}/{status['total_waypoints']} "
              f"({status['progress']*100:.1f}%)")
        
        if 'current_target' in status:
            target = status['current_target']
            print(f"Target: ({target['position'][0]:.2f}, "
                  f"{target['position'][1]:.2f}, "
                  f"{target['position'][2]:.2f})")
            print(f"Distance: {target['distance']:.2f}m")
            print(f"Description: {target['description']}")
        print("-------------------\n")


def create_square_mission(side_length: float = 5.0, altitude: float = 2.0) -> WaypointController:
    """
    正方形飛行ミッションを作成
    
    Args:
        side_length: 正方形の一辺の長さ（メートル）
        altitude: 飛行高度（メートル）
    
    Returns:
        設定済みのWaypointController
    """
    controller = WaypointController()
    
    waypoints = [
        (0.0, 0.0, altitude, "Takeoff"),
        (side_length, 0.0, altitude, "Corner 1"),
        (side_length, side_length, altitude, "Corner 2"),
        (0.0, side_length, altitude, "Corner 3"),
        (0.0, 0.0, altitude, "Return to start"),
        (0.0, 0.0, 0.5, "Land")
    ]
    
    controller.add_waypoint_sequence(waypoints)
    
    return controller


def create_custom_mission(waypoint_list: List[Tuple[float, float, float, str]]) -> WaypointController:
    """
    カスタムミッションを作成
    
    Args:
        waypoint_list: ウェイポイントリスト [(x, y, z, description), ...]
    
    Returns:
        設定済みのWaypointController
    """
    controller = WaypointController()
    controller.add_waypoint_sequence(waypoint_list)
    return controller


# 使用例
if __name__ == "__main__":
    print("=" * 60)
    print("Waypoint Controller Test")
    print("=" * 60)
    print()
    
    # 正方形ミッション作成
    controller = create_square_mission(side_length=5.0, altitude=2.0)
    controller.start_mission()
    
    # シミュレーション（簡易）
    dt = 0.1  # 10Hz
    for step in range(600):  # 60秒
        # 制御コマンド計算
        vx, vy, vz = controller.compute_control(dt)
        
        # 位置更新（簡易的な運動モデル）
        new_pos = controller.current_position + np.array([vx, vy, vz]) * dt
        controller.update_position(tuple(new_pos))
        controller.update_velocity((vx, vy, vz))
        
        # ウェイポイント到達チェック
        controller.check_waypoint_reached()
        
        # ステータス表示（5秒ごと）
        if step % 50 == 0:
            controller.print_status()
        
        # ミッション完了チェック
        if controller.flight_mode == FlightMode.IDLE:
            print("Mission completed!")
            break
    
    print()
    print("Test completed")
