# Accepted ZLB reader candidate

The user accepted the revised text on November 22, 2026:

> I agree that the text is sensible and better. Git commit and push.

This records acceptance of the text and authorization to publish these files to
the project's Git repository. It does not establish generalization or independent
reproduction, which remain in the [master program](../../docs/plans/ENSEMBLE_MASTER_PROGRAM_2026-09-30.md).

- [Revised manuscript](revision.pdf): 66 pages.
- [Blacklined comparison](comparison.pdf): 71 pages; red is deleted text and
  blue is added text. Unchanged prose is black; ordinary hyperlink colors are
  not change markers.
- [Revised LaTeX](revision/zlb_source.tex) and [original LaTeX](original/zlb_source.tex).
- [Source erratum](SOURCE_ERRATUM.md): the source confuses momentum along
  \(n\) with velocity along \(M^{-1}n\). This remains a separate scientific
  issue; the accepted preservation candidate has not been changed to apply it.

These files are byte-for-byte copies from native candidate
`20261117T235022.984126Z-8dc3251b`, completed November 18, 2026. All 21 units,
5,042 canonical concept mappings, 20 relationship reviews and 14 release gates
passed. The [delivery manifest](manifest.json) binds the copied files and the
original packet manifest. The [verification record](verification-2026-11-18.json)
is the unchanged November 18 check; its pending-acceptance fields describe that
earlier date. The user statement above is the subsequent acceptance record.

The full 27,214-file audit packet, including original receipts and retained
negative judgments, remains under the workspace path recorded in the manifest.
This Git directory contains the reader deliverables and verification summary;
it is not the full runtime archive or a portable pipeline installation.

From the repository root, open the blackline with:

```bash
xdg-open releases/zlb-2026-11-18/comparison.pdf
```
