#!/usr/bin/env python3
"""
Week 1: ROS2 Data Collector
Isaac Simから発行されるROS2トピックを購読してデータを保存
"""

import os
import sys
import time
import json
from pathlib import Path
from datetime import datetime

# ROS2のインポートチェック
try:
    import rclpy
    from rclpy.node import Node
    from sensor_msgs.msg import Image, Imu
    from geometry_msgs.msg import PoseStamped
    from nav_msgs.msg import Odometry
    from cv_bridge import CvBridge
    import cv2
    import numpy as np
except ImportError as e:
    print(f"ERROR: Required ROS2 packages not found: {e}")
    print()
    print("Make sure ROS2 environment is sourced:")
    print("  export ROS_DISTRO=humble")
    print("  export RMW_IMPLEMENTATION=rmw_fastrtps_cpp")
    sys.exit(1)

print("=" * 60)
print("Week 1: ROS2 Data Collector")
print("=" * 60)
print()

# データ保存ディレクトリ
DATA_DIR = Path("/workspace/week1-isaac-pegasus/data")
IMAGES_DIR = DATA_DIR / "images"
LOGS_DIR = DATA_DIR / "logs"

# ディレクトリ作成
IMAGES_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# タイムスタンプでセッション識別
SESSION_ID = datetime.now().strftime("%Y%m%d_%H%M%S")
SESSION_IMAGE_DIR = IMAGES_DIR / SESSION_ID
SESSION_IMAGE_DIR.mkdir(exist_ok=True)

print(f"Data save directory: {DATA_DIR}")
print(f"Session ID: {SESSION_ID}")
print()


