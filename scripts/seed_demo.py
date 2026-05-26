#!/usr/bin/env python3
"""Seed the Atuin history DB with realistic demo commands for Replay hackathon.

Adds ~250 commands covering Docker, Git, Python, Node, DB, K8s, and debugging
workflows with intentional fix-detection patterns (fail → succeed).

Run: python scripts/seed_demo.py
"""

import sqlite3
import uuid
import random
import time
from pathlib import Path

DB_PATH = Path.home() / ".local/share/atuin/history.db"

# Nanoseconds per second
NS = 1_000_000_000

def ns_now() -> int:
    """Current time in nanoseconds."""
    return int(time.time() * NS)

def rand_duration_ms(lo: int = 10, hi: int = 3000) -> int:
    """Random duration in nanoseconds (lo–hi milliseconds)."""
    return random.randint(lo * 1_000_000, hi * 1_000_000)

def rand_duration_s(lo: int = 1, hi: int = 30) -> int:
    """Random duration in nanoseconds (lo–hi seconds)."""
    return random.randint(lo * NS, hi * NS)

def session_id() -> str:
    return uuid.uuid4().hex

def make_id() -> str:
    return uuid.uuid4().hex

# ── Workflow definitions ──────────────────────────────────────────────

def docker_workflow(host: str) -> list[tuple]:
    """Docker build/debug session with fix patterns."""
    sid = session_id()
    base = ns_now() - 3 * 24 * 3600 * NS  # 3 days ago
    cwd = "/home/dev/projects/replay-api"
    t = 0
    cmds = []

    seq = [
        (0,   0, "cd /home/dev/projects/replay-api"),
        (2,   0, "docker compose up -d postgres redis"),
        (5,   0, "docker ps"),
        (8,   0, "docker build -t replay-api ."),
        (15,  1, "docker build -t replay-api ."),  # FAIL
        (18,  0, "cat Dockerfile"),
        (20,  0, "docker build -t replay-api --no-cache ."),  # fix
        (45,  0, "docker run -p 8000:8000 replay-api"),
        (48,  0, "curl localhost:8000/health"),
        (50,  0, "docker logs replay-api"),
        (55,  0, "docker compose down"),
        (58,  0, "docker compose up -d"),
        (62,  0, "docker exec -it replay-api python manage.py migrate"),
        (65,  1, "docker exec -it replay-api python manage.py migrate"),  # FAIL
        (68,  0, "docker exec -it replay-api python manage.py migrate --fake-initial"),  # fix
        (72,  0, "docker compose logs api"),
        (75,  0, "docker system prune -f"),
        (78,  0, "docker volume ls"),
    ]
    for dt, exit_code, cmd in seq:
        t += dt
        cmds.append((make_id(), base + t * NS, rand_duration_ms(50, 5000), exit_code, cmd, cwd, host, sid))
    return cmds

def python_debugging(host: str) -> list[tuple]:
    """Python testing and debugging session."""
    sid = session_id()
    base = ns_now() - 2 * 24 * 3600 * NS
    cwd = "/home/dev/projects/replay"
    t = 0
    cmds = []

    seq = [
        (0,   0, "cd /home/dev/projects/replay"),
        (2,   0, "source .venv/bin/activate"),
        (4,   0, "pytest tests/ -v"),
        (12,  1, "pytest tests/ -v"),  # FAIL
        (15,  0, "cat tests/test_search.py"),
        (18,  0, "pytest tests/test_search.py::test_embedding -v"),  # isolate
        (22,  1, "pytest tests/test_search.py::test_embedding -v"),  # FAIL again
        (25,  0, "python -c \"from replay.search.embedder import Embedder; e = Embedder(); print(e.embed('hello'))\""),
        (30,  0, "pip install -e '.[dev]'"),
        (35,  0, "pytest tests/test_search.py::test_embedding -v"),  # fix
        (38,  0, "pytest tests/ -v --tb=short"),
        (45,  0, "pytest tests/ -v --cov=replay"),
        (50,  0, "coverage report"),
        (52,  0, "python -m replay search 'docker build'"),
        (55,  0, "python -m replay list --limit 10"),
        (58,  0, "python -m replay stats"),
        (60,  0, "python -m replay fixes"),
    ]
    for dt, exit_code, cmd in seq:
        t += dt
        cmds.append((make_id(), base + t * NS, rand_duration_ms(50, 8000), exit_code, cmd, cwd, host, sid))
    return cmds

