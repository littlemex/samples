import { createParser, type EventSourceMessage } from 'eventsource-parser';
import { SSEMessage, CONFIG } from './types';

async function connectToSSE(): Promise<void> {
  try {
    const url = `http://${CONFIG.HOST}:${CONFIG.PORT}${CONFIG.ENDPOINT}`;
    const response = await fetch(url, {
      headers: { 'Accept': 'text/event-stream' }
    });
    
    if (!response.ok) {
      throw new Error(`HTTP エラー: ${response.status}`);
    }
    
    console.log('SSE接続確立');
    await processEventStream(response);
    
  } catch (error) {
    console.error('接続エラー:', error instanceof Error ? error.message : String(error));
  }
}

async function processEventStream(response: Response): Promise<void> {
  if (!response.body) {
    throw new Error('レスポンスボディが空です');
  }
  
  // 正しい形式でParserCallbacksオブジェクトを渡す
  const parser = createParser({
    onEvent(event: EventSourceMessage) {
      if (event.data) {
        try {
          const data = JSON.parse(event.data) as SSEMessage;
          console.log('受信データ:', data);
        } catch {
          console.log('生データ:', event.data);
        }
      }
    },
    onError(err) {
      console.error('パースエラー:', err);
    }
  });
  
  const reader = response.body.getReader();
  
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      
      const chunk = new TextDecoder().decode(value);
      parser.feed(chunk);
    }
  } catch (error) {
    console.error('ストリーム処理エラー:', error instanceof Error ? error.message : String(error));
  } finally {
    console.log('SSE接続終了');
  }
}

// SSE接続を開始
connectToSSE();
