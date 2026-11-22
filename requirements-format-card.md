# Requirements-list format

The first line starts with the exact requirements ID provided by the program.
For every open item use four consecutive lines. Blank lines between items are optional.

```text
## A7 [P1]
现象与证据：Describe what happened and cite the evidence.
预期行为：Describe the expected result.
验收测试：Describe how the user can verify it.
```

Use one line per field and a unique item ID. Move separate rationale to an appendix.
The requirements body defaults to 8,192 UTF-8 bytes. The appendix body defaults
to 12,288 UTF-8 bytes. The user may configure both limits. The identifier line is
included in the byte count. A requirements list or appendix must be the only
submission block in its reply. Ordinary prose may precede the block.
The first line of an appendix must
be the approved list identifier, a single space, and Appendix, for example
v35.3-1 Appendix. The approved archive is read-only in the application.
