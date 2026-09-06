# Humanvoice implementation schemas

`implementation_contract.json` is the machine-readable companion to the
normative implementation annex in the single proposal. Those two contract
artifacts govern behavior. The `*.schema.json` files define the records
exchanged by the first command surface; a permissive or incomplete schema does
not amend the contract.

Every record carries `schema_version`. Unknown top-level fields are rejected.
Within a major version, additions live under `extensions`, whose contents must
be preserved by readers. A major version change requires a migration and replay
of the locked fixtures before a run can be released. The contract file itself
is versioned by `contract_id` and `contract_version`.

`examples/manifest.json` identifies positive and negative instances. The
contract checker validates every positive instance and confirms that every
negative instance fails for the intended reason. The reference validator for
WP0 is pinned in `requirements-dev.txt` as Python `jsonschema` 4.26.0 using
Draft 2020-12.

The schemas describe the interface; they do not establish that a document is
clear or persuasive. Human reader acceptance remains a separate outcome.
