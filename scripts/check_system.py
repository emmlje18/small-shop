"""Checks system.yaml against the repository, beyond what the JSON schema can.

- every service folder, OpenAPI file and migrations folder exists;
- every service is a service in docker-compose.yml;
- every endpoint a service calls exists in the called service's OpenAPI file;
- the UI only calls services that exist.

Usage: python scripts/check_system.py   (exits 1 and lists problems if any)
"""

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


def main():
    system = yaml.safe_load((ROOT / "system.yaml").read_text())
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
    services = system["services"]
    problems = []

    for name, service in services.items():
        for key in ("path", "openapi", "migrations"):
            if not (ROOT / service[key]).exists():
                problems.append(f"{name}: {key} {service[key]} does not exist")
        if name not in compose["services"]:
            problems.append(f"{name}: not a service in docker-compose.yml")

        for call in service.get("calls", []):
            target = services.get(call["service"])
            if target is None:
                problems.append(f"{name}: calls unknown service {call['service']}")
                continue
            paths = yaml.safe_load((ROOT / target["openapi"]).read_text())["paths"]
            for endpoint in call["endpoints"]:
                method, path = endpoint.split(" ", 1)
                if method.lower() not in paths.get(path, {}):
                    problems.append(f"{name}: {endpoint} is not in {target['openapi']}")

    for called in system["ui"]["calls"]:
        if called not in services:
            problems.append(f"ui: calls unknown service {called}")

    for problem in problems:
        print(f"system.yaml: {problem}")
    if problems:
        sys.exit(1)
    print("system.yaml matches the repository")


if __name__ == "__main__":
    main()
