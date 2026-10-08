import argparse
import json
from .config import DATA, REPORTS
from .data import seed_data
from .evaluation import evaluate

def main():
    parser = argparse.ArgumentParser(description="NexusIQ local milestone")
    sub = parser.add_subparsers(dest="command", required=True)
    seed = sub.add_parser("seed")
    seed.add_argument("--seed", type=int, default=42)
    sub.add_parser("evaluate")
    benchmark = sub.add_parser("benchmark")
    benchmark.add_argument("--split", choices=["dev", "holdout"], default="dev")
    benchmark.add_argument("--top-k", type=int, default=5)
    benchmark.add_argument("--allow-holdout", action="store_true", help="Explicitly record a held-out evaluation; do not tune from its results")
    sub.add_parser("validate-evals")
    sub.add_parser("retrieval-experiments")
    sub.add_parser("cache-generation-model")
    sub.add_parser("generation-probes")
    build = sub.add_parser("build-dense")
    build.add_argument("--scope", choices=["demo", "benchmark"], default="demo")
    build.add_argument("--rebuild", action="store_true")
    hybrid = sub.add_parser("compare-hybrid")
    hybrid.add_argument("--split", choices=["dev", "holdout"], default="dev")
    hybrid.add_argument("--top-k", type=int, default=5)
    hybrid.add_argument("--allow-holdout", action="store_true")
    compare = sub.add_parser("compare-retrieval")
    compare.add_argument("--split", choices=["dev", "holdout"], default="dev")
    compare.add_argument("--top-k", type=int, default=5)
    compare.add_argument("--allow-holdout", action="store_true")
    for command in ('db-start','db-stop','db-use-local','db-migrate','db-seed','db-verify'):
        sub.add_parser(command)
    dbimport=sub.add_parser('db-import')
    dbimport.add_argument('--scope',choices=['demo','benchmark'],default='demo')
    server = sub.add_parser("serve")
    server.add_argument("--retriever", choices=["lexical", "dense", "postgres", "hybrid", "fts", "reranked"], default="lexical")
    server.add_argument("--generation", choices=["extractive", "ollama", "local_transformers"], default="extractive")
    server.add_argument("--host", default="127.0.0.1")
    server.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    if args.command == "seed":
        print(json.dumps(seed_data(seed=args.seed)['counts'], indent=2))
    elif args.command == "evaluate":
        report = evaluate()
        REPORTS.mkdir(exist_ok=True)
        (REPORTS / "baseline.json").write_text(json.dumps(report, indent=2))
        print(json.dumps(report, indent=2))
    elif args.command == "cache-generation-model":
        from .localgeneration import cache_model
        print(cache_model())
    elif args.command == "generation-probes":
        from .generationeval import run_probes
        report=run_probes()
        REPORTS.mkdir(exist_ok=True)
        (REPORTS/"generation_probes_dev.json").write_text(json.dumps(report,indent=2))
        print(json.dumps(report,indent=2))
    elif args.command == "retrieval-experiments":
        from .experiments import run_experiments
        report = run_experiments()
        REPORTS.mkdir(exist_ok=True)
        (REPORTS/"retrieval_experiments_dev.json").write_text(json.dumps(report, indent=2))
        print(json.dumps([dict(max_words=v["max_words"],chunks=v["chunks"],results={n:r["overall"] for n,r in v["reports"].items()}) for v in report["variants"]], indent=2))
    elif args.command == "validate-evals":
        from .benchmark import load_benchmark_index, validate_benchmark
        print(json.dumps(validate_benchmark(load_benchmark_index()), indent=2))
    elif args.command == "benchmark":
        if args.split == "holdout" and not args.allow_holdout:
            parser.error("Holdout requires --allow-holdout. Tune only with dev cases.")
        from .benchmark import run_benchmark
        report = run_benchmark(args.split, args.top_k)
        REPORTS.mkdir(exist_ok=True)
        (REPORTS / f"benchmark_{args.split}.json").write_text(json.dumps(report, indent=2))
        print(json.dumps({key: value for key,value in report.items() if key != "cases"}, indent=2))
    elif args.command == "build-dense":
        from .semantic import get_dense_index
        index = get_dense_index(args.scope, args.rebuild)
        print(json.dumps(dict(scope=args.scope, chunks=len(index.chunks), embedding=index.embedder.metadata), indent=2))
    elif args.command == "compare-hybrid":
        if args.split == "holdout" and not args.allow_holdout:
            parser.error("Holdout requires --allow-holdout. Tune only with dev cases.")
        from .hybrid import compare_hybrid
        report = compare_hybrid(args.split, args.top_k)
        REPORTS.mkdir(exist_ok=True)
        (REPORTS/f"hybrid_comparison_{args.split}.json").write_text(json.dumps(report, indent=2))
        print(json.dumps({name: value["overall"] for name,value in report["reports"].items()}, indent=2))
    elif args.command == "compare-retrieval":
        if args.split == "holdout" and not args.allow_holdout:
            parser.error("Holdout requires --allow-holdout. Tune only with dev cases.")
        from .semantic import compare_retrieval
        report = compare_retrieval(args.split,args.top_k)
        REPORTS.mkdir(exist_ok=True)
        (REPORTS/f"retrieval_comparison_{args.split}.json").write_text(json.dumps(report,indent=2))
        summary = dict(split=report['split'],embedding=report['embedding'],lexical=report['lexical']['overall'],dense=report['dense']['overall'],delta_evidence_recall_at_k=report['delta_evidence_recall_at_k'],note=report['note'])
        print(json.dumps(summary,indent=2))
    elif args.command=='db-use-local':
        from .localdb import use_existing_local
        print(json.dumps(use_existing_local(),indent=2))
    elif args.command in ('db-start','db-stop'):
        from .localdb import start, stop
        print(json.dumps(start() if args.command=='db-start' else stop(),indent=2))
    elif args.command in ('db-migrate','db-seed'):
        from .postgres import migrate, seed_business
        print(json.dumps(migrate() if args.command=='db-migrate' else seed_business(),indent=2))
    elif args.command=='db-import':
        from .semantic import get_dense_index
        from .postgres import import_index
        print(json.dumps(import_index(get_dense_index(args.scope),args.scope),indent=2))
    elif args.command=='db-verify':
        from .dbverify import verify
        report=verify()
        REPORTS.mkdir(exist_ok=True)
        (REPORTS/'postgres_verification.json').write_text(json.dumps(report,indent=2))
        print(json.dumps(report,indent=2))
    else:
        from .server import serve
        serve(args.host, args.port, args.retriever, args.generation)
