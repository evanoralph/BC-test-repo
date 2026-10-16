#!/usr/bin/env python3
"""
Offline menu extraction via OpenRouter vision models.

Default input: data-sets-sample/ (3 images) for testing.
Full set: --input-dir data-sets

Logs every step to stderr. Does not modify existing code paths.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "data-sets-sample"
DEFAULT_PROMPT = ROOT / "prompts" / "extract_v1.txt"
DEFAULT_RAW = ROOT / "raw"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# Bake-off defaults (cheap vision models)
MODEL_A = "openai/gpt-4o-mini"
MODEL_B = "google/gemini-2.5-flash"

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}


def log(msg: str) -> None:
    print(f"[extract] {msg}", file=sys.stderr, flush=True)


def load_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def get_api_key() -> str:
    env = load_env(ROOT / ".env")
    key = (
        os.environ.get("OPENROUTER_API_KEY")
        or os.environ.get("OPEN_ROUTER_API_KEY")
        or env.get("OPENROUTER_API_KEY")
        or env.get("open-router-api-key")
        or env.get("OPEN_ROUTER_API_KEY")
    )
    if not key:
        raise SystemExit("Missing OpenRouter API key in .env or env vars")
    return key


def stable_menu_id(path: Path, index: int) -> str:
    """Prefer sample_NN / menu_NN over raw screenshot names."""
    parent = path.parent.name
    if "sample" in parent.lower():
        return f"sample_{index:02d}"
    return f"menu_{index:02d}"


def list_images(input_dir: Path) -> list[Path]:
    files = sorted(
        p for p in input_dir.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTS
    )
    log(f"found {len(files)} images in {input_dir}")
    return files


def encode_image(path: Path, max_side: int = 1600) -> tuple[str, str]:
    """Return (media_type, base64). Optionally downscale via sips on macOS."""
    mime = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }.get(path.suffix.lower(), "image/png")

    data = path.read_bytes()
    # Try light resize for large files to cut tokens/cost
    if len(data) > 1_500_000:
        try:
            import tempfile
            import subprocess

            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
                tmp_path = Path(tmp.name)
            subprocess.run(
                [
                    "sips",
                    "-s",
                    "format",
                    "jpeg",
                    "-Z",
                    str(max_side),
                    str(path),
                    "--out",
                    str(tmp_path),
                ],
                check=True,
                capture_output=True,
            )
            data = tmp_path.read_bytes()
            tmp_path.unlink(missing_ok=True)
            mime = "image/jpeg"
            log(f"resized {path.name} -> {len(data)//1024}KB jpeg")
        except Exception as e:
            log(f"resize skipped for {path.name}: {e}")

    return mime, base64.b64encode(data).decode("ascii")


def strip_json_fence(text: str) -> str:
    text = text.strip()
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if m:
        return m.group(1).strip()
    # truncated fence: take after opening ```json
    m2 = re.search(r"```(?:json)?\s*([\s\S]+)", text)
    if m2:
        return m2.group(1).strip()
    return text


def salvage_json(text: str) -> dict:
    """Parse JSON; if truncated, close open arrays/objects best-effort."""
    text = strip_json_fence(text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Trim to last complete item object if possible
    cut = text
    # drop trailing incomplete string/field
    if '"items"' in cut:
        # close items array + root object
        last_brace = cut.rfind("}")
        if last_brace > 0:
            cut = cut[: last_brace + 1]
            # ensure items array closed
            if cut.count("[") > cut.count("]"):
                cut += "]" * (cut.count("[") - cut.count("]"))
            if cut.count("{") > cut.count("}"):
                cut += "}" * (cut.count("{") - cut.count("}"))
            try:
                parsed = json.loads(cut)
                log("salvaged truncated JSON")
                return parsed
            except json.JSONDecodeError as e:
                log(f"salvage failed: {e}")
    raise json.JSONDecodeError("Unable to parse/salvage JSON", text, 0)


def call_openrouter(
    api_key: str,
    model: str,
    prompt: str,
    menu_id: str,
    mime: str,
    b64: str,
    max_tokens: int = 8192,
) -> dict:
    user_text = (
        f"menu_id for this image: {menu_id}\n\n"
        "Extract the menu into the JSON schema. "
        "currency_notes must be one short sentence. "
        "Do not repeat phrases. Emit the items array promptly."
    )
    body = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": 0,
        "frequency_penalty": 0.4,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt + "\n\n" + user_text},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime};base64,{b64}"},
                    },
                ],
            }
        ],
    }
    req = urllib.request.Request(
        OPENROUTER_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://here.now",
            "X-Title": "boost-capital-menu-extract",
        },
        method="POST",
    )
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            raw = resp.read().decode("utf-8")
            status = resp.status
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        log(f"HTTP {e.code} for {menu_id}/{model}: {err_body[:400]}")
        raise
    elapsed = time.time() - t0
    log(f"ok {menu_id} model={model} status={status} {elapsed:.1f}s")
    return json.loads(raw)


def parse_model_content(resp: dict) -> dict:
    choices = resp.get("choices") or []
    if not choices:
        raise ValueError("no choices in response")
    content = choices[0]["message"]["content"]
    if isinstance(content, list):
        # some providers return content parts
        content = "".join(
            p.get("text", "") if isinstance(p, dict) else str(p) for p in content
        )
    return salvage_json(str(content))


def extract_one(
    api_key: str,
    model: str,
    prompt: str,
    image_path: Path,
    menu_id: str,
    out_dir: Path,
    force: bool,
) -> Path:
    out_path = out_dir / f"{menu_id}.json"
    if out_path.exists() and not force:
        log(f"skip existing {out_path}")
        return out_path

    mime, b64 = encode_image(image_path)
    resp = call_openrouter(api_key, model, prompt, menu_id, mime, b64)
    # always keep raw provider response for debug
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_path = out_dir / f"{menu_id}.raw_response.json"
    raw_path.write_text(json.dumps(resp, ensure_ascii=False, indent=2), encoding="utf-8")

    try:
        parsed = parse_model_content(resp)
    except Exception as e:
        log(f"parse failed for {menu_id}: {e}; attempting salvage from {raw_path}")
        try:
            choices = resp.get("choices") or []
            content = choices[0]["message"]["content"] if choices else ""
            if isinstance(content, list):
                content = "".join(
                    p.get("text", "") if isinstance(p, dict) else str(p) for p in content
                )
            parsed = salvage_json(str(content))
        except Exception as e2:
            log(f"salvage failed for {menu_id}: {e2}")
            raise e

    parsed["menu_id"] = menu_id
    parsed["_source_file"] = image_path.name
    parsed["_model"] = model
    out_path.write_text(json.dumps(parsed, ensure_ascii=False, indent=2), encoding="utf-8")
    n = len(parsed.get("items") or [])
    log(f"wrote {out_path} items={n}")
    return out_path


def model_slug(model: str) -> str:
    return model.replace("/", "__")


def main() -> None:
    ap = argparse.ArgumentParser(description="Extract menus to raw JSON")
    ap.add_argument(
        "--input-dir",
        type=Path,
        default=DEFAULT_INPUT,
        help="Image folder (default: data-sets-sample)",
    )
    ap.add_argument("--prompt", type=Path, default=DEFAULT_PROMPT)
    ap.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW)
    ap.add_argument(
        "--models",
        nargs="+",
        default=[MODEL_A],
        help="OpenRouter model ids",
    )
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--force", action="store_true")
    ap.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Only first N images (0 = all)",
    )
    ap.add_argument(
        "--only",
        nargs="+",
        default=[],
        help="Only these menu ids (e.g. menu_06 sample_01)",
    )
    args = ap.parse_args()

    api_key = get_api_key()
    prompt = args.prompt.read_text(encoding="utf-8")
    images = list_images(args.input_dir)
    if args.limit and args.limit > 0:
        images = images[: args.limit]
        log(f"limit applied -> {len(images)} images")

    only = set(args.only or [])
    jobs = []
    for model in args.models:
        out_dir = args.raw_dir / model_slug(model)
        for i, img in enumerate(images, start=1):
            mid = stable_menu_id(img, i)
            if only and mid not in only:
                continue
            jobs.append((model, out_dir, img, mid))
    if only:
        log(f"--only filter {sorted(only)} -> {len(jobs)} jobs")
        if not jobs:
            raise SystemExit(f"No matching images for --only {sorted(only)}")

    log(f"queue={len(jobs)} models={args.models} workers={args.workers}")

    errors = []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {
            ex.submit(
                extract_one,
                api_key,
                model,
                prompt,
                img,
                mid,
                out_dir,
                args.force,
            ): (model, mid)
            for model, out_dir, img, mid in jobs
        }
        for fut in as_completed(futs):
            model, mid = futs[fut]
            try:
                fut.result()
            except Exception as e:
                log(f"ERROR {mid}/{model}: {e}")
                errors.append((mid, model, str(e)))

    if errors:
        log(f"finished with {len(errors)} errors")
        for mid, model, err in errors:
            print(f"FAIL\t{mid}\t{model}\t{err}", file=sys.stderr)
        sys.exit(1)
    log("done")


if __name__ == "__main__":
    main()
