import * as vscode from 'vscode';
import {
    LanguageClient,
    LanguageClientOptions,
    ServerOptions,
    TransportKind
} from 'vscode-languageclient/node';

let client: LanguageClient;

export function activate(context: vscode.ExtensionContext) {
    const config = vscode.workspace.getConfiguration('param-lsp');

    if (!config.get('enable', true)) {
        return;
    }

    const serverOptions: ServerOptions = {
        command: 'param-lsp',
        transport: TransportKind.stdio
    };

    const clientOptions: LanguageClientOptions = {
        documentSelector: [{ scheme: 'file', language: 'python' }],
        synchronize: {
            fileEvents: vscode.workspace.createFileSystemWatcher('**/.clientrc')
        },
        workspaceFolder: vscode.workspace.workspaceFolders?.[0]
    };

    client = new LanguageClient(
        'param-lsp',
        'Param Language Server',
        serverOptions,
        clientOptions
    );

    client.start();
}

export function deactivate(): Thenable<void> | undefined {
    if (!client) {
        return undefined;
    }
    return client.stop();
}
