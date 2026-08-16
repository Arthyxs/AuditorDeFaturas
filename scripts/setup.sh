#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
project_root="$(cd -- "$script_dir/.." && pwd -P)"
template_path="$project_root/.env.example"
environment_file="$project_root/.env"
non_interactive=false
skip_docker=false

while (($#)); do
    case "$1" in
        --env-file)
            environment_file="$2"
            shift 2
            ;;
        --non-interactive)
            non_interactive=true
            shift
            ;;
        --skip-docker)
            skip_docker=true
            shift
            ;;
        *)
            printf 'Unknown argument: %s\n' "$1" >&2
            exit 2
            ;;
    esac
done

get_env_value() {
    local name="$1"
    local line
    while IFS= read -r line || [[ -n "$line" ]]; do
        if [[ "$line" == "$name="* ]]; then
            printf '%s' "${line#*=}"
            return 0
        fi
    done <"$environment_file"
}

set_env_value() {
    local name="$1"
    local value="$2"
    local temporary_file="${environment_file}.tmp.$$"
    local line
    local found=false

    if [[ "$value" == *$'\n'* || "$value" == *$'\r'* ]]; then
        printf 'Environment values cannot contain newlines.\n' >&2
        exit 1
    fi

    : >"$temporary_file"
    while IFS= read -r line || [[ -n "$line" ]]; do
        if [[ "$line" == "$name="* ]]; then
            printf '%s=%s\n' "$name" "$value" >>"$temporary_file"
            found=true
        else
            printf '%s\n' "$line" >>"$temporary_file"
        fi
    done <"$environment_file"
    if [[ "$found" == false ]]; then
        printf '%s=%s\n' "$name" "$value" >>"$temporary_file"
    fi
    mv -- "$temporary_file" "$environment_file"
}

env_literal() {
    local value="$1"
    value="${value//\\/\\\\}"
    value="${value//\"/\\\"}"
    value="${value//\$/\$\$}"
    printf '"%s"' "$value"
}

new_internal_secret() {
    od -An -N48 -tx1 /dev/urandom | tr -d ' \n'
}

mkdir -p -- "$(dirname -- "$environment_file")"
if [[ ! -f "$environment_file" ]]; then
    cp -- "$template_path" "$environment_file"
fi

app_secret="$(get_env_value APP_SECRET_KEY)"
if [[ -z "$app_secret" || "$app_secret" == CHANGE_ME ]]; then
    set_env_value APP_SECRET_KEY "$(new_internal_secret)"
fi

postgres_password="$(get_env_value POSTGRES_PASSWORD)"
if [[ -z "$postgres_password" || "$postgres_password" == CHANGE_ME ]]; then
    postgres_password="$(new_internal_secret)"
    set_env_value POSTGRES_PASSWORD "$postgres_password"
fi

database_url="$(get_env_value DATABASE_URL)"
if [[ -z "$database_url" || "$database_url" == *CHANGE_ME* ]]; then
    set_env_value DATABASE_URL "postgresql+psycopg://invoice_auditor:${postgres_password}@postgres:5432/invoice_auditor"
fi

imap_host="${INVOICE_AUDITOR_SETUP_IMAP_HOST:-}"
imap_user="${INVOICE_AUDITOR_SETUP_IMAP_USER:-}"
imap_password="${INVOICE_AUDITOR_SETUP_IMAP_PASSWORD:-}"
openai_api_key="${INVOICE_AUDITOR_SETUP_OPENAI_API_KEY:-}"

if [[ "$non_interactive" == false ]]; then
    if [[ -z "$imap_host" ]]; then
        read -r -p 'IMAP host (leave blank to configure later): ' imap_host
    fi
    if [[ -z "$imap_user" ]]; then
        read -r -p 'IMAP user/e-mail (leave blank to configure later): ' imap_user
    fi
    if [[ -z "$imap_password" ]]; then
        read -r -s -p 'IMAP password (leave blank to configure later): ' imap_password
        printf '\n'
    fi
    if [[ -z "$openai_api_key" ]]; then
        read -r -s -p 'OpenAI API key (leave blank to configure later): ' openai_api_key
        printf '\n'
    fi
fi

[[ -z "$imap_host" ]] || set_env_value IMAP_HOST "$(env_literal "$imap_host")"
[[ -z "$imap_user" ]] || set_env_value IMAP_USER "$(env_literal "$imap_user")"
[[ -z "$imap_password" ]] || set_env_value IMAP_PASSWORD "$(env_literal "$imap_password")"
[[ -z "$openai_api_key" ]] || set_env_value OPENAI_API_KEY "$(env_literal "$openai_api_key")"

mkdir -p -- \
    "$project_root/data/tariffs" \
    "$project_root/data/invoices" \
    "$project_root/data/reports" \
    "$project_root/data/temp" \
    "$project_root/data/backups"

printf 'Configuration is ready at %s. Internal secrets were generated or preserved.\n' "$environment_file"

if [[ "$skip_docker" == false ]]; then
    docker version --format '{{.Server.Version}}' >/dev/null
    docker compose version >/dev/null
    (
        cd -- "$project_root"
        docker compose up -d --build --wait --wait-timeout 120
        docker compose exec -T app alembic upgrade head
    )
    printf 'InvoiceAuditor services are running and database migrations are current.\n'
fi
