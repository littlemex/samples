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
  inputSchema?: Record<string, unknown>;
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
 * ストレージプロバイダーのインターフェース
 */
export interface StorageProvider {
  load(): Promise<HashStorage>;
  save(storage: HashStorage): Promise<void>;
}

/**
 * ファイルベースのストレージプロバイダー
 */
export class FileStorageProvider implements StorageProvider {
  private readonly filePath: string;

  constructor(filePath?: string) {
    this.filePath = filePath || path.join(process.cwd(), 'hash-storage.json');
  }

  async load(): Promise<HashStorage> {
    try {
      const data = await fs.readFile(this.filePath, 'utf-8');
      return JSON.parse(data);
    } catch (error) {
      // ファイルが存在しない場合は空のオブジェクトを返す
      return {};
    }
  }

  async save(storage: HashStorage): Promise<void> {
    await fs.writeFile(this.filePath, JSON.stringify(storage, null, 2), 'utf-8');
  }
}

/**
 * インメモリストレージプロバイダー（テスト用）
 */
export class InMemoryStorageProvider implements StorageProvider {
  private storage: HashStorage = {};

  async load(): Promise<HashStorage> {
    return { ...this.storage };
  }

  async save(storage: HashStorage): Promise<void> {
    this.storage = { ...storage };
  }

  // テスト用のヘルパーメソッド
  clear(): void {
    this.storage = {};
  }

  getStorage(): HashStorage {
    return { ...this.storage };
  }
}

/**
 * セキュリティユーティリティクラス
 */
export class SecurityUtils {
  private storageProvider: StorageProvider;

  constructor(storageProvider?: StorageProvider) {
    this.storageProvider = storageProvider || new FileStorageProvider();
  }

  /**
   * ツール定義からハッシュ値を計算する関数
   * @param toolDefinition ツール定義
   * @returns SHA-256 ハッシュ値
   */
  static calculateToolHash(toolDefinition: ToolDefinition): string {
    const normalizedDefinition = {
      name: toolDefinition.name,
      title: toolDefinition.title,
      description: toolDefinition.description,
      inputSchema: toolDefinition.inputSchema
        ? JSON.stringify(toolDefinition.inputSchema)
        : undefined,
    };

    return createHash('sha256').update(JSON.stringify(normalizedDefinition)).digest('hex');
  }

  /**
   * ハッシュストレージのキーを生成する関数
   * @param serverPath サーバーのパス（例: localhost:13000）
   * @param serverVersion サーバーのバージョン
   * @param toolName ツール名
   * @returns ストレージキー
   */
  static generateStorageKey(serverPath: string, serverVersion: string, toolName: string): string {
    return `${serverPath}-${serverVersion}-${toolName}`;
  }

  /**
   * ハッシュストレージを読み込む関数
   * @returns ハッシュストレージ
   */
  async loadHashStorage(): Promise<HashStorage> {
    return this.storageProvider.load();
  }

  /**
   * ハッシュストレージを保存する関数
   * @param storage ハッシュストレージ
   */
  async saveHashStorage(storage: HashStorage): Promise<void> {
    return this.storageProvider.save(storage);
  }

  /**
   * ツール定義のハッシュを保存する関数
   * @param serverPath サーバーのパス
   * @param serverVersion サーバーのバージョン
   * @param toolDefinition ツール定義
   */
  async saveToolHash(
    serverPath: string,
    serverVersion: string,
    toolDefinition: ToolDefinition
  ): Promise<void> {
    const storage = await this.loadHashStorage();
    const key = SecurityUtils.generateStorageKey(serverPath, serverVersion, toolDefinition.name);
    const hash = SecurityUtils.calculateToolHash(toolDefinition);

    storage[key] = {
      serverPath,
      serverVersion,
      toolName: toolDefinition.name,
      hash,
      timestamp: new Date().toISOString(),
      toolDefinition,
    };

    await this.saveHashStorage(storage);
  }

  /**
   * ツール定義の変更を検証する関数
   * @param serverPath サーバーのパス
   * @param serverVersion サーバーのバージョン
   * @param toolDefinition 現在のツール定義
   * @returns 検証結果
   */
  async verifyToolDefinition(
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
    const storage = await this.loadHashStorage();
    const key = SecurityUtils.generateStorageKey(serverPath, serverVersion, toolDefinition.name);
    const currentHash = SecurityUtils.calculateToolHash(toolDefinition);

    if (!storage[key]) {
      // 新しいツールの場合は自動的に保存
      await this.saveToolHash(serverPath, serverVersion, toolDefinition);
      return {
        isValid: true,
        isNew: true,
        currentHash,
        message: '新しいツールです。ハッシュ値を保存しました。',
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
        : '警告: ツール定義が変更されています！Rug Pull 攻撃の可能性があります。',
    };
  }

  /**
   * すべての保存されたハッシュを表示する関数
   * @returns ハッシュレコードの配列
   */
  async listAllHashes(): Promise<HashRecord[]> {
    const storage = await this.loadHashStorage();
    return Object.values(storage);
  }
}

// デフォルトのインスタンスをエクスポート（後方互換性のため）
const defaultSecurityUtils = new SecurityUtils();

// 後方互換性のための関数エクスポート
export const calculateToolHash = SecurityUtils.calculateToolHash;
export const generateStorageKey = SecurityUtils.generateStorageKey;
export const loadHashStorage = (): Promise<HashStorage> => defaultSecurityUtils.loadHashStorage();
export const saveHashStorage = (storage: HashStorage): Promise<void> =>
  defaultSecurityUtils.saveHashStorage(storage);
export const saveToolHash = (
  serverPath: string,
  serverVersion: string,
  toolDefinition: ToolDefinition
): Promise<void> => defaultSecurityUtils.saveToolHash(serverPath, serverVersion, toolDefinition);
export const verifyToolDefinition = (
  serverPath: string,
  serverVersion: string,
  toolDefinition: ToolDefinition
): Promise<{
  isValid: boolean;
  isNew: boolean;
  previousHash?: string;
  currentHash: string;
  message: string;
}> => defaultSecurityUtils.verifyToolDefinition(serverPath, serverVersion, toolDefinition);
export const listAllHashes = (): Promise<HashRecord[]> => defaultSecurityUtils.listAllHashes();
