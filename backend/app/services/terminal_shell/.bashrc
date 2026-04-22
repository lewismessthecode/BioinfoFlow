#!/usr/bin/env bash

set -o emacs

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "${SCRIPT_DIR}/prompt_common.sh"

PROMPT_COMMAND="_bif_terminal_set_bash_prompt"
_bif_terminal_set_bash_prompt
