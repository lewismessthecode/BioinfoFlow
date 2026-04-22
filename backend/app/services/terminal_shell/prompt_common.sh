#!/bin/sh

_bif_terminal_git_root() {
  git rev-parse --show-toplevel 2>/dev/null
}

_bif_terminal_git_branch() {
  git branch --show-current 2>/dev/null
}

_bif_terminal_display_path() {
  current_dir="$PWD"
  git_root="$(_bif_terminal_git_root)"

  if [ -n "$git_root" ]; then
    root_name=$(basename "$git_root")
    if [ "$current_dir" = "$git_root" ]; then
      printf '%s' "$root_name"
      return
    fi

    relative_path="${current_dir#"$git_root"/}"
    printf '%s/%s' "$root_name" "$relative_path"
    return
  fi

  printf '%s' "$(basename "$current_dir")"
}

_bif_terminal_set_bash_prompt() {
  display_path="$(_bif_terminal_display_path)"
  git_branch="$(_bif_terminal_git_branch)"

  if [ -n "$git_branch" ]; then
    PS1="\[\e[34m\]${display_path}\[\e[0m\] \[\e[90m\]${git_branch}\[\e[0m\]\n\[\e[34m\]❯\[\e[0m\] "
    return
  fi

  PS1="\[\e[34m\]${display_path}\[\e[0m\]\n\[\e[34m\]❯\[\e[0m\] "
}

_bif_terminal_set_zsh_prompt() {
  display_path="$(_bif_terminal_display_path)"
  git_branch="$(_bif_terminal_git_branch)"

  if [ -n "$git_branch" ]; then
    PROMPT="%F{33}${display_path}%f %F{242}${git_branch}%f"$'\n'"%F{33}❯%f "
    return
  fi

  PROMPT="%F{33}${display_path}%f"$'\n'"%F{33}❯%f "
}