def git_workflow(host: str) -> list[tuple]:
    """Git rebase/merge/fix session."""
    sid = session_id()
    base = ns_now() - 1 * 24 * 3600 * NS
    cwd = "/home/dev/projects/replay"
    t = 0
    cmds = []

    seq = [
        (0,   0, "git status"),
        (2,   0, "git log --oneline -10"),
        (4,   0, "git checkout main"),
        (6,   0, "git pull origin main"),
        (10,  0, "git checkout -b feature/search-v2"),
        (12,  0, "git add replay/search/"),
        (14,  0, "git commit -m 'feat: upgrade search to v2'"),
        (16,  0, "git push origin feature/search-v2"),
        (20,  1, "git rebase main"),  # CONFLICT → fail
        (22,  0, "git status"),
        (24,  0, "cat replay/search/query.py"),
        (28,  0, "git add replay/search/query.py"),
        (30,  0, "git rebase --continue"),  # fix
        (32,  0, "git push origin feature/search-v2 --force-with-lease"),
        (35,  0, "git diff main..feature/search-v2 --stat"),
        (38,  0, "git stash"),
        (40,  0, "git checkout main"),
        (42,  0, "git pull"),
        (44,  0, "git checkout feature/search-v2"),
        (46,  0, "git stash pop"),
        (48,  0, "git add -A"),
        (50,  0, "git commit -m 'fix: resolve rebase conflict in query.py'"),
        (52,  0, "git log --oneline --graph -15"),
    ]
    for dt, exit_code, cmd in seq:
        t += dt
        cmds.append((make_id(), base + t * NS, rand_duration_ms(20, 2000), exit_code, cmd, cwd, host, sid))
    return cmds

def node_frontend(host: str) -> list[tuple]:
    """Node/React frontend build and deploy."""
    sid = session_id()
    base = ns_now() - 2 * 24 * 3600 * NS + 6 * 3600 * NS
    cwd = "/home/dev/projects/replay-ui"
    t = 0
    cmds = []

    seq = [
        (0,   0, "cd /home/dev/projects/replay-ui"),
        (2,   0, "npm install"),
        (15,  0, "npm run dev"),
        (18,  0, "npm run build"),
        (30,  1, "npm run build"),  # FAIL - type error
        (33,  0, "cat src/components/SearchBar.tsx"),
        (36,  0, "npx tsc --noEmit"),
        (40,  1, "npx tsc --noEmit"),  # FAIL
        (43,  0, "vi src/components/SearchBar.tsx"),
        (48,  0, "npx tsc --noEmit"),  # fix
        (50,  0, "npm run build"),  # fix
        (60,  0, "npm run test"),
        (65,  0, "npm run test -- --coverage"),
        (70,  0, "npm run lint"),
        (72,  1, "npm run lint"),  # FAIL
        (75,  0, "npm run lint:fix"),  # fix
        (78,  0, "npm run build"),
        (85,  0, "npx vercel --prod"),
        (95,  0, "curl https://replay-ui.vercel.app"),
    ]
    for dt, exit_code, cmd in seq:
        t += dt
        cmds.append((make_id(), base + t * NS, rand_duration_ms(100, 15000), exit_code, cmd, cwd, host, sid))
    return cmds

def database_work(host: str) -> list[tuple]:
    """Database migration and query sessions."""
    sid = session_id()
    base = ns_now() - 1 * 24 * 3600 * NS + 4 * 3600 * NS
    cwd = "/home/dev/projects/replay-api"
    t = 0
    cmds = []

    seq = [
        (0,   0, "psql -U replay -d replay_db"),
        (5,   0, "\\dt"),
        (7,   0, "SELECT COUNT(*) FROM history;"),
        (10,  0, "\\q"),
        (12,  0, "python manage.py makemigrations"),
        (15,  0, "python manage.py migrate"),
        (20,  1, "python manage.py migrate"),  # FAIL
        (23,  0, "python manage.py showmigrations"),
        (26,  0, "python manage.py migrate --fake api 0003"),
        (30,  0, "python manage.py migrate"),  # fix
        (33,  0, "python manage.py dbshell"),
        (36,  0, "SELECT * FROM api_embeddedchunk LIMIT 5;"),
        (38,  0, "\\q"),
        (40,  0, "pg_dump -U replay replay_db > backup.sql"),
        (45,  0, "psql -U replay -d replay_db -f seed.sql"),
        (48,  0, "python manage.py shell -c \"from api.models import Chunk; print(Chunk.objects.count())\""),
        (50,  0, "redis-cli KEYS '*'"),
        (52,  0, "redis-cli FLUSHDB"),
        (54,  0, "python manage.py clear_cache"),
    ]
    for dt, exit_code, cmd in seq:
        t += dt
        cmds.append((make_id(), base + t * NS, rand_duration_ms(50, 5000), exit_code, cmd, cwd, host, sid))
    return cmds

