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
    sub.add_parser("cache-citation-model")
    sub.add_parser("citation-eval")
    sub.add_parser("churn-seed")
    sub.add_parser("churn-snapshots")
    sub.add_parser("churn-eval")
    sub.add_parser("churn-advanced")
    sql_query = sub.add_parser("sql-query", help="Run a bounded read-only business SELECT")
    sql_query.add_argument("--sql", required=True)
    sql_query.add_argument("--max-rows", type=int, default=50)
    fx_rate = sub.add_parser('fx-rate', help='Fetch one validated public exchange rate')
    fx_rate.add_argument('--base', required=True, choices=['USD', 'EUR', 'GBP', 'INR'])
    fx_rate.add_argument('--quote', required=True, choices=['USD', 'EUR', 'GBP', 'INR'])
    fx_rate.add_argument('--date', help='Optional historical date YYYY-MM-DD')
    sub.add_parser('chart-customers', help='Create the validated customer-region SVG chart')
    olist_download = sub.add_parser('olist-download', help='Download public Olist CSVs with KaggleHub')
    olist_download.add_argument('--handle', default='olistbr/brazilian-ecommerce', help='Dataset handle, optionally with /versions/N')
    olist_download.add_argument('--force', action='store_true')
    olist_import = sub.add_parser('olist-import', help='Import downloaded Olist CSVs into isolated PostgreSQL tables')
    olist_import.add_argument('--source-dir', help='Directory returned by kagglehub.dataset_download')
    olist_import.add_argument('--handle', default='olistbr/brazilian-ecommerce')
    sub.add_parser('olist-status', help='Report actual Olist table and review-text counts')
    sub.add_parser('olist-eval', help='Run full evaluation benchmark on Olist large dataset')
    olist_search = sub.add_parser('olist-search-reviews', help='Search imported Olist review text')
    olist_search.add_argument('--query', required=True)
    olist_search.add_argument('--limit', type=int, default=5)
    workflow_query = sub.add_parser('workflow-query', help='Run the bounded local RAG/SQL/ML workflow')
    workflow_query.add_argument('--question', required=True)
    sub.add_parser('workflow-eval', help='Run fixed development workflow scenarios')
    sub.add_parser("generation-probes")
    generation_eval = sub.add_parser("generation-eval")
    generation_eval.add_argument("--all-dev", action="store_true", help="Score all development cases; never scores holdout")
    generation_eval.add_argument("--provider", choices=['local_transformers','ranked_extracts'], default='local_transformers')
    generation_challenges = sub.add_parser("generation-challenges")
    generation_challenges.add_argument("--provider", choices=['local_transformers','ranked_extracts'], default='local_transformers')
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
    server.add_argument("--generation", choices=["extractive", "ollama", "local_transformers", "ranked_extracts"], default="extractive")
    server.add_argument("--host", default="127.0.0.1")
    server.add_argument("--port", type=int, default=8000)
    server.add_argument("--api", action="store_true", help="Launch typed FastAPI gateway with JWT auth")
    server.add_argument("--require-auth", action="store_true", help="Disallow anonymous fallback in API mode")
    token_cmd = sub.add_parser("issue-token", help="Issue signed JWT caller token")
    token_cmd.add_argument("--user-id", default="demo-analyst")
    token_cmd.add_argument("--tenant-id", default="atlascloud")
    token_cmd.add_argument("--role", default="analyst", choices=["admin", "analyst", "viewer"])
    token_cmd.add_argument("--expires", type=int, default=3600)
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
    elif args.command == "cache-citation-model":
        from .citationverify import cache_model
        print(cache_model())
    elif args.command == "citation-eval":
        from .citationverify import evaluate_dev
        report = evaluate_dev()
        REPORTS.mkdir(exist_ok=True)
        (REPORTS/'citation_verification_dev.json').write_text(json.dumps(report, indent=2))
        print(json.dumps(report['summary'], indent=2))
    elif args.command == "churn-seed":
        from .churn import seed_churn
        print(json.dumps(seed_churn(), indent=2))
    elif args.command == "churn-snapshots":
        from .churn import export_snapshots
        print(json.dumps(export_snapshots(), indent=2))
    elif args.command == "churn-eval":
        from .churn import evaluate_baseline, write_report
        report = evaluate_baseline()
        write_report(report)
        print(json.dumps(report['split_metrics'], indent=2))
    elif args.command == "churn-advanced":
        from .churnadvanced import compare_models, write_report
        report = compare_models()
        write_report(report)
        print(json.dumps(dict(selected_model=report['selected_model'],
                              validation_candidates=report['validation_candidates'],
                              calibration=report['calibration'],
                              test_decision=report['test_decision'], mlflow=report['mlflow']), indent=2))
    elif args.command == "sql-query":
        from .sqltool import ReadOnlySQLTool
        print(json.dumps(ReadOnlySQLTool().run(args.sql, max_rows=args.max_rows), indent=2))
    elif args.command == 'fx-rate':
        from .external import ExchangeRateTool
        print(json.dumps(ExchangeRateTool().rate(args.base, args.quote, args.date), indent=2))
    elif args.command == 'chart-customers':
        from .charts import export_customer_regions
        print(json.dumps(export_customer_regions(), indent=2))
    elif args.command == 'olist-download':
        from .olist import download, inspect_source
        path = download(handle=args.handle, force=args.force)
        print(json.dumps({'path': str(path), **inspect_source(path, args.handle)}, indent=2))
    elif args.command == 'olist-import':
        from pathlib import Path
        from .olist import RAW, import_source
        print(json.dumps(import_source(Path(args.source_dir) if args.source_dir else RAW, args.handle), indent=2))
    elif args.command == 'olist-status':
        from .olist import status
        print(json.dumps(status(), indent=2))
    elif args.command == 'olist-eval':
        from .olist_eval import run_benchmark
        report = run_benchmark()
        print(json.dumps({
            "scale": report["scale"],
            "retrieval_benchmark": report["retrieval_benchmark"],
            "sql_analytics_benchmark": report["sql_analytics_benchmark"],
        }, indent=2))
    elif args.command == 'olist-search-reviews':
        from .olist import search_reviews
        print(json.dumps(search_reviews(args.query, args.limit), indent=2))
    elif args.command == 'workflow-query':
        from .workflow import build_default_workflow
        print(json.dumps(build_default_workflow().run(args.question), indent=2))
    elif args.command == 'workflow-eval':
        from .workfloweval import evaluate as evaluate_workflow
        report = evaluate_workflow()
        REPORTS.mkdir(exist_ok=True)
        (REPORTS/'workflow_dev.json').write_text(json.dumps(report, indent=2))
        print(json.dumps(report['summary'], indent=2))
    elif args.command == "generation-probes":
        from .generationeval import run_probes
        report=run_probes()
        REPORTS.mkdir(exist_ok=True)
        (REPORTS/"generation_probes_dev.json").write_text(json.dumps(report,indent=2))
        print(json.dumps(report,indent=2))
    elif args.command == "generation-eval":
        from .generationeval import run_evaluation
        from .benchmark import load_cases
        from .generation import load_provider
        case_ids = tuple(c['id'] for c in load_cases('dev')) if args.all_dev else None
        provider, config = load_provider(args.provider)
        stem = 'generation' if args.provider == 'local_transformers' else 'generation_ranked'
        checkpoint = REPORTS/f'{stem}_full_dev.checkpoint.json' if args.all_dev else None
        report = run_evaluation(case_ids, provider=provider, config=config, checkpoint_path=checkpoint) if case_ids else run_evaluation(provider=provider, config=config)
        REPORTS.mkdir(exist_ok=True)
        filename = f'{stem}_full_dev.json' if args.all_dev else f'{stem}_sample_dev.json'
        (REPORTS/filename).write_text(json.dumps(report, indent=2))
        if checkpoint is not None:
            checkpoint.unlink(missing_ok=True)
        print(json.dumps(dict(overall=report['overall'], by_category=report['by_category'],
                              limitations=report['limitations']), indent=2))
    elif args.command == "generation-challenges":
        from .generationchallenges import run_challenges
        from .generation import load_provider
        provider, config = load_provider(args.provider)
        report = run_challenges(provider=provider, config=config)
        REPORTS.mkdir(exist_ok=True)
        stem = 'generation' if args.provider == 'local_transformers' else 'generation_ranked'
        (REPORTS/f'{stem}_challenges_dev.json').write_text(json.dumps(report, indent=2))
        print(json.dumps(dict(overall=report['overall'], limitations=report['limitations']), indent=2))
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
    elif args.command == 'issue-token':
        from .auth import issue_token
        token = issue_token(args.user_id, args.tenant_id, args.role, expires_in_seconds=args.expires)
        print(json.dumps(dict(access_token=token, token_type="bearer", expires_in=args.expires,
                              user_id=args.user_id, tenant_id=args.tenant_id, role=args.role), indent=2))
    else:
        from .server import serve
        serve(args.host, args.port, args.retriever, args.generation, api=getattr(args, 'api', False),
              allow_anonymous=not getattr(args, 'require_auth', False))
