#!/usr/bin/env bash

# Fetch the tags and branches from the remote repository
git fetch --tags -q
git fetch origin main -q

CURRENT_PACKAGE_VERSION=$(poetry version | awk '{print $2}')

if git tag -l | grep -q "v$CURRENT_PACKAGE_VERSION"
then
  echo "Please bump version prior to commit"
  exit 1
else
  echo "Version good to go"
  exit 0
fi
