#!/usr/bin/env python3
"""
汎用 VLM テストスクリプト

AWS Bedrock の Vision-Language Model を使用して画像からテキストを抽出し、
処理時間とコストを測定します。
"""

import base64
import json
import time
from pathlib import Path
from typing import Dict, Any

import boto3
from botocore.exceptions import ClientError


# モデル設定
# 料金情報: 実測値に基づく固定値（2026-04-01時点、us-east-1）
MODELS = {
    "palmyra": {
        "model_id": "writer.palmyra-vision-7b",
        "name": "Writer Palmyra Vision 7B",
        "price_per_1k_input": 0.0003,  # $0.30 per 1M tokens (実測値から推定)
        "price_per_1k_output": 0.0015,  # $1.50 per 1M tokens (実測値から推定)
    },
    "nemotron": {
        "model_id": "nvidia.nemotron-nano-12b-v2",
        "name": "NVIDIA Nemotron Nano 12B V2 VL BF16",
        "price_per_1k_input": 0.0003,  # $0.30 per 1M tokens (実測値から推定)
        "price_per_1k_output": 0.0015,  # $1.50 per 1M tokens (実測値から推定)
    },
    "nova2-lite": {
        "model_id": "us.amazon.nova-2-lite-v1:0",
        "name": "Amazon Nova 2 Lite",
        "price_per_1k_input": 0.0003,  # $0.30 per 1M tokens (実測値から推定)
        "price_per_1k_output": 0.0015,  # $1.50 per 1M tokens (実測値から推定)
    },
    "kimi": {
        "model_id": "moonshotai.kimi-k2.5",
        "name": "Moonshot AI Kimi K2.5",
        "price_per_1k_input": 0.0003,  # $0.30 per 1M tokens (実測値から推定)
        "price_per_1k_output": 0.0015,  # $1.50 per 1M tokens (実測値から推定)
    },
    "qwen3": {
        "model_id": "qwen.qwen3-vl-235b-a22b",
        "name": "Qwen3 VL 235B-A22B (MoE)",
        "price_per_1k_input": 0.0003,  # $0.30 per 1M tokens (実測値から推定)
        "price_per_1k_output": 0.0015,  # $1.50 per 1M tokens (実測値から推定)
    },
    "claude-opus": {
        "model_id": "us.anthropic.claude-opus-4-6-v1",
        "name": "Anthropic Claude Opus 4.6",
        "price_per_1k_input": 0.015,  # $15 per 1M tokens (実測値から確認)
        "price_per_1k_output": 0.075,  # $75 per 1M tokens (実測値から確認)
    },
}

USD_TO_JPY = 150  # 為替レート（仮）


