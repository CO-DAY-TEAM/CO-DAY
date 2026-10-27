"""공식 ReviewBench 도구를 그대로 호출하는 로컬 실행 진입점."""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

from dotenv import dotenv_values

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
UPSTREAM = HERE / ".cache" / "ReviewBench"
REVIEWBENCH_REV = "36cc8a8dbce3375c80f58f957a2a2be34681cf49"
JUDGE_PROVIDER = "openai-codex"
PI_DIR = HERE / ".cache" / "pi"


def config() -> dict[str, str]:
    # 전용 파일만 읽는다. 셸 환경변수가 파일보다 우선한다.
    defaults = dotenv_values(HERE / ".env.example")
    local = dotenv_values(HERE / ".env")
    return {
        key: os.environ.get(key, local.get(key, value)) or "" for key, value in defaults.items()
    }


def require(cfg, *keys):
    missing = [key for key in keys if not cfg.get(key)]
    if missing:
        raise ValueError(f"evals/reviewbench/.env에 설정하세요: {', '.join(missing)}")


def judge_env():
    # 로그인과 채점이 같은 pi 저장소를 사용한다. 구독 인증을 API 키로 대체하지 않는다.
    env = os.environ.copy()
    env.pop("OPENAI_API_KEY", None)
    env["PI_CODING_AGENT_DIR"] = str(PI_DIR)
    return env


def require_judge_login():
    auth = PI_DIR / "auth.json"
    if (
        not auth.exists()
        or json.loads(auth.read_text()).get(JUDGE_PROVIDER, {}).get("type") != "oauth"
    ):
        raise RuntimeError(
            "먼저 run.py --login에서 /login → ChatGPT Plus/Pro (Codex)로 로그인하세요."
        )


def command(args, *, cwd=ROOT, env=None):
    subprocess.run([str(arg) for arg in args], cwd=cwd, env=env, check=True)


def capture(args, cwd=ROOT):
    return subprocess.check_output([str(a) for a in args], cwd=cwd, text=True).strip()


def save(path, data):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def pr_key(entry):
    return f"{entry['nwo'].replace('/', '_')}_{entry['pr_number']}-{entry['head'][:8]}"


def setup():
    if not UPSTREAM.exists():
        UPSTREAM.parent.mkdir(parents=True, exist_ok=True)
        command(["git", "clone", "https://github.com/review-bench/ReviewBench.git", UPSTREAM])
    if capture(["git", "rev-parse", "HEAD"], UPSTREAM) != REVIEWBENCH_REV:
        command(["git", "fetch", "origin", REVIEWBENCH_REV], cwd=UPSTREAM)
        command(["git", "checkout", "--detach", REVIEWBENCH_REV], cwd=UPSTREAM)
    stamp = HERE / ".cache" / "npm-revision"
    if (
        not (UPSTREAM / "node_modules").is_dir()
        or not stamp.exists()
        or stamp.read_text() != REVIEWBENCH_REV
    ):
        command(["npm", "ci", "--no-audit", "--no-fund"], cwd=UPSTREAM)
        stamp.write_text(REVIEWBENCH_REV)


