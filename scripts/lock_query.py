"""Read .claude/skills.lock.json and emit tab-separated rows for the shell scripts.

Kept in Python because the lockfile is JSON and jq is not a dependency of this
repository. Every query fails loudly rather than emitting a partial list: a
silently short list would make the drift check pass while missing a skill.
"""

import json
import sys
from collections import OrderedDict
from pathlib import Path


def load(path: str) -> OrderedDict:
    with Path(path).open(encoding="utf-8") as handle:
        return json.load(handle, object_pairs_hook=OrderedDict)


def sha_for(lock: OrderedDict, repo: str) -> str:
    sha = lock["sources"].get(repo)
    if not sha:
        sys.exit(f"erro: repo {repo} referenciado em skills mas ausente de sources")
    return sha


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit("uso: lock_query.py <lockfile> <skills|sources|repo-paths|own>")
    lock_path, query = sys.argv[1], sys.argv[2]
    lock = load(lock_path)
    out = []

    if query == "skills":
        for skill in lock["skills"]:
            out.append(
                "\t".join(
                    [skill["name"], skill["repo"], skill["path"], sha_for(lock, skill["repo"])]
                )
            )
    elif query == "sources":
        for repo, sha in lock["sources"].items():
            out.append(f"{repo}\t{sha}")
    elif query == "repo-paths":
        paths: OrderedDict = OrderedDict()
        for skill in lock["skills"]:
            paths.setdefault(skill["repo"], []).append(skill["path"])
        for repo, repo_paths in paths.items():
            out.append("\t".join([repo, sha_for(lock, repo), " ".join(repo_paths)]))
    elif query == "own":
        out.extend(lock.get("own", []))
    else:
        sys.exit(f"erro: query desconhecida: {query}")

    # Escreve bytes com LF explicito: no Windows o stdout de texto do Python
    # traduz LF para CRLF, e o CR acabaria dentro do ultimo campo lido pelo
    # shell — o SHA sairia como "abc123\r" e o rodape de vendorizacao viria
    # errado, silenciosamente.
    payload = "\n".join(out) + ("\n" if out else "")
    sys.stdout.buffer.write(payload.encode("utf-8"))


if __name__ == "__main__":
    main()
