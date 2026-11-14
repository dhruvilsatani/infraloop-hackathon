#!/bin/bash
# Double-click this file in Finder. It runs the scanner + YOUR model on the repos in repos_to_test.txt.
cd "$(dirname "$0")"
bash ./run_my_model.sh repos_to_test.txt
echo; echo "Finished. You can close this window."; read -n 1 -s -r -p "Press any key..."
