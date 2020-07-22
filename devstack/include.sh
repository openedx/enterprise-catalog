#!/usr/bin/env bash
# Utilities to be included into provisioning scripts.

set -e
set -o pipefail
set -u
set -x

# Colored text.
BOLD_GREEN='\033[1;32m'
GREEN='\033[0;32m'
BOLD_YELLOW='\033[1;33m'
BOLD_RED='\033[1;31m'
NC='\033[0m' # No Color

log_major(){
	echo -e "${BOLD_GREEN}<<<$(date +%T)>>> $*${NC}"
}

log(){
	echo -e "${GREEN}<<<$(date +%T)>>> $*${NC}"
}

log_warning(){
	echo -e "${BOLD_YELLOW}<<<$(date +%T)>>> $*${NC}"
}

log_error(){
	echo -e "${BOLD_RED}<<<$(date +%T)>>> $*${NC}"
}

# Execute a shell command in a service's container.
# Usage:
#   service_exec SERVICE COMMAND [ARGS...]
# Examples:
#   service_exec discovery make migrate
service_exec(){ 
	service="$1"
	shift
	command_and_args="$*"
	# TODO: Remove conditional when we have slim LMS image.
	if [[ "$service" == lms ]]; then
		docker-compose exec -T lms bash -c "source /edx/app/edxapp/edxapp_env && cd /edx/app/edxapp/edx-platform && $command_and_args"
	else
		docker-compose exec -T "$service" bash -c "$command_and_args"
	fi
}

# Execute a Django management command in a service's container.
# Usage:
#   service_exec_management SERVICE MANAGEMENT_COMMAND [ARGS..]
# Examples:
#   service_exec_management discovery createsuperuser
service_exec_management(){
	service="$1"
	management_command_and_args="$2"
	# If LMS/Studio, handle weird manage.py that expects lms/cms argument.
	if [[ "$service" == lms ]]; then
		edxapp_service_variant=lms
	elif [[ "$service" == studio ]]; then
		edxapp_service_variant=cms
	else
		edxapp_service_variant=""
	fi
	service_exec "$service" "python ./manage.py ${edxapp_service_variant} ${management_command_and_args}"
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
	if [[ "$service" == lms ]]; then
		edxapp_service_variant=lms
	elif [[ "$service" == studio ]]; then
		edxapp_service_variant=cms
	else
		edxapp_service_variant=""
	fi
	service_exec "$service" "echo '${python_code}' | python ./manage.py ${edxapp_service_variant} shell"
}