/**
 * client-hash-monitor.ts のテスト
 */
import { ClientHashMonitor, ToolDefinition } from './client-hash-monitor.js';

/**
 * テスト関数の型定義
 */
type TestFunction = (name: string, fn: () => void | Promise<void>) => void;

/**
 * テスト関数（実際の Jest の代わりに使用）
 */
const test: TestFunction = async (name, fn) => {
  console.log(`テスト実行: ${name}`);
  try {
    await fn();
    console.log('✅ テスト成功');
  } catch (error) {
    console.error('❌ テスト失敗:', error);
    throw error;
  }
};

/**
 * 複数のテストをグループ化する関数
 */
function describe(name: string, fn: () => void | Promise<void>): void {
  console.log(`\nテストグループ: ${name}`);
  fn();
}

/**
 * 値が等しいことを検証する関数
 */
function assertEqual<T>(actual: T, expected: T, message?: string): void {
  if (actual !== expected) {
    throw new Error(message || `期待値: ${expected}, 実際の値: ${actual}`);
  }
}

/**
 * 値が真であることを検証する関数
 */
function assertTrue(actual: boolean, message?: string): void {
  if (!actual) {
    throw new Error(message || `期待値: true, 実際の値: ${actual}`);
  }
}

/**
 * 値が偽であることを検証する関数
 */
function assertFalse(actual: boolean, message?: string): void {
  if (actual) {
    throw new Error(message || `期待値: false, 実際の値: ${actual}`);
  }
}

/**
 * テスト用の Tool 定義を作成
 */
function createTestTool(name: string, description: string): ToolDefinition {
  return {
    name,
    title: `${name} Tool`,
    description,
    inputSchema: {
      type: 'object',
      properties: {
        a: { type: 'number' },
        b: { type: 'number' },
      },
    },
  };
}

// テストの実行
console.log('\n=== client-hash-monitor.ts のテスト実行 ===');

describe('ClientHashMonitor', () => {
  test('ベースラインハッシュの取得と保存', async () => {
    const monitor = new ClientHashMonitor();
    const tools: ToolDefinition[] = [
      createTestTool('add', '2つの数値を足し算するツール'),
      createTestTool('multiply', '2つの数値を掛け算するツール'),
    ];

    await monitor.captureBaseline(tools);

    // ベースラインが正しく保存されているかテスト
    const results = await monitor.validateAllTools(tools);
    assertEqual(results.length, 2);
    assertTrue(results[0].isValid);
    assertTrue(results[1].isValid);
  });

  test('Tool 定義変更の検出', async () => {
    const monitor = new ClientHashMonitor();
    const originalTool = createTestTool('add', '2つの数値を足し算するツール');

    // ベースラインを設定
    await monitor.captureBaseline([originalTool]);

    // Tool 定義を変更
    const modifiedTool = createTestTool('add', '2つの数値を足し算するツール（変更済み）');

    // 変更が検出されることを確認
    const isValid = await monitor.validateBeforeToolCall([modifiedTool], 'add');
    assertFalse(isValid, 'Tool 定義の変更が検出されるべき');
  });

  test('同じ Tool 定義での検証成功', async () => {
    const monitor = new ClientHashMonitor();
    const tool = createTestTool('add', '2つの数値を足し算するツール');

    // ベースラインを設定
    await monitor.captureBaseline([tool]);

    // 同じ定義で検証
    const isValid = await monitor.validateBeforeToolCall([tool], 'add');
    assertTrue(isValid, '同じ Tool 定義では検証が成功するべき');
  });

  test('存在しない Tool の検証', async () => {
    const monitor = new ClientHashMonitor();
    const tool = createTestTool('add', '2つの数値を足し算するツール');

    await monitor.captureBaseline([tool]);

    // 存在しない Tool を検証
    const isValid = await monitor.validateBeforeToolCall([tool], 'nonexistent');
    assertFalse(isValid, '存在しない Tool では検証が失敗するべき');
  });

  test('ベースラインが未設定の Tool の検証', async () => {
    const monitor = new ClientHashMonitor();
    const tool = createTestTool('add', '2つの数値を足し算するツール');

    // ベースラインを設定せずに検証
    const isValid = await monitor.validateBeforeToolCall([tool], 'add');
    assertFalse(isValid, 'ベースライン未設定では検証が失敗するべき');
  });

  test('全 Tool の検証結果', async () => {
    const monitor = new ClientHashMonitor();
    const originalTools: ToolDefinition[] = [
      createTestTool('add', '足し算ツール'),
      createTestTool('subtract', '引き算ツール'),
    ];

    await monitor.captureBaseline(originalTools);

    // 一部の Tool を変更
    const currentTools: ToolDefinition[] = [
      createTestTool('add', '足し算ツール'), // 変更なし
      createTestTool('subtract', '引き算ツール（変更済み）'), // 変更あり
    ];

    const results = await monitor.validateAllTools(currentTools);

    assertEqual(results.length, 2);
    assertTrue(results[0].isValid, 'add Tool は変更されていないので有効');
    assertFalse(results[1].isValid, 'subtract Tool は変更されているので無効');
  });

  test('ベースラインの更新', async () => {
    const monitor = new ClientHashMonitor();
    const originalTool = createTestTool('add', '元の説明');

    await monitor.captureBaseline([originalTool]);

    // Tool 定義を変更
    const modifiedTool = createTestTool('add', '新しい説明');

    // 変更前は検証失敗
    let isValid = await monitor.validateBeforeToolCall([modifiedTool], 'add');
    assertFalse(isValid);

    // ベースラインを更新
    monitor.updateBaseline('add', modifiedTool);

    // 更新後は検証成功
    isValid = await monitor.validateBeforeToolCall([modifiedTool], 'add');
    assertTrue(isValid);
  });

  test('ベースラインのクリア', async () => {
    const monitor = new ClientHashMonitor();
    const tool = createTestTool('add', '足し算ツール');

    await monitor.captureBaseline([tool]);

    // クリア前は検証成功
    let isValid = await monitor.validateBeforeToolCall([tool], 'add');
    assertTrue(isValid);

    // ベースラインをクリア
    monitor.clearBaseline();

    // クリア後は検証失敗
    isValid = await monitor.validateBeforeToolCall([tool], 'add');
    assertFalse(isValid);
  });

  test('inputSchema が undefined の Tool の処理', async () => {
    const monitor = new ClientHashMonitor();
    const tool: ToolDefinition = {
      name: 'simple',
      description: 'シンプルなツール',
      // inputSchema は undefined
    };

    await monitor.captureBaseline([tool]);

    // 同じ定義で検証成功
    const isValid = await monitor.validateBeforeToolCall([tool], 'simple');
    assertTrue(isValid);
  });

  test('title が undefined の Tool の処理', async () => {
    const monitor = new ClientHashMonitor();
    const tool: ToolDefinition = {
      name: 'notitle',
      description: 'タイトルなしツール',
      // title は undefined
      inputSchema: { type: 'object' },
    };

    await monitor.captureBaseline([tool]);

    // 同じ定義で検証成功
    const isValid = await monitor.validateBeforeToolCall([tool], 'notitle');
    assertTrue(isValid);
  });
});

console.log('\n✅ client-hash-monitor.ts のすべてのテストが完了しました！');
