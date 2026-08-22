#!/usr/bin/env bash
# Developer verbs for proc_gen_temple.  devtool.bat carries the same verbs; keep them in step.
#
#   ./devtool.sh setup        install the venv with the build group (poetry)
#   ./devtool.sh test [args]  pytest; args go to pytest (-k, paths, -x ...)
#   ./devtool.sh fuzz         the 150-seed union fuzz and every range edge
#   ./devtool.sh lint         ruff over the package, tests and tools
#   ./devtool.sh check        lint then test: the pre-push gate
#   ./devtool.sh run [args]   the editor
#   ./devtool.sh export ...   the headless command (mandapa ...)
#   ./devtool.sh shot NAME    render examples/NAME.xml to out/NAME.png
#   ./devtool.sh icons        draw build/icons/mandapa.{ico,icns,png} from the app's own icon
#   ./devtool.sh licenses     fetch the LGPL-3.0 and GPL-3.0 texts into licenses/ (commit them)
#   ./devtool.sh build        icons, then the PyInstaller folder, then the smoke test
#   ./devtool.sh smoke        smoke-test an existing dist/proc_gen_temple
#   ./devtool.sh clean        remove build/ and dist/
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

setup()    { poetry install --with build "$@"; poetry env info --path; }
test_()    { poetry run pytest -q "$@"; }
fuzz()     { MANDAPA_FUZZ="${MANDAPA_FUZZ:-150}" poetry run pytest -q tests/test_builder.py -k "fuzz or edge" "$@"; }
lint()     { poetry run ruff check mandapa tests tools "$@"; }
check()    { lint && test_; }
run_()     { poetry run temple-gen "$@"; }
export_()  { poetry run mandapa "$@"; }
icons()    { poetry run python tools/make_icons.py; }
smoke()    { poetry run python tools/smoke_dist.py "$@"; }
clean()    { rm -rf build dist; }

shot() {
    local name="${1:?usage: devtool.sh shot EXAMPLE  (a stem from examples/)}"; shift
    mkdir -p out
    poetry run temple-gen --params "examples/$name.xml" --screenshot "out/$name.png" "$@"
    echo "out/$name.png"
}

licenses() {
    mkdir -p licenses
    curl -fsSL https://www.gnu.org/licenses/lgpl-3.0.txt -o licenses/LGPL-3.0.txt
    curl -fsSL https://www.gnu.org/licenses/gpl-3.0.txt -o licenses/GPL-3.0.txt
    echo "licenses/LGPL-3.0.txt and licenses/GPL-3.0.txt written; commit them"
}

build() {
    icons
    poetry run pyinstaller proc_gen_temple.spec --noconfirm --clean "$@"
    smoke
}

usage() { sed -n '2,17p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; }

verb="${1:-help}"
shift || true
case "$verb" in
    setup)    setup "$@" ;;
    test)     test_ "$@" ;;
    fuzz)     fuzz "$@" ;;
    lint)     lint "$@" ;;
    check)    check ;;
    run)      run_ "$@" ;;
    export)   export_ "$@" ;;
    shot)     shot "$@" ;;
    icons)    icons ;;
    licenses) licenses ;;
    build)    build "$@" ;;
    smoke)    smoke "$@" ;;
    clean)    clean ;;
    help|-h|--help) usage ;;
    *)        echo "unknown verb: $verb" >&2; usage >&2; exit 2 ;;
esac
