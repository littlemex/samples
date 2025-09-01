"""
拒否トピックのみのガードレール設定

このモジュールは、拒否トピックのみのガードレール設定を提供します。
他のコンテンツフィルターなどと機能が被らないようにするため、
拒否トピックポリシーのみを有効にした設定を提供します。
"""

import json
import logging
import os
from typing import Dict, List

from utils.filter_configs import get_topic_policy_config

logger = logging.getLogger(__name__)


def get_topic_only_guardrail_config(allowed_tools: List[str] = None) -> Dict:
    """拒否トピックのみのガードレール設定を取得する

    Args:
        allowed_tools: 許可ツールリスト（指定した場合は許可ツールリストによる制限を追加）

    Returns:
        Dict: ガードレール設定
    """
    # 拒否トピックポリシーのみを有効にした設定
    return {
        "contentPolicyConfig": {
            "filtersConfig": [],
            "tierConfig": {
                "tierName": "STANDARD",
            }
        },
        "topicPolicyConfig": get_topic_policy_config(allowed_tools),
        "contextualGroundingPolicyConfig": {
            "filtersConfig": []
        },
        "wordPolicyConfig": {
            "managedWordListsConfig": []
        },
        "sensitiveInformationPolicyConfig": {
            "piiEntitiesConfig": [],
            "regexesConfig": []
        },
        "crossRegionConfig": {
            "guardrailProfileIdentifier": "us.guardrail.v1:0"
        }
    }


def create_topic_only_guardrail(
    guardrails_manager,
    allowed_tools_file: str = "data/allowed_tools.json"
) -> str:
    """拒否トピックのみのガードレールを作成する

    Args:
        guardrails_manager: GuardrailsManager インスタンス
        allowed_tools_file: 許可ツールリストファイルのパス

    Returns:
        str: ガードレール ID
    """
    try:
        # 許可ツールリストを読み込む
        with open(allowed_tools_file, "r", encoding="utf-8") as f:
            allowed_tools_data = json.load(f)
        
        allowed_tools = allowed_tools_data.get("approved_tools", [])
        
        # 基本設定
        config = get_topic_only_guardrail_config(allowed_tools)
        
        # 名前と説明を設定
        import time
        timestamp = int(time.time())
        config["name"] = f"topic-only-guardrail-{timestamp}"
        config["description"] = "拒否トピックのみのガードレール"
        
        # ガードレールを作成
        guardrail_id = guardrails_manager.create_guardrail(config)
        
        # ガードレールIDを保存
        if guardrail_id:
            guardrails_manager.save_guardrail_id(guardrail_id, policy_type="topic_only")
        
        return guardrail_id
    
    except Exception as e:
        logger.error(f"拒否トピックのみのガードレールの作成に失敗しました: {e}")
        return ""


if __name__ == "__main__":
    # ロギングの設定
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    
    # GuardrailsManager をインポート
    import sys
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from guardrails_manager import GuardrailsManager
    
    # GuardrailsManager インスタンスを作成
    manager = GuardrailsManager()
    
    # 拒否トピックのみのガードレールを作成
    guardrail_id = create_topic_only_guardrail(manager)
    
    if guardrail_id:
        print(f"拒否トピックのみのガードレールを作成しました: {guardrail_id}")
    else:
        print("拒否トピックのみのガードレールの作成に失敗しました")
