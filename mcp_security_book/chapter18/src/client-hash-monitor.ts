import { createHash } from 'node:crypto';

/**
 * Tool 定義の型定義
 */
export interface ToolDefinition {
  name: string;
  title?: string;
  description: string;
  inputSchema?: Record<string, unknown>;
}

/**
 * ハッシュレコードの型定義
 */
export interface HashRecord {
  toolName: string;
  hash: string;
  timestamp: string;
  toolDefinition: ToolDefinition;
}

/**
 * Client 側独立ハッシュ監視システム
 * Server の _meta に依存せず、Client が独自にハッシュ値を計算して検証
 */
export class ClientHashMonitor {
  private baselineHashes: Map<string, HashRecord> = new Map();

  /**
   * Tool 定義のハッシュ値を計算する関数
   * Server の _meta を無視して、Client が独自に計算
   * @param tool Tool 定義
   * @returns SHA-256 ハッシュ値
   */
  private calculateToolHash(tool: ToolDefinition): string {
    const normalizedTool = {
      name: tool.name,
      title: tool.title || '',
      description: tool.description,
      inputSchema: tool.inputSchema ? JSON.stringify(tool.inputSchema) : '',
    };

    return createHash('sha256').update(JSON.stringify(normalizedTool)).digest('hex');
  }

  /**
   * 起動時のベースラインハッシュを記録
   * @param tools Tool 定義の配列
   */
  async captureBaseline(tools: ToolDefinition[]): Promise<void> {
    console.log('\n=== Client 側ベースラインハッシュ取得開始 ===');

    for (const tool of tools) {
      const hash = this.calculateToolHash(tool);
      const record: HashRecord = {
        toolName: tool.name,
        hash,
        timestamp: new Date().toISOString(),
        toolDefinition: { ...tool },
      };

      this.baselineHashes.set(tool.name, record);
      console.log(`[Baseline] Tool ${tool.name}: ${hash}`);
    }

    console.log(`✅ ベースラインハッシュ取得完了 (${tools.length} tools)`);
    console.log('=== ベースライン取得完了 ===\n');
  }

  /**
   * Tool 利用前の検証
   * @param currentTools 現在の Tool 定義配列
   * @param toolName 検証対象の Tool 名
   * @returns 検証結果 (true: 安全, false: 危険)
   */
  async validateBeforeToolCall(currentTools: ToolDefinition[], toolName: string): Promise<boolean> {
    console.log(`\n--- Tool ${toolName} のセキュリティ検証開始 ---`);

    const currentTool = currentTools.find((t) => t.name === toolName);
    if (!currentTool) {
      console.error(`❌ Tool ${toolName} が見つかりません`);
      return false;
    }

    const currentHash = this.calculateToolHash(currentTool);
    const baselineRecord = this.baselineHashes.get(toolName);

    if (!baselineRecord) {
      console.warn(`⚠️  Tool ${toolName} のベースラインハッシュが存在しません`);
      console.log(`現在のハッシュ: ${currentHash}`);
      return false;
    }

    if (baselineRecord.hash !== currentHash) {
      console.error('🚨 セキュリティアラート: Tool 定義が変更されました！');
      console.error(`Tool: ${toolName}`);
      console.error(`期待値 (Baseline): ${baselineRecord.hash}`);
      console.error(`現在値: ${currentHash}`);
      console.error(`ベースライン取得時刻: ${baselineRecord.timestamp}`);
      console.error(`現在時刻: ${new Date().toISOString()}`);

      // 変更内容の詳細比較
      console.error('\n--- 変更内容の詳細 ---');
      console.error('ベースライン定義:');
      console.error(JSON.stringify(baselineRecord.toolDefinition, null, 2));
      console.error('現在の定義:');
      console.error(JSON.stringify(currentTool, null, 2));

      return false;
    }

    console.log(`✅ Tool ${toolName} のセキュリティ検証完了`);
    console.log(`ハッシュ値: ${currentHash}`);
    return true;
  }

  /**
   * 全 Tool の現在状態を検証
   * @param currentTools 現在の Tool 定義配列
   * @returns 検証結果の配列
   */
  async validateAllTools(currentTools: ToolDefinition[]): Promise<
    {
      toolName: string;
      isValid: boolean;
      currentHash: string;
      baselineHash?: string;
    }[]
  > {
    console.log('\n=== 全 Tool セキュリティ検証開始 ===');

    const results = [];

    for (const tool of currentTools) {
      const currentHash = this.calculateToolHash(tool);
      const baselineRecord = this.baselineHashes.get(tool.name);
      const isValid = baselineRecord ? baselineRecord.hash === currentHash : false;

      results.push({
        toolName: tool.name,
        isValid,
        currentHash,
        baselineHash: baselineRecord?.hash,
      });

      if (!isValid) {
        console.error(`❌ Tool ${tool.name}: ハッシュ不一致`);
      } else {
        console.log(`✅ Tool ${tool.name}: 検証 OK`);
      }
    }

    console.log('=== 全 Tool 検証完了 ===\n');
    return results;
  }

  /**
   * ベースラインハッシュの一覧を表示
   */
  displayBaseline(): void {
    console.log('\n=== ベースラインハッシュ一覧 ===');

    if (this.baselineHashes.size === 0) {
      console.log('ベースラインハッシュが記録されていません。');
      return;
    }

    this.baselineHashes.forEach((record, toolName) => {
      console.log(`\nTool: ${toolName}`);
      console.log(`  Hash: ${record.hash}`);
      console.log(`  取得時刻: ${record.timestamp}`);
      console.log(`  説明: ${record.toolDefinition.description}`);
    });

    console.log('=== 一覧表示完了 ===\n');
  }

  /**
   * ベースラインハッシュをクリア（テスト用）
   */
  clearBaseline(): void {
    this.baselineHashes.clear();
    console.log('ベースラインハッシュをクリアしました。');
  }

  /**
   * 特定の Tool のベースラインハッシュを更新
   * @param toolName Tool 名
   * @param tool 新しい Tool 定義
   */
  updateBaseline(toolName: string, tool: ToolDefinition): void {
    const hash = this.calculateToolHash(tool);
    const record: HashRecord = {
      toolName,
      hash,
      timestamp: new Date().toISOString(),
      toolDefinition: { ...tool },
    };

    this.baselineHashes.set(toolName, record);
    console.log(`Tool ${toolName} のベースラインハッシュを更新しました: ${hash}`);
  }
}
