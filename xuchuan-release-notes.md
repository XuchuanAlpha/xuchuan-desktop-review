# v35.4.1b review candidate — 2026-11-23

Review status
Developer self-review | 砚舟 (GPT-6.2 Sol Medium) | 2026-11-23T08:14:06+00:00 | xuchuan_desktop.pyw SHA-256 e777e86f

Baseline: v35.4.1a candidate, source SHA-256
`769f73d711f44e90d2aab34cb799f7898ac00a247b3090e8b2d234f59d5e8bf8`.

| Item | Proposer | Approver | Executor |
|---|---|---|---|
| A34 outbound evidence | 小序 (DeepSeek V4.1-Flash-1017, reasoning low), formalized by 砚舟 and supplemented by 十一七 (Claude Sonnet 5.5 Medium) | 精华 | 砚舟 (GPT-6.2 Sol Medium) |
| A35 persistent verification counts and retention view | 小序 (DeepSeek V4.1-Flash-1017, reasoning low); 90-day visibility proposed by 砚舟 following 十一七's retention recommendation | 精华 | 砚舟 (GPT-6.2 Sol Medium) |
| A36 checkpoint export and verification | 小序 (DeepSeek V4.1-Flash-1017, reasoning low); checkpoint design by 十一七 (Claude Sonnet 5.5 Medium), prefix verification by 砚舟 | 精华 | 砚舟 (GPT-6.2 Sol Medium) |
| v35.4.1b identifier compatibility | 砚舟 (GPT-6.2 Sol Medium), necessary to use the approved version | 精华 (approved version and work order) | 砚舟 (GPT-6.2 Sol Medium) |

- A34. Each desktop chat, direct search, attachment upload and later attempt receives a distinct request ID. An immediate SQLite transaction commits the pending event and the exact outgoing body digest before transport starts. A cancelled preview has a local cancelled result and starts no transport. Replies, timeouts and failures link to the same ID. An incomplete attempt after restart displays “已发起，结果未知，内容可能已发出” (“attempt initiated, result unknown; contents may have been sent”). There is no recovery resend. Existing outbound confirmations remain. Ordinary chat displays “无单独审批记录” (“no separate approval record”) when there is no A11 record. Search and upload confirmations are linked, and A11 references are recorded where the request relies on a covered same-turn file decision.
- B1. Storing the complete body would let a reviewer inspect what went out and recalculate its digest without a matching copy. It would also duplicate private context, tool results and attachments into the database and backups. This release stores hashes and limited metadata in the new journal. Existing conversation and public-search records retain their prior behavior.
- A35. The count is backed by admitted verification events, including malformed attempts within the cap. The ninth and each subsequent call in a turn has a refusal event. The 90-day boundary is a read-only display filter. All audit entries and refusal/count evidence remain in SQLite. Migration is additive and takes a verified backup before adding the journal to an existing database.
- A36. Journal rows are chained with SHA-256. A one-line UTF-8 checkpoint records version, count, chain head and UTC time. Release verification and on-demand export are explicit local actions. The user retains the file and may give it to witnesses. Storage edits, removals and order changes are identified by recomputing the chain. An older checkpoint validates the matching prefix after ordinary appends. A checkpoint retained independently detects rollback before its position or replacement of its covered history. A consistently rewritten, unwitnessed suffix cannot be authenticated by an older checkpoint. The chain covers the new outbound and verification journal. Existing audit tables remain as historical records and A11 links refer back to them.
- The version identifier recognizes both the previous `a` suffix and the new `b` suffix. The format card, examples and external submission guidance retain their approved contents.
- The v35.4.1a implementation report is evidence for roadmap maintenance. The roadmap and the release hash sheet were not revised. The work order, prior original submission summary and the user's explicit follow-up decisions were applied. The full verbatim v35.4.1a-1 source was unavailable for a line-by-line comparison.

Linux offline results and Shield evidence are bundled. Windows GUI, live API and independent review remain pending. The guidance module was not sent to a live API.
