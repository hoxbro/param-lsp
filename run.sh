#!/usr/bin/env bash

cd /home/shh/projects/holoviz/repos/$1

unset VIRTUAL_ENV
ENV=holoviz
export CONDA_DEFAULT_ENV="$ENV"
export CONDA_PREFIX="$CONDA_HOME/envs/$ENV"
export PATH="$CONDA_PREFIX/bin:$PATH"
param-lsp --log-level ERROR cache --regenerate  # We don't care about this

param-lsp check $1/$2
