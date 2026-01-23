#!/usr/bin/env python3
"""
LoRAアダプターをHuggingFaceから事前ダウンロードするスクリプト

vLLMは自動的にダウンロードしますが、事前にダウンロードしておくことで：
- 初回実行時の待ち時間を削減
- オフライン環境での使用
- ダウンロード状況の確認
"""

import os
from pathlib import Path
from huggingface_hub import snapshot_download
from typing import List, Dict


# ダウンロードするLoRAアダプターのリスト
LORA_ADAPTERS = {
    "TinyLlama用アダプター": [
        {
            "repo_id": "unclecode/tinyllama-function-call-lora-adapter-250424",
            "description": "関数呼び出し・ツール利用",
        },
        {
            "repo_id": "sid321axn/tiny-llama-text2sql",
            "description": "SQL生成",
        },
        {
            "repo_id": "philimon/TinyLlama-gsm8k-lora",
            "description": "数学問題解答",
        },
    ],
}


def download_adapter(repo_id: str, local_dir: Path = None) -> str:
    """
    LoRAアダプターをダウンロード

    Args:
        repo_id: HuggingFaceリポジトリID
        local_dir: 保存先ディレクトリ（Noneの場合はデフォルトキャッシュ）

    Returns:
        ダウンロードされたローカルパス
    """
    print(f"\n{'='*80}")
    print(f"📦 ダウンロード中: {repo_id}")
    print(f"{'='*80}")

    try:
        if local_dir:
            local_dir.mkdir(parents=True, exist_ok=True)
            local_path = snapshot_download(
                repo_id=repo_id,
                local_dir=str(local_dir),
                local_dir_use_symlinks=False,
            )
        else:
            # デフォルトのHuggingFaceキャッシュを使用
            local_path = snapshot_download(repo_id=repo_id)

        print(f"✅ 成功: {local_path}")
        return local_path

    except Exception as e:
        print(f"❌ エラー: {e}")
        return None


def main():
    """メイン処理"""
    print("=" * 80)
    print("LoRAアダプター ダウンロードツール")
    print("=" * 80)

    # ダウンロード先ディレクトリの設定
    base_dir = Path("./lora_adapters_cache")
    print(f"\n保存先: {base_dir.absolute()}")

    # デフォルトのHuggingFaceキャッシュを使用する場合はNone
    use_custom_dir = input("\nカスタムディレクトリに保存しますか？ (y/N): ").lower() == 'y'
    download_dir = base_dir if use_custom_dir else None

    total_count = 0
    success_count = 0

    # 各カテゴリのアダプターをダウンロード
    for category, adapters in LORA_ADAPTERS.items():
        print(f"\n\n{'#'*80}")
        print(f"# {category}")
        print(f"{'#'*80}")

        for adapter in adapters:
            repo_id = adapter["repo_id"]
            description = adapter["description"]

            print(f"\n説明: {description}")

            if download_dir:
                # カスタムディレクトリを使用
                adapter_name = repo_id.replace("/", "_")
                local_dir = download_dir / adapter_name
            else:
                local_dir = None

            result = download_adapter(repo_id, local_dir)

            total_count += 1
            if result:
                success_count += 1

    # 結果サマリー
    print("\n\n" + "=" * 80)
    print("ダウンロード完了")
    print("=" * 80)
    print(f"成功: {success_count}/{total_count}")

    if use_custom_dir:
        print(f"\n保存先: {base_dir.absolute()}")
        print("\n使用方法:")
        print("  lora_request = LoRARequest(")
        print("      lora_name='adapter_name',")
        print("      lora_int_id=1,")
        print(f"      lora_path='{base_dir.absolute()}/repo_owner_repo_name',")
        print("  )")
    else:
        print("\nデフォルトのHuggingFaceキャッシュに保存されました。")
        print("vLLMは自動的にキャッシュから読み込みます。")

    # キャッシュ情報の表示
    if not use_custom_dir:
        cache_dir = Path.home() / ".cache" / "huggingface" / "hub"
        if cache_dir.exists():
            print(f"\nキャッシュディレクトリ: {cache_dir}")


if __name__ == "__main__":
    main()
