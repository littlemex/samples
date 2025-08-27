## MCP Inspector から AgentCore Runtime に接続してみよう

MCP Inspector から AgentCore Runtime に接続してみてください。おそらくうまく接続できないはずです。
これは MCP Server の起動時にデフォルトで SigV4 が利用されるためです。

そして重要なポイントは、**SigV4 認証の仕組みによる認可は MCP 仕様ではサポートされていない**ため MCP Inspector やそのほかの一般的な MCP Client では SigV4 認証での接続ができません。

AgentCore Runtime では JWT Bearer Token をサポートしており、deploy.py でも Cognito を IdP として対応できるようには作ってあります。
MCP Server の設定を JWT Bearer Token 認可に変更すれば問題なく MCP Inspector で接続できるので試してみましょう。
変更の仕方については `../README.md` を読めばわかるはずです。