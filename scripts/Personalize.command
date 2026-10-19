#!/bin/zsh
# Resolve beside this launcher, independently of Terminal's current directory.
launcher_directory="${0:A:h}"
"$launcher_directory/pdf-watermark" --interactive "$@"
result_code=$?
printf '\nPress Return to close. '
IFS= read -r reply
exit "$result_code"
