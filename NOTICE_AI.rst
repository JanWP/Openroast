AI Co-Authorship Notice
=======================

This fork includes substantial AI-assisted and AI-authored code changes.

Project history context
-----------------------

- Since this fork was created, most code changes (with very few exceptions)
  were produced with GitHub Copilot assistance.
- The primary model family used was GPT-5.3-Codex.
- Human maintainers performed minimal code review. They tested changes with respect to their impact on the functions of
  the app, and integrated changes before keeping them in the repository.

What this means for contributors
--------------------------------

- Treat this repository as human-maintained, AI-assisted software.
- Continue normal code review, testing, and hardware validation practices.
- Keep commit history and documentation transparent about significant
  AI-assisted development where useful.

Commit message disclosure policy
--------------------------------

This repository uses the following commit trailer scheme to disclose the level
of AI tooling involvement:

- ``Assisted-by: TOOL (OPTIONAL: MODEL)`` for commits where AI tooling was
  involved in decision-making and/or generated only part of the code.
- ``Generated-by: TOOL (OPTIONAL: MODEL)`` for commits where almost all code
  was generated through AI tooling.

The ``Co-authored-by`` trailer is reserved for human collaborators and is not
used for AI disclosure.

History note
------------

Commits in this fork after
``f0254c650dee1be2d628230c1700b43eb79fed2d`` are marked using this policy.

