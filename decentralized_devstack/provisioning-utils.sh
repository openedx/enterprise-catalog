#!/usr/bin/env bash
# Utilities to be included into provisioning scripts.

# Echo all commands being run back to console.
set -x

# Strictness: fail on errors and undefined variables.
set -eu -o pipefail

# Colored text.
BOLD_GREEN='\033[1;32m'
BOLD_YELLOW='\033[1;33m'
BOLD_RED='\033[1;31m'
NC='\033[0m' # No Color

LAST_MAJOR_LOG_SECONDS="${LAST_MAJOR_LOG_SECONDS:-}"

# TODO document
log_step(){
	if [[ -n "$LAST_MAJOR_LOG_SECONDS" ]]; then
		elapsed=$((SECONDS - LAST_MAJOR_LOG_SECONDS))
	else
		elapsed=0
	fi
	LAST_MAJOR_LOG_SECONDS="$SECONDS"
	total="total=$(printf "%03d" "$SECONDS")s"
	prevstep="prevstep=$(printf "%03d" "$elapsed")s"
	echo -e "${BOLD_GREEN}[$(date +%T)][${prevstep}][${total}] $*${NC}"
}

# TODO document
log_message(){
	echo -e "${BOLD_GREEN}[$(date +%T)] $*${NC}"
}

# TODO document
log_warning(){
	echo -e "${BOLD_YELLOW}[$(date +%T)] $*${NC}"
}

# TODO document
log_error(){
	echo -e "${BOLD_RED}[$(date +%T)] $*${NC}"
}

# Execute a shell command in a service's container.
# Usage:
#   service_exec SERVICE COMMAND [ARGS...]
# Examples:
#   service_exec discovery make migrate
service_exec(){
	service="$1"
	shift
	docker-compose exec -T "$service" "$@"
}

# Execute a Django management command in a service's container.
# Usage:
#   service_exec_management SERVICE MANAGEMENT_COMMAND [ARGS..]
# Examples:
#   service_exec_management discovery createsuperuser
service_exec_management(){
	service="$1"
	shift
	# If LMS/Studio, handle weird manage.py that expects lms/cms argument.
        declare -a edxapp_service_args
	if [[ "$service" == lms ]]; then
		edxapp_service_args=(lms)
	elif [[ "$service" == studio ]]; then
		edxapp_service_args=(cms)
	fi
	service_exec "$service" python ./manage.py "${edxapp_service_args[@]}" "$@"
}

# Execute Python code through the Django shell of a service's container.
# Usage:
#   service_exec_python SERVICE PYTHON_CODE
# Examples:
#   service_exec_python discovery "from django.conf import settings; print(settings.API_ROOT)"
service_exec_python(){
	service="$1"
	python_code="$2"
	# If LMS/Studio, handle weird manage.py that expects lms/cms argument.
        declare -a edxapp_service_args
	if [[ "$service" == lms ]]; then
		edxapp_service_args=(lms)
	elif [[ "$service" == studio ]]; then
		edxapp_service_args=(cms)
	fi
	echo "${python_code}" | service_exec "$service" python ./manage.py "${edxapp_service_args[@]}" shell
}

# TODO document
service_create_edx_user(){
	service="$1"
	service_exec_python "$service" "\
from django.contrib.auth import get_user_model; \
User = get_user_model(); \
User.objects.create_superuser(\"edx\", \"edx@example.com\", \"edx\") if not User.objects.filter(username=\"edx\").exists() else None \
"
}

# TODO document
create_lms_integration_for_service(){
	service_name="$1"
	service_port="$2"
	service_exec_management lms manage_user \
		"$service_name"_worker "$service_name"_worker@example.com \
		--staff --superuser
	service_exec_management lms create_dot_application \
		--grant-type authorization-code \
		--skip-authorization \
		--redirect-uris "http://localhost:${service_port}/complete/edx-oauth2/" \
		--client-id  "$service_name"-sso-key \
		--client-secret  "$service_name"-sso-secret \
		--scopes 'user_id' "$service_name"-sso "$service_name"_worker
	service_exec_management lms create_dot_application \
		--grant-type client-credentials  \
		--client-id "$service_name"-backend-service-key  \
		--client-secret "$service_name"-backend-service-secret \
		"$service_name"-backend-service "$service_name"_worker
}
