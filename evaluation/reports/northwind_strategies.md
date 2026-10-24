# Northwind sample — retrieval strategy comparison

Measured 2026-10-24T13:33:36+00:00 through the Retrieva API on the fictional Northwind corpus (`evaluation/datasets/sample_corpus`, 3 documents) with Northwind Q&A v3 (18 questions).
Embeddings `BAAI/bge-small-en-v1.5`; reranker `cross-encoder/ms-marco-MiniLM-L-6-v2`.

| Configuration | precision@1 | recall@5 | mrr | ndcg@10 | context_precision | retrieval_ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| BM25 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 934 ms |
| Dense | 0.944 | 0.944 | 0.944 | 0.944 | 0.944 | 568 ms |
| Hybrid (RRF) | 0.944 | 1.000 | 0.972 | 0.980 | 0.972 | 977 ms |
| Hybrid + rerank | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 2540 ms |

Latency is the mean end-to-end retrieval time per question measured by the API on a laptop CPU, with the four configurations running concurrently, so it includes database access and CPU contention; compare it across rows, not as an isolated per-query figure.

This corpus is deliberately small (a few dozen chunks), so differences between strategies are
smaller and noisier than on a realistic collection; see `beir_scifact.md` for a larger benchmark.
