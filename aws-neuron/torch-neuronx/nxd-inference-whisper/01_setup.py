#!/usr/bin/env python3
"""
環境確認スクリプト

必要なライブラリとバージョンが正しくインストールされているか確認します。

Usage:
    python3 01_setup.py
"""

import sys
import subprocess


def print_section(title):
    """セクションタイトルを表示"""
    print("\n" + "=" * 80)
    print(title)
    print("=" * 80)


def check_version(module_name, min_version=None, import_path=None):
    """モジュールのバージョンを確認"""
    try:
        if import_path:
            exec(f"import {import_path}")
            module = eval(import_path.split('.')[0])
        else:
            exec(f"import {module_name}")
            module = eval(module_name)

        version = getattr(module, '__version__', 'unknown')
        print(f"✓ {module_name}: {version}")

        if min_version:
            if version != 'unknown':
                current_parts = version.split('.')
                min_parts = min_version.split('.')

                # バージョン比較（簡易版）
                try:
                    for i in range(min(len(current_parts), len(min_parts))):
                        current_num = int(current_parts[i].split('+')[0].split('-')[0])
                        min_num = int(min_parts[i])
                        if current_num > min_num:
                            print(f"  → OK ({min_version}+)")
                            return True
                        elif current_num < min_num:
                            print(f"  → NG ({min_version}+ required)")
                            return False
                    print(f"  → OK ({min_version}+)")
                    return True
                except:
                    print(f"  → Cannot parse version")
                    return None
        return True
    except Exception as e:
        print(f"✗ {module_name}: {e}")
        return False


def check_neuron_cores():
    """NeuronCore の状態を確認"""
    try:
        result = subprocess.run(['neuron-ls'], capture_output=True, text=True)
        if result.returncode == 0:
            lines = result.stdout.split('\n')
            neuron_devices = [line for line in lines if 'neuron' in line.lower() and '|' in line]
            print(f"✓ NeuronCores: {len(neuron_devices)} detected")
            for device in neuron_devices[:3]:  # 最初の 3 つを表示
                print(f"  {device.strip()}")
            return len(neuron_devices) > 0
        else:
            print(f"✗ NeuronCores: neuron-ls failed")
            return False
    except Exception as e:
        print(f"✗ NeuronCores: {e}")
        return False


def main():
    print_section("環境確認")

    results = {}

    # 1. neuronxcc
    print("\n1. neuronxcc バージョン確認...")
    results['neuronxcc'] = check_version('neuronxcc', '2.22')

    # 2. torch
    print("\n2. PyTorch バージョン確認...")
    results['torch'] = check_version('torch', '2.5')

    # 3. transformers
    print("\n3. Transformers バージョン確認...")
    results['transformers'] = check_version('transformers', '4.40')

    # 4. NxD Inference
    print("\n4. NxD Inference バージョン確認...")
    results['nxd'] = check_version('neuronx_distributed_inference', '0.7')

    # 5. Whisper モジュール
    print("\n5. Whisper モジュール確認...")
    try:
        from neuronx_distributed_inference.models.whisper.modeling_whisper import (
            WhisperInferenceConfig,
            NeuronApplicationWhisper
        )
        print("✓ Whisper module: Available")
        print("  → WhisperInferenceConfig: OK")
        print("  → NeuronApplicationWhisper: OK")
        results['whisper_module'] = True
    except Exception as e:
        print(f"✗ Whisper module: {e}")
        results['whisper_module'] = False

    # 6. get_program_sharding_info
    print("\n6. KV-Cache 依存関数確認...")
    try:
        from neuronxcc.nki._pre_prod_kernels.util.kernel_helpers import get_program_sharding_info
        print("✓ get_program_sharding_info: Available")
        results['kv_cache_func'] = True
    except Exception as e:
        print(f"✗ get_program_sharding_info: {e}")
        print("  → neuronxcc 2.22+ が必要です")
        results['kv_cache_func'] = False

    # 7. NeuronCore
    print("\n7. NeuronCore 確認...")
    results['neuron_cores'] = check_neuron_cores()

    # 8. openai-whisper
    print("\n8. OpenAI Whisper パッケージ確認...")
    try:
        import whisper
        print(f"✓ openai-whisper: {whisper.__version__ if hasattr(whisper, '__version__') else 'installed'}")
        results['openai_whisper'] = True
    except Exception as e:
        print(f"✗ openai-whisper: {e}")
        results['openai_whisper'] = False

    # 結果サマリー
    print_section("結果サマリー")

    all_ok = all(v for v in results.values() if v is not None)
    critical_ok = results.get('nxd', False) and results.get('whisper_module', False) and results.get('kv_cache_func', False) and results.get('neuron_cores', False)

    if all_ok:
        print("\n✅ すべてのチェックが成功しました！")
        print("   NxD Inference Whisper を使用する準備ができています。")
    elif critical_ok:
        print("\n⚠️  一部のチェックが失敗しましたが、NxD Inference Whisper は使用できます。")
        print("   警告が出ている項目を確認してください。")
    else:
        print("\n❌ 重要なチェックが失敗しました。")
        print("   以下の項目を修正してください:")

        if not results.get('neuronxcc', False):
            print("   - neuronxcc 2.22+ をインストール")
        if not results.get('nxd', False):
            print("   - NxD Inference 0.7.0+ をインストール")
        if not results.get('whisper_module', False):
            print("   - NxD Inference の Whisper モジュールを確認")
        if not results.get('kv_cache_func', False):
            print("   - neuronxcc 2.22+ にアップグレード")
        if not results.get('neuron_cores', False):
            print("   - NeuronCore が利用可能か確認（inf2/trn1 インスタンスが必要）")

    print("=" * 80)

    return 0 if critical_ok else 1


if __name__ == "__main__":
    sys.exit(main())
