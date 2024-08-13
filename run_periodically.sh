#!/bin/bash

# Check if the interval parameter is provided
if [ -z "$1" ]; then
    echo "Usage: $0 <interval_in_seconds>"
    exit 1
fi

INTERVAL=$1

while true; do
    python -m src.auto_archiver --config secrets/config.yaml
    
    # Sleep for the specified interval
    sleep $INTERVAL
done

# gcloud compute ssh --zone "us-central1-c" "vi-workflow-vm" --project "nytint-stg"
# gcloud compute scp --zone "us-central1-c" --recurse auto-archiver/ vi-workflow-vm:~/
