"""Project generator to scaffold a new project from this template.

Usage:
  python scripts/init_project.py --name myproj --package myproj_pkg --out ../myproj

The script copies selected template files into `out` and renames the
`agent_sdlc` package directory to the requested package name, replacing
occurrences of the template package name in text files.
"""
from __future__ import annotations
import argparse
import shutil
from pathlib import Path
from typing import Iterable

TEMPLATE_PYPROJECT = "pyproject.template.toml"


TEMPLATE_NAME = "agent_sdlc"


def copy_tree(src: Path, dest: Path, ignore: Iterable[str] | None = None) -> None:
    shutil.copytree(src, dest, dirs_exist_ok=True, ignore=shutil.ignore_patterns(*(ignore or [])))


def replace_in_file(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf8")
    if old in text:
        path.write_text(text.replace(old, new), encoding="utf8")


def is_text_file(path: Path) -> bool:
    try:
        s = path.suffix.lower()
        return s in {".py", ".md", ".txt", ".toml", ".yml", ".yaml", ".ini", ".cfg", ".json"}
    except Exception:
        return False


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--name", required=True, help="Project name (directory)")
    p.add_argument("--package", help="Python package name to create (default: project name)")
    p.add_argument("--out", help="Output parent dir (default: .)", default=".")
    p.add_argument("--include-integration", action="store_true", help="Include integration tests and heavy deps")
    p.add_argument("--force", action="store_true", help="Overwrite existing output directory")
    p.add_argument("--author", help="Author name to place into templates", default="Your Name")
    p.add_argument("--author-email", help="Author email to place into templates", default="you@example.com")
    p.add_argument("--license", help="License identifier to add (MIT)", default="MIT")
    args = p.parse_args()

    project_name = args.name
    package_name = args.package or project_name
    out_parent = Path(args.out).resolve()
    dest = out_parent / project_name

    if dest.exists() and not args.force:
        raise SystemExit(f"Destination {dest} already exists. Use --force to overwrite.")

    template_root = Path(__file__).resolve().parents[1]

    # Create destination
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)

    # Files and dirs to copy
    entries = ["README.md", "CONTRIBUTING.md", "requirements.txt", "requirements-dev.txt"]
    dirs = [".github", "scripts", "tests"]

    for e in entries:
        src = template_root / e
        if src.exists():
            shutil.copy2(src, dest / src.name)

    for d in dirs:
        src = template_root / d
        if src.exists():
            # skip integration tests if not requested
            if d == "tests" and not args.include_integration:
                # copy only unit tests
                unit_tests = template_root / "tests"
                dst_tests = dest / "tests"
                dst_tests.mkdir(exist_ok=True)
                for tf in unit_tests.glob("test_*.py"):
                    shutil.copy2(tf, dst_tests / tf.name)
            else:
                copy_tree(src, dest / src.name, ignore=[".git", "*.pyc", "__pycache__"])  # type: ignore[arg-type]

    # Copy package and rename
    src_pkg = template_root / TEMPLATE_NAME
    if src_pkg.exists():
        dst_pkg = dest / package_name
        copy_tree(src_pkg, dst_pkg, ignore=[".git", "*.pyc", "__pycache__"])  # type: ignore[arg-type]

    # Replace occurrences of template package name in text files
    for path in dest.rglob("*"):
        if path.is_file() and is_text_file(path):
            try:
                replace_in_file(path, TEMPLATE_NAME, package_name)
            except Exception:
                # skip files we can't read/replace
                continue

    # Render pyproject template if present
    tpl = template_root / TEMPLATE_PYPROJECT
    if tpl.exists():
        txt = tpl.read_text(encoding="utf8")
        # minimal templating: replace placeholders
        meta = {
            "project_name": project_name,
            "author": args.author,
            "author_email": args.author_email,
            "license": args.license,
        }
        # optional repository owner placeholder
        meta.setdefault("github_owner", "your-github-org-or-username")
        for k, v in meta.items():
            txt = txt.replace("{{" + k + "}}", v)
        (dest / "pyproject.toml").write_text(txt, encoding="utf8")

    # Render LICENSE if template exists
    lic_tpl = template_root / "LICENSE.template.MIT"
    if lic_tpl.exists():
        lic_txt = lic_tpl.read_text(encoding="utf8")
        lic_txt = lic_txt.replace("{{year}}", str(__import__("datetime").datetime.now().year))
        lic_txt = lic_txt.replace("{{author}}", args.author)
        (dest / "LICENSE").write_text(lic_txt, encoding="utf8")

    print(f"Scaffolded project at: {dest}")
    print("Next steps:")
    print(f"  cd {dest}")
    print("  python scripts/bootstrap.py")


if __name__ == "__main__":
    main()
