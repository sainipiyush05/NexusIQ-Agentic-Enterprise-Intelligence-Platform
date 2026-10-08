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
    server = sub.add_parser("serve")
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
    else:
        from .server import serve
        serve(args.host, args.port)
