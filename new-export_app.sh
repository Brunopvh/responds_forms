#!/bin/bash

THIS=$0
DIR_ROOT_PROJ=$(dirname $(readlink -f "$THIS"))
APPNAME='responds-forms'
PREFIX_OUTDIR="Documentos/PROMPTS/${APPNAME}"

OUTPUT_DIR="${HOME}/${PREFIX_OUTDIR}"
DIR_APP="${DIR_ROOT_PROJ}/responds"

DIR_HOME_PAGE="${DIR_APP}/home_page"
DIR_PAGE_FORMS="${DIR_APP}/page_forms"
DIR_PAGE_WHATSAPP="${DIR_APP}/page_whatsapp"


# 1. Declaração do Mapa: [Diretório de Origem]="Arquivo de Saída"
declare -A MODULOS=(
    ["${DIR_ROOT_PROJ}/pyflutter_ui"]="${OUTPUT_DIR}/pyflutter_ui.py"
    ["${DIR_HOME_PAGE}"]="${OUTPUT_DIR}/home_page.py"
    ["${DIR_PAGE_FORMS}"]="${OUTPUT_DIR}/page_forms.py"
    ["${DIR_PAGE_WHATSAPP}"]="${OUTPUT_DIR}/page_whatsapp.py"
    ["${DIR_ROOT_PROJ}/whatsapp_files"]="${OUTPUT_DIR}/whatsapp_files.py"
    ["${DIR_ROOT_PROJ}/cartas"]="${OUTPUT_DIR}/cartas.py"
)

function start(){
    mkdir -p "$OUTPUT_DIR"
    
    # Limpa/cria todos os arquivos de saída mapeados antes do processamento
    for output_file in "${MODULOS[@]}"; do
        > "$output_file"
    done
}

function save_dir(){
    local CURRENT_DIR=$1
    local EXPORT_DIR=$2

    [[ -z "$CURRENT_DIR" ]] && { echo "* save_dir: diretório nulo"; return 1; }
    [[ -z "$EXPORT_DIR" ]]  && { echo "* save_dir: arquivo nulo"; return 1; }

    [[ ! -d "$CURRENT_DIR" ]] && { echo "* save_dir: diretório inexistente ... $CURRENT_DIR"; return 1; }
    [[ ! -f "$EXPORT_DIR" ]]  && { echo "* save_dir: arquivo inexistente ... $EXPORT_DIR"; return 1; }

    echo -e "[*] Iniciando cópia dos arquivos *.py ... $CURRENT_DIR"
    
    # Encontra todos os .py e concatena
    find "$CURRENT_DIR" -type f -name "*.py" | sort | while read -r file; do
        echo -e "#===[ $(date) FILE: $file ===]\n" >> "$EXPORT_DIR"
        cat "$file" >> "$EXPORT_DIR"
        echo -e "\n\n" >> "$EXPORT_DIR"
    done
    
    echo -e "[OK] arquivo gerado: $EXPORT_DIR"
}

function main(){
    start

    # 2. Percorre as chaves (diretórios) e acessa os valores (arquivos de saída)
    for dir in "${!MODULOS[@]}"; do
        save_dir "$dir" "${MODULOS[$dir]}"
    done
}

main "$@"
