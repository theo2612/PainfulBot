# Engineering Principles

Universal principles for building solid codebases. Language- and domain-agnostic.

## Modularity: code lives in the thing it's about

Module-specific code lives in the module — and nowhere else. When adding a new variant to a system, it should be a single new file containing everything: type, implementation, registration, helpers, constants. No central dispatcher with a match arm to update. No hand-maintained registry list. No constants table to extend.

Prefer auto-discovery (build-time scanning, decorator-based registration, plugin loading) over manual lists. **Adding a new variant should touch exactly one file.**

**Type-owned dispatch.** When behavior varies by type, the dispatch lives behind a uniform interface that the type implements — consumers call the interface, never branch on which variant they got. If you find yourself writing the same `if` ladder across multiple call sites, the dispatch belongs in the type's interface, not at every call site.

## DRY, broadly interpreted

If two pieces of code aren't identical but follow a similar enough pattern that they could be generalized, they should be. This applies across modules, across architectural layers, and across systems.

**Place functionality where it generalizes.** Before writing logic, ask: "where does this belong so it works for all cases, not just this one?" Behavior that applies to any tool belongs in the tool system's generic hooks, not inside one specific tool. Behavior that applies to any async operation belongs in the async pipeline, not at one call site.

A good signal you've placed something wrong: it only works for one workflow, or a second caller would have to copy-paste the same pattern.

## Ownership: state belongs to what it describes

State belongs to the thing it describes — not to a parent that manages it on its behalf. Don't let language ergonomics dictate the data model. If splitting state out of a struct makes the implementation easier but scatters a logical concept across multiple locations, find a different way to satisfy the language constraint and keep the data model clean.

## Prior art over invention

Before deciding on an approach, research how established projects handle it. **Read the actual source** — never rely on web searches, docs, blog posts, or LLM training data for architectural claims. If a reference codebase isn't checked out, clone it. Never claim "Project X does Y" without pointing to a specific file and function.

When delegating research, instruct collaborators to cite specific files and line numbers — reject any claim not backed by source.

Don't blindly copy prior art; use it to inform decisions. The implementation will differ in specifics, but core algorithms and architectural decisions should be informed by what's been tried, not invented from scratch.

## Test every feature; regression-test every bug

**Every feature gets a test.** Verify it works. The test exists; it passes. That's it.

**Every bug gets a regression test — one that defends against that specific bug being reintroduced.** "Regression" means "the bug we just fixed must not come back"; a test for a new feature is not a regression test, even if it follows the same pattern.

Write the regression test **first**, confirm it **fails** against the unfixed code, **then** fix the bug and confirm it passes. If the test doesn't fail without the fix, it doesn't count — it's not actually defending against anything.

## No hacks. Bugs are signals.

Every system must be implemented properly. No hacks, no hardcoding, no shortcuts. If you're going to implement one of something, build a proper system for it. It's okay to step back from the current task to do things right.

**Every bug is a signal that something nearby is awkward or overcomplicated.** Before patching, ask: "is this an elegant solution?" If no, the bug is telling you the code wants to be restructured — propose a refactor instead of layering a fix on top. The cleanest fix is often the one that makes the bug **impossible to express**, not the one that handles it.

## Run every check before committing

Establish the full set of automated checks the project requires — formatting, linting, type-checking, tests, builds for every target — and run them all before committing. "It compiles on my machine" is not a substitute for the full matrix. If the checks are slow, make them faster; don't skip them.
