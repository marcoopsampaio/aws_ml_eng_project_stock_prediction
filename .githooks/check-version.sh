#!/usr/bin/env bash

# Fetch the tags and branches from the remote repository
git fetch --tags -q
git fetch origin main -q

MAIN_PACKAGE_VERSION=$(git ls-remote --tags origin | \
                      awk '{print $2}' | \
                      grep 'refs/tags' | \
                      sed 's/refs\/tags\/v//' | \
                      grep -v '{}' | \
                      sort -V | \
                      tail -n 1)

CURRENT_PACKAGE_VERSION=$(poetry version | awk '{print $2}')

if [[ "$CURRENT_PACKAGE_VERSION" > "$MAIN_PACKAGE_VERSION" ]]
then
  echo "Version good to go"
  exit 0
else
  echo "Please bump version prior to commit"
  exit 1
fi
