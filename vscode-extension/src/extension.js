const vscode = require("vscode");
const { LanguageClient, TransportKind } = require("vscode-languageclient/node");
const { spawn } = require("child_process");
const path = require("path");
const os = require("os");

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
 * Check if Python has param_lsp module
 * @param {string} pythonPath - Path to Python executable
 * @returns {Promise<boolean>}
 */
async function pythonHasParamLsp(pythonPath) {
  return new Promise((resolve) => {
    const child = spawn(pythonPath, ["-c", "import param_lsp"], {
      stdio: "ignore",
    });
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
          vscode.Uri.parse("https://github.com/hoxbro/param-lsp#installation"),
        );
      }
    });
}

/**
 * Detect active Python environment
 * @returns {string | null} Path to Python executable in active environment
 */
function detectPythonEnvironment() {
  const isWindows = os.platform() === "win32";
  const pythonExe = isWindows ? "python.exe" : "python";

  // Check for virtual environment
  if (process.env.VIRTUAL_ENV) {
    const binDir = isWindows ? "Scripts" : "bin";
    const pythonPath = path.join(process.env.VIRTUAL_ENV, binDir, pythonExe);
    return pythonPath;
  }

  // Check for Conda environment
  if (process.env.CONDA_PREFIX) {
    const binDir = isWindows ? "Scripts" : "bin";
    const pythonPath = path.join(process.env.CONDA_PREFIX, binDir, pythonExe);
    return pythonPath;
  }

  return null;
}

/**
 * Get server options based on configuration
 * @param {vscode.WorkspaceConfiguration} config - The configuration
 * @returns {Promise<import('vscode-languageclient/node').ServerOptions | null>}
 */
async function getServerOptions(config) {
  const pythonPath = config.get("pythonPath");

  // Try different approaches in order of preference
  let serverOptions = null;

  if (pythonPath) {
    // 1. Use explicitly configured Python path
    const pythonExists = await commandExists(pythonPath);
    if (!pythonExists) {
      showInstallationError(`Python interpreter not found: ${pythonPath}`);
      return null;
    }

    serverOptions = {
      command: pythonPath,
      args: ["-c", "import param_lsp.__main__; param_lsp.__main__.main()"],
      transport: TransportKind.stdio,
    };
  } else {
    // 2. Try active Python environment first
    const envPython = detectPythonEnvironment();
    if (envPython) {
      const pythonExists = await commandExists(envPython);
      if (pythonExists) {
        const hasParamLsp = await pythonHasParamLsp(envPython);
        if (hasParamLsp) {
          serverOptions = {
            command: envPython,
            args: [
              "-c",
              "import param_lsp.__main__; param_lsp.__main__.main()",
            ],
            transport: TransportKind.stdio,
          };
        } else {
          // Active environment exists but doesn't have param-lsp
          const envType = process.env.VIRTUAL_ENV
            ? "virtual environment"
            : "conda environment";
          const envPath = process.env.VIRTUAL_ENV || process.env.CONDA_PREFIX;
          showInstallationError(
            `Active ${envType} (${envPath}) does not have param-lsp installed. Please run 'pip install param-lsp' in this environment.`,
          );
          return null;
        }
      }
    }

    // 3. Try direct command if no environment or environment failed
    if (!serverOptions) {
      const commandExists_ = await commandExists("param-lsp");
      if (commandExists_) {
        serverOptions = {
          command: "param-lsp",
          transport: TransportKind.stdio,
        };
      }
    }

    // 4. Try system python
    if (!serverOptions) {
      const pythonExists = await commandExists("python");
      if (pythonExists) {
        const hasParamLsp = await pythonHasParamLsp("python");
        if (hasParamLsp) {
          serverOptions = {
            command: "python",
            args: [
              "-c",
              "import param_lsp.__main__; param_lsp.__main__.main()",
            ],
            transport: TransportKind.stdio,
          };
        }
      }
    }

    // 5. Final fallback to python3
    if (!serverOptions) {
      const python3Exists = await commandExists("python3");
      if (python3Exists) {
        const hasParamLsp = await pythonHasParamLsp("python3");
        if (hasParamLsp) {
          serverOptions = {
            command: "python3",
            args: [
              "-c",
              "import param_lsp.__main__; param_lsp.__main__.main()",
            ],
            transport: TransportKind.stdio,
          };
        }
      }
    }
  }

  if (!serverOptions) {
    showInstallationError(
      `Cannot find param-lsp. Please install it with 'pip install param-lsp' or configure the path.`,
    );
    return null;
  }

  return serverOptions;
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
