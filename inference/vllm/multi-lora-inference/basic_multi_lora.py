"""
基本的なvLLM Multi-LoRA推論のサンプル

このスクリプトは、vLLMのMulti-LoRA機能の最もシンプルな使用例を示します。
"""

from vllm import LLM, SamplingParams
from vllm.lora.request import LoRARequest


def main():
    # ベースモデルとLoRA設定でLLMを初期化
    print("Initializing vLLM with Multi-LoRA support...")
    llm = LLM(
        model="TinyLlama/TinyLlama-1.1B-Chat-v1.0",
        enable_lora=True,
        max_loras=2,
        max_lora_rank=8,
        max_cpu_loras=4,
        gpu_memory_utilization=0.85,
    )

    # サンプリングパラメータの設定
    sampling_params = SamplingParams(
        temperature=0.0,
        top_p=0.95,
        max_tokens=256,
    )

    # プロンプトの準備（まずはベースモデルのみでテスト）
    prompts = [
        "Create a SQL query to find all users who signed up in the last 30 days",
        "Write a Python function to calculate fibonacci numbers",
        "What is the capital of France?",
    ]

    # 推論実行
    print("\nGenerating responses...")
    outputs = llm.generate(prompts, sampling_params)

    # 結果の表示
    print("\n" + "=" * 80)
    for i, output in enumerate(outputs):
        prompt_text = output.prompt
        generated_text = output.outputs[0].text

        print(f"\n--- Request {i + 1} ---")
        print(f"Prompt: {prompt_text[:100]}...")
        print(f"\nGenerated:\n{generated_text}")
        print("-" * 80)


if __name__ == "__main__":
    main()
