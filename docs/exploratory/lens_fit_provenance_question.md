# Draft publisher question — not sent

Subject: Fit revision records for the released Qwen3-4B J++ lens

We are evaluating the J++ lens in `neuronpedia/jacobian-lens` at release commit
`e166deb5ad540932100ef803c8c9bcc2a5453694`, file
`qwen3-4b/jpp/Salesforce-wikitext/Qwen3-4B_jpp_lens.pt`.
Our complete-file SHA-256 matches
`893f7da243ab60d0628548a8c2b3afebaa45afdb1877d1c11521fde53209722d`.

We inspected the authoritative embedded `provenance`, including `source_config`,
using CPU `torch.load(weights_only=True)`. It names `Qwen/Qwen3-4B`, method `jpp`,
`lrp_mode=rlens`, 96 prompts, source layers 0–34, block-output capture and relative
transport target −1, but does not name model or tokenizer fit revisions.

Could you share the immutable Hugging Face model and tokenizer commits actually
used for this fit (including tokenizer repository), together with the fitting code
commit, invocation/configuration and dependency record? If the original cache
snapshot IDs or resolved file hashes survive, those would also establish identity.
We need historical records, rather than a current main revision. Our intended
study model and tokenizer pin is `1cfa9a7208912126459214e8b04321603b3df60c`.

For reproducibility, could you also identify the exact WikiText configuration,
split/revision, prompt selection/order/seed and formatting (special tokens,
chat/thinking mode), and confirm the block-output/final-normalization convention
and conversion commit? The embedded source string says `koayon/jpp_lens`, while
the adjacent YAML says `safety-research/jpp_lens`; which fitting code commit do
these refer to? The YAML reports absolute target 35 and FP16 conversion; we would
retain the original fit dtype and conversion/error record separately.

If these records are unavailable, an explicit unknown is useful. We can continue
original-model baseline parity and controlled residual-patching preparation
without claiming this lens was fitted to the study revision.

This is an unsent draft. No publisher contact or GitHub comment was made.