def k8s_deploy(host: str) -> list[tuple]:
    """Kubernetes deployment workflow."""
    sid = session_id()
    base = ns_now() - 12 * 3600 * NS
    cwd = "/home/dev/projects/replay"
    t = 0
    cmds = []

    seq = [
        (0,   0, "kubectl get pods"),
        (3,   0, "kubectl get svc"),
        (5,   0, "kubectl apply -f k8s/deployment.yaml"),
        (8,   0, "kubectl rollout status deployment/replay-api"),
        (12,  1, "kubectl rollout status deployment/replay-api"),  # FAIL
        (15,  0, "kubectl describe pod replay-api-7d8f9"),
        (18,  0, "kubectl logs replay-api-7d8f9 --tail=50"),
        (22,  0, "kubectl set image deployment/replay-api replay-api=ghcr.io/replay/api:v0.2.1"),
        (25,  0, "kubectl rollout status deployment/replay-api"),  # fix
        (28,  0, "kubectl get pods -o wide"),
        (30,  0, "kubectl exec -it replay-api-7d8f9 -- python manage.py migrate"),
        (35,  0, "kubectl port-forward svc/replay-api 8000:80"),
        (38,  0, "curl localhost:8000/health"),
        (40,  0, "kubectl top pods"),
        (42,  0, "kubectl get events --sort-by='.lastTimestamp'"),
        (45,  0, "kubectl rollout undo deployment/replay-api"),
        (48,  0, "kubectl get pods"),
    ]
    for dt, exit_code, cmd in seq:
        t += dt
        cmds.append((make_id(), base + t * NS, rand_duration_ms(200, 10000), exit_code, cmd, cwd, host, sid))
    return cmds

def ai_ml_workflow(host: str) -> list[tuple]:
    """Jina AI / embedding / ML experimentation."""
    sid = session_id()
    base = ns_now() - 18 * 3600 * NS
    cwd = "/home/dev/projects/replay"
    t = 0
    cmds = []

    seq = [
        (0,   0, "python -c \"import openai; print(openai.__version__)\""),
        (3,   0, "export JINA_API_KEY=jina_abc123"),
        (5,   0, "python -c \"from replay.search.embedder import Embedder; e = Embedder(); print(len(e.embed('test')))\""),
        (10,  0, "python -c \"import faiss; print(faiss.__version__)\""),
        (12,  0, "python -c \"import numpy as np; v = np.random.randn(1024).astype('float32'); faiss.normalize_L2(v.reshape(1,-1)); print(v[:5])\""),
        (15,  0, "python scripts/benchmark_embed.py"),
        (25,  0, "python -m replay refresh"),
        (35,  0, "python -m replay search 'how to fix docker permission denied'"),
        (38,  0, "python -m replay search 'git rebase conflict' --top-k 5"),
        (42,  0, "python -m replay search 'npm build failed' --plain"),
        (45,  0, "python -m replay stats"),
        (48,  0, "python -m replay export --format jsonl > replay_export.jsonl"),
        (50,  0, "wc -l replay_export.jsonl"),
        (52,  0, "python -c \"import json; data = [json.loads(l) for l in open('replay_export.jsonl')]; print(len(data))\""),
    ]
    for dt, exit_code, cmd in seq:
        t += dt
        cmds.append((make_id(), base + t * NS, rand_duration_ms(100, 20000), exit_code, cmd, cwd, host, sid))
    return cmds

