/**
 * security-utils.ts のテスト
 */
import {
  ToolDefinition,
  HashStorage,
  SecurityUtils,
  InMemoryStorageProvider,
  calculateToolHash,
  generateStorageKey,
} from './security-utils.js';

/**
 * テスト関数の型定義
 */
type TestFunction = (name: string, fn: () => void | Promise<void>) => void;

/**
 * テスト関数（実際のJestの代わりに使用）
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
function assertEquals<T>(actual: T, expected: T, message?: string): void {
  if (actual !== expected) {
    throw new Error(message || `期待値: ${expected}, 実際の値: ${actual}`);
  }
}

/**
 * 値が等しくないことを検証する関数
 */
function assertNotEquals<T>(actual: T, expected: T, message?: string): void {
  if (actual === expected) {
    throw new Error(message || `値が等しくないことを期待しましたが、両方とも: ${actual}`);
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
 * 値がundefinedであることを検証する関数
 */
function assertUndefined(actual: unknown, message?: string): void {
  if (actual !== undefined) {
    throw new Error(message || `期待値: undefined, 実際の値: ${actual}`);
  }
}

/**
 * 値が定義されていることを検証する関数
 */
function assertDefined(actual: unknown, message?: string): void {
  if (actual === undefined) {
    throw new Error(message || `値が定義されていることを期待しましたが、undefinedでした`);
  }
}

/**
 * 正規表現にマッチすることを検証する関数
 */
function assertMatches(actual: string, pattern: RegExp, message?: string): void {
  if (!pattern.test(actual)) {
    throw new Error(message || `値 "${actual}" がパターン ${pattern} にマッチしません`);
  }
}

/**
 * オブジェクトが等しいことを検証する関数
 */
function assertDeepEquals<T>(actual: T, expected: T, message?: string): void {
  const actualStr = JSON.stringify(actual);
  const expectedStr = JSON.stringify(expected);
  if (actualStr !== expectedStr) {
    throw new Error(message || `期待値: ${expectedStr}, 実際の値: ${actualStr}`);
  }
}

/**
 * 配列の長さを検証する関数
 */
function assertLength<T>(array: T[], expectedLength: number, message?: string): void {
  if (array.length !== expectedLength) {
    throw new Error(message || `期待される長さ: ${expectedLength}, 実際の長さ: ${array.length}`);
  }
}

// テスト用のツール定義
const testToolDefinition: ToolDefinition = {
  name: 'test-tool',
  title: 'テストツール',
  description: 'テスト用のツール',
  inputSchema: {
    type: 'object',
    properties: {
      input: { type: 'string' },
    },
  },
};

const testServerPath = 'localhost:13000';
const testServerVersion = '1.0.0';

// テストの実行
console.log('\n=== security-utils.ts のテスト実行 ===');

describe('calculateToolHash', () => {
  test('同じツール定義に対して同じハッシュを生成する', () => {
    const hash1 = calculateToolHash(testToolDefinition);
    const hash2 = calculateToolHash(testToolDefinition);

    assertEquals(hash1, hash2);
    assertMatches(hash1, /^[a-f0-9]{64}$/); // SHA-256ハッシュの形式
  });

  test('異なるツール定義に対して異なるハッシュを生成する', () => {
    const modifiedTool: ToolDefinition = {
      ...testToolDefinition,
      description: '変更されたツール',
    };

    const hash1 = calculateToolHash(testToolDefinition);
    const hash2 = calculateToolHash(modifiedTool);

    assertNotEquals(hash1, hash2);
  });

  test('inputSchemaがundefinedの場合も正しく処理する', () => {
    const toolWithoutSchema: ToolDefinition = {
      name: 'simple-tool',
      title: 'シンプルツール',
      description: 'スキーマなしのツール',
    };

    const hash = calculateToolHash(toolWithoutSchema);
    assertMatches(hash, /^[a-f0-9]{64}$/);
  });
});

describe('generateStorageKey', () => {
  test('正しいストレージキーを生成する', () => {
    const key = generateStorageKey(testServerPath, testServerVersion, 'test-tool');
    assertEquals(key, 'localhost:13000-1.0.0-test-tool');
  });

  test('異なるパラメータで異なるキーを生成する', () => {
    const key1 = generateStorageKey('localhost:13000', '1.0.0', 'tool1');
    const key2 = generateStorageKey('localhost:13000', '1.0.0', 'tool2');
    const key3 = generateStorageKey('localhost:13000', '2.0.0', 'tool1');

    assertNotEquals(key1, key2);
    assertNotEquals(key1, key3);
    assertNotEquals(key2, key3);
  });
});

describe('SecurityUtils with InMemoryStorageProvider', () => {
  test('loadHashStorage and saveHashStorage', async () => {
    const storageProvider = new InMemoryStorageProvider();
    const securityUtils = new SecurityUtils(storageProvider);

    // 初期状態では空のオブジェクト
    const initialStorage = await securityUtils.loadHashStorage();
    assertDeepEquals(initialStorage, {});

    // テストデータを保存
    const testStorage: HashStorage = {
      'test-key': {
        serverPath: testServerPath,
        serverVersion: testServerVersion,
        toolName: 'test-tool',
        hash: 'test-hash',
        timestamp: '2024-01-01T00:00:00.000Z',
        toolDefinition: testToolDefinition,
      },
    };

    await securityUtils.saveHashStorage(testStorage);
    const loadedStorage = await securityUtils.loadHashStorage();

    assertDeepEquals(loadedStorage, testStorage);
  });

  test('saveToolHash', async () => {
    const storageProvider = new InMemoryStorageProvider();
    const securityUtils = new SecurityUtils(storageProvider);

    await securityUtils.saveToolHash(testServerPath, testServerVersion, testToolDefinition);

    const storage = await securityUtils.loadHashStorage();
    const key = generateStorageKey(testServerPath, testServerVersion, testToolDefinition.name);

    assertDefined(storage[key]);
    assertEquals(storage[key].serverPath, testServerPath);
    assertEquals(storage[key].serverVersion, testServerVersion);
    assertEquals(storage[key].toolName, testToolDefinition.name);
    assertEquals(storage[key].hash, calculateToolHash(testToolDefinition));
    assertDeepEquals(storage[key].toolDefinition, testToolDefinition);
    assertMatches(storage[key].timestamp, /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/);
  });

  test('verifyToolDefinition - 新しいツールの場合', async () => {
    const storageProvider = new InMemoryStorageProvider();
    const securityUtils = new SecurityUtils(storageProvider);

    const result = await securityUtils.verifyToolDefinition(
      testServerPath,
      testServerVersion,
      testToolDefinition
    );

    assertTrue(result.isValid);
    assertTrue(result.isNew);
    assertUndefined(result.previousHash);
    assertEquals(result.currentHash, calculateToolHash(testToolDefinition));
    assertEquals(result.message, '新しいツールです。ハッシュ値を保存しました。');
  });

  test('verifyToolDefinition - 変更されていないツールの場合', async () => {
    const storageProvider = new InMemoryStorageProvider();
    const securityUtils = new SecurityUtils(storageProvider);

    // 最初にツールを保存
    await securityUtils.saveToolHash(testServerPath, testServerVersion, testToolDefinition);

    // 同じツールで検証
    const result = await securityUtils.verifyToolDefinition(
      testServerPath,
      testServerVersion,
      testToolDefinition
    );

    assertTrue(result.isValid);
    assertFalse(result.isNew);
    assertEquals(result.previousHash, calculateToolHash(testToolDefinition));
    assertEquals(result.currentHash, calculateToolHash(testToolDefinition));
    assertEquals(result.message, 'ツール定義は変更されていません。');
  });

  test('verifyToolDefinition - 変更されたツールの場合', async () => {
    const storageProvider = new InMemoryStorageProvider();
    const securityUtils = new SecurityUtils(storageProvider);

    // 最初にツールを保存
    await securityUtils.saveToolHash(testServerPath, testServerVersion, testToolDefinition);

    // 変更されたツールで検証
    const modifiedTool: ToolDefinition = {
      ...testToolDefinition,
      description: '変更されたツール',
    };

    const result = await securityUtils.verifyToolDefinition(
      testServerPath,
      testServerVersion,
      modifiedTool
    );

    assertFalse(result.isValid);
    assertFalse(result.isNew);
    assertEquals(result.previousHash, calculateToolHash(testToolDefinition));
    assertEquals(result.currentHash, calculateToolHash(modifiedTool));
    assertEquals(
      result.message,
      '警告: ツール定義が変更されています！Rug Pull攻撃の可能性があります。'
    );
  });

  test('listAllHashes - 空のストレージの場合', async () => {
    const storageProvider = new InMemoryStorageProvider();
    const securityUtils = new SecurityUtils(storageProvider);

    const hashes = await securityUtils.listAllHashes();
    assertLength(hashes, 0);
  });

  test('listAllHashes - 保存されたハッシュをすべて返す', async () => {
    const storageProvider = new InMemoryStorageProvider();
    const securityUtils = new SecurityUtils(storageProvider);

    // 複数のツールを保存
    const tool1: ToolDefinition = { ...testToolDefinition, name: 'tool1' };
    const tool2: ToolDefinition = { ...testToolDefinition, name: 'tool2' };

    await securityUtils.saveToolHash(testServerPath, testServerVersion, tool1);
    await securityUtils.saveToolHash(testServerPath, '2.0.0', tool2);

    const hashes = await securityUtils.listAllHashes();

    assertLength(hashes, 2);
    assertTrue(hashes.some((h) => h.toolName === 'tool1'));
    assertTrue(hashes.some((h) => h.toolName === 'tool2'));
  });
});

console.log('\n✅ security-utils.ts のすべてのテストが完了しました！');
