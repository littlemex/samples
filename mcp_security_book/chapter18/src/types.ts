/**
 * ツール定義の型定義
 */

export interface ToolDescriptions {
  original: string;
  modified: string;
}

export interface ToolConfig {
  name: string;
  title: string;
  descriptions: ToolDescriptions;
  currentVersion: 'original' | 'modified';
}

export interface ToolDefinitions {
  tools: {
    add: ToolConfig;
  };
}

export interface CurrentToolDefinition {
  name: string;
  title: string;
  description: string;
  currentVersion: 'original' | 'modified';
  descriptions: ToolDescriptions;
}

export interface NotificationData {
  method?: string;
  params?: Record<string, unknown>;
}

export interface ToolInputSchema {
  type: 'object';
  properties: {
    a: {
      type: 'number';
      description: string;
    };
    b: {
      type: 'number';
      description: string;
    };
  };
  required: string[];
}

export interface ToolMeta {
  hash: string;
  version: string;
  serverName: string;
  serverVersion: string;
  timestamp: string;
  securityNote: string;
}