class DataCollectorNode(Node):
    """ROS2データ収集ノード"""
    
    def __init__(self):
        super().__init__('data_collector')
        
        self.bridge = CvBridge()
        self.image_count = 0
        self.imu_count = 0
        self.odom_count = 0
        
        # ログファイル
        self.log_file = LOGS_DIR / f"flight_log_{SESSION_ID}.jsonl"
        self.log_handle = open(self.log_file, 'w')
        
        # データカウンター
        self.stats = {
            'session_id': SESSION_ID,
            'start_time': time.time(),
            'images_saved': 0,
            'imu_messages': 0,
            'odom_messages': 0,
            'last_update': time.time()
        }
        
        # ROS2サブスクライバーの作成
        # カメラ画像（Irisの前方カメラを想定）
        self.image_sub = self.create_subscription(
            Image,
            '/iris/camera/rgb',
            self.image_callback,
            10
        )
        
        # IMUデータ
        self.imu_sub = self.create_subscription(
            Imu,
            '/iris/imu',
            self.imu_callback,
            10
        )
        
        # オドメトリ（位置・姿勢）
        self.odom_sub = self.create_subscription(
            Odometry,
            '/iris/odom',
            self.odom_callback,
            10
        )
        
        # ステータス表示タイマー（1秒ごと）
        self.timer = self.create_timer(1.0, self.status_callback)
        
        self.get_logger().info('Data Collector Node initialized')
        self.get_logger().info(f'Saving images to: {SESSION_IMAGE_DIR}')
        self.get_logger().info(f'Saving logs to: {self.log_file}')
        print()
    
    def image_callback(self, msg):
        """カメラ画像のコールバック"""
        try:
            # ROS Image → OpenCV format
            cv_image = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
            
            # 画像保存（10フレームに1回）
            if self.image_count % 10 == 0:
                filename = SESSION_IMAGE_DIR / f"frame_{self.image_count:06d}.jpg"
                cv2.imwrite(str(filename), cv_image)
                self.stats['images_saved'] += 1
            
            self.image_count += 1
            
        except Exception as e:
            self.get_logger().error(f'Image callback error: {e}')
    
    def imu_callback(self, msg):
        """IMUデータのコールバック"""
        try:
            # IMUデータをログに記録
            log_entry = {
                'timestamp': time.time(),
                'type': 'imu',
                'linear_acceleration': {
                    'x': msg.linear_acceleration.x,
                    'y': msg.linear_acceleration.y,
                    'z': msg.linear_acceleration.z
                },
                'angular_velocity': {
                    'x': msg.angular_velocity.x,
                    'y': msg.angular_velocity.y,
                    'z': msg.angular_velocity.z
                }
            }
            
            self.log_handle.write(json.dumps(log_entry) + '\n')
            self.imu_count += 1
            self.stats['imu_messages'] += 1
            
        except Exception as e:
            self.get_logger().error(f'IMU callback error: {e}')
    
    def odom_callback(self, msg):
        """オドメトリのコールバック"""
        try:
            # 位置・姿勢データをログに記録
            log_entry = {
                'timestamp': time.time(),
                'type': 'odometry',
                'position': {
                    'x': msg.pose.pose.position.x,
                    'y': msg.pose.pose.position.y,
                    'z': msg.pose.pose.position.z
                },
                'orientation': {
                    'x': msg.pose.pose.orientation.x,
                    'y': msg.pose.pose.orientation.y,
                    'z': msg.pose.pose.orientation.z,
                    'w': msg.pose.pose.orientation.w
                },
                'linear_velocity': {
                    'x': msg.twist.twist.linear.x,
                    'y': msg.twist.twist.linear.y,
                    'z': msg.twist.twist.linear.z
                }
            }
            
            self.log_handle.write(json.dumps(log_entry) + '\n')
            self.odom_count += 1
            self.stats['odom_messages'] += 1
            
        except Exception as e:
            self.get_logger().error(f'Odometry callback error: {e}')
    
    def status_callback(self):
        """ステータス表示（1秒ごと）"""
        elapsed = time.time() - self.stats['start_time']
        
        print(f"\r[{elapsed:>6.1f}s] "
              f"Images: {self.stats['images_saved']:>4d} | "
              f"IMU: {self.imu_count:>5d} | "
              f"Odom: {self.odom_count:>5d}",
              end='', flush=True)
    
    def shutdown(self):
        """シャットダウン処理"""
        print("\n")
        print("=" * 60)
        print("Data Collection Summary")
        print("=" * 60)
        
        elapsed = time.time() - self.stats['start_time']
        
        print(f"Session ID: {SESSION_ID}")
        print(f"Duration: {elapsed:.2f} seconds")
        print(f"Images saved: {self.stats['images_saved']}")
        print(f"IMU messages: {self.stats['imu_messages']}")
        print(f"Odom messages: {self.stats['odom_messages']}")
        print()
        print(f"Image directory: {SESSION_IMAGE_DIR}")
        print(f"Log file: {self.log_file}")
        print("=" * 60)
        
        # ログファイルクローズ
        self.log_handle.close()
        
        # サマリーファイル作成
        summary_file = LOGS_DIR / f"summary_{SESSION_ID}.json"
        with open(summary_file, 'w') as f:
            summary = {
                **self.stats,
                'duration': elapsed,
                'end_time': time.time()
            }
            json.dump(summary, f, indent=2)
        
        print(f"Summary saved: {summary_file}")
        print()


def main():
    """メイン関数"""
    
    # ROS2初期化
    rclpy.init()
    
    print("Initializing ROS2 node...")
    node = DataCollectorNode()
    
    print("Data collection started!")
    print("Press Ctrl+C to stop")
    print()
    
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        print("\n\nData collection stopped by user")
    finally:
        node.shutdown()
        node.destroy_node()
        rclpy.shutdown()
    
    print()
    print("Data collector closed")
    print()
    print("Next steps:")
    print("1. Review collected data:")
    print(f"   ls {SESSION_IMAGE_DIR}")
    print(f"   cat {LOGS_DIR}/flight_log_{SESSION_ID}.jsonl")
    print()
    print("2. Use data for Week 2 (Cosmos Transfer)")
    print()


if __name__ == '__main__':
    main()
