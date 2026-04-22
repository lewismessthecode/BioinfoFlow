setopt PROMPT_SUBST
unsetopt BEEP

source "${ZDOTDIR}/prompt_common.sh"
PROMPT=""
RPROMPT=""
autoload -Uz add-zsh-hook
add-zsh-hook precmd _bif_terminal_set_zsh_prompt
_bif_terminal_set_zsh_prompt
