import { EventSource } from 'eventsource';

const SERVER_URL = 'http://localhost:13000';

interface MCPRequest {
  jsonrpc: string;
  method: string;
  params?: Record<string, unknown>;
  id: string | number;
}

interface MCPResponse {
  jsonrpc: string;
  result?: unknown;
  error?: {
    code: number;
    message: string;
    data?: unknown;
  };
  id: string | number;
}

/**
 * SSE接続テストスクリプト
 * SSE接続の問題を素早くデバッグするためのスクリプト
 */
async function testSSEConnection() {
  console.log('=== SSE接続テスト開始 ===\n');

  let sessionId: string | null = null;
  let eventSource: EventSource | null = null;

  try {
    // ステップ1: MCPセッションの初期化
    console.log('📋 ステップ1: MCPセッションを初期化');
    
    const initRequest: MCPRequest = {
      jsonrpc: '2.0',
      method: 'initialize',
      params: {
        protocolVersion: '2025-06-18',
        capabilities: {},
        clientInfo: {
          name: 'sse-test-client',
          version: '1.0.0',
        },
      },
      id: 1,
    };

    console.log('送信リクエスト:', JSON.stringify(initRequest, null, 2));

    const initResponse = await fetch(`${SERVER_URL}/mcp`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json, text/event-stream',  // MCP SDKが要求する両方のコンテンツタイプ
      },
      body: JSON.stringify(initRequest),
    });

    console.log('レスポンスステータス:', initResponse.status);
    
    // ヘッダーを手動で取得（Headers.entries()の互換性問題を回避）
    const headers: Record<string, string> = {};
    initResponse.headers.forEach((value, key) => {
      headers[key] = value;
    });
    console.log('レスポンスヘッダー:', headers);

    sessionId = initResponse.headers.get('mcp-session-id');
    console.log('取得したセッションID:', sessionId);

    // Content-Typeをチェックしてレスポンスを適切に処理
    const contentType = initResponse.headers.get('content-type');
    let initData: MCPResponse;
    
    if (contentType?.includes('text/event-stream')) {
      // SSE形式のレスポンスを処理
      const text = await initResponse.text();
      console.log('SSEレスポンス:', text);
      
      // SSEデータから実際のJSONを抽出
      const dataMatch = text.match(/data:\s*(.+)/);
      if (dataMatch) {
        initData = JSON.parse(dataMatch[1]) as MCPResponse;
      } else {
        throw new Error('SSEレスポンスからデータを抽出できませんでした');
      }
    } else {
      // 通常のJSONレスポンス
      initData = await initResponse.json() as MCPResponse;
    }
    
    console.log('初期化レスポンス:', JSON.stringify(initData, null, 2));

    if (initData.error) {
      throw new Error(`初期化エラー: ${initData.error.message}`);
    }

    if (!sessionId) {
      throw new Error('セッションIDが取得できませんでした');
    }

    console.log('✅ セッション初期化成功\n');

    // ステップ2: SSE接続の確立
    console.log('📡 ステップ2: SSE接続を確立');
    
    // SDK標準に準拠したSSE接続
    const sseUrl = `${SERVER_URL}/mcp`;
    console.log(`\nSSE接続URL: ${sseUrl}`);
    
    // EventSourceのオプションを設定（SDK標準準拠）
    // EventSourceはURLにパラメータを含める必要がある
    const sseUrlWithParams = `${sseUrl}?mcp-session-id=${encodeURIComponent(sessionId)}&mcp-protocol-version=2025-06-18`;
    
    console.log(`SSE接続URL（パラメータ付き）: ${sseUrlWithParams}`);

    eventSource = new EventSource(sseUrlWithParams, {
      withCredentials: false,
    });

    // 接続成功を待つPromise
    const connectionPromise = new Promise<void>((resolve, reject) => {
      const timeout = setTimeout(() => {
        reject(new Error('SSE接続タイムアウト（10秒）'));
      }, 10000);

      eventSource!.onopen = (event) => {
        clearTimeout(timeout);
        console.log('✅ SSE接続成功！');
        console.log('接続イベント:', event);
        resolve();
      };

      eventSource!.onerror = (error) => {
        clearTimeout(timeout);
        console.error('❌ SSE接続エラー:');
        console.error('エラー詳細:', error);
        
        // EventSourceのエラーオブジェクトの詳細を出力
        if (error && typeof error === 'object') {
          console.error('エラープロパティ:');
          Object.entries(error).forEach(([key, value]) => {
            console.error(`  ${key}:`, value);
          });
        }
        
        reject(error);
      };

      eventSource!.onmessage = (event) => {
        console.log('📨 メッセージ受信:', event.data);
        try {
          const data = JSON.parse(event.data);
          if (data.method === 'notifications/tools/list_changed') {
            console.log('🚨 tools/list_changed 通知を受信しました！');
          }
        } catch (e) {
          // JSON以外のメッセージの場合は無視
        }
      };

      // 特定のイベントタイプをリッスン
      eventSource!.addEventListener('message', (event) => {
        console.log('📨 message イベント受信:', event.data);
      });
    });

    try {
      await connectionPromise;
      console.log('✅ SSE接続成功');
    } catch (error) {
      console.error('❌ SSE接続失敗:', error);
      throw error;
    }

    // ステップ3: テスト通知の送信
    console.log('\n📤 ステップ3: テスト通知を送信');
    
    // ツール定義を変更してlistChanged通知をトリガー
    const changeResponse = await fetch(`${SERVER_URL}/change-description`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
    });

    const changeData = await changeResponse.json();
    console.log('ツール定義変更レスポンス:', JSON.stringify(changeData, null, 2));

    // 通知を待つ
    console.log('\n⏳ 通知を10秒間待機中...');
    await new Promise(resolve => setTimeout(resolve, 10000));

  } catch (error) {
    console.error('\n❌ テスト失敗:', error);
    if (error instanceof Error) {
      console.error('エラーメッセージ:', error.message);
      console.error('スタックトレース:', error.stack);
    }
  } finally {
    // クリーンアップ
    if (eventSource) {
      console.log('\n🧹 SSE接続を終了');
      eventSource.close();
    }

    if (sessionId) {
      console.log('🧹 MCPセッションを終了');
      try {
        await fetch(`${SERVER_URL}/mcp`, {
          method: 'DELETE',
          headers: {
            'mcp-session-id': sessionId,
            'mcp-protocol-version': '2025-06-18',
          },
        });
      } catch (error) {
        console.error('セッション終了エラー:', error);
      }
    }
  }

  console.log('\n=== SSE接続テスト完了 ===');
}

// メイン実行
console.log('🚀 SSE接続テストを開始します...\n');

// サーバーが起動していることを確認
fetch(`${SERVER_URL}/tool-status`)
  .then(response => {
    if (!response.ok) {
      throw new Error(`サーバーが応答しません: ${response.status}`);
    }
    console.log('✅ サーバーが稼働中です\n');
    
    // トランスポートをリセットしてクリーンな状態でテスト開始
    console.log('🔄 テスト開始前にトランスポートをリセット...');
    return fetch(`${SERVER_URL}/reset-transport`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
    });
  })
  .then(response => {
    if (!response.ok) {
      console.warn('⚠️ トランスポートリセットに失敗しましたが、テストを続行します');
    } else {
      console.log('✅ トランスポートリセット完了\n');
    }
    return testSSEConnection();
  })
  .catch(error => {
    console.error('❌ サーバーに接続できません:', error.message);
    console.error('サーバーが起動していることを確認してください');
    process.exit(1);
  })
  .then(() => {
    process.exit(0);
  })
  .catch(() => {
    process.exit(1);
  });
