import { createHash } from 'node:crypto';
import { promises as fs } from 'node:fs';
import path from 'node:path';

/**
 * ツール定義の型
 */
export interface ToolDefinition {
  name: string;
  title: string;
  description: string;
  inputSchema?: any;
}

/**
 * 保存されるハッシュ情報の型
 */
export interface HashRecord {
  serverPath: string;
  serverVersion: string;
  toolName: string;
  hash: string;
  timestamp: string;
  toolDefinition: ToolDefinition;
}

/**
 * ハッシュストレージの型
 */
export interface HashStorage {
  [key: string]: HashRecord;
}

/**
 * ツール定義からハッシュ値を計算する関数
 * @param toolDefinition ツール定義
 * @returns SHA-256ハッシュ値
 */
export function calculateToolHash(toolDefinition: ToolDefinition): string {
  const normalizedDefinition = {
    name: toolDefinition.name,
    title: toolDefinition.title,
    description: toolDefinition.description,
    inputSchema: toolDefinition.inputSchema ? JSON.stringify(toolDefinition.inputSchema) : undefined
  };
  
  return createHash('sha256')
    .update(JSON.stringify(normalizedDefinition))
    .digest('hex');
}

/**
 * ハッシュストレージのキーを生成する関数
 * @param serverPath サーバーのパス（例: localhost:13000）
 * @param serverVersion サーバーのバージョン
 * @param toolName ツール名
 * @returns ストレージキー
 */
export function generateStorageKey(serverPath: string, serverVersion: string, toolName: string): string {
  return `${serverPath}-${serverVersion}-${toolName}`;
}

/**
 * ハッシュストレージファイルのパス
 */
const HASH_STORAGE_PATH = path.join(process.cwd(), 'hash-storage.json');

/**
 * ハッシュストレージを読み込む関数
 * @returns ハッシュストレージ
 */
export async function loadHashStorage(): Promise<HashStorage> {
  try {
    const data = await fs.readFile(HASH_STORAGE_PATH, 'utf-8');
    return JSON.parse(data);
  } catch (error) {
    // ファイルが存在しない場合は空のオブジェクトを返す
    return {};
  }
}

/**
 * ハッシュストレージを保存する関数
 * @param storage ハッシュストレージ
 */
export async function saveHashStorage(storage: HashStorage): Promise<void> {
  await fs.writeFile(HASH_STORAGE_PATH, JSON.stringify(storage, null, 2), 'utf-8');
}

/**
 * ツール定義のハッシュを保存する関数
 * @param serverPath サーバーのパス
 * @param serverVersion サーバーのバージョン
 * @param toolDefinition ツール定義
 */
export async function saveToolHash(
  serverPath: string,
  serverVersion: string,
  toolDefinition: ToolDefinition
): Promise<void> {
  const storage = await loadHashStorage();
  const key = generateStorageKey(serverPath, serverVersion, toolDefinition.name);
  const hash = calculateToolHash(toolDefinition);
  
  storage[key] = {
    serverPath,
    serverVersion,
    toolName: toolDefinition.name,
    hash,
    timestamp: new Date().toISOString(),
    toolDefinition
  };
  
  await saveHashStorage(storage);
}

/**
 * ツール定義の変更を検証する関数
 * @param serverPath サーバーのパス
 * @param serverVersion サーバーのバージョン
 * @param toolDefinition 現在のツール定義
 * @returns 検証結果
 */
export async function verifyToolDefinition(
  serverPath: string,
  serverVersion: string,
  toolDefinition: ToolDefinition
): Promise<{
  isValid: boolean;
  isNew: boolean;
  previousHash?: string;
  currentHash: string;
  message: string;
}> {
  const storage = await loadHashStorage();
  const key = generateStorageKey(serverPath, serverVersion, toolDefinition.name);
  const currentHash = calculateToolHash(toolDefinition);
  
  if (!storage[key]) {
    return {
      isValid: true,
      isNew: true,
      currentHash,
      message: '新しいツールです。ハッシュ値を保存しました。'
    };
  }
  
  const storedRecord = storage[key];
  const isValid = storedRecord.hash === currentHash;
  
  return {
    isValid,
    isNew: false,
    previousHash: storedRecord.hash,
    currentHash,
    message: isValid 
      ? 'ツール定義は変更されていません。' 
      : '警告: ツール定義が変更されています！Rug Pull攻撃の可能性があります。'
  };
}

/**
 * すべての保存されたハッシュを表示する関数
 * @returns ハッシュレコードの配列
 */
export async function listAllHashes(): Promise<HashRecord[]> {
  const storage = await loadHashStorage();
  return Object.values(storage);
}
