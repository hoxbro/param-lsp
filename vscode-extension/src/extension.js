const vscode = require("vscode");
const { LanguageClient, TransportKind } = require("vscode-languageclient/node");

/**
 * @type {LanguageClient}
 */
let client;

/**
 * Activates the extension
 * @param {vscode.ExtensionContext} context - The extension context
 */
function activate(context) {
  const config = vscode.workspace.getConfiguration("param-lsp");

  if (!config.get("enable", true)) {
    return;
  }

  /** @type {import('vscode-languageclient/node').ServerOptions} */
  const serverOptions = {
    command: "param-lsp",
    transport: TransportKind.stdio,
  };

  /** @type {import('vscode-languageclient/node').LanguageClientOptions} */
  const clientOptions = {
    documentSelector: [{ scheme: "file", language: "python" }],
    synchronize: {
      fileEvents: vscode.workspace.createFileSystemWatcher("**/.clientrc"),
    },
    workspaceFolder: vscode.workspace.workspaceFolders?.[0],
  };

  client = new LanguageClient(
    "param-lsp",
    "Param Language Server",
    serverOptions,
    clientOptions,
  );

  client.start();
}

/**
 * Deactivates the extension
 * @returns {Promise<void> | undefined}
 */
function deactivate() {
  if (!client) {
    return undefined;
  }
  return client.stop();
}

module.exports = {
  activate,
  deactivate,
};