def langfuse_client(cfg, *, tracing=False):
    require(cfg, "LANGFUSE_BASE_URL", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY")
    from langfuse import Langfuse

    return Langfuse(
        base_url=cfg["LANGFUSE_BASE_URL"],
        public_key=cfg["LANGFUSE_PUBLIC_KEY"],
        secret_key=cfg["LANGFUSE_SECRET_KEY"],
        tracing_enabled=tracing,
        environment="reviewbench",
        timeout=30,
    )


def prepare(cfg, args):
    require(
        cfg,
        "REVIEW_API_KEY",
        "REVIEW_MODEL",
        "JUDGE_MODEL",
        "RUN_BY",
        "LANGFUSE_BASE_URL",
        "LANGFUSE_PUBLIC_KEY",
        "LANGFUSE_SECRET_KEY",
    )
    require_judge_login()
    label, actor = args.label or cfg["RUN_LABEL"], cfg["RUN_BY"]
    for text in (label, actor):
        if not re.fullmatch(r"[\w.-]{1,60}", text):
            raise ValueError("RUN_LABEL/RUN_BY에는 문자·숫자·하이픈·밑줄을 사용하세요.")
    stamp = datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y%m%d-%H%M%S")
    run_name = f"{label}-{stamp}-{actor}-{uuid4().hex[:6]}"
    run = HERE / "runs" / run_name
    run.mkdir(parents=True)
    entries = json.loads(
        (
            UPSTREAM / ("corpus/test/test.json" if args.set == "test" else "corpus/manifest.json")
        ).read_text()
    )
    if args.pr is not None and not 0 <= args.pr < len(entries):
        raise ValueError(f"--pr must be between 0 and {len(entries) - 1}")
    selected = entries if args.pr is None else [entries[args.pr]]
    # 정답은 호스트/채점기에만 존재한다. Docker 컨텍스트에서 runs/는 제외한다.
    dataset = []
    for entry in entries:
        key = pr_key(entry)
        golden = json.loads((UPSTREAM / "golden" / f"{key}.json").read_text())
        dataset.append({"pr_key": key, "input": entry, "expected_output": golden["findings"]})
    save(run / "dataset.json", dataset)
    manifest = {
        "run_name": run_name,
        "description": args.description or cfg["RUN_DESCRIPTION"],
        "run_by": actor,
        "created_at": datetime.now(ZoneInfo("Asia/Seoul")).isoformat(),
        "set": args.set,
        "pr_index": args.pr,
        "expected_prs": [pr_key(e) for e in selected],
        "reviewbench_revision": REVIEWBENCH_REV,
        "coday_revision": capture(["git", "rev-parse", "HEAD"]),
        "coday_dirty": bool(capture(["git", "status", "--porcelain"])),
        "review_model": cfg["REVIEW_MODEL"],
        "judge_model": cfg["JUDGE_MODEL"],
        "review_base_url": cfg["REVIEW_BASE_URL"],
        "judge_provider": JUDGE_PROVIDER,
        "prompt": {"name": "prompt", "label": "production"},
        "status": "prepared",
    }
    save(run / "run.json", manifest)
    print(f"Run: {run}", flush=True)
    return run, manifest


def score(run, manifest, cfg):
    require(cfg, "JUDGE_MODEL")
    require_judge_login()
    if (
        cfg["JUDGE_MODEL"] != manifest["judge_model"]
        or manifest["judge_provider"] != JUDGE_PROVIDER
    ):
        raise ValueError("재개 시 심사 provider와 모델은 원래 실행과 같아야 합니다.")
    found = {p.stem for p in (run / "findings").glob("*.json")}
    if found != set(manifest["expected_prs"]):
        raise ValueError("리뷰 결과가 요청한 PR 목록과 다릅니다. 부분 평가를 게시하지 않습니다.")
    output = run / "scoring" / "results.json"
    output.parent.mkdir(exist_ok=True)
    command(
        [
            "npm",
            "run",
            "judge",
            "--",
            "--candidate",
            run / "findings",
            "--provider",
            JUDGE_PROVIDER,
            "--model",
            cfg["JUDGE_MODEL"],
            "--output",
            output,
            "--repo-dir",
            HERE / ".cache" / "judge-repos",
            "--concurrency",
            cfg["JUDGE_CONCURRENCY"],
        ],
        cwd=UPSTREAM,
        env=judge_env(),
    )
    manifest["status"] = "scored"
    save(run / "run.json", manifest)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--setup", action="store_true", help="공식 도구 설치만 수행")
    parser.add_argument(
        "--login", action="store_true", help="pi의 ChatGPT Plus/Pro 로그인 화면 실행"
    )
    parser.add_argument("--set", choices=("test", "full"), default="test")
    parser.add_argument(
        "--pr", type=int, help="공식 manifest의 0-based PR 번호; 생략하면 선택 세트 전체"
    )
    parser.add_argument("--label")
    parser.add_argument("--description")
    parser.add_argument("--resume-judge", type=Path, help="리뷰가 완료된 실행의 채점부터 재개")
    args = parser.parse_args()
    setup()
    if args.setup:
        return
    if args.login:
        PI_DIR.mkdir(parents=True, exist_ok=True)
        print(
            "pi에서 /login → ChatGPT Plus/Pro (Codex)를 선택하세요. 완료 후 /quit로 종료합니다.",
            flush=True,
        )
        command([UPSTREAM / "node_modules/.bin/pi"], cwd=UPSTREAM, env=judge_env())
        return
    cfg = config()
    if args.resume_judge:
        run = args.resume_judge.resolve()
        manifest = json.loads((run / "run.json").read_text())
        if manifest["reviewbench_revision"] != REVIEWBENCH_REV:
            raise ValueError("이 실행과 다른 ReviewBench 버전입니다.")
    else:
        run, manifest = prepare(cfg, args)
        image = "coday-reviewbench:" + uuid4().hex[:12]
        command(
            [
                "docker",
                "build",
                "--platform",
                "linux/amd64",
                "-f",
                HERE / "Dockerfile",
                "-t",
                image,
                ROOT,
            ],
        )
        manifest["image_id"] = capture(["docker", "image", "inspect", "--format", "{{.Id}}", image])
        save(run / "run.json", manifest)
        work = HERE / ".cache" / "work" / manifest["run_name"]
        env = dict(
            os.environ,
            OPENAI_API_KEY=cfg["REVIEW_API_KEY"],
            RB_CONFIG_MODEL=cfg["REVIEW_MODEL"],
            RB_MODEL_BASE_URL=cfg["REVIEW_BASE_URL"],
            LANGFUSE_BASE_URL=cfg["LANGFUSE_BASE_URL"],
            LANGFUSE_PUBLIC_KEY=cfg["LANGFUSE_PUBLIC_KEY"],
            LANGFUSE_SECRET_KEY=cfg["LANGFUSE_SECRET_KEY"],
            TRY_AGENT_WORK=str(work),
        )
        args_rb = [
            "bash",
            UPSTREAM / "scripts/try-agent.sh",
            image,
            "--set",
            args.set,
            "-e",
            "OPENAI_API_KEY",
            "-e",
            "RB_CONFIG_MODEL",
            "-e",
            "RB_MODEL_BASE_URL",
            "-e",
            "LANGFUSE_BASE_URL",
            "-e",
            "LANGFUSE_PUBLIC_KEY",
            "-e",
            "LANGFUSE_SECRET_KEY",
            "-e",
            "RB_AGENT=coday",
        ]
        if args.pr is not None:
            args_rb += ["--pr", str(args.pr)]
        try:
            command(args_rb, cwd=run, env=env)
            manifest["status"] = "reviewed"
            save(run / "run.json", manifest)
        finally:
            for raw in (work / "out").glob("*/coday.json"):
                (run / "coday").mkdir(exist_ok=True)
                shutil.copyfile(raw, run / "coday" / f"{raw.parent.name}.json")
        manifest["prompt"] = json.loads(next((run / "coday").glob("*.json")).read_text())["prompt"]
        save(run / "run.json", manifest)
    score(run, manifest, cfg)
    command([sys.executable, HERE / "upload.py", run])


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"ReviewBench: {error}", file=sys.stderr)
        sys.exit(1)
