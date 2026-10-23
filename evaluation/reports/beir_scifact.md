# BEIR/scifact retrieval benchmark

Run 2026-10-23T18:34:17+00:00 on Windows-11-10.0.26200-SP0 (CPU). 5183 documents, 300 test queries with official relevance judgments.

Embedding model `BAAI/bge-small-en-v1.5` · reranker `cross-encoder/ms-marco-MiniLM-L-6-v2` (top 30) · BM25 k1=1.2, b=0.75 · RRF k=60.

| Configuration | nDCG@10 | Recall@100 | MRR@10 | P@1 | Query latency (mean) |
| --- | ---: | ---: | ---: | ---: | ---: |
| BM25 | 0.6852 | 0.9176 | 0.6460 | 0.5333 | 0.9 ms |
| Dense | 0.7127 | 0.9417 | 0.6822 | 0.6067 | 62.1 ms |
| Hybrid (RRF k=60) | 0.7235 | 0.9717 | 0.6890 | 0.6000 | 63.0 ms |
| Hybrid + rerank (top 30) | 0.6995 | 0.9717 | 0.6668 | 0.5833 | 7048.2 ms (+ rerank) |

Latency is per query on CPU and excludes network and database overhead; hybrid latency is the sum of its BM25 and dense components. Indexing: BM25 9.53 s, embeddings 1865.9 s.

Reproduce: `cd backend && uv run python ../evaluation/benchmarks/beir_benchmark.py --dataset scifact`
