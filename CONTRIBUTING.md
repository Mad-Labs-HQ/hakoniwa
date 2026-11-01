# Working on the Mad Labs fork

## Branches

`origin` points to `Mad-Labs-HQ/hakoniwa`. `upstream` points to
`souk4711/hakoniwa`.

- `main`: the Mad Labs downstream integration branch
- `upstream/main`: the original project's main branch, updated by fetching upstream
- Feature branches: changes based on our main, reviewed and tested before merging
- Upstream PR branches: focused contributions based on upstream/main
- `codex/prepare-fork`: preserved baseline and repair history, outside this transition

Do not reset our main to upstream or rebase its published history. Bring selected
upstream updates in through a review branch and test the combined result. Select
a qualified commit or release for consumers; do not follow a moving branch head.

This initial downstream main adds CI to the upstream implementation. It does not
yet contain the product repairs preserved in the integration history. Those
require separate review and qualification before promotion.

## CI on branch pushes

Branches based on our main inherit automatic CI on every branch push. PRs targeting
our main also run CI. These can produce separate push and PR runs. There are no
path filters, so workflow and documentation changes receive CI too.

The workflow checks dependency policy, feature combinations, formatting and
Clippy. It tests the library and its documentation on native Linux x86-64 and
ARM64. CLI tests and documentation run on x86-64. CLI execution on ARM64 is not
qualified by this workflow. Tests run on hosted VMs, without architecture
emulation or a dependency on a developer's shell environment.

The library's Landlock tests use strict enforcement and check both denied
operations and success after access is granted. They run as part of the
all-features suite on both architectures. There is no separate kernel probe.
Results apply to the tests present in the selected source revision and the
hosted kernel used for that run.

Release and Dependabot merge automation remain disabled on this fork. A passing
CI run does not publish a crate or release and does not qualify the Mad Stack
integration chain.

## Manual CI for any branch or commit

Open [Actions](https://github.com/Mad-Labs-HQ/hakoniwa/actions/workflows/ci.yml),
select **Run workflow**, and use `main` as the workflow branch. Enter a branch
name or commit in **source_ref**. Leave it blank to test the selected workflow
revision. Write access to the fork is required.

For example, test a clean upstream PR branch without adding our CI files to it:

```sh
gh workflow run ci.yml --repo Mad-Labs-HQ/hakoniwa \
  --ref main -f source_ref=fix/pin-workload-ownership
```

The workflow resolves the source once. All jobs check out that same commit. The
**Resolve source** job records the tested SHA in its summary. GitHub associates
the run with the workflow revision, so its head SHA can differ from the tested
source SHA. Cite the tested SHA when reporting results.

For a branch that already contains our workflow, this also works:

```sh
gh workflow run ci.yml --repo Mad-Labs-HQ/hakoniwa --ref YOUR_BRANCH
```

A clean upstream branch may lack manual dispatch or branch push triggers. Use
the first form for those branches. It needs no qualification branch. Invalid
source refs fail before the checks begin.

Manual dispatch selects source code; it does not port downstream changes or
adapt package layouts. This workflow expects the upstream `hakoniwa` and
`hakoniwa-cli` workspace. A branch with a different workspace, such as the
preserved integration fork, requires a suitable workflow before it can be
qualified.

Run jobs with read-only repository permissions and no publishing credentials.
Test logs are retained as artifacts for seven days. Preserve any evidence needed
for an upstream contribution before it expires.

## Upstream contributions

Prepare focused PR branches from `upstream/main`. Keep downstream packaging and
CI changes out of those PRs. Verify that each extracted repair matches the
implementation tested in our supported fork.

Upstream controls its own required checks and fork-workflow approvals. A run on
our fork provides additional evidence; it does not satisfy upstream's required
checks. Retire completed branches after preserving useful evidence. Keep
internal reports under the locally ignored `docs/local/` directory.