class VLMTester:
    """VLM のテストクラス"""

    def __init__(self, model_key: str, region_name: str = "us-east-1", profile_name: str = None):
        """
        初期化

        Args:
            model_key: モデルキー（"palmyra" または "nemotron"）
            region_name: AWS リージョン
            profile_name: AWS プロファイル名（None の場合はデフォルト）
        """
        if model_key not in MODELS:
            raise ValueError(f"Unknown model: {model_key}. Available: {list(MODELS.keys())}")

        self.model_config = MODELS[model_key]
        self.model_id = self.model_config["model_id"]
        self.model_name = self.model_config["name"]

        session_kwargs = {"region_name": region_name}
        if profile_name:
            session_kwargs["profile_name"] = profile_name

        session = boto3.Session(**session_kwargs)
        self.client = session.client("bedrock-runtime")

    def load_image_as_base64(self, image_path: str) -> str:
        """
        画像を Base64 エンコード

        Args:
            image_path: 画像ファイルパス

        Returns:
            Base64 エンコードされた画像データ
        """
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

    def extract_text_from_image(
        self,
        image_path: str,
        prompt: str = "Extract all text from this image.",
        max_tokens: int = 2048
    ) -> Dict[str, Any]:
        """
        画像からテキストを抽出

        Args:
            image_path: 画像ファイルパス
            prompt: プロンプト
            max_tokens: 最大出力トークン数

        Returns:
            結果辞書（response, elapsed_time, cost_jpy, tokens）
        """
        # 画像をバイト列として読み込み
        with open(image_path, "rb") as f:
            image_bytes = f.read()

        # Converse API を使用
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "image": {
                            "format": "jpeg" if image_path.endswith(".jpg") or image_path.endswith(".jpeg") else "png",
                            "source": {
                                "bytes": image_bytes
                            }
                        }
                    },
                    {
                        "text": prompt
                    }
                ]
            }
        ]

        # 実行時間測定開始
        start_time = time.time()

        try:
            response = self.client.converse(
                modelId=self.model_id,
                messages=messages,
                inferenceConfig={
                    "maxTokens": max_tokens
                }
            )

            # 実行時間測定終了
            elapsed_time = time.time() - start_time

            # トークン数とコスト計算
            input_tokens = response["usage"]["inputTokens"]
            output_tokens = response["usage"]["outputTokens"]

            cost_usd = (
                (input_tokens / 1000) * self.model_config["price_per_1k_input"] +
                (output_tokens / 1000) * self.model_config["price_per_1k_output"]
            )
            cost_jpy = cost_usd * USD_TO_JPY

            # 出力テキスト抽出
            output_text = ""
            if "output" in response and "message" in response["output"]:
                content = response["output"]["message"]["content"]
                for item in content:
                    if "text" in item:
                        output_text += item["text"]

            return {
                "success": True,
                "output_text": output_text,
                "elapsed_time": elapsed_time,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
                "cost_usd": cost_usd,
                "cost_jpy": cost_jpy,
                "raw_response": response
            }

        except Exception as e:
            elapsed_time = time.time() - start_time
            return {
                "success": False,
                "error": str(e),
                "elapsed_time": elapsed_time
            }

    def print_result(self, result: Dict[str, Any], image_path: str):
        """
        結果を見やすく出力

        Args:
            result: extract_text_from_image の結果
            image_path: 画像ファイルパス
        """
        print("=" * 80)
        print(f"[{self.model_name} テスト結果]")
        print(f"画像: {image_path}")
        print("=" * 80)

        if not result["success"]:
            print(f"[エラー] {result['error']}")
            print(f"実行時間: {result['elapsed_time']:.2f}秒")
            return

        print(f"\n[抽出されたテキスト]")
        print("-" * 80)
        print(result["output_text"])
        print("-" * 80)

        print(f"\n[パフォーマンス]")
        print(f"  実行時間: {result['elapsed_time']:.2f}秒")

        print(f"\n[トークン数]")
        print(f"  入力トークン: {result['input_tokens']:,}")
        print(f"  出力トークン: {result['output_tokens']:,}")
        print(f"  合計トークン: {result['total_tokens']:,}")

        print(f"\n[コスト]")
        print(f"  USD: ${result['cost_usd']:.4f}")
        print(f"  JPY: ¥{result['cost_jpy']:.2f}")

        print("=" * 80)


def main():
    """メイン関数"""
    import argparse

    parser = argparse.ArgumentParser(
        description="汎用 VLM テスト"
    )
    parser.add_argument(
        "image_path",
        type=str,
        help="テスト画像のパス"
    )
    parser.add_argument(
        "--model",
        type=str,
        choices=list(MODELS.keys()),
        default="palmyra",
        help="使用するモデル"
    )
    parser.add_argument(
        "--prompt",
        type=str,
        default="Extract all text from this image.",
        help="プロンプト"
    )
    parser.add_argument(
        "--region",
        type=str,
        default="us-east-1",
        help="AWS リージョン"
    )
    parser.add_argument(
        "--profile",
        type=str,
        default=None,
        help="AWS プロファイル名"
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=2048,
        help="最大出力トークン数"
    )

    args = parser.parse_args()

    # 画像ファイルの存在確認
    if not Path(args.image_path).exists():
        print(f"[エラー] 画像ファイルが見つかりません: {args.image_path}")
        return 1

    # テスト実行
    tester = VLMTester(
        model_key=args.model,
        region_name=args.region,
        profile_name=args.profile
    )

    result = tester.extract_text_from_image(
        image_path=args.image_path,
        prompt=args.prompt,
        max_tokens=args.max_tokens
    )

    tester.print_result(result, args.image_path)

    return 0 if result["success"] else 1


if __name__ == "__main__":
    exit(main())
