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
 * 修正版SSE接続テストスクリプト
 */
async function testSSEConnection() {
  console.log('=== 修正版SSE接続テスト開始 ===\n');

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
        capabilities: {
          tools: {
            listChanged: true
          }
        },
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
        'Accept': 'application/json',
      },
      body: JSON.stringify(initRequest),
    });

    console.log('レスポンスステータス:', initResponse.status);

    // ヘッダーを取得
    const headers: Record<string, string> = {};
    initResponse.headers.forEach((value, key) => {
      headers[key] = value;
    });
    console.log('レスポンスヘッダー:', headers);

    sessionId = initResponse.headers.get('mcp-session-id');
    console.log('取得したセッションID:', sessionId);

    if (!initResponse.ok) {
      const errorText = await initResponse.text();
      throw new Error(`初期化失敗: ${initResponse.status} - ${errorText}`);
    }

    const initData = await initResponse.json() as MCPResponse;
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
    
    const sseUrl = `${SERVER_URL}/mcp`;
    console.log(`SSE接続URL: ${sseUrl}`);

    // EventSourceのオプションを設定
    const eventSourceOptions = {
      headers: {
        'mcp-session-id': sessionId,
        'Accept': 'text/event-stream',
        'Cache-Control': 'no-cache',
      },
      withCredentials: false,
    };

    console.log('EventSourceオプション:', JSON.stringify(eventSourceOptions, null, 2));

    eventSource = new EventSource(sseUrl, eventSourceOptions);

    // 接続成功を待つPromise
    const connectionPromise = new Promise<void>((resolve, reject) => {
      const timeout = setTimeout(() => {
        reject(new Error('SSE接続タイムアウト（15秒）'));
      }, 15000);

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
            console.log('通知内容:', JSON.stringify(data, null, 2));
          }
        } catch (e) {
          console.log('📨 非JSON メッセージ:', event.data);
        }
      };

      // 特定のイベントタイプをリッスン
      eventSource!.addEventListener('message', (event) => {
        console.log('📨 message イベント受信:', event.data);
      });

      eventSource!.addEventListener('notification', (event) => {
        console.log('📨 notification イベント受信:', event.data);
      });
    });

    try {
      await connectionPromise;
      console.log('✅ SSE接続確立完了');
    } catch (error) {
      console.error('❌ SSE接続失敗:', error);
      throw error;
    }

    // ステップ3: ツールリストの取得
    console.log('\n📋 ステップ3: ツールリストを取得');
    const toolsListRequest: MCPRequest = {
      jsonrpc: '2.0',
      method: 'tools/list',
      params: {},
      id: 2,
    };

    const toolsResponse = await fetch(`${SERVER_URL}/mcp`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'mcp-session-id': sessionId,
      },
      body: JSON.stringify(toolsListRequest),
    });

    const toolsData = await toolsResponse.json();
    console.log('ツールリスト:', JSON.stringify(toolsData, null, 2));

    // ステップ4: テスト通知の送信
    console.log('\n📤 ステップ4: テスト通知を送信');
    
    const changeResponse = await fetch(`${SERVER_URL}/change-description`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
    });

    const changeData = await changeResponse.json();
    console.log('ツール定義変更レスポンス:', JSON.stringify(changeData, null, 2));

    // 通知を待つ
    console.log('\n⏳ 通知を15秒間待機中...');
    await new Promise(resolve => setTimeout(resolve, 15000));

    // ステップ5: 変更後のツールリストを取得
    console.log('\n📋 ステップ5: 変更後のツールリストを取得');
    const updatedToolsResponse = await fetch(`${SERVER_URL}/mcp`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'mcp-session-id': sessionId,
      },
      body: JSON.stringify({
        ...toolsListRequest,
        id: 3,
      }),
    });

    const updatedToolsData = await updatedToolsResponse.json();
    console.log('更新されたツールリスト:', JSON.stringify(updatedToolsData, null, 2));

    console.log('\n✅ テスト完了！');

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
          },
        });
      } catch (error) {
        console.error('セッション終了エラー:', error);
      }
    }
  }

  console.log('\n=== 修正版SSE接続テスト完了 ===');
}

// メイン実行
console.log('🚀 修正版SSE接続テストを開始します...\n');

// サーバーが起動していることを確認
fetch(`${SERVER_URL}/tool-status`)
  .then(response => {
    if (!response.ok) {
      throw new Error(`サーバーが応答しません: ${response.status}`);
    }
    console.log('✅ サーバーが稼働中です\n');
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