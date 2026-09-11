
## Desktop task integration (2026-09-11)

- Task sync paging requires both `updated_since` and `updated_since_id`; stable sorting alone does not prevent skipping equal timestamps. Keep business/tech docs, plan and generated knowledge consistent.
- External executor ownership is documented with input tasks; it affects realtime marker events, session creation and status repair candidate eligibility. Separate server E2 readiness from the desktop repository's socket client.
- `make check-docs` does not check ignored drafts; use `check_docs_references.py --files` for edited drafts as well. Historical deleted paths should be described without live path citations. Run `make sync-platform-knowledge` after contract/docs changes.
