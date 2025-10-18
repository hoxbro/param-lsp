const vscode = require("vscode");
const { LanguageClient, TransportKind } = require("vscode-languageclient/node");
const { spawn } = require("child_process");

/**
 * @type {LanguageClient}
 */
let client;

/**
 * Check if a command exists
 * @param {string} command - The command to check
 * @returns {Promise<boolean>}
 */
async function commandExists(command) {
  return new Promise((resolve) => {
    const child = spawn(command, ["--version"], { stdio: "ignore" });
    child.on("error", () => resolve(false));
    child.on("close", (code) => resolve(code === 0));
  });
}

/**
 * Show error message with helpful guidance
 * @param {string} message - The error message
 */
function showInstallationError(message) {
  const installAction = "Installation Guide";
  vscode.window
    .showErrorMessage(`Param LSP: ${message}`, installAction)
    .then((selection) => {
      if (selection === installAction) {
        vscode.env.openExternal(
          vscode.Uri.parse(
            "https://param-lsp.readthedocs.io/en/latest/installation/#installing-param-lsp",
          ),
        );
      }
    });
}

/**
 * Create server options for a given command
 * @param {string} command - The command to run
 * @param {string[]} args - Arguments for the command (optional)
 * @returns {import('vscode-languageclient/node').ServerOptions}
 */
function createServerOptions(command, args = []) {
  return {
    command,
    args,
    transport: TransportKind.stdio,
  };
}

/**
 * Get server options based on configuration
 * @param {vscode.WorkspaceConfiguration} config - The configuration
 * @returns {Promise<import('vscode-languageclient/node').ServerOptions | null>}
 */
async function getServerOptions(config) {
  // Check if param-lsp is available in PATH
  const paramLspExists = await commandExists("param-lsp");
  if (paramLspExists) {
    return createServerOptions("param-lsp");
  }

  // No valid server found
  showInstallationError(
    `Cannot find param-lsp. Please install it and ensure it's available to you.`,
  );
  return null;
}

/**
 * Activates the extension
 * @param {vscode.ExtensionContext} context - The extension context
 */
async function activate(context) {
  const config = vscode.workspace.getConfiguration("param-lsp");

  if (!config.get("enable", true)) {
    return;
  }

  const serverOptions = await getServerOptions(config);
  if (!serverOptions) {
    return; // Error already shown to user
  }

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

  try {
    await client.start();
  } catch (error) {
    showInstallationError(`Failed to start language server: ${error.message}`);
  }
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
