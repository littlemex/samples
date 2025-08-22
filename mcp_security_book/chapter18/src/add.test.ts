/**
 * add.ts の足し算機能に対するテスト
 */
import { addNumbers, calculateAndSave, getLastCalculation } from './add.js';

/**
 * テスト関数の型定義
 */
type TestFunction = (name: string, fn: () => void) => void;

/**
 * テスト関数（実際のJestの代わりに使用）
 */
const test: TestFunction = (name, fn) => {
  console.log(`テスト実行: ${name}`);
  try {
    fn();
    console.log('✅ テスト成功');
  } catch (error) {
    console.error('❌ テスト失敗:', error);
    throw error; // テスト失敗時にエラーを再スローして、テストの失敗を明示的に示す
  }
};

/**
 * 複数のテストをグループ化する関数
 */
function describe(name: string, fn: () => void): void {
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
 * オブジェクトが特定のプロパティを持つことを検証する関数
 */
function assertHasProperties<T extends object>(obj: T, props: string[], message?: string): void {
  for (const prop of props) {
    if (!(prop in obj)) {
      throw new Error(message || `オブジェクトにプロパティ '${prop}' がありません`);
    }
  }
}

// テストの実行
describe('addNumbers関数のテスト', () => {
  test('正の数の足し算', () => {
    assertEquals(addNumbers(5, 3), 8);
  });

  test('負の数の足し算', () => {
    assertEquals(addNumbers(-5, -3), -8);
  });

  test('正と負の数の足し算', () => {
    assertEquals(addNumbers(5, -3), 2);
  });

  test('小数の足し算', () => {
    assertEquals(addNumbers(0.1, 0.2), 0.30000000000000004); // JavaScriptの浮動小数点数の特性による
  });

  test('大きな数の足し算', () => {
    assertEquals(addNumbers(Number.MAX_SAFE_INTEGER, 1), Number.MAX_SAFE_INTEGER + 1);
  });
});

describe('calculateAndSave関数のテスト', () => {
  test('計算結果が正しく返される', () => {
    const result = calculateAndSave(10, 20);
    assertEquals(result.a, 10);
    assertEquals(result.b, 20);
    assertEquals(result.sum, 30);
    assertHasProperties(result, ['timestamp']);
  });

  test('計算結果が保存される', () => {
    const result1 = calculateAndSave(100, 200);
    const lastResult = getLastCalculation();

    assertEquals(lastResult.a, 100);
    assertEquals(lastResult.b, 200);
    assertEquals(lastResult.sum, 300);
    assertEquals(lastResult.timestamp, result1.timestamp);
  });
});

describe('getLastCalculation関数のテスト', () => {
  test('最後の計算結果が取得できる', () => {
    // 新しい計算を実行
    calculateAndSave(50, 70);

    // 最後の計算結果を取得
    const lastResult = getLastCalculation();

    assertEquals(lastResult.a, 50);
    assertEquals(lastResult.b, 70);
    assertEquals(lastResult.sum, 120);
    assertHasProperties(lastResult, ['timestamp']);
  });

  test('返されるオブジェクトは元のオブジェクトのコピー', () => {
    // 新しい計算を実行
    calculateAndSave(1, 2);

    // 最後の計算結果を取得
    const lastResult = getLastCalculation();

    // 取得した結果を変更
    lastResult.a = 999;

    // 再度取得して、元のオブジェクトが変更されていないことを確認
    const newLastResult = getLastCalculation();
    assertEquals(newLastResult.a, 1, '元のオブジェクトが変更されていないこと');
  });
});

// すべてのテストを実行
console.log('\n=== テスト実行結果 ===');
try {
  describe('add.ts のすべてのテスト', () => {
    describe('addNumbers関数のテスト', () => {
      test('正の数の足し算', () => {
        assertEquals(addNumbers(5, 3), 8);
      });

      test('負の数の足し算', () => {
        assertEquals(addNumbers(-5, -3), -8);
      });

      test('正と負の数の足し算', () => {
        assertEquals(addNumbers(5, -3), 2);
      });
    });

    describe('calculateAndSave関数のテスト', () => {
      test('計算結果が正しく返される', () => {
        const result = calculateAndSave(10, 20);
        assertEquals(result.a, 10);
        assertEquals(result.b, 20);
        assertEquals(result.sum, 30);
        assertHasProperties(result, ['timestamp']);
      });
    });

    describe('getLastCalculation関数のテスト', () => {
      test('最後の計算結果が取得できる', () => {
        calculateAndSave(50, 70);
        const lastResult = getLastCalculation();
        assertEquals(lastResult.a, 50);
        assertEquals(lastResult.b, 70);
        assertEquals(lastResult.sum, 120);
      });
    });
  });

  console.log('\n✅ すべてのテストが成功しました！');
} catch (error) {
  console.error('\n❌ テスト実行中にエラーが発生しました:', error);
}
