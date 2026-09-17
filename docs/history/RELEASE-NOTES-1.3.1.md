# Project Manager 1.3.1

This is the recommended public release of the complete
[1.3.0 feature set](RELEASE-NOTES-1.3.0.md).

The initial public CI run found that two existing Markdown renderers used
f-string syntax accepted only by Python 3.12 and newer. This patch restores
compatibility with the documented Python 3.10 minimum without changing rendered
content or record semantics. The GitHub matrix runs the complete behavior checks
on the actual Python 3.10, 3.12 and 3.13 runtimes; parsing on a newer interpreter
alone does not establish backward compatibility.

Use the complete 1.3.1 package when installing or updating. Existing projects
still require explicit migration assessment and reviewed tooling updates;
installation does not rewrite their records. The MIT license, noncertified
SPICE-inspired scope and previously documented limitations are unchanged.
