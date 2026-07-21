# Source And Adaptation

This native Bioinfoflow skill suite is adapted from OpenAI's curated
`ngs-analysis` package version 1.0.3, which declares the MIT license.

Bioinfoflow adaptations:

- expose every skill directly under the Bioinfoflow skills root;
- place shared scripts, workflows, references, and assets under
  `ngs-runtime-env`;
- replace Codex plugin-relative command paths with
  `$BIOINFOFLOW_SKILLS_ROOT/ngs-runtime-env`;
- record skill-bundle metadata instead of Codex plugin metadata; and
- document that local helper files are not synchronized to SSH targets.

The analysis behavior, validation rules, runners, and workflow resources are
otherwise preserved from the reviewed upstream package.