def system_admin(host: str) -> list[tuple]:
    """System administration and debugging."""
    sid = session_id()
    base = ns_now() - 6 * 3600 * NS
    cwd = "/home/dev"
    t = 0
    cmds = []

    seq = [
        (0,   0, "htop"),
        (2,   0, "df -h"),
        (4,   0, "du -sh /home/dev/*"),
        (6,   0, "free -m"),
        (8,   0, "sudo journalctl -u docker --since '1 hour ago'"),
        (12,  1, "sudo systemctl restart nginx"),  # FAIL
        (15,  0, "sudo nginx -t"),
        (18,  0, "sudo vi /etc/nginx/sites-available/replay"),
        (22,  0, "sudo nginx -t"),
        (24,  0, "sudo systemctl restart nginx"),  # fix
        (26,  0, "sudo systemctl status nginx"),
        (28,  0, "curl -I https://replay.dev"),
        (30,  0, "sudo certbot renew --dry-run"),
        (33,  0, "sudo ufw status"),
        (35,  0, "ss -tlnp"),
        (37,  0, "tail -f /var/log/nginx/error.log"),
        (40,  0, "sudo fail2ban-client status"),
        (42,  0, "crontab -l"),
    ]
    for dt, exit_code, cmd in seq:
        t += dt
        cmds.append((make_id(), base + t * NS, rand_duration_ms(50, 5000), exit_code, cmd, cwd, host, sid))
    return cmds

def pip_package_mgmt(host: str) -> list[tuple]:
    """Package management and publishing."""
    sid = session_id()
    base = ns_now() - 4 * 3600 * NS
    cwd = "/home/dev/projects/replay"
    t = 0
    cmds = []

    seq = [
        (0,   0, "cat pyproject.toml"),
        (2,   0, "uv pip install -e '.[dev]'"),
        (8,   0, "uv pip list | grep replay"),
        (10,  0, "python -m build"),
        (18,  1, "python -m build"),  # FAIL - missing build dep
        (20,  0, "uv pip install build"),
        (22,  0, "python -m build"),  # fix
        (28,  0, "ls dist/"),
        (30,  0, "twine check dist/*"),
        (32,  1, "twine check dist/*"),  # FAIL
        (35,  0, "cat pyproject.toml | grep -A5 classifiers"),
        (38,  0, "vi pyproject.toml"),
        (42,  0, "python -m build"),
        (45,  0, "twine check dist/*"),  # fix
        (48,  0, "twine upload --repository testpypi dist/*"),
        (55,  0, "pip install -i https://test.pypi.org/simple/ replay-ai"),
    ]
    for dt, exit_code, cmd in seq:
        t += dt
        cmds.append((make_id(), base + t * NS, rand_duration_ms(100, 10000), exit_code, cmd, cwd, host, sid))
    return cmds

def random_misc_commands(host: str) -> list[tuple]:
    """Random developer miscellany to pad the dataset."""
    sid = session_id()
    base = ns_now() - 5 * 24 * 3600 * NS
    cwd = "/home/dev"
    t = 0
    cmds = []

    misc = [
        "ls", "cd projects", "pwd", "whoami", "echo $PATH",
        "cat ~/.bashrc", "source ~/.bashrc", "alias ll='ls -la'",
        "which python", "python --version", "node --version",
        "nvim README.md", "cat /etc/os-release", "uname -a",
        "ssh deploy@replay.dev", "scp backup.sql deploy@replay.dev:~/",
        "curl ifconfig.me", "ping google.com",
        "brew update", "brew upgrade",
        "code .", "gh pr list", "gh issue create -t 'Bug: search timeout'",
        "atuin search docker", "atuin stats",
        "tmux ls", "tmux attach -t dev",
        "rg -l 'Embedder' replay/", "fd '.py' replay/ | head -20",
        "watch docker ps", "nc -zv localhost 5432",
        "openssl s_client -connect replay.dev:443",
        "dig replay.dev", "traceroute replay.dev",
        "git remote -v", "git branch -a",
        "cat Makefile", "make test", "make lint",
        "pre-commit run --all-files",
        "act -l",  # GitHub Actions local
        "gh run list", "gh workflow view ci.yml",
        "docker images", "docker rmi $(docker images -q -f dangling=true)",
        "pip list --outdated", "pip-audit",
        "safety check", "bandit -r replay/",
    ]

    for i, cmd in enumerate(misc):
        t += random.randint(30, 300)
        exit_code = 0
        # Sprinkle a few failures
        if cmd in ("brew update", "pre-commit run --all-files", "safety check"):
            exit_code = random.choice([0, 1])
        cmds.append((make_id(), base + t * NS, rand_duration_ms(10, 3000), exit_code, cmd, cwd, host, sid))
    return cmds

