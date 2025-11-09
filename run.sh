#!/usr/bin/env bash

project=$(echo $1 | cut -d/ -f1)
cd /home/shh/projects/holoviz/repos/$project

unset VIRTUAL_ENV
ENV=holoviz
export CONDA_DEFAULT_ENV="$ENV"
export CONDA_PREFIX="$CONDA_HOME/envs/$ENV"
export PATH="$CONDA_PREFIX/bin:$PATH"
param-lsp --log-level ERROR cache --regenerate  # We don't care about this

param-lsp check $1
