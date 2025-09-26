vim.lsp.config("param-lsp", {
    cmd = { "param-lsp" },
    filetypes = { "python" },
    root_markers = { ".git", "setup.py", "pyproject.toml" },
})

vim.lsp.enable("param-lsp")

vim.diagnostic.config({
    virtual_text = { severity = { min = vim.diagnostic.severity.INFO } },
})

vim.api.nvim_create_autocmd("LspAttach", {
    pattern = "*",
    callback = function(args)
        local client = vim.lsp.get_client_by_id(args.data.client_id)
        if not client or client.name ~= "basedpyright" then return end

        local bufname = vim.api.nvim_buf_get_name(args.buf)
        local filename = vim.fn.fnamemodify(bufname, ":t")

        if vim.startswith(filename, "example") then vim.lsp.stop_client(client.id) end
    end,
})

return {}
