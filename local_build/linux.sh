#!/bin/bash
#
# Script para compilar o projeto localmente e preparar para enviar ao PyPI.
#
THIS_FILE=$(readlink -f "$0")
THIS_DIR=$(dirname "$THIS_FILE")
DIR_ROOT=$(cd "$THIS_DIR"; cd ..; pwd) # Raiz do projeto
LOCAL_DIR_VENV="${DIR_ROOT}/.venv"
VENV_ACTIVATE="${LOCAL_DIR_VENV}/bin/activate"
source "${VENV_ACTIVATE}" || exit 1

function main(){
    uv sync || exit 1
    # Executa o build usando o ambiente gerenciado pelo uv
    uv run python -m build || exit 1
    # pip3 install build
    #python3 -m build

    echo -e "\nPara enviar ao PyPI use ->> python3 -m twine upload dist/*"
}

main "$@"
