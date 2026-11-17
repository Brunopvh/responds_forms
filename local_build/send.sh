#!/bin/bash

THIS_FILE=$(readlink -f "$0")
THIS_DIR=$(dirname "$THIS_FILE")
DIR_ROOT=$(cd "$THIS_DIR"; cd ..; pwd) # Raiz do projeto
LOCAL_DIR_VENV="${DIR_ROOT}/.venv"
VENV_ACTIVATE="${LOCAL_DIR_VENV}/bin/activate"
source "${VENV_ACTIVATE}" || exit 1

function main(){
    # pip3 install twine
    # uv add twine build
    echo -e "Enviando ao PyPI"
    python3 -m twine upload dist/* #
}

main "$@"
