#!/bin/zsh
preview_directory="${0:A:h}"
python3 "$preview_directory/serve.py"
result_code=$?
if (( result_code != 0 )); then
  printf '\nPress Return to close. '
  IFS= read -r reply
fi
exit "$result_code"
