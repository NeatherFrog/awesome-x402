# Primary-source retrieval receipts

The repository's authorized [GitHub Actions run36996838955](https://github.com/NeatherFrog/awesome-x402/actions/runs/36996838955) completed successfully. This means receipt acquisition completed, not that every requested paper or contract specification was available.

Producer commit: `950e5ca3b66d79013d37ed9ff09ecb08eaa9eb58`. Pinned `scripts/fetch_pattern_sources.py` SHA-256: `33cde8f3fd90b69ddbcf8ef7f03aeb2dfcdec06abec486b824e0b39b1dc68a9e`, matching the checked-out source at retrieval.

Public metadata-only artifact: [receipts.json at immutable commit4e279275e9a07c6362fe9f49b4034029f224fb72](https://github.com/NeatherFrog/awesome-x402/blob/4e279275e9a07c6362fe9f49b4034029f224fb72/receipts.json). Local restored receipt: `.local/pattern-source-receipts.json`, 9,636 bytes; SHA-256 `d1f4d74ea96fff264594c248b27020e1defad86fb927176423ba1baa49648b60`. Its Git blob hash matches the published immutable commit tree. The artifact's `producer_commit` matches the workflow source commit. No authentication tokens or raw headers were read or published.

| Requested primary source | Actual retrieval | Verified limit |
| --- | --- | --- |
| NBER working-paper URL w7032 | HTTP200, PDF,35pages; exact PDF SHA in receipt | Full PDF/extracted body is not available to the local reviewer. No verified title metadata; brief pairs-trading excerpts support topical relevance without proving profitability or completing a full paper review. |
| Concretum ORB author page | HTTP200; final URL unchanged; title “A Profitable Day Trading Strategy For The U.S. Equity Market” | Author overview, not the original paper or exact executable strategy replication. |
| Concretum noise/momentum author page | HTTP200; final URL unchanged; title “Beat the Market: An Effective Intraday Momentum Strategy for S&P500 ETF (SPY)” | Author overview, not independently reproduced reported returns. |
| Three SSRN pages | HTTP403 | No source body, verified final title or claimed full review. |
| Toronto author-pairs PDF | HTTP403 | No paper body acquired. |
| CME MES and MNQ contract-specification pages | HTTP403 even on GitHub worker | No verified final URL/title/body. Standard tick/multiplier conventions remain unverified by this attempted current official-source retrieval. |
| Stale SNB “FX” URL | HTTP200 redirected to an unrelated labor-relations working paper | Final title is “The Business Cycle Implications of Reciprocity in Labor Relations”; rejected as an FX/trading strategy source. HTTP success alone does not establish intended paper identity. |

The retrieval job published only receipts and at most80 excerpt words in total per source. Full copyrighted PDFs and extracted text remained ephemeral on the worker. A successful retrieval receipt is not a complete local reading, verified current broker contract, strategy backtest, stable-profit result or prop payout proof. Source identity must be checked before a paper is counted as evidence; a historical paper's returns must not be transferred to new instruments, hourly adaptations or different costs.
