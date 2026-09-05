import type { LanguageRegistration } from "shiki"

// Shiki does not bundle WDL. Keep this small TextMate grammar local so workspace
// previews never silently fall back to plain text for BioinfoFlow's other core
// workflow language.
export const wdlLanguage: LanguageRegistration = {
  name: "wdl",
  displayName: "Workflow Description Language",
  scopeName: "source.wdl",
  patterns: [
    { include: "#comments" },
    { include: "#strings" },
    { include: "#version" },
    { include: "#declarations" },
    { include: "#types" },
    { include: "#keywords" },
    { include: "#constants" },
    { include: "#numbers" },
    { include: "#operators" },
  ],
  repository: {
    comments: {
      patterns: [
        {
          match: "#.*$",
          name: "comment.line.number-sign.wdl",
        },
      ],
    },
    strings: {
      patterns: [
        {
          begin: '"',
          beginCaptures: { 0: { name: "punctuation.definition.string.begin.wdl" } },
          end: '"',
          endCaptures: { 0: { name: "punctuation.definition.string.end.wdl" } },
          name: "string.quoted.double.wdl",
          patterns: [
            { match: "\\\\.", name: "constant.character.escape.wdl" },
            { include: "#placeholder" },
          ],
        },
        {
          begin: "'",
          beginCaptures: { 0: { name: "punctuation.definition.string.begin.wdl" } },
          end: "'",
          endCaptures: { 0: { name: "punctuation.definition.string.end.wdl" } },
          name: "string.quoted.single.wdl",
          patterns: [
            { match: "\\\\.", name: "constant.character.escape.wdl" },
            { include: "#placeholder" },
          ],
        },
        {
          begin: "<<<",
          end: ">>>",
          name: "string.unquoted.heredoc.wdl",
          patterns: [{ include: "#placeholder" }],
        },
      ],
    },
    placeholder: {
      begin: "[$~]\\{",
      beginCaptures: { 0: { name: "punctuation.section.embedded.begin.wdl" } },
      end: "}",
      endCaptures: { 0: { name: "punctuation.section.embedded.end.wdl" } },
      name: "meta.interpolation.wdl",
      patterns: [
        { include: "#types" },
        { include: "#keywords" },
        { include: "#constants" },
        { include: "#numbers" },
        { include: "#operators" },
      ],
    },
    version: {
      match: "\\b(version)(\\s+)([0-9]+(?:\\.[0-9]+)?)",
      captures: {
        1: { name: "keyword.other.version.wdl" },
        3: { name: "constant.numeric.version.wdl" },
      },
    },
    declarations: {
      patterns: [
        {
          match: "\\b(workflow|task|struct|enum)(\\s+)([A-Za-z][A-Za-z0-9_]*)",
          captures: {
            1: { name: "storage.type.declaration.wdl" },
            3: { name: "entity.name.type.wdl" },
          },
        },
        {
          match: "\\b(call)(\\s+)([A-Za-z][A-Za-z0-9_.]*)",
          captures: {
            1: { name: "keyword.control.wdl" },
            3: { name: "entity.name.function.wdl" },
          },
        },
      ],
    },
    types: {
      match:
        "\\b(Array|Boolean|Directory|File|Float|Int|Map|None|Object|Pair|String)\\b",
      name: "storage.type.wdl",
    },
    keywords: {
      match:
        "\\b(after|alias|as|call|command|else|env|hints|if|import|in|input|meta|object|output|parameter_meta|requirements|runtime|scatter|then)\\b",
      name: "keyword.control.wdl",
    },
    constants: {
      match: "\\b(true|false|null)\\b",
      name: "constant.language.wdl",
    },
    numbers: {
      match: "(?<![A-Za-z0-9_])-?\\b(?:0[xX][0-9a-fA-F]+|[0-9]+(?:\\.[0-9]+)?(?:[eE][+-]?[0-9]+)?)\\b",
      name: "constant.numeric.wdl",
    },
    operators: {
      match: "(?:==|!=|<=|>=|&&|\\|\\||[+*/%<>=!?-])",
      name: "keyword.operator.wdl",
    },
  },
}
