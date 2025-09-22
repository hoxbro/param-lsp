vim.lsp.config("param-lsp", {
	cmd = { "param-lsp" },
	filetypes = { "python" },
	root_markers = { ".git", "setup.py", "pyproject.toml" },
})

vim.lsp.enable("param-lsp")

return {}
