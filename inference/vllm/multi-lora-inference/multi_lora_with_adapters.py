"""
実際のLoRAアダプターを使用したMulti-LoRA推論サンプル

TinyLlama + 公開LoRAアダプターを使用
"""

from vllm import LLM, SamplingParams
from vllm.lora.request import LoRARequest


def main():
    print("=" * 80)
    print("vLLM Multi-LoRA推論デモ")
    print("=" * 80)

    # ベースモデルの初期化
    print("\n[1/4] TinyLlamaベースモデルを初期化中...")
    llm = LLM(
        model="TinyLlama/TinyLlama-1.1B-Chat-v1.0",
        enable_lora=True,
        max_loras=3,
        max_lora_rank=64,
        max_cpu_loras=6,
        gpu_memory_utilization=0.85,
    )

    # サンプリングパラメータ
    sampling_params = SamplingParams(
        temperature=0.7,
        top_p=0.95,
        max_tokens=200,
    )

    # LoRAアダプターの設定
    print("\n[2/4] LoRAアダプターを設定中...")
    lora_adapters = {
        "function_call": LoRARequest(
            lora_name="function_call",
            lora_int_id=1,
            lora_local_path="unclecode/tinyllama-function-call-lora-adapter-250424",
        ),
        "text2sql": LoRARequest(
            lora_name="text2sql",
            lora_int_id=2,
            lora_local_path="sid321axn/tiny-llama-text2sql",
        ),
        "gsm8k_math": LoRARequest(
            lora_name="gsm8k_math",
            lora_int_id=3,
            lora_local_path="philimon/TinyLlama-gsm8k-lora",
        ),
    }

    # テストケース
    print("\n[3/4] 推論リクエストを準備中...")
    test_cases = [
        {
            "name": "関数呼び出し (Function Call LoRA)",
            "prompt": "Create a function to get weather information for a given city.",
            "lora": lora_adapters["function_call"],
        },
        {
            "name": "SQL生成 (Text2SQL LoRA)",
            "prompt": "Generate SQL to find all customers who purchased more than 5 items in the last month.",
            "lora": lora_adapters["text2sql"],
        },
        {
            "name": "数学問題 (GSM8K Math LoRA)",
            "prompt": "If John has 5 apples and gives 2 to Mary, then buys 3 more, how many apples does he have?",
            "lora": lora_adapters["gsm8k_math"],
        },
        {
            "name": "ベースモデル (LoRAなし)",
            "prompt": "What is the capital of France?",
            "lora": None,
        },
    ]

    # 推論実行
    print("\n[4/4] 推論を実行中...")
    print("=" * 80)

    for i, test in enumerate(test_cases, 1):
        print(f"\n--- テストケース {i}/{len(test_cases)}: {test['name']} ---")
        print(f"プロンプト: {test['prompt']}\n")

        try:
            # 推論実行
            outputs = llm.generate(
                prompts=[test['prompt']],
                sampling_params=sampling_params,
                lora_request=test['lora'],
            )

            # 結果表示
            generated_text = outputs[0].outputs[0].text
            num_tokens = len(outputs[0].outputs[0].token_ids)

            print(f"生成テキスト:\n{generated_text}")
            print(f"\nトークン数: {num_tokens}")
            print("-" * 80)

        except Exception as e:
            print(f"❌ エラー: {e}")
            print("-" * 80)

    print("\n✅ Multi-LoRA推論デモ完了！")


if __name__ == "__main__":
    main()