def web_dev_workflow(host: str) -> list[tuple]:
    """Web development with Next.js / Tailwind."""
    sid = session_id()
    base = ns_now() - 2 * 24 * 3600 * NS + 10 * 3600 * NS
    cwd = "/home/dev/projects/portfolio"
    t = 0
    cmds = []

    seq = [
        (0,   0, "cd /home/dev/projects/portfolio"),
        (2,   0, "npm run dev"),
        (5,   0, "npm run build"),
        (20,  1, "npm run build"),  # FAIL
        (23,  0, "cat next.config.js"),
        (26,  0, "vi next.config.js"),
        (30,  0, "npm run build"),  # fix
        (45,  0, "npm run export"),
        (50,  0, "ls out/"),
        (52,  0, "npx serve out"),
        (55,  0, "git add ."),
        (57,  0, "git commit -m 'chore: static export config'"),
        (59,  0, "git push"),
        (62,  0, "gh workflow run deploy"),
        (65,  0, "gh run watch"),
    ]
    for dt, exit_code, cmd in seq:
        t += dt
        cmds.append((make_id(), base + t * NS, rand_duration_ms(100, 12000), exit_code, cmd, cwd, host, sid))
    return cmds

def devops_cicd(host: str) -> list[tuple]:
    """CI/CD pipeline debugging."""
    sid = session_id()
    base = ns_now() - 8 * 3600 * NS
    cwd = "/home/dev/projects/replay"
    t = 0
    cmds = []

    seq = [
        (0,   0, "gh run list --limit 5"),
        (3,   0, "gh run view 12345"),
        (5,   1, "gh run view 12345 --log"),  # FAIL (exit 1 from gh)
        (8,   0, "cat .github/workflows/ci.yml"),
        (12,  0, "act -j test"),  # local CI run
        (25,  1, "act -j test"),  # FAIL
        (28,  0, "act -j test --verbose"),
        (35,  0, "vi .github/workflows/ci.yml"),
        (38,  0, "act -j test"),  # fix
        (48,  0, "git add .github/"),
        (50,  0, "git commit -m 'ci: fix test workflow'"),
        (52,  0, "git push"),
        (55,  0, "gh run watch"),
    ]
    for dt, exit_code, cmd in seq:
        t += dt
        cmds.append((make_id(), base + t * NS, rand_duration_ms(500, 15000), exit_code, cmd, cwd, host, sid))
    return cmds


# ── Main ──────────────────────────────────────────────────────────────

def main():
    if not DB_PATH.exists():
        print(f"ERROR: Atuin DB not found at {DB_PATH}")
        print("Install Atuin first: https://atuin.sh/docs/installation")
        return

    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()

    # Count existing
    cur.execute("SELECT COUNT(*) FROM history")
    before = cur.fetchone()[0]
    print(f"Existing commands: {before}")

    # Gather all demo workflows
    host = "kali:midlaj"
    all_cmds = []
    all_cmds.extend(docker_workflow(host))
    all_cmds.extend(python_debugging(host))
    all_cmds.extend(git_workflow(host))
    all_cmds.extend(node_frontend(host))
    all_cmds.extend(database_work(host))
    all_cmds.extend(k8s_deploy(host))
    all_cmds.extend(ai_ml_workflow(host))
    all_cmds.extend(system_admin(host))
    all_cmds.extend(pip_package_mgmt(host))
    all_cmds.extend(random_misc_commands(host))
    all_cmds.extend(web_dev_workflow(host))
    all_cmds.extend(devops_cicd(host))

    # Insert
    cur.executemany(
        """INSERT OR IGNORE INTO history
           (id, timestamp, duration, exit_status, command, cwd, hostname, session)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        all_cmds,
    )
    conn.commit()

    cur.execute("SELECT COUNT(*) FROM history")
    after = cur.fetchone()[0]
    added = after - before

    print(f"Inserted: {added} commands")
    print(f"Total:    {after} commands")
    print(f"Target:   500+ {'✓ ACHIEVED' if after >= 500 else '✗ NOT MET'}")

    # Show session breakdown
    cur.execute("SELECT COUNT(DISTINCT session) FROM history")
    sessions = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM history WHERE exit_status != 0")
    failures = cur.fetchone()[0]
    print(f"Sessions: {sessions}")
    print(f"Failures: {failures} (fix detection candidates)")

    conn.close()

if __name__ == "__main__":
    main()
