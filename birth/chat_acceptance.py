"""Controlled external acceptance; no network unless --allow-network is explicit."""
import argparse
import sys

from . import pipeline
from .windows_chat import BACKEND_MESSAGES, BackendUnavailable, ChatSession


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--memory-path", required=True)
    parser.add_argument("--send")
    parser.add_argument("--allow-network", action="store_true")
    parser.add_argument("--expect-prior-fact")
    args = parser.parse_args(argv)
    if args.send and not args.allow_network:
        parser.error("--send requires --allow-network")
    try:
        session = ChatSession(memory_path=args.memory_path)
        prior = pipeline.active_store().snapshot().prior_session
        facts = prior.facts if prior else []
        print(f"PRIOR_LOADED={bool(facts)}", flush=True)
        if args.expect_prior_fact is not None:
            found = any(args.expect_prior_fact in fact for fact in facts)
            print(f"PRIOR_FACT_MATCH={found}", flush=True)
            if not found:
                return 2
        if args.send:
            def display(result):
                print(result.utterance, flush=True)
            session.send(args.send, display)
            session.close()
            print("DELIVERED_AND_SAVED=True", flush=True)
        return 0
    except BackendUnavailable as exc:
        print(BACKEND_MESSAGES[exc.code], file=sys.stderr, flush=True)
        return 3
    except Exception:
        print("Acceptance failed; output or save was not confirmed.", file=sys.stderr, flush=True)
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
