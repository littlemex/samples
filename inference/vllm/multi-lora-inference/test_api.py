"""
APIサーバーのテストスクリプト

online_serving.pyを起動した後、このスクリプトでAPIをテストできます。
"""

import requests
import json


def test_health_check(base_url: str):
    """ヘルスチェック"""
    print("Testing health check...")
    response = requests.get(f"{base_url}/")
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}\n")
    return response.status_code == 200


def test_list_adapters(base_url: str):
    """LoRAアダプターのリスト取得"""
    print("Testing list adapters...")
    response = requests.get(f"{base_url}/lora-adapters")
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}\n")
    return response.status_code == 200


def test_single_generation(base_url: str):
    """単一プロンプトの推論"""
    print("Testing single generation...")

    request_data = {
        "prompt": "### Input:\nCreate a SQL query to find all active users\n\n### Response:\n",
        "lora_adapter": "sql",
        "temperature": 0.0,
        "max_tokens": 256,
    }

    response = requests.post(
        f"{base_url}/generate",
        json=request_data,
    )

    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        result = response.json()
        print(f"LoRA Adapter: {result['lora_adapter']}")
        print(f"Generated Tokens: {result['num_tokens']}")
        print(f"Generated Text:\n{result['generated_text']}\n")
    else:
        print(f"Error: {response.text}\n")

    return response.status_code == 200


def test_batch_generation(base_url: str):
    """バッチ推論"""
    print("Testing batch generation...")

    request_data = {
        "requests": [
            {
                "prompt": "### Input:\nCreate a SQL query to delete old records\n\n### Response:\n",
                "lora_adapter": "sql",
                "temperature": 0.0,
                "max_tokens": 256,
            },
            {
                "prompt": "### Input:\nWrite a Python function to sort a dictionary by values\n\n### Response:\n",
                "lora_adapter": "python",
                "temperature": 0.0,
                "max_tokens": 512,
            },
            {
                "prompt": "What is machine learning?",
                "temperature": 0.7,
                "max_tokens": 256,
            },
        ]
    }

    response = requests.post(
        f"{base_url}/batch-generate",
        json=request_data,
    )

    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        result = response.json()
        for i, res in enumerate(result["results"]):
            print(f"\n--- Result {i + 1} ---")
            print(f"LoRA Adapter: {res['lora_adapter']}")
            print(f"Generated Tokens: {res['num_tokens']}")
            print(f"Generated Text:\n{res['generated_text'][:200]}...")
    else:
        print(f"Error: {response.text}\n")

    return response.status_code == 200


def main():
    base_url = "http://localhost:8000"

    print("=" * 80)
    print("vLLM Multi-LoRA API Test")
    print("=" * 80)
    print(f"Testing API at: {base_url}\n")

    # テストを実行
    tests = [
        ("Health Check", lambda: test_health_check(base_url)),
        ("List Adapters", lambda: test_list_adapters(base_url)),
        ("Single Generation", lambda: test_single_generation(base_url)),
        ("Batch Generation", lambda: test_batch_generation(base_url)),
    ]

    results = []
    for test_name, test_func in tests:
        try:
            success = test_func()
            results.append((test_name, success))
        except Exception as e:
            print(f"Test failed with exception: {e}\n")
            results.append((test_name, False))

    # 結果サマリー
    print("=" * 80)
    print("Test Results Summary")
    print("=" * 80)
    for test_name, success in results:
        status = "PASS" if success else "FAIL"
        print(f"{test_name}: {status}")

    total_tests = len(results)
    passed_tests = sum(1 for _, success in results if success)
    print(f"\nTotal: {passed_tests}/{total_tests} tests passed")


if __name__ == "__main__":
    main()
