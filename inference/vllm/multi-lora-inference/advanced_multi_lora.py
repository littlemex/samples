"""
高度なvLLM Multi-LoRA推論のサンプル

このスクリプトは、エラーハンドリング、ロギング、
パフォーマンス測定を含む実践的な使用例を示します。
"""

import os
import time
from typing import Dict, List, Optional, Tuple

from vllm import LLM, SamplingParams
from vllm.lora.request import LoRARequest


class MultiLoRAInference:
    """Multi-LoRA推論を管理するクラス"""

    def __init__(
        self,
        model_name: str,
        max_loras: int = 4,
        max_lora_rank: int = 64,
        max_cpu_loras: int = 8,
        gpu_memory_utilization: float = 0.85,
    ):
        """
        Args:
            model_name: ベースモデルの名前またはパス
            max_loras: 同時に使用可能なLoRA数
            max_lora_rank: 最大rank値
            max_cpu_loras: CPUキャッシュサイズ
            gpu_memory_utilization: GPU メモリ使用率
        """
        self.model_name = model_name
        self.max_loras = max_loras
        self.lora_adapters: Dict[str, str] = {}

        print(f"Initializing LLM with model: {model_name}")
        print(f"Configuration: max_loras={max_loras}, max_lora_rank={max_lora_rank}")

        self.llm = LLM(
            model=model_name,
            enable_lora=True,
            max_loras=max_loras,
            max_lora_rank=max_lora_rank,
            max_cpu_loras=max_cpu_loras,
            gpu_memory_utilization=gpu_memory_utilization,
        )

    def register_lora_adapter(self, name: str, path: str) -> bool:
        """
        LoRAアダプターを登録

        Args:
            name: アダプターの識別名
            path: アダプターのパス

        Returns:
            登録成功の場合True
        """
        if not os.path.exists(path):
            print(f"Warning: LoRA adapter path does not exist: {path}")
            return False

        self.lora_adapters[name] = path
        print(f"Registered LoRA adapter: {name} -> {path}")
        return True

    def generate(
        self,
        prompts: List[Tuple[str, Optional[str]]],
        temperature: float = 0.0,
        top_p: float = 0.95,
        max_tokens: int = 512,
    ) -> List[Dict]:
        """
        複数のプロンプトに対して推論を実行

        Args:
            prompts: (prompt_text, lora_adapter_name)のリスト
            temperature: サンプリング温度
            top_p: Top-pサンプリング値
            max_tokens: 最大生成トークン数

        Returns:
            推論結果のリスト
        """
        sampling_params = SamplingParams(
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
        )

        # LoRARequestオブジェクトを含むリクエストを作成
        requests = []
        for i, (prompt_text, lora_name) in enumerate(prompts):
            if lora_name is not None:
                if lora_name not in self.lora_adapters:
                    print(f"Warning: Unknown LoRA adapter '{lora_name}', using base model")
                    lora_request = None
                else:
                    lora_path = self.lora_adapters[lora_name]
                    lora_request = LoRARequest(
                        lora_name=lora_name,
                        lora_int_id=hash(lora_name) % (2**31),
                        lora_local_path=lora_path,
                    )
            else:
                lora_request = None

            requests.append((prompt_text, sampling_params, lora_request))

        # 推論実行と時間測定
        print(f"\nGenerating {len(requests)} responses...")
        start_time = time.time()
        outputs = self.llm.generate(requests)
        elapsed_time = time.time() - start_time

        # 結果を整形
        results = []
        total_tokens = 0
        for i, output in enumerate(outputs):
            generated_text = output.outputs[0].text
            num_tokens = len(output.outputs[0].token_ids)
            total_tokens += num_tokens

            results.append(
                {
                    "prompt": output.prompt,
                    "generated": generated_text,
                    "lora_adapter": prompts[i][1],
                    "num_tokens": num_tokens,
                }
            )

        # パフォーマンス統計
        tokens_per_second = total_tokens / elapsed_time if elapsed_time > 0 else 0
        print(f"\nPerformance:")
        print(f"  Total time: {elapsed_time:.2f}s")
        print(f"  Total tokens: {total_tokens}")
        print(f"  Throughput: {tokens_per_second:.2f} tokens/s")

        return results


def main():
    # Multi-LoRA推論システムを初期化
    inference = MultiLoRAInference(
        model_name="meta-llama/Llama-2-7b-hf",
        max_loras=4,
        max_lora_rank=64,
    )

    # LoRAアダプターを登録
    inference.register_lora_adapter("sql", "./lora_adapters/sql-lora")
    inference.register_lora_adapter("python", "./lora_adapters/python-lora")
    inference.register_lora_adapter("math", "./lora_adapters/math-lora")

    # テストプロンプト
    test_prompts = [
        (
            "### Input:\nCreate a SQL query to find the top 10 customers by revenue\n\n### Response:\n",
            "sql",
        ),
        (
            "### Input:\nWrite a Python function to merge two sorted lists\n\n### Response:\n",
            "python",
        ),
        (
            "### Input:\nSolve the equation: 2x + 5 = 15\n\n### Response:\n",
            "math",
        ),
        ("What is the meaning of life?", None),  # ベースモデルのみ
        (
            "### Input:\nCreate a SQL query to delete duplicate records\n\n### Response:\n",
            "sql",
        ),
    ]

    # 推論実行
    results = inference.generate(
        prompts=test_prompts,
        temperature=0.0,
        max_tokens=256,
    )

    # 結果の表示
    print("\n" + "=" * 80)
    print("RESULTS")
    print("=" * 80)
    for i, result in enumerate(results):
        print(f"\n--- Request {i + 1} ---")
        print(f"LoRA Adapter: {result['lora_adapter'] or 'None (base model)'}")
        print(f"Prompt: {result['prompt'][:80]}...")
        print(f"\nGenerated ({result['num_tokens']} tokens):")
        print(result["generated"])
        print("-" * 80)


if __name__ == "__main__":
    main()
